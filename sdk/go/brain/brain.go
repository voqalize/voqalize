// Package brain is the ergonomic, capability-free agent surface over the cortex
// wire — the Go analogue of voqalcloud.sdk.Brain (Python), with NO pipecat
// dependency. You implement a Brain (your object holds only your state); SDK
// capability arrives as the *Session / *Interaction / *Inference passed into
// your callbacks.
//
//	type Greeter struct{}
//
//	func (Greeter) OnSessionStart(ctx context.Context, s *brain.Session, _ brain.SessionStart) error {
//	    return s.Inference(ctx, func(inf *brain.Inference) error { return inf.Speak("Hi!") })
//	}
//	func (Greeter) OnInteraction(ctx context.Context, in *brain.Interaction) error {
//	    // in.Conversation() is the faithful (heard) transcript, already incl. this
//	    // user turn — build your LLM prompt from it; the SDK commits heard for you.
//	    return in.Inference(ctx, func(inf *brain.Inference) error {
//	        return inf.Speak("You said: " + in.Transcript)
//	    })
//	}
//
// Only OnInteraction is required. The rest are optional interfaces, checked at
// runtime (SessionStarter, SessionEnder, InferenceFinalizer, AppEventHandler,
// ErrorHandler).
package brain

import (
	"context"
	"errors"
	"sync"

	"github.com/voqalize/voqalize/sdk/go/wire"
)

// greetingInteractionID is the "no user stimulus" sentinel for agent-initiated
// speech (the opening greeting). Voice mints user interaction ids from 1.
const greetingInteractionID = 0

// Brain is the required contract.
type Brain interface {
	// OnInteraction is the core callback: input is complete; respond via
	// in.Inference(...). Returning ends the interaction.
	OnInteraction(ctx context.Context, in *Interaction) error
}

// Optional capabilities — implement any subset.
type (
	// SessionStarter runs setup; may open agent-initiated speech via s.Inference.
	SessionStarter interface {
		OnSessionStart(ctx context.Context, s *Session, start SessionStart) error
	}
	// SessionEnder runs teardown.
	SessionEnder interface {
		OnSessionEnd(ctx context.Context, s *Session)
	}
	// InferenceFinalizer is a per-inference side-effect hook (logging, durable
	// store). The faithful record is already committed to s.Conversation.
	InferenceFinalizer interface {
		OnInferenceFinalized(ctx context.Context, inf *Inference)
	}
	// AppEventHandler receives out-of-interaction UI→Brain feedback (e.g. state_sync).
	AppEventHandler interface {
		OnAppEvent(ctx context.Context, s *Session, ev AppEvent)
	}
	// ErrorHandler receives non-fatal congestion ErrorFrames (drop-newest).
	ErrorHandler interface {
		OnError(ctx context.Context, s *Session, direction, message string)
	}
)

// SessionStart is delivered to OnSessionStart.
type SessionStart struct{ Init map[string]any }

// AppEvent is a browser→Brain message: Name is its type, Data its payload.
type AppEvent struct {
	Name string
	Data map[string]any
}

// Outcome is the async result of an Action (the action.outcome event). Correlated
// by ActionID at session scope, so a late outcome in a later interaction still
// fires the original callback.
type Outcome struct {
	ActionID      uint64
	InteractionID uint64
	Status        string
	Result        any
}

// Message is one committed conversation turn (the faithful record). For an
// "assistant" message Content is the text the user actually HEARD.
type Message struct {
	Role    string // "user" | "assistant"
	Content string
}

// Conversation is the session's faithful, heard-truth transcript —
// framework-maintained. The SDK records the user utterance at interaction start
// and one assistant message per inference from its HEARD text at finalize, so
// the generated-but-never-spoken tail of a barged-in reply never lands here.
// Read Messages() to build your LLM prompt and to persist; you never commit.
type Conversation struct {
	mu   sync.Mutex
	msgs []Message
}

// Messages returns a copy of the committed transcript so far.
func (c *Conversation) Messages() []Message {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]Message, len(c.msgs))
	copy(out, c.msgs)
	return out
}

func (c *Conversation) recordUser(text string) {
	c.mu.Lock()
	c.msgs = append(c.msgs, Message{Role: "user", Content: text})
	c.mu.Unlock()
}

