// Package cortex is the native (no-pipecat) agent runtime: one outbound
// multiplexed WebSocket to cortex's /agent endpoint, many sessions demuxed by a
// 16-byte prefix, each wrapped in its own two-lane buffered runner with
// ack-gated ordering, drop-newest backpressure, and reconnect.
package cortex

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync"

	"github.com/coder/websocket"

	"github.com/voqalize/voqalize/sdk/go/wire"
)

// Options configures a CortexAgent. Provide exactly one auth source: APIKey (a
// static ak_… customer key) or AuthorizationProvider (mints a fresh
// "Bearer <jwt>" per connect, for platform agents).
type Options struct {
	Version               string
	CortexURL             string
	APIKey                string
	AuthorizationProvider func() string
	NormalMax             int // per-session normal-lane bound (default 256)
	Logger                wire.Logger
}

// Agent connects to cortex and dispatches per-session frames into Session
// consumers built by a SessionFactory.
type Agent struct {
	opts      Options
	factory   SessionFactory
	log       wire.Logger
	normalMax int

	wire *wire.MultiplexedWire

	mu       sync.Mutex
	sessions map[wire.SessionID]*sessionRunner

	ready *readyQueue
	stop  chan struct{}
}

// New builds an agent. The factory is invoked once per session.
func New(opts Options, factory SessionFactory) (*Agent, error) {
	if (opts.APIKey == "") == (opts.AuthorizationProvider == nil) {
		return nil, errors.New("cortex: pass exactly one of APIKey or AuthorizationProvider")
	}
	if opts.Logger == nil {
		opts.Logger = noopLogger{}
	}
	nm := opts.NormalMax
	if nm <= 0 {
		nm = defaultNormalMax
	}
	return &Agent{
		opts:      opts,
		factory:   factory,
		log:       opts.Logger,
		normalMax: nm,
		sessions:  map[wire.SessionID]*sessionRunner{},
		ready:     newReadyQueue(),
		stop:      make(chan struct{}),
	}, nil
}

// Run connects and dispatches until the wire closes permanently or ctx is done.
func (a *Agent) Run(ctx context.Context) error {
	static := http.Header{"X-Agent-Version": {a.opts.Version}}
	var provider func() http.Header
	if a.opts.APIKey != "" {
		static.Set("Authorization", "Bearer "+a.opts.APIKey)
	} else {
		p := a.opts.AuthorizationProvider
		provider = func() http.Header { return http.Header{"Authorization": {p()}} }
	}

	a.wire = wire.NewMultiplexedWire(wire.Config{
		URL:            a.opts.CortexURL,
		Header:         static,
		HeaderProvider: provider,
	}, a.onReconnect, a.log)

	if err := a.wire.Start(ctx); err != nil {
		return fmt.Errorf("cortex: initial connect: %w", err)
	}

	writerDone := make(chan struct{})
	go func() { defer close(writerDone); a.writer(ctx) }()

	err := a.reader(ctx)

	a.wire.Close(websocket.StatusNormalClosure, "agent stopping")
	close(a.stop)
	a.ready.wake()
	<-writerDone
	<-a.wire.Done() // wait for the reconnect manager to exit (no goroutine leak)
	a.teardownAll()
	return err
}

// ─── reader: wire → per-session lanes ─────────────────────────────────────────

