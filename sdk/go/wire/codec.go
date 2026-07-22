// Package wire is the cortex wire vocabulary for the native Go agent SDK.
//
// It mirrors sdk/python (Python) but carries no pipecat dependency: the
// contract is protobuf Envelope frames over a multiplexed WebSocket to cortex's
// /agent endpoint. This file is the codec — typed Go frames <-> Envelope bytes.
//
// Frames are decoded into small typed structs (with JSON payloads parsed) rather
// than exposing the raw protobuf, so the runtime/brain layers switch on Go types.
package wire

import (
	"encoding/json"
	"fmt"

	"google.golang.org/protobuf/proto"

	"github.com/voqalize/voqalize/sdk/go/wire/framespb"
)

// Direction is the 1-byte direction tag on every multiplexed message. The values
// MUST match pipecat's FrameDirection enum (DOWNSTREAM=1, UPSTREAM=2) — pygato
// decodes the byte as FrameDirection(b) and rejects anything else. pygato sends
// everything DOWNSTREAM; the agent replies DOWNSTREAM too.
type Direction byte

const (
	Downstream Direction = 1
	Upstream   Direction = 2
)

// Frame is the decoded wire vocabulary. Each concrete type is one Envelope body.
type Frame interface{ isFrame() }

// ─── Inbound frames (cortex/pygato → agent) ──────────────────────────────────

// VqlStart opens a session. SessionID is the hyphenated UUID; the 16-byte wire
// prefix is the same id in raw form.
type VqlStart struct {
	SessionID string
	AgentID   string
	Payload   map[string]any
}

// VqlUserText is a committed user utterance; Voice mints InteractionID.
type VqlUserText struct {
	InteractionID uint64
	Text          string
}

// Interruption is the field-less barge-in / drain-barrier signal.
type Interruption struct{}

// VqlInferenceFinalized is the post-playout finalize: HeardText is what the user
// actually heard for this inference (truncated on barge-in).
type VqlInferenceFinalized struct {
	InteractionID uint64
	InferenceID   uint64
	HeardText     string
	Interrupted   bool
	Reason        framespb.FinalizeReason
}

// RTVIClientMessage is a browser→agent app event (e.g. state_sync).
type RTVIClientMessage struct {
	MsgID string
	Type  string
	Data  map[string]any
}

// End tears the session down. Cancel/Error are lifecycle/transport signals.
type End struct{}
type Cancel struct{ Reason string }
type Error struct {
	Error string
	Fatal bool
}

// ─── Outbound frames (agent → cortex/pygato) ─────────────────────────────────

// VqlLLMStart/Text/End bracket one inference (LLM call). Text is one bot-speech
// chunk; many per bracket.
type VqlLLMStart struct{ InteractionID, InferenceID uint64 }
type VqlLLMText struct {
	InteractionID, InferenceID uint64
	Text                       string
}
type VqlLLMEnd struct{ InteractionID, InferenceID uint64 }

// RTVIServerMessage is a UI command to the browser (pygato relays it UPSTREAM to
// its RTVI processor). Data is the ui_command envelope.
type RTVIServerMessage struct{ Data map[string]any }

// InteractionCompleted (Brain→Voice) signals the brain is done responding to the
// whole interaction. Emitted when OnInteraction returns cleanly (skipped on
// barge-in). pygato consumes it.
type InteractionCompleted struct{ InteractionID uint64 }

// TTSUpdateSettings changes TTS voice/language/model mid-call — pygato applies
// it to whichever inference's TTS context opens next (vql-speech locks
// voice/model/language per context, so a change never lands mid-utterance).
// Settings is a plain dict, matching pipecat's legacy
// TTSUpdateSettingsFrame(settings={...}) dict path — the only form portable
// over the wire. Recognized keys: "voice", "language", "model".
type TTSUpdateSettings struct{ Settings map[string]any }

