package tests

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/joho/godotenv"

	"github.com/voqalize/voqalize/sdk/go/brain"
	"github.com/voqalize/voqalize/sdk/go/examples/travel"
	"github.com/voqalize/voqalize/sdk/go/wire"
)

// TestTravelLiveScreenDriving drives the real Gemini travel brain through the
// fake cortex: a dated brief must make the brain SPEAK then call create_itinerary
// (a ui_command on the wire) — proving the genai tool-calling loop, multi-
// inference brackets, and screen-driving work end to end on the native Go SDK.
//
// Gated on GEMINI_API_KEY (loaded from the repo-root .env); skipped otherwise.
func TestTravelLiveScreenDriving(t *testing.T) {
	loadRepoEnv(t)
	if os.Getenv("GEMINI_API_KEY") == "" {
		t.Skip("GEMINI_API_KEY not set (live Gemini integration test)")
	}

	fc := newFakeCortex(t)
	defer fc.close()

	newBrain := func() brain.Brain {
		b, err := travel.New(context.Background(), "")
		if err != nil {
			t.Fatalf("travel.New: %v", err)
		}
		return b
	}
	p, stop := runAgent(t, fc, newBrain)
	defer stop()

	// Greeting (interaction 0) — the fixed English opener (see examples/travel
	// tools.go `greeting`; it matches the Python travel brain).
	p.send(t, wire.VqlStart{SessionID: sid.String(), AgentID: "t:demo-tenant:voqal-travel", Payload: map[string]any{}}, 0)
	greet := p.collect(3 * time.Second)
	if !containsText(greet, "Priya") {
		t.Fatalf("greeting did not contain the Priya opener; texts=%v", texts(greet))
	}

	// A complete dated brief so create_itinerary fires (it requires dates).
	p.send(t, wire.VqlUserText{InteractionID: 1, Text: "Start a new Vietnam trip for the Mehta family, twelve to eighteen August twenty twenty six."}, 11)
	frames := p.collect(25 * time.Second)

	if !hasUICommand(frames, "create_itinerary") {
		t.Fatalf("brain never drove the screen with create_itinerary; frames=%s", summarize(frames))
	}
	// An ack for the user turn must have come back (SDK-level guarantee).
	if !hasAck(frames, 11) {
		t.Errorf("no ack(11) for the user turn")
	}
	// Voice-first is requested in the prompt but is model behavior, not an SDK
	// guarantee — flash-lite sometimes calls the tool silently. Log, don't fail.
	if len(texts(frames)) == 0 {
		t.Logf("note: model called create_itinerary without a spoken preamble this run")
	}
}

// TestTravelLiveMultiTurn drives a real multi-turn conversation
// (create → flights → day-wise plan) and asserts each turn drives the screen
// with the expected ui_command. Between turns it finalizes the assistant
// inferences, so the next turn's working context is rebuilt from the heard
// transcript — exercising the multi-turn tool round-trip path (the class of bug
// that kept surfacing only live: missing tools, contract drift, signature loss).
//
// Gated on GEMINI_API_KEY (loaded from the repo-root .env); skipped otherwise.
func TestTravelLiveMultiTurn(t *testing.T) {
	loadRepoEnv(t)
	if os.Getenv("GEMINI_API_KEY") == "" {
		t.Skip("GEMINI_API_KEY not set (live Gemini integration test)")
	}

	fc := newFakeCortex(t)
	defer fc.close()
	newBrain := func() brain.Brain {
		b, err := travel.New(context.Background(), "")
		if err != nil {
			t.Fatalf("travel.New: %v", err)
		}
		return b
	}
	p, stop := runAgent(t, fc, newBrain)
	defer stop()

	p.send(t, wire.VqlStart{SessionID: sid.String(), AgentID: "t:demo-tenant:voqal-travel", Payload: map[string]any{}}, 0)
	_ = p.collectTurn(5*time.Second, 2*time.Second) // drain greeting

	turns := []struct {
		iid, req uint64
		text     string
		want     string
	}{
		{1, 11, "Start a new Vietnam trip for the Mehta family, twelve to eighteen August twenty twenty six.", "create_itinerary"},
		{2, 12, "Search flights from Bangalore to Ho Chi Minh for the outbound leg.", "search_flights"},
		{3, 13, "Great. Now show me the full day-wise itinerary.", "generate_day_plan"},
	}
	for _, tn := range turns {
		p.send(t, wire.VqlUserText{InteractionID: tn.iid, Text: tn.text}, tn.req)
		frames := p.collectTurn(25*time.Second, 5*time.Second)
		if !hasAck(frames, tn.req) {
			t.Errorf("turn %d: no ack(%d)", tn.iid, tn.req)
		}
		if !hasUICommand(frames, tn.want) {
			t.Fatalf("turn %d (%q): expected ui_command %q; got: %s", tn.iid, tn.text, tn.want, summarize(frames))
		}
		finalizeInferences(t, p, tn.iid, frames)
	}
}

// collectTurn gathers frames for one turn: wait up to firstWait for the first
// frame, then return once idleGap elapses with no further frame.
func (p *peer) collectTurn(firstWait, idleGap time.Duration) []wire.Decoded {
	dec, ok := p.recv(firstWait)
	if !ok {
		return nil
	}
	out := []wire.Decoded{dec}
	for {
		dec, ok := p.recv(idleGap)
		if !ok {
			return out
		}
		out = append(out, dec)
	}
}

// finalizeInferences simulates pygato's post-playout finalize: for each inference
// that spoke, send VqlInferenceFinalized with the heard text, so the SDK records
// the assistant turn in the conversation for the next turn's context.
func finalizeInferences(t *testing.T, p *peer, iid uint64, frames []wire.Decoded) {
	heard := map[uint64]string{}
	var order []uint64
	for _, d := range frames {
		if f, ok := d.Frame.(wire.VqlLLMText); ok && f.InteractionID == iid {
			if _, seen := heard[f.InferenceID]; !seen {
				order = append(order, f.InferenceID)
			}
			heard[f.InferenceID] += f.Text
		}
	}
	for _, infID := range order {
		p.send(t, wire.VqlInferenceFinalized{InteractionID: iid, InferenceID: infID, HeardText: heard[infID]}, 0)
	}
}

func loadRepoEnv(t *testing.T) {
	t.Helper()
	dir, _ := os.Getwd()
	for {
		if _, err := os.Stat(filepath.Join(dir, ".dev-keys")); err == nil {
			_ = godotenv.Load(filepath.Join(dir, ".env"))
			return
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return
		}
		dir = parent
	}
}

func containsText(frames []wire.Decoded, sub string) bool {
	for _, s := range texts(frames) {
		if strings.Contains(s, sub) {
			return true
		}
	}
	return false
}

func hasAck(frames []wire.Decoded, id uint64) bool {
	for _, d := range frames {
		if d.IsAck && d.AckID == id {
			return true
		}
	}
	return false
}

func summarize(frames []wire.Decoded) string {
	var b strings.Builder
	for _, d := range frames {
		switch f := d.Frame.(type) {
		case wire.VqlLLMText:
			b.WriteString("text(" + f.Text + ") ")
		case wire.RTVIServerMessage:
			b.WriteString("ui(" + asString(f.Data["action"]) + ") ")
		case wire.VqlLLMStart:
			b.WriteString("start ")
		case wire.VqlLLMEnd:
			b.WriteString("end ")
		default:
			if d.IsAck {
				b.WriteString("ack ")
			}
		}
	}
	return b.String()
}

func asString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