func (a *Agent) reader(ctx context.Context) error {
	for {
		sid, _, payload, err := a.wire.Recv(ctx)
		if err != nil {
			if errors.Is(err, wire.ErrPermanent) || errors.Is(err, wire.ErrClosed) {
				return err
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			a.log.Warnf("cortex: recv error: %v", err)
			return err
		}
		dec, err := wire.Decode(payload)
		if err != nil {
			a.log.Warnf("cortex: decode failed for session %s: %v", sid, err)
			continue
		}
		if dec.IsAck {
			// The agent sends acks; receiving one is unexpected. Ignore.
			a.log.Warnf("cortex: ignoring unexpected ack %d for session %s", dec.AckID, sid)
			continue
		}
		r := a.routeSession(ctx, sid, dec.Frame)
		if r == nil {
			continue
		}
		r.enqueueInbound(inboundItem{frame: dec.Frame, requestID: dec.RequestID})
	}
}

// routeSession returns the runner for sid, creating one on a VqlStart.
func (a *Agent) routeSession(ctx context.Context, sid wire.SessionID, f wire.Frame) *sessionRunner {
	a.mu.Lock()
	r, ok := a.sessions[sid]
	if ok {
		a.mu.Unlock()
		return r
	}
	if _, isStart := f.(wire.VqlStart); !isStart {
		a.mu.Unlock()
		a.log.Warnf("cortex: dropping %T for unknown session %s", f, sid)
		return nil
	}
	r = newSessionRunner(ctx, sid, a)
	a.sessions[sid] = r
	a.mu.Unlock()
	r.start()
	a.log.Infof("cortex: opened session %s", sid)
	return r
}

func (a *Agent) closeSession(sid wire.SessionID) {
	a.mu.Lock()
	r, ok := a.sessions[sid]
	if ok {
		delete(a.sessions, sid)
	}
	a.mu.Unlock()
	if ok {
		r.teardown()
		a.log.Infof("cortex: closed session %s", sid)
	}
}

func (a *Agent) teardownAll() {
	a.mu.Lock()
	runners := make([]*sessionRunner, 0, len(a.sessions))
	for _, r := range a.sessions {
		runners = append(runners, r)
	}
	a.sessions = map[wire.SessionID]*sessionRunner{}
	a.mu.Unlock()
	for _, r := range runners {
		r.teardown()
	}
}

// onReconnect drops all sessions; pygato re-sends VqlStart for live ones.
func (a *Agent) onReconnect(ctx context.Context) error {
	a.log.Infof("cortex: reconnected, tearing down sessions")
	a.teardownAll()
	return nil
}

// ─── writer: shared, fair round-robin over outbound lanes ────────────────────

func (a *Agent) writer(ctx context.Context) {
	for {
		sid, ok := a.ready.pop(ctx, a.stop)
		if !ok {
			return
		}
		a.mu.Lock()
		r := a.sessions[sid]
		a.mu.Unlock()
		if r == nil {
			continue
		}
		it, ok := r.out.pop()
		if !ok {
			continue
		}
		var payload []byte
		var err error
		if it.isAck {
			payload, err = wire.EncodeAck(it.ackID)
		} else {
			payload, err = wire.Encode(it.frame)
		}
		if err != nil {
			a.log.Warnf("cortex: encode failed (%T) on session %s: %v", it.frame, sid, err)
			if !r.out.empty() {
				a.signalReady(sid)
			}
			continue
		}
		if err := a.wire.Send(ctx, sid, wire.Downstream, payload); err != nil {
			if errors.Is(err, wire.ErrPermanent) || errors.Is(err, wire.ErrClosed) {
				return
			}
			a.log.Warnf("cortex: send failed on session %s: %v", sid, err)
			continue
		}
		if !r.out.empty() {
			a.signalReady(sid)
		}
	}
}

func (a *Agent) signalReady(sid wire.SessionID) { a.ready.push(sid) }

// ─── runnerHost impl (see session.go) ────────────────────────────────────────

func (a *Agent) sessionFactory() SessionFactory { return a.factory }
func (a *Agent) laneMax() int                   { return a.normalMax }
func (a *Agent) logger() wire.Logger            { return a.log }

// ─── ready queue: dedup'd FIFO of sessions with outbound work ─────────────────

type readyQueue struct {
	mu     sync.Mutex
	set    map[wire.SessionID]bool
	list   []wire.SessionID
	notify chan struct{}
}

func newReadyQueue() *readyQueue {
	return &readyQueue{set: map[wire.SessionID]bool{}, notify: make(chan struct{}, 1)}
}

func (q *readyQueue) push(sid wire.SessionID) {
	q.mu.Lock()
	if !q.set[sid] {
		q.set[sid] = true
		q.list = append(q.list, sid)
	}
	q.mu.Unlock()
	select {
	case q.notify <- struct{}{}:
	default:
	}
}

func (q *readyQueue) pop(ctx context.Context, stop <-chan struct{}) (wire.SessionID, bool) {
	for {
		q.mu.Lock()
		if len(q.list) > 0 {
			sid := q.list[0]
			q.list = q.list[1:]
			delete(q.set, sid)
			q.mu.Unlock()
			return sid, true
		}
		q.mu.Unlock()
		select {
		case <-q.notify:
		case <-ctx.Done():
			return wire.SessionID{}, false
		case <-stop:
			return wire.SessionID{}, false
		}
	}
}

func (q *readyQueue) wake() {
	select {
	case q.notify <- struct{}{}:
	default:
	}
}

type noopLogger struct{}

func (noopLogger) Infof(string, ...any) {}
func (noopLogger) Warnf(string, ...any) {}