// STTUpdateSettings changes STT VAD/turn-detection knobs mid-call — pygato
// forwards it directly as a Flux Configure message on the live STT websocket,
// no queuing (unlike TTS, vql-speech applies these live against
// self-resetting counters). Recognized keys: vad_confidence, vad_min_volume,
// vad_start_frames, vad_stop_frames_to_trigger_update, vad_eager_frames,
// vad_barge_in_ms, resume_frames, min_segment_speech_frames, confidence_tail_ms.
type STTUpdateSettings struct{ Settings map[string]any }

func (VqlStart) isFrame()              {}
func (VqlUserText) isFrame()           {}
func (Interruption) isFrame()          {}
func (VqlInferenceFinalized) isFrame() {}
func (RTVIClientMessage) isFrame()     {}
func (End) isFrame()                   {}
func (Cancel) isFrame()                {}
func (Error) isFrame()                 {}
func (VqlLLMStart) isFrame()           {}
func (VqlLLMText) isFrame()            {}
func (VqlLLMEnd) isFrame()             {}
func (RTVIServerMessage) isFrame()     {}
func (InteractionCompleted) isFrame()  {}
func (TTSUpdateSettings) isFrame()     {}
func (STTUpdateSettings) isFrame()     {}

// IsSystem reports whether a frame rides the priority (system) lane — it must
// bypass queued data frames. Matches pipecat's SystemFrame set: StartFrame
// (VqlStart), InterruptionFrame, CancelFrame. EndFrame is a ControlFrame and
// rides the normal lane (FIFO behind data), so it tears down after draining.
func IsSystem(f Frame) bool {
	switch f.(type) {
	case VqlStart, Interruption, Cancel:
		return true
	default:
		return false
	}
}

// ─── Decode ──────────────────────────────────────────────────────────────────

// Decoded is one Envelope's worth of wire data. Frame is nil for a pure Ack.
type Decoded struct {
	Frame     Frame
	RequestID uint64 // non-zero ⇒ send an Ack back after handling
	AckID     uint64 // set (with Frame nil) for an Ack envelope
	IsAck     bool
}

