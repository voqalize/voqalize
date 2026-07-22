package cortex

import (
	"context"
	"crypto/rsa"
	"errors"
	"net/http"
	"strings"
	"sync"

	"github.com/coder/websocket"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/voqalize/voqalize/sdk/go/wire"
)

// DirectServer is the inbound counterpart to Agent: instead of one outbound
// multiplexed socket carrying many sessions, it accepts one inbound WebSocket
// per session (PyGato dials {brain_url}/s/{session_id} directly — no Cortex
// relay). Each connection runs exactly one sessionRunner over the SAME
// per-session engine the multiplexed Agent uses; the only difference is the
// transport (bare [1-byte direction][protobuf], session in the URL) and a
// dedicated per-connection writer (no cross-session fairness needed).
//
// This is the primary "bring your own brain" path in Go. Mount ServeHTTP on any
// route ending in /s/{session_id}, or call ListenAndServe for a standalone
// server.
type DirectServer struct {
	factory   SessionFactory
	log       wire.Logger
	normalMax int

	// publicKeys verifies PyGato's RS256 bearer token — the customer's keys if
	// they passed any, else Voqalize's embedded platform keys (the default).
	publicKeys      []*rsa.PublicKey
	audience        string
	allowUnverified bool
}

// DirectOptions configures a DirectServer.
type DirectOptions struct {
	NormalMax int // per-session normal-lane bound (default 256)
	Logger    wire.Logger
	// PublicKeysPEM overrides the embedded Voqalize platform keys with your own
	// (a self-hosted deployment, or to pre-stage a rotation). One or more
	// concatenated RSA public-key PEM blocks. Empty ⇒ use the embedded keys.
	PublicKeysPEM string
	// Audience, when set, is required to match the token's aud claim.
	Audience string
	// AllowUnverified accepts connections WITHOUT verifying the token. Local dev
	// only; never in production. Logged loudly.
	AllowUnverified bool
}

// NewDirectServer builds a server. The factory runs once per connection/session.
//
// Verification is on by default: with neither PublicKeysPEM nor AllowUnverified
// set, the embedded Voqalize platform keys (platform_keys.go) are used, so a
// customer needs no key configuration. Returns an error if verification is on
// but no keys are available.
func NewDirectServer(factory SessionFactory, opts DirectOptions) (*DirectServer, error) {
	if opts.Logger == nil {
		opts.Logger = noopLogger{}
	}
	nm := opts.NormalMax
	if nm <= 0 {
		nm = defaultNormalMax
	}
	pem := opts.PublicKeysPEM
	if strings.TrimSpace(pem) == "" {
		pem = platformPublicKeysPEM // embedded Voqalize keys (zero-config default)
	}
	keys, err := parsePublicKeys(pem)
	if err != nil {
		return nil, err
	}
	if opts.AllowUnverified {
		opts.Logger.Warnf("direct: AllowUnverified=true — brain connections are " +
			"NOT authenticated. Local dev only; never run this in production.")
	} else if len(keys) == 0 {
		return nil, errors.New("direct: no verification keys available (embedded " +
			"platform keys empty and PublicKeysPEM not set); set PublicKeysPEM, or " +
			"AllowUnverified for local dev")
	}
	return &DirectServer{
		factory:         factory,
		log:             opts.Logger,
		normalMax:       nm,
		publicKeys:      keys,
		audience:        opts.Audience,
		allowUnverified: opts.AllowUnverified,
	}, nil
}

// ListenAndServe starts an HTTP server on addr serving /s/{session_id}. Blocks
// until ctx is cancelled or the server errors.
func (s *DirectServer) ListenAndServe(ctx context.Context, addr string) error {
	srv := &http.Server{Addr: addr, Handler: s}
	go func() {
		<-ctx.Done()
		_ = srv.Close()
	}()
	err := srv.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}

// ServeHTTP upgrades an inbound request to a WebSocket and runs one session.
// The path must end in /s/{session_id}.
func (s *DirectServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	sessionID := sessionIDFromPath(r.URL.Path)
	if sessionID == "" {
		http.Error(w, "expected /s/{session_id}", http.StatusBadRequest)
		return
	}
	if !s.authorize(r, sessionID) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		s.log.Warnf("direct: rejected session %s (auth)", sessionID)
		return
	}
	conn, err := websocket.Accept(w, r, nil)
	if err != nil {
		s.log.Warnf("direct: accept failed: %v", err)
		return
	}
	conn.SetReadLimit(maxDirectRead)

	dc := newDirectConn(s, conn, sessionID)
	dc.run(r.Context())
}

func (s *DirectServer) authorize(r *http.Request, sessionID string) bool {
	if s.allowUnverified {
		return true
	}
	tok := bearer(r)
	if tok == "" {
		return false
	}
	for _, pk := range s.publicKeys {
		claims := jwt.MapClaims{}
		parsed, err := jwt.ParseWithClaims(tok, claims, func(*jwt.Token) (any, error) {
			return pk, nil
		}, jwt.WithValidMethods([]string{"RS256"}))
		if err != nil || !parsed.Valid {
			continue
		}
		if sub, _ := claims["sub"].(string); sub != sessionID {
			s.log.Warnf("direct: token sub != session id for %s", sessionID)
			return false
		}
		if s.audience != "" {
			if aud, _ := claims["aud"].(string); aud != s.audience {
				return false
			}
		}
		return true
	}
	return false
}

// runnerHost impl.
func (s *DirectServer) sessionFactory() SessionFactory { return s.factory }
func (s *DirectServer) laneMax() int                   { return s.normalMax }
func (s *DirectServer) logger() wire.Logger            { return s.log }

