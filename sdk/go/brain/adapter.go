package brain

import (
	"context"
	"sync"

	"github.com/voqalize/voqalize/sdk/go/cortex"
	"github.com/voqalize/voqalize/sdk/go/wire"
)

// actionOutcomeType is the browser→Brain message type carrying an action result.
const actionOutcomeType = "action_outcome"

// Factory adapts a Brain constructor into a cortex.SessionFactory. newBrain is
// called once per session, so state on the returned Brain is session-scoped.
func Factory(newBrain func() Brain, log wire.Logger) cortex.SessionFactory {
	if log == nil {
		log = noopLogger{}
	}
	return func(ctx context.Context, sid wire.SessionID, emit cortex.Emitter) cortex.Session {
		return &adapter{
			ctx:     ctx,
			sid:     sid,
			brain:   newBrain(),
			emit:    emit,
			log:     log,
			pending: map[uint64]context.CancelFunc{},
		}
	}
}

// adapter translates wire frames into Brain callbacks (the Go _BrainProcessor):
// it owns the framework-enforced Conversation and the cancellable goroutines
// that run on_session_start / on_interaction so barge-in can preempt them.
type adapter struct {
	ctx   context.Context
	sid   wire.SessionID
	brain Brain
	emit  cortex.Emitter
	log   wire.Logger

	session *Session

	mu      sync.Mutex
	pending map[uint64]context.CancelFunc // interactionID -> cancel
	wg      sync.WaitGroup
}

// HandleFrame is called sequentially by the session feeder (system lane first).
func (a *adapter) HandleFrame(f wire.Frame) {
	switch v := f.(type) {
	case wire.VqlStart:
		a.session = &Session{
			ID:           v.SessionID,
			Init:         v.Payload,
			Conversation: &Conversation{},
			emit:         emitFunc(a.emit.Send),
		}
		if ss, ok := a.brain.(SessionStarter); ok {
			start := SessionStart{Init: v.Payload}
			a.spawn(greetingInteractionID, func(ctx context.Context) error {
				return ss.OnSessionStart(ctx, a.session, start)
			}, nil)
		}

	case wire.VqlUserText:
		if a.session == nil {
			a.log.Warnf("brain: user text before session start on %s", a.sid)
			return
		}
		// Commit the user utterance at interaction start, before on_interaction.
		a.session.Conversation.recordUser(v.Text)
		in := &Interaction{
			ID:         v.InteractionID,
			Transcript: v.Text,
			Session:    a.session,
			emit:       emitFunc(a.emit.Send),
		}
		a.spawn(v.InteractionID, func(ctx context.Context) error {
			return a.brain.OnInteraction(ctx, in)
		}, func() {
			// Clean return ⇒ done responding to the whole interaction.
			a.emit.Send(wire.InteractionCompleted{InteractionID: v.InteractionID})
		})

	case wire.Interruption:
		// Barge-in: cancel in-flight callback goroutines, then echo the
		// Interruption back (pygato's drain barrier).
		a.cancelAll()
		a.emit.Send(wire.Interruption{})

	case wire.VqlInferenceFinalized:
		if a.session == nil {
			return
		}
		// Framework-enforced heard-text commit, before the side-effect hook.
		a.session.Conversation.recordAssistantHeard(v.HeardText)
		if fin, ok := a.brain.(InferenceFinalizer); ok {
			inf := &Inference{InteractionID: v.InteractionID, ID: v.InferenceID, Heard: v.HeardText, Interrupted: v.Interrupted}
			fin.OnInferenceFinalized(a.ctx, inf)
		}

	case wire.RTVIClientMessage:
		if a.session == nil {
			return
		}
		// action.outcome (App→Brain): correlated by action_id, routed to the
		// pending callback — never surfaced as a generic app event.
		if v.Type == actionOutcomeType {
			a.dispatchActionOutcome(v.Data)
			return
		}
		if h, ok := a.brain.(AppEventHandler); ok {
			h.OnAppEvent(a.ctx, a.session, AppEvent{Name: v.Type, Data: v.Data})
		}

	case wire.Error:
		if h, ok := a.brain.(ErrorHandler); ok && a.session != nil {
			h.OnError(a.ctx, a.session, "downstream", v.Error)
		}

	case wire.End, wire.Cancel:
		// Lifecycle; the runtime drives teardown via Close.
	}
}

// DeliverError surfaces a non-fatal congestion ErrorFrame to the brain.
func (a *adapter) DeliverError(direction wire.Direction, message string) {
	if h, ok := a.brain.(ErrorHandler); ok && a.session != nil {
		dir := "downstream"
		if direction == wire.Upstream {
			dir = "upstream"
		}
		h.OnError(a.ctx, a.session, dir, message)
	} else {
		a.log.Warnf("brain: %s drop on %s: %s", direction, a.sid, message)
	}
}

// Close tears down: cancel in-flight work, run OnSessionEnd.
func (a *adapter) Close() {
	a.cancelAll()
	if se, ok := a.brain.(SessionEnder); ok && a.session != nil {
		se.OnSessionEnd(a.ctx, a.session)
	}
}

// spawn runs a brain callback in a cancellable goroutine tracked by id, so a
// barge-in (cancelAll) can preempt it. onComplete (if non-nil) runs only when fn
// returns cleanly (no error, not cancelled) — e.g. to emit interaction.completed.
func (a *adapter) spawn(id uint64, fn func(context.Context) error, onComplete func()) {
	ctx, cancel := context.WithCancel(a.ctx)
	a.mu.Lock()
	a.pending[id] = cancel
	a.mu.Unlock()
	a.wg.Add(1)
	go func() {
		defer a.wg.Done()
		defer func() {
			a.mu.Lock()
			delete(a.pending, id)
			a.mu.Unlock()
			cancel()
		}()
		err := fn(ctx)
		if ctx.Err() != nil {
			return // barge-in / teardown: skip completion
		}
		if err != nil {
			a.log.Warnf("brain: callback for interaction %d on %s failed: %v", id, a.sid, err)
			return
		}
		if onComplete != nil {
			onComplete()
		}
	}()
}

// dispatchActionOutcome routes an inbound action.outcome to its pending callback.
func (a *adapter) dispatchActionOutcome(data map[string]any) {
	id, ok := toUint64(data["action_id"])
	if !ok {
		return
	}
	cb := a.session.popActionCallback(id)
	if cb == nil {
		return
	}
	iid, _ := toUint64(data["interaction_id"])
	status, _ := data["status"].(string)
	cb(Outcome{ActionID: id, InteractionID: iid, Status: status, Result: data["result"]})
}

func toUint64(v any) (uint64, bool) {
	switch n := v.(type) {
	case float64:
		return uint64(n), true
	case int:
		return uint64(n), true
	case uint64:
		return n, true
	default:
		return 0, false
	}
}

func (a *adapter) cancelAll() {
	a.mu.Lock()
	cancels := make([]context.CancelFunc, 0, len(a.pending))
	for _, c := range a.pending {
		cancels = append(cancels, c)
	}
	a.mu.Unlock()
	for _, c := range cancels {
		c()
	}
}

// emitFunc adapts a Send func to the brain.emitter interface.
type emitFunc func(wire.Frame)

func (e emitFunc) Send(f wire.Frame) { e(f) }

type noopLogger struct{}

func (noopLogger) Infof(string, ...any) {}
func (noopLogger) Warnf(string, ...any) {}
