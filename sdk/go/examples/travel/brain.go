// Package travel is the travel-desk agent, ported from the Python
// examples/travel brain to the native Go SDK (no pipecat). It exercises the
// cortex core concepts: per-turn interaction, multi-inference tool round-trips
// (speak a line → call a screen tool → speak the result), screen-driving via
// interaction.Action (the RTVI ui_command pygato relays), the framework-enforced
// heard-text Conversation, and browser→brain app events (state_sync).
//
// The conversation record is framework-owned: the SDK keeps the faithful,
// heard-text transcript in interaction.Conversation(); we rebuild Gemini's
// working context from it each turn (generated text + tool round-trips stay
// transient, in-flight only) so past turns are always the heard truth.
package travel

import (
	"context"
	"fmt"
	"os"

	"google.golang.org/genai"

	"github.com/voqalize/voqalize/sdk/go/brain"
)

const model = "gemini-3.1-flash-lite"

const maxToolHops = 6

// TravelBrain is one per session: owns this session's itinerary state. The
// conversation transcript is owned by the SDK (interaction.Conversation()).
type TravelBrain struct {
	client *genai.Client
	cfg    *genai.GenerateContentConfig

	// Domain state mirrored to the browser via Action; the durable conversation
	// record is NOT here (the SDK owns it).
	itinerary    map[string]any
	flights      map[string]any // leg_id -> options
	hotels       map[string]any // city -> options
	selected     map[string]any
	browserState map[string]any // latest state_sync (what's on screen, incl. hand edits)
}

// New builds a TravelBrain. apiKey defaults to GEMINI_API_KEY.
func New(ctx context.Context, apiKey string) (*TravelBrain, error) {
	if apiKey == "" {
		apiKey = os.Getenv("GEMINI_API_KEY")
	}
	if apiKey == "" {
		return nil, fmt.Errorf("travel: GEMINI_API_KEY not set")
	}
	client, err := genai.NewClient(ctx, &genai.ClientConfig{APIKey: apiKey, Backend: genai.BackendGeminiAPI})
	if err != nil {
		return nil, fmt.Errorf("travel: genai client: %w", err)
	}
	return &TravelBrain{
		client:   client,
		cfg:      newConfig(),
		flights:  map[string]any{},
		hotels:   map[string]any{},
		selected: map[string]any{},
	}, nil
}

// OnSessionStart speaks the fixed English greeting (agent-initiated, interaction 0).
func (b *TravelBrain) OnSessionStart(ctx context.Context, s *brain.Session, _ brain.SessionStart) error {
	return s.Inference(ctx, func(inf *brain.Inference) error { return inf.Speak(greeting) })
}

// OnInteraction runs the manual Gemini function-calling loop. Each LLM call is
// one inference bracket (1:1 with the wire), so a tool round-trip is naturally
// multi-inference.
func (b *TravelBrain) OnInteraction(ctx context.Context, in *brain.Interaction) error {
	contents := b.workingContext(in) // faithful (heard) transcript incl. this user turn
	for hop := 0; hop < maxToolHops; hop++ {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		fcalls, modelParts, err := b.oneInference(ctx, in, contents)
		if err != nil {
			return err
		}
		if len(modelParts) > 0 {
			contents = append(contents, &genai.Content{Role: genai.RoleModel, Parts: modelParts})
		}
		if len(fcalls) == 0 {
			return nil
		}
		for _, fc := range fcalls {
			result := b.dispatchTool(in, fc.Name, fc.Args)
			contents = append(contents, genai.NewContentFromFunctionResponse(
				fc.Name, map[string]any{"result": result}, genai.RoleUser))
		}
	}
	return nil
}

// oneInference streams one Gemini call inside one inference bracket: speak text
// chunks, collect function calls, and return clean model parts for the loop.
// Streamed parts are reassembled (text deltas concatenated, function calls
// rebuilt) — forwarding raw stream parts can include empty/partial parts that
// the API rejects on the follow-up request.
func (b *TravelBrain) oneInference(ctx context.Context, in *brain.Interaction, contents []*genai.Content) ([]*genai.FunctionCall, []*genai.Part, error) {
	var fcalls []*genai.FunctionCall
	var modelParts []*genai.Part
	err := in.Inference(ctx, func(inf *brain.Inference) error {
		for resp, err := range b.client.Models.GenerateContentStream(ctx, model, contents, b.cfg) {
			if err != nil {
				return err
			}
			for _, cand := range resp.Candidates {
				if cand.Content == nil {
					continue
				}
				for _, part := range cand.Content.Parts {
					if part.Text != "" {
						_ = inf.Speak(part.Text)
					}
					if part.FunctionCall != nil {
						fcalls = append(fcalls, part.FunctionCall)
					}
					// Keep non-empty parts verbatim for the working context. This
					// preserves the thought_signature Gemini 3 attaches to
					// function-call parts — required when the turn is sent back on
					// the next tool round-trip. Empty/thought-only parts are dropped
					// (the API rejects a part with no data field set).
					if part.Text != "" || part.FunctionCall != nil {
						modelParts = append(modelParts, part)
					}
				}
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
		}
		return nil
	})
	return fcalls, modelParts, err
}

// OnAppEvent stores the latest browser state_sync so get_active_itinerary
// reflects what's actually on screen (incl. the agent's hand edits).
func (b *TravelBrain) OnAppEvent(ctx context.Context, _ *brain.Session, ev brain.AppEvent) {
	if ev.Name == "state_sync" {
		b.browserState = ev.Data
	}
}

// workingContext rebuilds genai contents from the framework's heard transcript.
// Skips assistant turns before the first user turn (the greeting) so contents
// start with a user turn, as Gemini expects.
func (b *TravelBrain) workingContext(in *brain.Interaction) []*genai.Content {
	var out []*genai.Content
	seenUser := false
	for _, m := range in.Conversation().Messages() {
		switch m.Role {
		case "user":
			seenUser = true
			out = append(out, genai.NewContentFromText(m.Content, genai.RoleUser))
		case "assistant":
			if seenUser {
				out = append(out, genai.NewContentFromText(m.Content, genai.RoleModel))
			}
		}
	}
	return out
}