const maxDirectRead = 16 << 20

// ─── directConn: one socket, one session ─────────────────────────────────────

// directConn drives a single inbound connection. It implements runnerHost so it
// can own the sessionRunner directly; signalReady pokes a dedicated writer (one
// session ⇒ no ready queue), and closeSession ends the connection.
type directConn struct {
	server *DirectServer
	conn   *websocket.Conn
	sidStr string
	sid    wire.SessionID
	log    wire.Logger

	runner   *sessionRunner
	ready    chan struct{} // buffered(1): outbound work pending
	done     chan struct{} // closed when the session ends / socket drops
	doneOnce sync.Once
}

func newDirectConn(s *DirectServer, conn *websocket.Conn, sessionID string) *directConn {
	return &directConn{
		server: s,
		conn:   conn,
		sidStr: sessionID,
		sid:    sessionIDBytes(sessionID),
		log:    s.log,
		ready:  make(chan struct{}, 1),
		done:   make(chan struct{}),
	}
}

func (c *directConn) run(ctx context.Context) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	c.runner = newSessionRunner(ctx, c.sid, c)
	c.runner.start()
	c.log.Infof("direct: opened session %s", c.sidStr)

	writerDone := make(chan struct{})
	go func() { defer close(writerDone); c.writer(ctx) }()

	// Reader loop: socket → decode → per-session lanes.
	for {
		_, data, err := c.conn.Read(ctx)
		if err != nil {
			break
		}
		if len(data) < 1 {
			c.log.Warnf("direct: empty message on session %s", c.sidStr)
			continue
		}
		// data[0] is the direction byte (from PyGato); the payload is the rest.
		dec, derr := wire.Decode(data[1:])
		if derr != nil {
			c.log.Warnf("direct: decode failed on session %s: %v", c.sidStr, derr)
			continue
		}
		if dec.IsAck {
			// PyGato sends request_id-tagged frames and the SDK acks them; a
			// PyGato→SDK ack is unexpected. Ignore.
			continue
		}
		c.runner.enqueueInbound(inboundItem{frame: dec.Frame, requestID: dec.RequestID})
	}

	c.finish()
	cancel()
	<-writerDone
	c.runner.teardown()
	_ = c.conn.Close(websocket.StatusNormalClosure, "session ended")
	c.log.Infof("direct: closed session %s", c.sidStr)
}

// writer drains this session's outbound lanes and writes bare framing.
func (c *directConn) writer(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		case <-c.done:
			return
		case <-c.ready:
		}
		// Drain everything currently queued, then wait for the next signal.
		for {
			it, ok := c.runner.out.pop()
			if !ok {
				break
			}
			var payload []byte
			var err error
			if it.isAck {
				payload, err = wire.EncodeAck(it.ackID)
			} else {
				payload, err = wire.Encode(it.frame)
			}
			if err != nil {
				c.log.Warnf("direct: encode failed (%T) on session %s: %v", it.frame, c.sidStr, err)
				continue
			}
			// Bare framing: [1-byte direction][payload]. Everything the SDK sends
			// is DOWNSTREAM (1); pygato flips ui_command to UPSTREAM on its read.
			msg := append([]byte{byte(wire.Downstream)}, payload...)
			if werr := c.conn.Write(ctx, websocket.MessageBinary, msg); werr != nil {
				c.finish()
				return
			}
		}
	}
}

func (c *directConn) finish() { c.doneOnce.Do(func() { close(c.done) }) }

// runnerHost impl — see session.go.
func (c *directConn) sessionFactory() SessionFactory { return c.server.factory }
func (c *directConn) laneMax() int                   { return c.server.normalMax }
func (c *directConn) logger() wire.Logger            { return c.server.log }

func (c *directConn) signalReady(_ wire.SessionID) {
	select {
	case c.ready <- struct{}{}:
	default:
	}
}

func (c *directConn) closeSession(_ wire.SessionID) { c.finish() }

// ─── helpers ─────────────────────────────────────────────────────────────────

func sessionIDFromPath(path string) string {
	const prefix = "/s/"
	idx := strings.LastIndex(path, prefix)
	if idx < 0 {
		return ""
	}
	return strings.Trim(path[idx+len(prefix):], "/")
}

// sessionIDBytes maps a session-id string to the 16-byte wire id. A real PyGato
// session id is a UUID; anything else is hashed deterministically.
func sessionIDBytes(sessionID string) wire.SessionID {
	var sid wire.SessionID
	if u, err := uuid.Parse(sessionID); err == nil {
		copy(sid[:], u[:])
		return sid
	}
	u := uuid.NewSHA1(uuid.Nil, []byte(sessionID))
	copy(sid[:], u[:])
	return sid
}

func bearer(r *http.Request) string {
	raw := r.Header.Get("Authorization")
	if raw == "" || !strings.HasPrefix(strings.ToLower(raw), "bearer ") {
		return ""
	}
	return strings.TrimSpace(raw[len("Bearer "):])
}

func parsePublicKeys(pem string) ([]*rsa.PublicKey, error) {
	pem = strings.TrimSpace(pem)
	if pem == "" {
		return nil, nil
	}
	// Split concatenated PEM blocks on the END marker so rotation bundles work.
	var keys []*rsa.PublicKey
	blocks := strings.SplitAfter(pem, "-----END PUBLIC KEY-----")
	for _, b := range blocks {
		b = strings.TrimSpace(b)
		if b == "" {
			continue
		}
		pk, err := jwt.ParseRSAPublicKeyFromPEM([]byte(b))
		if err != nil {
			return nil, err
		}
		keys = append(keys, pk)
	}
	return keys, nil
}
