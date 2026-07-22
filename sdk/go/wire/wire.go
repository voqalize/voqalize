package wire

import (
	"context"
	"errors"
	"fmt"
	"math/rand"
	"net/http"
	"sync"
	"time"

	"github.com/coder/websocket"
	"github.com/google/uuid"
)

// Close codes (mirror cortex/internal/protocol).
const (
	CloseNoAgent   = 4000 // permanent: no agent for this pool
	CloseAgentGone = 4001 // transient: pinned agent dropped
)

// SessionIDLen is the raw session-id prefix length on the /agent leg.
const SessionIDLen = 16

// maxReadBytes caps a single inbound message (tool args / state_sync can be big).
const maxReadBytes = 16 << 20

// SessionID is the raw 16-byte session id used as the multiplex prefix.
type SessionID [SessionIDLen]byte

// String renders the id as a hyphenated UUID for logs.
func (s SessionID) String() string {
	u, err := uuid.FromBytes(s[:])
	if err != nil {
		return fmt.Sprintf("%x", s[:])
	}
	return u.String()
}

// ErrPermanent is returned once the wire hits a non-retriable close (4000).
var ErrPermanent = errors.New("wire: cortex permanently closed")

// ErrClosed is returned after Close.
var ErrClosed = errors.New("wire: closed by caller")

// Config configures the multiplexed wire.
type Config struct {
	URL    string
	Header http.Header // static headers (e.g. X-Agent-Version)
	// HeaderProvider returns per-attempt headers merged over Header (token rotation).
	HeaderProvider func() http.Header

	InitialBackoff time.Duration
	MaxBackoff     time.Duration
	Multiplier     float64
	Jitter         float64 // ± fraction
	ConnectTimeout time.Duration
}

func (c *Config) defaults() {
	if c.InitialBackoff == 0 {
		c.InitialBackoff = 100 * time.Millisecond
	}
	if c.MaxBackoff == 0 {
		c.MaxBackoff = 60 * time.Second
	}
	if c.Multiplier == 0 {
		c.Multiplier = 2.0
	}
	if c.Jitter == 0 {
		c.Jitter = 0.1
	}
	if c.ConnectTimeout == 0 {
		c.ConnectTimeout = 10 * time.Second
	}
}

// MultiplexedWire is the agent leg of the cortex wire: one outbound WebSocket,
// many sessions multiplexed by a 16-byte prefix. Message layout:
//
//	[16-byte session_id][1-byte direction][protobuf Envelope]
//
// Reconnect/backoff is owned by a single manager goroutine; Recv and Send use
// whatever connection it currently holds.
type MultiplexedWire struct {
	cfg         Config
	onReconnect func(context.Context) error
	log         Logger

	mu        sync.Mutex
	conn      *websocket.Conn
	ready     chan struct{} // closed when conn is live; replaced on disconnect
	permanent bool
	closedBy  bool

	disconnectCh chan struct{}
	done         chan struct{} // closed when the manager exits (permanent/closed)
	managerOnce  sync.Once
}

// Logger is a minimal logging hook (so the wire doesn't pin a logging library).
type Logger interface {
	Infof(format string, args ...any)
	Warnf(format string, args ...any)
}

// NewMultiplexedWire builds a wire. onReconnect (optional) fires after every
// successful *reconnect* (not the first connect) so the caller can replay state.
func NewMultiplexedWire(cfg Config, onReconnect func(context.Context) error, log Logger) *MultiplexedWire {
	cfg.defaults()
	return &MultiplexedWire{
		cfg:          cfg,
		onReconnect:  onReconnect,
		log:          log,
		ready:        make(chan struct{}),
		disconnectCh: make(chan struct{}, 1),
		done:         make(chan struct{}),
	}
}

// Start establishes the first connection and launches the reconnect manager.
// It blocks until the first connection succeeds or the context is cancelled.
func (w *MultiplexedWire) Start(ctx context.Context) error {
	conn, err := w.dial(ctx)
	if err != nil {
		return err
	}
	w.setConn(conn)
	w.managerOnce.Do(func() { go w.manage(ctx) })
	return nil
}

// Recv reads one message, transparently reconnecting on transient closes.
func (w *MultiplexedWire) Recv(ctx context.Context) (SessionID, Direction, []byte, error) {
	for {
		conn, ready, perm, closed := w.snapshot()
		if perm {
			return SessionID{}, 0, nil, ErrPermanent
		}
		if closed {
			return SessionID{}, 0, nil, ErrClosed
		}
		if conn == nil {
			select {
			case <-ready:
			case <-ctx.Done():
				return SessionID{}, 0, nil, ctx.Err()
			case <-w.done:
			}
			continue
		}
		_, data, err := conn.Read(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return SessionID{}, 0, nil, ctx.Err()
			}
			w.signalDisconnect(conn)
			continue
		}
		if len(data) < SessionIDLen+1 {
			w.log.Warnf("wire: short message (%d bytes); skipping", len(data))
			continue
		}
		var sid SessionID
		copy(sid[:], data[:SessionIDLen])
		dir := Direction(data[SessionIDLen])
		payload := data[SessionIDLen+1:]
		return sid, dir, payload, nil
	}
}

