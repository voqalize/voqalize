package wire

import (
	"reflect"
	"testing"
)

// TestSTTUpdateSettingsRoundTrip and TestTTSUpdateSettingsRoundTrip exercise
// Encode -> Decode for the two mid-call configure frames. Fixtures use
// float64 (not int) values because JSON round-trips numbers as float64 — an
// int fixture would false-fail the equality check after Decode.

func TestSTTUpdateSettingsRoundTrip(t *testing.T) {
	f := STTUpdateSettings{Settings: map[string]any{
		"vad_confidence":  0.7,
		"vad_barge_in_ms": float64(300),
	}}

	data, err := Encode(f)
	if err != nil {
		t.Fatalf("Encode: %v", err)
	}
	decoded, err := Decode(data)
	if err != nil {
		t.Fatalf("Decode: %v", err)
	}
	got, ok := decoded.Frame.(STTUpdateSettings)
	if !ok {
		t.Fatalf("decoded frame is %T, want STTUpdateSettings", decoded.Frame)
	}
	if !reflect.DeepEqual(got.Settings, f.Settings) {
		t.Fatalf("Settings = %#v, want %#v", got.Settings, f.Settings)
	}
}

func TestTTSUpdateSettingsRoundTrip(t *testing.T) {
	f := TTSUpdateSettings{Settings: map[string]any{
		"voice":    "gaurav",
		"language": "hi",
		"model":    "omnivoice",
	}}

	data, err := Encode(f)
	if err != nil {
		t.Fatalf("Encode: %v", err)
	}
	decoded, err := Decode(data)
	if err != nil {
		t.Fatalf("Decode: %v", err)
	}
	got, ok := decoded.Frame.(TTSUpdateSettings)
	if !ok {
		t.Fatalf("decoded frame is %T, want TTSUpdateSettings", decoded.Frame)
	}
	if !reflect.DeepEqual(got.Settings, f.Settings) {
		t.Fatalf("Settings = %#v, want %#v", got.Settings, f.Settings)
	}
}
