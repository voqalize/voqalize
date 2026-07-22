// Package tests drives the native Go SDK end to end against a fake cortex over a
// real WebSocket — the analogue of the Python FakeCortex harness. It validates
// the protocol mechanics the travel demo relies on: greeting, per-turn
// inference, ack-gating, the framework-enforced heard-text Conversation,
// barge-in (cancel + Interruption echo), screen-driving (ui_command), and
// browser→brain app events.
package tests

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/voqalize/voqalize/sdk/go/brain"
	"github.com/voqalize/voqalize/sdk/go/cortex"
	"github.com/voqalize/voqalize/sdk/go/wire"
)

var sid = wire.SessionID{0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x01}

// ─── fake cortex ───────────────────────────────────────────────────────────────

// peer wraps the cortex-side connection with a read-pump. coder/websocket closes
// the conn if a Read's context is cancelled, so we never cancel reads — a single
// pump goroutine reads with a background context and fans frames into a channel.
type peer struct {
	conn   *websocket.Conn
	frames chan wire.Decoded
}

type fakeCortex struct {
	srv    *httptest.Server
	connCh chan *websocket.Conn
}

func newFakeCortex(t *testing.T) *fakeCortex {
	t.Helper()
	fc := &fakeCortex{connCh: make(chan *websocket.Conn, 1)}
	fc.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := websocket.Accept(w, r, &websocket.AcceptOptions{InsecureSkipVerify: true})
		if err != nil {
			return
		}
		fc.connCh <- c
		<-r.Context().Done()
	}))
	return fc
}

func (fc *fakeCortex) wsURL() string { return "ws" + strings.TrimPrefix(fc.srv.URL, "http") + "/agent" }
func (fc *fakeCortex) close()        { fc.srv.Close() }

func (fc *fakeCortex) accept(t *testing.T) *peer {
	t.Helper()
	select {
	case c := <-fc.connCh:
		p := &peer{conn: c, frames: make(chan wire.Decoded, 256)}
		go p.pump()
		return p
	case <-time.After(5 * time.Second):
		t.Fatal("fakeCortex: agent never connected")
		return nil
	}
}

func (p *peer) pump() {
	for {
		_, data, err := p.conn.Read(context.Background())
		if err != nil {
			close(p.frames)
			return
		}
		dec, err := wire.Decode(data[wire.SessionIDLen+1:])
		if err != nil {
			continue
		}
		p.frames <- dec
	}
}

func (p *peer) send(t *testing.T, f wire.Frame, reqID uint64) {
	t.Helper()
	payload, err := wire.EncodeWithRequest(f, reqID)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	msg := append(append(append([]byte{}, sid[:]...), byte(wire.Downstream)), payload...)
	if err := p.conn.Write(context.Background(), websocket.MessageBinary, msg); err != nil {
		t.Fatalf("write: %v", err)
	}
}

func (p *peer) recv(d time.Duration) (wire.Decoded, bool) {
	select {
	case dec, ok := <-p.frames:
		return dec, ok
	case <-time.After(d):
		return wire.Decoded{}, false
	}
}

// collect drains frames until a quiet period of d, returning all seen.
func (p *peer) collect(d time.Duration) []wire.Decoded {
	var out []wire.Decoded
	for {
		dec, ok := p.recv(d)
		if !ok {
			return out
		}
		out = append(out, dec)
	}
}

// ─── test brains ───────────────────────────────────────────────────────────────

type greeterBrain struct {
	mu        sync.Mutex
	session   *brain.Session
	appEvents []brain.AppEvent
}

func (g *greeterBrain) OnSessionStart(ctx context.Context, s *brain.Session, _ brain.SessionStart) error {
	g.mu.Lock()
	g.session = s
	g.mu.Unlock()
	return s.Inference(ctx, func(inf *brain.Inference) error { return inf.Speak("hello there friend") })
}

func (g *greeterBrain) OnInteraction(ctx context.Context, in *brain.Interaction) error {
	in.Action("open_dashboard", map[string]any{"tab": "trips"})
	return in.Inference(ctx, func(inf *brain.Inference) error {
		return inf.Speak("you said " + in.Transcript)
	})
}

