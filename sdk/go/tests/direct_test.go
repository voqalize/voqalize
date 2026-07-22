// Direct-mode end-to-end tests: PyGato dials the brain server straight (no
// Cortex relay), one WebSocket per session, bare [direction][payload] framing.
// Drives the real DirectServer + the shared per-session runner + brain adapter
// over a real WebSocket, mirroring the multiplexed integration_test.go but with
// the inbound-server transport.
package tests

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/coder/websocket"
	"github.com/golang-jwt/jwt/v5"

	"github.com/voqalize/voqalize/sdk/go/brain"
	"github.com/voqalize/voqalize/sdk/go/cortex"
	"github.com/voqalize/voqalize/sdk/go/wire"
)

// directPeer is the PyGato side: one socket per session, bare framing (no
// 16-byte prefix — session is in the URL).
type directPeer struct {
	conn   *websocket.Conn
	frames chan wire.Decoded
}

func (p *directPeer) pump() {
	for {
		_, data, err := p.conn.Read(context.Background())
		if err != nil {
			close(p.frames)
			return
		}
		if len(data) < 1 {
			continue
		}
		dec, err := wire.Decode(data[1:]) // strip the 1-byte direction
		if err != nil {
			continue
		}
		p.frames <- dec
	}
}

func (p *directPeer) send(t *testing.T, f wire.Frame, reqID uint64) {
	t.Helper()
	payload, err := wire.EncodeWithRequest(f, reqID)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	msg := append([]byte{byte(wire.Downstream)}, payload...)
	if err := p.conn.Write(context.Background(), websocket.MessageBinary, msg); err != nil {
		t.Fatalf("write: %v", err)
	}
}

func (p *directPeer) recv(d time.Duration) (wire.Decoded, bool) {
	select {
	case dec, ok := <-p.frames:
		return dec, ok
	case <-time.After(d):
		return wire.Decoded{}, false
	}
}

func (p *directPeer) collect(d time.Duration) []wire.Decoded {
	var out []wire.Decoded
	for {
		dec, ok := p.recv(d)
		if !ok {
			return out
		}
		out = append(out, dec)
	}
}

// serveDirect starts a DirectServer on an httptest server and dials one session.
func serveDirect(
	t *testing.T,
	newBrain func() brain.Brain,
	opts cortex.DirectOptions,
	sessionID string,
	header http.Header,
) (*directPeer, func(), error) {
	t.Helper()
	log := testLogger{t}
	if opts.Logger == nil {
		opts.Logger = log
	}
	server, err := cortex.NewDirectServer(brain.Factory(newBrain, log), opts)
	if err != nil {
		t.Fatalf("NewDirectServer: %v", err)
	}
	hs := httptest.NewServer(server)
	url := "ws" + strings.TrimPrefix(hs.URL, "http") + "/s/" + sessionID
	conn, _, derr := websocket.Dial(context.Background(), url, &websocket.DialOptions{HTTPHeader: header})
	if derr != nil {
		hs.Close()
		return nil, func() {}, derr
	}
	conn.SetReadLimit(16 << 20)
	p := &directPeer{conn: conn, frames: make(chan wire.Decoded, 256)}
	go p.pump()
	cleanup := func() {
		_ = conn.Close(websocket.StatusNormalClosure, "done")
		hs.Close()
	}
	return p, cleanup, nil
}