func (c *Conversation) recordAssistantHeard(text string) {
	if text == "" {
		return
	}
	c.mu.Lock()
	c.msgs = append(c.msgs, Message{Role: "assistant", Content: text})
	c.mu.Unlock()
}

// emitter is the wire-facing sink (implemented by the runtime via cortex.Emitter).
type emitter interface{ Send(f wire.Frame) }

// Session is the session-level handle (reachable as in.Session).
type Session struct {
	ID           string
	Init         map[string]any
	Conversation *Conversation

	emit    emitter
	greetMu sync.Mutex
	greetN  uint64

	// Brain-minted action ids + pending outcome callbacks, at SESSION scope so a
	// late action.outcome (even in a later interaction) still fires.
	actionMu  sync.Mutex
	actionSeq uint64
	actionCbs map[uint64]func(Outcome)
}

func (s *Session) registerAction(cb func(Outcome)) uint64 {
	s.actionMu.Lock()
	defer s.actionMu.Unlock()
	s.actionSeq++
	if cb != nil {
		if s.actionCbs == nil {
			s.actionCbs = map[uint64]func(Outcome){}
		}
		s.actionCbs[s.actionSeq] = cb
	}
	return s.actionSeq
}

func (s *Session) popActionCallback(id uint64) func(Outcome) {
	s.actionMu.Lock()
	defer s.actionMu.Unlock()
	cb := s.actionCbs[id]
	delete(s.actionCbs, id)
	return cb
}

// ConfigureTTS changes TTS voice/language/model for the **next** inference
// (mid-call). Fire-and-forget, like Action. Not instantaneous: vql-speech
// locks voice/model/language per Cartesia context, and pygato pins one
// context per inference, so a change here only takes effect once the current
// inference (if any) finishes — never mid-utterance. Zero-value fields are
// omitted, leaving that setting unchanged.
//
// This is the TTS half of the voice-protocol session.configure() DTO
// (docs/voice-protocol.md) — see ConfigureSTT for the STT-VAD half; mid-call
// locale reconfigure is not yet exposed here.
func (s *Session) ConfigureTTS(voice, language, model string) {
	settings := map[string]any{}
	if voice != "" {
		settings["voice"] = voice
	}
	if language != "" {
		settings["language"] = language
	}
	if model != "" {
		settings["model"] = model
	}
	if len(settings) == 0 {
		return
	}
	s.emit.Send(wire.TTSUpdateSettings{Settings: settings})
}

// STTConfig is the set of STT VAD/turn-detection knobs ConfigureSTT can
// change. Nil pointers leave that setting unchanged (pointers, not
// zero-value sentinels, since 0 is a valid VAD value). Field names match
// vql-speech's Flux Configure thresholds verbatim. Named fields (rather than
// positional args) so callers can't silently transpose two same-typed knobs
// — set only the ones you mean to change:
//
//	s.ConfigureSTT(brain.STTConfig{VadBargeInMs: brain.IntPtr(300)})
type STTConfig struct {
	VadConfidence *float64
	VadMinVolume  *float64

	VadStartFrames               *int
	VadStopFramesToTriggerUpdate *int
	VadEagerFrames               *int
	VadBargeInMs                 *int
	ResumeFrames                 *int
	MinSegmentSpeechFrames       *int
	ConfidenceTailMs             *int
}

// Float64Ptr and IntPtr are convenience constructors for STTConfig's pointer
// fields (Go has no address-of-literal syntax).
func Float64Ptr(v float64) *float64 { return &v }
func IntPtr(v int) *int             { return &v }