// Decode parses an Envelope payload into a typed frame.
func Decode(payload []byte) (Decoded, error) {
	var env framespb.Envelope
	if err := proto.Unmarshal(payload, &env); err != nil {
		return Decoded{}, fmt.Errorf("wire: envelope parse failed: %w", err)
	}
	reqID := env.GetRequestId()

	switch body := env.GetBody().(type) {
	case *framespb.Envelope_Ack:
		return Decoded{IsAck: true, AckID: body.Ack.GetAckId(), RequestID: reqID}, nil
	case *framespb.Envelope_VqlStart:
		m := body.VqlStart
		payloadMap, err := decodeJSONObject(m.GetPayload())
		if err != nil {
			return Decoded{}, fmt.Errorf("wire: vql_start payload: %w", err)
		}
		return Decoded{Frame: VqlStart{
			SessionID: m.GetSessionId(),
			AgentID:   m.GetAgentId(),
			Payload:   payloadMap,
		}, RequestID: reqID}, nil
	case *framespb.Envelope_VqlUserText:
		m := body.VqlUserText
		return Decoded{Frame: VqlUserText{InteractionID: m.GetInteractionId(), Text: m.GetText()}, RequestID: reqID}, nil
	case *framespb.Envelope_VqlInterruption:
		return Decoded{Frame: Interruption{}, RequestID: reqID}, nil
	case *framespb.Envelope_VqlInferenceFinalized:
		m := body.VqlInferenceFinalized
		return Decoded{Frame: VqlInferenceFinalized{
			InteractionID: m.GetInteractionId(),
			InferenceID:   m.GetInferenceId(),
			HeardText:     m.GetHeardText(),
			Interrupted:   m.GetInterrupted(),
			Reason:        m.GetReason(),
		}, RequestID: reqID}, nil
	case *framespb.Envelope_RtviClientMessage:
		m := body.RtviClientMessage
		data, err := decodeJSONObject(m.GetData())
		if err != nil {
			return Decoded{}, fmt.Errorf("wire: rtvi_client_message data: %w", err)
		}
		return Decoded{Frame: RTVIClientMessage{MsgID: m.GetMsgId(), Type: m.GetType(), Data: data}, RequestID: reqID}, nil
	case *framespb.Envelope_End:
		return Decoded{Frame: End{}, RequestID: reqID}, nil
	case *framespb.Envelope_Cancel:
		return Decoded{Frame: Cancel{Reason: body.Cancel.GetReason()}, RequestID: reqID}, nil
	case *framespb.Envelope_Error:
		return Decoded{Frame: Error{Error: body.Error.GetError(), Fatal: body.Error.GetFatal()}, RequestID: reqID}, nil
	// Outbound frames (agent → pygato) — decoded so a fake peer / test can read them.
	case *framespb.Envelope_VqlLlmStart:
		m := body.VqlLlmStart
		return Decoded{Frame: VqlLLMStart{InteractionID: m.GetInteractionId(), InferenceID: m.GetInferenceId()}, RequestID: reqID}, nil
	case *framespb.Envelope_VqlLlmText:
		m := body.VqlLlmText
		return Decoded{Frame: VqlLLMText{InteractionID: m.GetInteractionId(), InferenceID: m.GetInferenceId(), Text: m.GetText()}, RequestID: reqID}, nil
	case *framespb.Envelope_VqlLlmEnd:
		m := body.VqlLlmEnd
		return Decoded{Frame: VqlLLMEnd{InteractionID: m.GetInteractionId(), InferenceID: m.GetInferenceId()}, RequestID: reqID}, nil
	case *framespb.Envelope_RtviServerMessage:
		data, err := decodeJSONObject(body.RtviServerMessage.GetData())
		if err != nil {
			return Decoded{}, fmt.Errorf("wire: rtvi_server_message data: %w", err)
		}
		return Decoded{Frame: RTVIServerMessage{Data: data}, RequestID: reqID}, nil
	case *framespb.Envelope_VqlInteractionCompleted:
		return Decoded{Frame: InteractionCompleted{InteractionID: body.VqlInteractionCompleted.GetInteractionId()}, RequestID: reqID}, nil
	case *framespb.Envelope_TtsUpdateSettings:
		settings, err := decodeJSONObject(body.TtsUpdateSettings.GetSettings())
		if err != nil {
			return Decoded{}, fmt.Errorf("wire: tts_update_settings settings: %w", err)
		}
		return Decoded{Frame: TTSUpdateSettings{Settings: settings}, RequestID: reqID}, nil
	case *framespb.Envelope_SttUpdateSettings:
		settings, err := decodeJSONObject(body.SttUpdateSettings.GetSettings())
		if err != nil {
			return Decoded{}, fmt.Errorf("wire: stt_update_settings settings: %w", err)
		}
		return Decoded{Frame: STTUpdateSettings{Settings: settings}, RequestID: reqID}, nil
	default:
		return Decoded{}, fmt.Errorf("wire: unsupported/empty envelope body %T", body)
	}
}

// ─── Encode ────────────────────────────────────────────────────────────────────

// Encode marshals a frame to Envelope bytes with request_id 0 (the agent's own
// frames don't expect acks back).
func Encode(f Frame) ([]byte, error) { return EncodeWithRequest(f, 0) }