func TestDirectGreetingSingleTurnAndAck(t *testing.T) {
	g := &greeterBrain{}
	p, cleanup, err := serveDirect(t, func() brain.Brain { return g }, cortex.DirectOptions{AllowUnverified: true}, sid.String(), nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer cleanup()

	// Session start → greeting (interaction_id 0), no Cortex in the path.
	p.send(t, wire.VqlStart{SessionID: sid.String(), AgentID: "direct-agent", Payload: map[string]any{}}, 0)
	greet := p.collect(800 * time.Millisecond)
	if got := texts(greet); len(got) != 1 || got[0] != "hello there friend" {
		t.Fatalf("greeting texts = %v", got)
	}

	// A user turn with request_id → ack + response, ack-gated after dispatch.
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
	if !hasUICommand(turn, "open_dashboard") {
		t.Errorf("no open_dashboard ui_command; frames=%+v", turn)
	}
}

func TestDirectInterruptionEchoesBarrier(t *testing.T) {
	b := &talkerBrain{}
	p, cleanup, err := serveDirect(t, func() brain.Brain { return b }, cortex.DirectOptions{AllowUnverified: true}, sid.String(), nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer cleanup()

	p.send(t, wire.VqlStart{SessionID: sid.String(), AgentID: "direct-agent", Payload: map[string]any{}}, 0)
	p.send(t, wire.VqlUserText{InteractionID: 1, Text: "talk"}, 1)
	time.Sleep(120 * time.Millisecond) // let a couple chunks flow
	p.send(t, wire.Interruption{}, 0)

	// The brain echoes an Interruption back — PyGato's drain barrier.
	frames := p.collect(800 * time.Millisecond)
	sawInterruptEcho := false
	for _, d := range frames {
		if _, ok := d.Frame.(wire.Interruption); ok {
			sawInterruptEcho = true
		}
	}
	if !sawInterruptEcho {
		t.Errorf("no interruption echo (drain barrier); frames=%+v", frames)
	}
	b.mu.Lock()
	spoken := b.spoken
	b.mu.Unlock()
	if spoken >= 10 {
		t.Errorf("talker was not cut off by barge-in: spoke %d/10", spoken)
	}
}

func TestDirectAuthAcceptsValidRejectsForged(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	pubPEM := publicKeyPEM(t, &key.PublicKey)

	mint := func(signing *rsa.PrivateKey, sessionID string) string {
		tok := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{
			"iss":       "pygato",
			"aud":       "direct-agent",
			"sub":       sessionID,
			"kind":      "voqal-voice",
			"agent_id":  "direct-agent",
			"tenant_id": "t1",
			"iat":       time.Now().Unix(),
			"exp":       time.Now().Add(5 * time.Minute).Unix(),
		})
		s, e := tok.SignedString(signing)
		if e != nil {
			t.Fatal(e)
		}
		return s
	}

	opts := cortex.DirectOptions{PublicKeysPEM: pubPEM, Audience: "direct-agent"}
	g := &greeterBrain{}

	// Valid token → connects and greets.
	good := jwtHeader(mint(key, sid.String()))
	p, cleanup, err := serveDirect(t, func() brain.Brain { return g }, opts, sid.String(), good)
	if err != nil {
		t.Fatalf("valid token was rejected: %v", err)
	}
	p.send(t, wire.VqlStart{SessionID: sid.String(), AgentID: "direct-agent", Payload: map[string]any{}}, 0)
	if got := texts(p.collect(800 * time.Millisecond)); len(got) == 0 {
		t.Fatalf("valid connection produced no greeting")
	}
	cleanup()

	// Forged token (different signing key) → handshake rejected (401).
	other, _ := rsa.GenerateKey(rand.Reader, 2048)
	bad := jwtHeader(mint(other, sid.String()))
	_, cleanup2, err := serveDirect(t, func() brain.Brain { return &greeterBrain{} }, opts, sid.String(), bad)
	defer cleanup2()
	if err == nil {
		t.Fatalf("forged token was accepted; expected a rejected handshake")
	}
}

// TestDirectDefaultVerifiesWithEmbeddedKeys proves the zero-config posture: with
// no PublicKeysPEM and no AllowUnverified, NewDirectServer uses the embedded
// Voqalize platform keys, so a peer presenting no (or a non-Voqalize) token is
// rejected — verification is on by default, not opt-in.
func TestDirectDefaultVerifiesWithEmbeddedKeys(t *testing.T) {
	// Empty opts ⇒ embedded keys. Construction must succeed (keys are present).
	if _, err := cortex.NewDirectServer(
		brain.Factory(func() brain.Brain { return &greeterBrain{} }, testLogger{t}),
		cortex.DirectOptions{},
	); err != nil {
		t.Fatalf("default construction should succeed with embedded keys: %v", err)
	}

	// A peer with no Authorization header is rejected by the embedded-key default.
	_, cleanup, err := serveDirect(
		t, func() brain.Brain { return &greeterBrain{} }, cortex.DirectOptions{}, sid.String(), nil,
	)
	defer cleanup()
	if err == nil {
		t.Fatalf("unauthenticated peer was accepted; embedded-key verification should reject it")
	}
}

func jwtHeader(tok string) http.Header {
	return http.Header{"Authorization": {"Bearer " + tok}}
}

func publicKeyPEM(t *testing.T, pub *rsa.PublicKey) string {
	t.Helper()
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
}