func (g *greeterBrain) OnAppEvent(ctx context.Context, _ *brain.Session, ev brain.AppEvent) {
	g.mu.Lock()
	g.appEvents = append(g.appEvents, ev)
	g.mu.Unlock()
}

func (g *greeterBrain) convo() []brain.Message {
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.session == nil {
		return nil
	}
	return g.session.Conversation.Messages()
}

// talkerBrain speaks many chunks in one inference, checking ctx so a barge-in
// stops it.
type talkerBrain struct {
	mu      sync.Mutex
	spoken  int
	session *brain.Session
}

func (b *talkerBrain) OnSessionStart(ctx context.Context, s *brain.Session, _ brain.SessionStart) error {
	b.mu.Lock()
	b.session = s
	b.mu.Unlock()
	return nil
}

func (b *talkerBrain) OnInteraction(ctx context.Context, in *brain.Interaction) error {
	words := []string{"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}
	return in.Inference(ctx, func(inf *brain.Inference) error {
		for _, w := range words {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			_ = inf.Speak(w)
			b.mu.Lock()
			b.spoken++
			b.mu.Unlock()
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(40 * time.Millisecond):
			}
		}
		return nil
	})
}

func (b *talkerBrain) convo() []brain.Message {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.session == nil {
		return nil
	}
	return b.session.Conversation.Messages()
}

// configureBrain captures its session so a test can drive Session.ConfigureTTS /
// ConfigureSTT directly and observe the resulting wire frame on the fake-cortex peer.
type configureBrain struct {
	mu      sync.Mutex
	session *brain.Session
}

func (b *configureBrain) OnSessionStart(ctx context.Context, s *brain.Session, _ brain.SessionStart) error {
	b.mu.Lock()
	b.session = s
	b.mu.Unlock()
	return nil
}

func (b *configureBrain) OnInteraction(ctx context.Context, in *brain.Interaction) error {
	return in.Inference(ctx, func(inf *brain.Inference) error { return inf.Speak("ok") })
}

// ─── helpers ───────────────────────────────────────────────────────────────────

type testLogger struct{ t *testing.T }

func (l testLogger) Infof(f string, a ...any) { l.t.Logf("INFO "+f, a...) }
func (l testLogger) Warnf(f string, a ...any) { l.t.Logf("WARN "+f, a...) }

