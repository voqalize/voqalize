// Package tests hosts the live-Gemini example tests for the travel brain. The
// travel example pulls the heavy google.golang.org/genai tree, so these tests
// live in the separate examples module rather than the lean core module.
//
// This file is a minimal copy of the core SDK's fake-cortex harness (see
// sdk/go/tests/integration_test.go) — just the pieces the live travel tests
// need to drive a Brain against a fake cortex over a real WebSocket.
package tests

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/voqalize/voqalize/sdk/go/brain"
	"github.com/voqalize/voqalize/sdk/go/cortex"
	"github.com/voqalize/voqalize/sdk/go/wire"
)

var sid = wire.SessionID{0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x01}

// peer wraps the cortex-side connection with a read-pump.
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