// Send writes one message, waiting for a live connection.
func (w *MultiplexedWire) Send(ctx context.Context, sid SessionID, dir Direction, payload []byte) error {
	msg := make([]byte, 0, SessionIDLen+1+len(payload))
	msg = append(msg, sid[:]...)
	msg = append(msg, byte(dir))
	msg = append(msg, payload...)
	for {
		conn, ready, perm, closed := w.snapshot()
		if perm {
			return ErrPermanent
		}
		if closed {
			return ErrClosed
		}
		if conn == nil {
			select {
			case <-ready:
			case <-ctx.Done():
				return ctx.Err()
			case <-w.done:
			}
			continue
		}
		if err := conn.Write(ctx, websocket.MessageBinary, msg); err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			w.signalDisconnect(conn)
			continue
		}
		return nil
	}
}

// Close closes the wire; no further reconnects. It wakes the reconnect manager
// so it exits promptly (see Done).
func (w *MultiplexedWire) Close(code websocket.StatusCode, reason string) {
	w.mu.Lock()
	w.closedBy = true
	conn := w.conn
	w.conn = nil
	w.mu.Unlock()
	if conn != nil {
		_ = conn.Close(code, reason)
	}
	w.signalSelf() // wake manage so it observes closedBy and returns
}

// Done is closed when the reconnect manager has exited (permanent close, user
// Close, or ctx cancel). Callers wait on it to ensure no wire goroutine leaks.
func (w *MultiplexedWire) Done() <-chan struct{} { return w.done }

// ─── internals ────────────────────────────────────────────────────────────────

func (w *MultiplexedWire) snapshot() (*websocket.Conn, chan struct{}, bool, bool) {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.conn, w.ready, w.permanent, w.closedBy
}

func (w *MultiplexedWire) setConn(conn *websocket.Conn) {
	conn.SetReadLimit(maxReadBytes)
	w.mu.Lock()
	w.conn = conn
	close(w.ready) // wake everyone waiting for a connection
	w.ready = make(chan struct{})
	w.mu.Unlock()
}

// signalDisconnect notifies the manager that the given (failed) conn is dead.
func (w *MultiplexedWire) signalDisconnect(failed *websocket.Conn) {
	w.mu.Lock()
	if w.conn == failed {
		w.conn = nil // future Recv/Send will wait on ready
	}
	w.mu.Unlock()
	select {
	case w.disconnectCh <- struct{}{}:
	default:
	}
}

// manage owns reconnection. It waits for a disconnect signal, then reconnects
// with backoff (or marks permanent on 4000 / stops on user close).
func (w *MultiplexedWire) manage(ctx context.Context) {
	defer close(w.done)
	for {
		select {
		case <-ctx.Done():
			return
		case <-w.disconnectCh:
		}
		w.mu.Lock()
		closed := w.closedBy
		w.mu.Unlock()
		if closed {
			return
		}
		conn, err := w.dial(ctx)
		if err != nil {
			if errors.Is(err, ErrPermanent) {
				w.mu.Lock()
				w.permanent = true
				prev := w.ready
				w.mu.Unlock()
				close(prev) // wake waiters so they observe permanent
				return
			}
			if ctx.Err() != nil {
				return
			}
			// dial already retried to the backoff cap; loop and try again.
			w.signalSelf()
			continue
		}
		w.setConn(conn)
		// drain any stale disconnect signals from the old connection.
		select {
		case <-w.disconnectCh:
		default:
		}
		if w.onReconnect != nil {
			if err := w.onReconnect(ctx); err != nil {
				w.log.Warnf("wire: onReconnect failed: %v", err)
			}
		}
	}
}

func (w *MultiplexedWire) signalSelf() {
	select {
	case w.disconnectCh <- struct{}{}:
	default:
	}
}

// dial connects with exponential backoff + jitter. Returns ErrPermanent on a
// 4000 close, ctx error on cancellation; otherwise keeps retrying to the cap and
// only returns a non-permanent error if the context is cancelled.
func (w *MultiplexedWire) dial(ctx context.Context) (*websocket.Conn, error) {
	delay := w.cfg.InitialBackoff
	attempt := 0
	for {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		w.mu.Lock()
		closed := w.closedBy
		w.mu.Unlock()
		if closed {
			return nil, ErrClosed
		}
		attempt++
		hdr := http.Header{}
		for k, v := range w.cfg.Header {
			hdr[k] = v
		}
		if w.cfg.HeaderProvider != nil {
			for k, v := range w.cfg.HeaderProvider() {
				hdr[k] = v
			}
		}
		dialCtx, cancel := context.WithTimeout(ctx, w.cfg.ConnectTimeout)
		conn, _, err := websocket.Dial(dialCtx, w.cfg.URL, &websocket.DialOptions{HTTPHeader: hdr})
		cancel()
		if err == nil {
			w.log.Infof("wire: connected to %s (attempt %d)", w.cfg.URL, attempt)
			return conn, nil
		}
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		if websocket.CloseStatus(err) == CloseNoAgent {
			return nil, ErrPermanent
		}
		w.log.Warnf("wire: connect attempt %d failed (%v); retrying in %s", attempt, err, delay)
		select {
		case <-time.After(w.jitter(delay)):
		case <-ctx.Done():
			return nil, ctx.Err()
		}
		delay = time.Duration(float64(delay) * w.cfg.Multiplier)
		if delay > w.cfg.MaxBackoff {
			delay = w.cfg.MaxBackoff
		}
	}
}

func (w *MultiplexedWire) jitter(d time.Duration) time.Duration {
	if w.cfg.Jitter <= 0 {
		return d
	}
	f := 1.0 + (rand.Float64()*2-1)*w.cfg.Jitter
	return time.Duration(float64(d) * f)
}