// ConfigureSTT changes STT VAD/turn-detection knobs mid-call. Fire-and-forget,
// like Action. Unlike ConfigureTTS, these apply live with no queuing —
// vql-speech treats them as comparison bounds against self-resetting
// counters, safe to change mid-utterance.
//
// This is the STT-VAD half of the voice-protocol session.configure() DTO
// (docs/voice-protocol.md) — mid-call locale reconfigure is not yet exposed
// here.
func (s *Session) ConfigureSTT(cfg STTConfig) {
	settings := map[string]any{}
	if cfg.VadConfidence != nil {
		settings["vad_confidence"] = *cfg.VadConfidence
	}
	if cfg.VadMinVolume != nil {
		settings["vad_min_volume"] = *cfg.VadMinVolume
	}
	if cfg.VadStartFrames != nil {
		settings["vad_start_frames"] = *cfg.VadStartFrames
	}
	if cfg.VadStopFramesToTriggerUpdate != nil {
		settings["vad_stop_frames_to_trigger_update"] = *cfg.VadStopFramesToTriggerUpdate
	}
	if cfg.VadEagerFrames != nil {
		settings["vad_eager_frames"] = *cfg.VadEagerFrames
	}
	if cfg.VadBargeInMs != nil {
		settings["vad_barge_in_ms"] = *cfg.VadBargeInMs
	}
	if cfg.ResumeFrames != nil {
		settings["resume_frames"] = *cfg.ResumeFrames
	}
	if cfg.MinSegmentSpeechFrames != nil {
		settings["min_segment_speech_frames"] = *cfg.MinSegmentSpeechFrames
	}
	if cfg.ConfidenceTailMs != nil {
		settings["confidence_tail_ms"] = *cfg.ConfidenceTailMs
	}
	if len(settings) == 0 {
		return
	}
	s.emit.Send(wire.STTUpdateSettings{Settings: settings})
}

// Inference opens an agent-initiated inference (e.g. the opening greeting),
// scoped to the interaction_id = 0 sentinel.
func (s *Session) Inference(ctx context.Context, fn func(inf *Inference) error) error {
	s.greetMu.Lock()
	s.greetN++
	id := s.greetN
	s.greetMu.Unlock()
	return runInference(s.emit, greetingInteractionID, id, fn)
}

// Interaction is one committed user stimulus + the handle you respond through.
type Interaction struct {
	ID         uint64
	Transcript string
	Session    *Session

	emit emitter
	n    uint64
}

// Conversation is the session's faithful transcript (already incl. this turn's
// user utterance).
func (in *Interaction) Conversation() *Conversation { return in.Session.Conversation }

// Inference opens one inference bracket — 1:1 with an LLM call. Never wrap a
// whole multi-inference run in a single bracket.
func (in *Interaction) Inference(ctx context.Context, fn func(inf *Inference) error) error {
	in.n++
	return runInference(in.emit, in.ID, in.n, fn)
}

// Action fires a UI command to the browser and returns its action_id.
// Fire-and-return — never blocks. Emits the RTVI ui_command envelope pygato
// relays: {"type":"ui_command","action":name,"action_id":id, ...args}.
func (in *Interaction) Action(name string, args map[string]any) uint64 {
	return in.action(name, args, nil)
}

// ActionWithResult is Action plus an out-of-band callback fired when the
// browser's action.outcome arrives (matched by action_id at session scope, so a
// late outcome in a later interaction still fires).
func (in *Interaction) ActionWithResult(name string, args map[string]any, cb func(Outcome)) uint64 {
	return in.action(name, args, cb)
}

func (in *Interaction) action(name string, args map[string]any, cb func(Outcome)) uint64 {
	actionID := in.Session.registerAction(cb)
	data := map[string]any{"type": "ui_command", "action": name, "action_id": actionID}
	for k, v := range args {
		data[k] = v
	}
	in.emit.Send(wire.RTVIServerMessage{Data: data})
	return actionID
}

// Inference is one LLM call. Inside a bracket, Speak streams bot output. In
// OnInferenceFinalized, Heard/Interrupted carry the post-playout truth.
type Inference struct {
	InteractionID uint64
	ID            uint64
	Heard         string
	Interrupted   bool

	emit emitter
}

// Speak emits a chunk of bot speech (one inference.output chunk). May be called
// many times within one bracket.
func (inf *Inference) Speak(text string) error {
	if inf.emit == nil {
		return errors.New("brain: Speak called outside an inference bracket")
	}
	if text == "" {
		return nil
	}
	inf.emit.Send(wire.VqlLLMText{InteractionID: inf.InteractionID, InferenceID: inf.ID, Text: text})
	return nil
}

// runInference brackets fn with VqlLLMStart/End (End emitted even on error/cancel).
func runInference(emit emitter, interactionID, inferenceID uint64, fn func(*Inference) error) error {
	emit.Send(wire.VqlLLMStart{InteractionID: interactionID, InferenceID: inferenceID})
	defer emit.Send(wire.VqlLLMEnd{InteractionID: interactionID, InferenceID: inferenceID})
	return fn(&Inference{InteractionID: interactionID, ID: inferenceID, emit: emit})
}