// EncodeWithRequest marshals a frame, stamping request_id when non-zero (used by
// a peer/test to request an ack). The codec is symmetric: it can encode both
// inbound and outbound frames.
func EncodeWithRequest(f Frame, requestID uint64) ([]byte, error) {
	env := &framespb.Envelope{}
	switch v := f.(type) {
	case VqlLLMStart:
		env.Body = &framespb.Envelope_VqlLlmStart{VqlLlmStart: &framespb.VqlLLMFullResponseStart{InteractionId: v.InteractionID, InferenceId: v.InferenceID}}
	case VqlLLMText:
		env.Body = &framespb.Envelope_VqlLlmText{VqlLlmText: &framespb.VqlLLMText{InteractionId: v.InteractionID, InferenceId: v.InferenceID, Text: v.Text}}
	case VqlLLMEnd:
		env.Body = &framespb.Envelope_VqlLlmEnd{VqlLlmEnd: &framespb.VqlLLMFullResponseEnd{InteractionId: v.InteractionID, InferenceId: v.InferenceID}}
	case RTVIServerMessage:
		data, err := json.Marshal(v.Data)
		if err != nil {
			return nil, fmt.Errorf("wire: rtvi_server_message marshal: %w", err)
		}
		env.Body = &framespb.Envelope_RtviServerMessage{RtviServerMessage: &framespb.RTVIServerMessage{Data: string(data)}}
	case InteractionCompleted:
		env.Body = &framespb.Envelope_VqlInteractionCompleted{VqlInteractionCompleted: &framespb.VqlInteractionCompleted{InteractionId: v.InteractionID}}
	case TTSUpdateSettings:
		data, err := json.Marshal(orEmpty(v.Settings))
		if err != nil {
			return nil, fmt.Errorf("wire: tts_update_settings marshal: %w", err)
		}
		env.Body = &framespb.Envelope_TtsUpdateSettings{TtsUpdateSettings: &framespb.TTSUpdateSettings{Settings: string(data)}}
	case STTUpdateSettings:
		data, err := json.Marshal(orEmpty(v.Settings))
		if err != nil {
			return nil, fmt.Errorf("wire: stt_update_settings marshal: %w", err)
		}
		env.Body = &framespb.Envelope_SttUpdateSettings{SttUpdateSettings: &framespb.STTUpdateSettings{Settings: string(data)}}
	case Interruption:
		env.Body = &framespb.Envelope_VqlInterruption{VqlInterruption: &framespb.VqlInterruption{}}
	case Error:
		env.Body = &framespb.Envelope_Error{Error: &framespb.Error{Error: v.Error, Fatal: v.Fatal}}
	case End:
		env.Body = &framespb.Envelope_End{End: &framespb.End{}}
	// Inbound frames (pygato → agent) — encoded so a fake peer / test can send them.
	case VqlStart:
		payload, err := json.Marshal(orEmpty(v.Payload))
		if err != nil {
			return nil, fmt.Errorf("wire: vql_start marshal: %w", err)
		}
		env.Body = &framespb.Envelope_VqlStart{VqlStart: &framespb.VqlStart{SessionId: v.SessionID, AgentId: v.AgentID, Payload: string(payload)}}
	case VqlUserText:
		env.Body = &framespb.Envelope_VqlUserText{VqlUserText: &framespb.VqlUserText{InteractionId: v.InteractionID, Text: v.Text}}
	case VqlInferenceFinalized:
		env.Body = &framespb.Envelope_VqlInferenceFinalized{VqlInferenceFinalized: &framespb.VqlInferenceFinalized{
			InteractionId: v.InteractionID, InferenceId: v.InferenceID, HeardText: v.HeardText, Interrupted: v.Interrupted, Reason: v.Reason,
		}}
	case RTVIClientMessage:
		data, err := json.Marshal(orEmpty(v.Data))
		if err != nil {
			return nil, fmt.Errorf("wire: rtvi_client_message marshal: %w", err)
		}
		env.Body = &framespb.Envelope_RtviClientMessage{RtviClientMessage: &framespb.RTVIClientMessage{MsgId: v.MsgID, Type: v.Type, Data: string(data)}}
	case Cancel:
		env.Body = &framespb.Envelope_Cancel{Cancel: &framespb.Cancel{Reason: v.Reason}}
	default:
		return nil, fmt.Errorf("wire: no encoder for frame type %T", f)
	}
	if requestID != 0 {
		env.RequestId = requestID
	}
	return proto.Marshal(env)
}

func orEmpty(m map[string]any) map[string]any {
	if m == nil {
		return map[string]any{}
	}
	return m
}

// EncodeAck marshals a wire-level Ack envelope.
func EncodeAck(ackID uint64) ([]byte, error) {
	env := &framespb.Envelope{Body: &framespb.Envelope_Ack{Ack: &framespb.Ack{AckId: ackID}}}
	return proto.Marshal(env)
}

func decodeJSONObject(s string) (map[string]any, error) {
	if s == "" {
		return map[string]any{}, nil
	}
	var m map[string]any
	if err := json.Unmarshal([]byte(s), &m); err != nil {
		return nil, err
	}
	return m, nil
}