func runAgent(t *testing.T, fc *fakeCortex, newBrain func() brain.Brain) (*peer, func()) {
	t.Helper()
	log := testLogger{t}
	agent, err := cortex.New(cortex.Options{
		Version:   "go-test/0.1",
		CortexURL: fc.wsURL(),
		APIKey:    "ak_test",
		Logger:    log,
	}, brain.Factory(newBrain, log))
	if err != nil {
		t.Fatalf("cortex.New: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { _ = agent.Run(ctx); close(done) }()
	stop := func() {
		cancel()
		select {
		case <-done:
		case <-time.After(3 * time.Second):
		}
	}
	return fc.accept(t), stop
}

func texts(frames []wire.Decoded) []string {
	var out []string
	for _, d := range frames {
		if t, ok := d.Frame.(wire.VqlLLMText); ok {
			out = append(out, t.Text)
		}
	}
	return out
}

// ─── tests ─────────────────────────────────────────────────────────────────────

func TestGreetingSingleTurnAndHeardConversation(t *testing.T) {
	fc := newFakeCortex(t)
	defer fc.close()
	g := &greeterBrain{}
	p, stop := runAgent(t, fc, func() brain.Brain { return g })
	defer stop()

	// Greeting: VqlStart → one inference (interaction_id 0).
	p.send(t, wire.VqlStart{SessionID: sid.String(), AgentID: "t:demo:travel", Payload: map[string]any{}}, 0)
	greet := p.collect(800 * time.Millisecond)
	if got := texts(greet); len(got) != 1 || got[0] != "hello there friend" {
		t.Fatalf("greeting texts = %v", got)
	}

	// User turn with request_id → expect an ack(7) plus the response.
	p.send(t, wire.VqlUserText{InteractionID: 1, Text: "good morning"}, 7)
	turn := p.collect(800 * time.Millisecond)
	gotAck := false
	for _, d := range turn {
		if d.IsAck && d.AckID == 7 {
			gotAck = true
		}
	}
	if !gotAck {
		t.Errorf("no ack(7) for the user turn; frames=%+v", turn)
	}
	if got := texts(turn); len(got) != 1 || got[0] != "you said good morning" {
		t.Fatalf("turn texts = %v", got)
	}
	// ui_command (screen-driving) surfaced.
	if !hasUICommand(turn, "open_dashboard") {
		t.Errorf("no open_dashboard ui_command; frames=%+v", turn)
	}

	// Finalize both inferences → framework records HEARD text into Conversation.
	p.send(t, wire.VqlInferenceFinalized{InteractionID: 0, InferenceID: 1, HeardText: "hello there friend"}, 0)
	p.send(t, wire.VqlInferenceFinalized{InteractionID: 1, InferenceID: 1, HeardText: "you said good morning"}, 0)

	waitFor(t, 1*time.Second, func() bool {
		c := g.convo()
		return countRole(c, "assistant") >= 2 && countRole(c, "user") >= 1
	})
	c := g.convo()
	if !hasMsg(c, "user", "good morning") {
		t.Errorf("conversation missing user turn: %+v", c)
	}
	if !hasMsg(c, "assistant", "hello there friend") || !hasMsg(c, "assistant", "you said good morning") {
		t.Errorf("conversation missing assistant heard text: %+v", c)
	}
}

func TestBargeInCancelsAndEchoesAndRecordsTruncatedHeard(t *testing.T) {
	fc := newFakeCortex(t)
	defer fc.close()
	b := &talkerBrain{}
	p, stop := runAgent(t, fc, func() brain.Brain { return b })
	defer stop()

	p.send(t, wire.VqlStart{SessionID: sid.String(), Payload: map[string]any{}}, 0)

	// Start a long turn; wait until a few chunks have streamed, then barge in.
	p.send(t, wire.VqlUserText{InteractionID: 1, Text: "tell me a lot"}, 3)
	// Read until we've seen at least 2 text chunks.
	seen := 0
	deadline := time.Now().Add(2 * time.Second)
	for seen < 2 && time.Now().Before(deadline) {
		if d, ok := p.recv(time.Until(deadline)); ok {
			if _, isText := d.Frame.(wire.VqlLLMText); isText {
				seen++
			}
		}
	}
	if seen < 2 {
		t.Fatalf("did not see streaming chunks before barge-in (saw %d)", seen)
	}
	p.send(t, wire.Interruption{}, 0)

	// Expect the Interruption echo (drain barrier) back from the agent.
	rest := p.collect(1 * time.Second)
	if !hasInterruption(rest) {
		t.Errorf("no Interruption echo after barge-in; frames=%+v", rest)
	}
	// The talker must have stopped well before all ten words.
	b.mu.Lock()
	spoken := b.spoken
	b.mu.Unlock()
	if spoken >= 10 {
		t.Errorf("brain spoke all %d words; barge-in did not cancel it", spoken)
	}

	// Finalize as interrupted with the truncated heard prefix; the framework
	// records the truncated heard, never the full generated reply.
	p.send(t, wire.VqlInferenceFinalized{InteractionID: 1, InferenceID: 1, HeardText: "one two", Interrupted: true}, 0)
	waitFor(t, 1*time.Second, func() bool { return countRole(b.convo(), "assistant") >= 1 })
	c := b.convo()
	if !hasMsg(c, "assistant", "one two") {
		t.Errorf("conversation missing truncated heard text: %+v", c)
	}
}

func TestBrowserAppEventReachesBrain(t *testing.T) {
	fc := newFakeCortex(t)
	defer fc.close()
	g := &greeterBrain{}
	p, stop := runAgent(t, fc, func() brain.Brain { return g })
	defer stop()

	p.send(t, wire.VqlStart{SessionID: sid.String(), Payload: map[string]any{}}, 0)
	_ = p.collect(500 * time.Millisecond) // drain greeting

	p.send(t, wire.RTVIClientMessage{Type: "state_sync", Data: map[string]any{"itinerary": map[string]any{"name": "Mehta Vietnam"}}}, 0)
	waitFor(t, 1*time.Second, func() bool {
		g.mu.Lock()
		defer g.mu.Unlock()
		return len(g.appEvents) >= 1
	})
	g.mu.Lock()
	defer g.mu.Unlock()
	if len(g.appEvents) == 0 || g.appEvents[0].Name != "state_sync" {
		t.Fatalf("app event not delivered: %+v", g.appEvents)
	}
}

// outcomeBrain fires a UI action with a result callback and records the outcome.
type outcomeBrain struct {
	mu  sync.Mutex
	got *brain.Outcome
}

func (b *outcomeBrain) OnInteraction(ctx context.Context, in *brain.Interaction) error {
	in.ActionWithResult("collect_travelers", map[string]any{"trip": "x"}, func(o brain.Outcome) {
		b.mu.Lock()
		b.got = &o
		b.mu.Unlock()
	})
	return in.Inference(ctx, func(inf *brain.Inference) error { return inf.Speak("collecting") })
}

func (b *outcomeBrain) outcome() *brain.Outcome {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.got
}

func TestInteractionCompletedOnCleanReturn(t *testing.T) {
	fc := newFakeCortex(t)
	defer fc.close()
	g := &greeterBrain{}
	p, stop := runAgent(t, fc, func() brain.Brain { return g })
	defer stop()

	p.send(t, wire.VqlStart{SessionID: sid.String(), Payload: map[string]any{}}, 0)
	_ = p.collect(500 * time.Millisecond) // greeting (agent-initiated; no completed)

	p.send(t, wire.VqlUserText{InteractionID: 1, Text: "hi"}, 5)
	frames := p.collect(800 * time.Millisecond)
	if !hasInteractionCompleted(frames, 1) {
		t.Fatalf("no interaction.completed after a clean turn; frames=%+v", frames)
	}
}

func TestInteractionCompletedSkippedOnBargeIn(t *testing.T) {
	fc := newFakeCortex(t)
	defer fc.close()
	b := &talkerBrain{}
	p, stop := runAgent(t, fc, func() brain.Brain { return b })
	defer stop()

	p.send(t, wire.VqlStart{SessionID: sid.String(), Payload: map[string]any{}}, 0)
	p.send(t, wire.VqlUserText{InteractionID: 1, Text: "talk a lot"}, 3)
	seen := 0
	deadline := time.Now().Add(2 * time.Second)
	for seen < 2 && time.Now().Before(deadline) {
		if d, ok := p.recv(time.Until(deadline)); ok {
			if _, isText := d.Frame.(wire.VqlLLMText); isText {
				seen++
			}
		}
	}
	p.send(t, wire.Interruption{}, 0)
	rest := p.collect(800 * time.Millisecond)
	if hasInteractionCompleted(rest, 1) {
		t.Errorf("interaction.completed emitted despite barge-in; frames=%+v", rest)
	}
	if !hasInterruption(rest) {
		t.Errorf("no interruption echo on barge-in")
	}
}

func TestActionOutcomeFiresCallback(t *testing.T) {
	fc := newFakeCortex(t)
	defer fc.close()
	b := &outcomeBrain{}
	p, stop := runAgent(t, fc, func() brain.Brain { return b })
	defer stop()

	p.send(t, wire.VqlStart{SessionID: sid.String(), Payload: map[string]any{}}, 0)
	p.send(t, wire.VqlUserText{InteractionID: 1, Text: "go"}, 7)
	frames := p.collect(800 * time.Millisecond)
	aid := uiCommandActionID(frames, "collect_travelers")
	if aid == 0 {
		t.Fatalf("no collect_travelers ui_command with action_id; frames=%+v", frames)
	}

	// Browser reports the outcome (App→V→B), correlated by action_id.
	p.send(t, wire.RTVIClientMessage{Type: "action_outcome", Data: map[string]any{
		"action_id":      aid,
		"interaction_id": uint64(1),
		"status":         "ok",
		"result":         map[string]any{"count": 2},
	}}, 0)

	waitFor(t, 1*time.Second, func() bool { return b.outcome() != nil })
	o := b.outcome()
	if o.ActionID != aid || o.Status != "ok" {
		t.Fatalf("unexpected outcome: %+v", o)
	}
}

func TestConfigureTTS(t *testing.T) {
	fc := newFakeCortex(t)
	defer fc.close()
	b := &configureBrain{}
	p, stop := runAgent(t, fc, func() brain.Brain { return b })
	defer stop()

	p.send(t, wire.VqlStart{SessionID: sid.String(), Payload: map[string]any{}}, 0)
	waitFor(t, 1*time.Second, func() bool {
		b.mu.Lock()
		defer b.mu.Unlock()
		return b.session != nil
	})

	b.mu.Lock()
	b.session.ConfigureTTS("gaurav", "hi", "omnivoice")
	b.mu.Unlock()

	frames := p.collect(500 * time.Millisecond)
	got := ttsUpdateSettings(frames)
	if got == nil {
		t.Fatalf("no TTSUpdateSettings frame; frames=%+v", frames)
	}
	if got.Settings["voice"] != "gaurav" || got.Settings["language"] != "hi" || got.Settings["model"] != "omnivoice" {
		t.Fatalf("unexpected settings: %+v", got.Settings)
	}
}

func TestConfigureSTT(t *testing.T) {
	fc := newFakeCortex(t)
	defer fc.close()
	b := &configureBrain{}
	p, stop := runAgent(t, fc, func() brain.Brain { return b })
	defer stop()

	p.send(t, wire.VqlStart{SessionID: sid.String(), Payload: map[string]any{}}, 0)
	waitFor(t, 1*time.Second, func() bool {
		b.mu.Lock()
		defer b.mu.Unlock()
		return b.session != nil
	})

	b.mu.Lock()
	b.session.ConfigureSTT(brain.STTConfig{
		VadConfidence: brain.Float64Ptr(0.7),
		VadBargeInMs:  brain.IntPtr(300),
	})
	b.mu.Unlock()

	frames := p.collect(500 * time.Millisecond)
	got := sttUpdateSettings(frames)
	if got == nil {
		t.Fatalf("no STTUpdateSettings frame; frames=%+v", frames)
	}
	if got.Settings["vad_confidence"] != 0.7 || got.Settings["vad_barge_in_ms"] != float64(300) {
		t.Fatalf("unexpected settings: %+v", got.Settings)
	}
	if _, unwanted := got.Settings["vad_min_volume"]; unwanted {
		t.Fatalf("unset knob leaked into settings: %+v", got.Settings)
	}
}

// ─── assertion helpers ───────────────────────────────────────────────────────

func waitFor(t *testing.T, d time.Duration, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(d)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("condition not met within %s", d)
}

func countRole(msgs []brain.Message, role string) int {
	n := 0
	for _, m := range msgs {
		if m.Role == role {
			n++
		}
	}
	return n
}

func hasMsg(msgs []brain.Message, role, content string) bool {
	for _, m := range msgs {
		if m.Role == role && m.Content == content {
			return true
		}
	}
	return false
}

func hasUICommand(frames []wire.Decoded, action string) bool {
	for _, d := range frames {
		if m, ok := d.Frame.(wire.RTVIServerMessage); ok {
			if m.Data["type"] == "ui_command" && m.Data["action"] == action {
				return true
			}
		}
	}
	return false
}

func hasInterruption(frames []wire.Decoded) bool {
	for _, d := range frames {
		if _, ok := d.Frame.(wire.Interruption); ok {
			return true
		}
	}
	return false
}

func ttsUpdateSettings(frames []wire.Decoded) *wire.TTSUpdateSettings {
	for _, d := range frames {
		if m, ok := d.Frame.(wire.TTSUpdateSettings); ok {
			return &m
		}
	}
	return nil
}

func sttUpdateSettings(frames []wire.Decoded) *wire.STTUpdateSettings {
	for _, d := range frames {
		if m, ok := d.Frame.(wire.STTUpdateSettings); ok {
			return &m
		}
	}
	return nil
}

func hasInteractionCompleted(frames []wire.Decoded, id uint64) bool {
	for _, d := range frames {
		if c, ok := d.Frame.(wire.InteractionCompleted); ok && c.InteractionID == id {
			return true
		}
	}
	return false
}

// uiCommandActionID returns the action_id stamped on a ui_command for the given
// action (0 if not found). JSON numbers decode as float64.
func uiCommandActionID(frames []wire.Decoded, action string) uint64 {
	for _, d := range frames {
		if m, ok := d.Frame.(wire.RTVIServerMessage); ok && m.Data["action"] == action {
			if f, ok := m.Data["action_id"].(float64); ok {
				return uint64(f)
			}
		}
	}
	return 0
}
