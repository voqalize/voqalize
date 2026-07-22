package cortex

import (
	"context"
	"sync"

	"github.com/voqalize/voqalize/sdk/go/wire"
)

// Emitter is how a Session pushes frames back toward cortex. Non-blocking:
// frames are enqueued onto the session's outbound lanes and drained by the
// agent's shared writer.
type Emitter interface {
	Send(f wire.Frame)
}

// Session is the per-session consumer the runtime drives. The brain adapter
// implements it. HandleFrame is called sequentially by one feeder goroutine
// (system lane before normal lane), so it must not block on long work — spawn
// a goroutine for anything slow (the adapter does this for on_interaction).
type Session interface {
	HandleFrame(f wire.Frame)
	// DeliverError surfaces a non-fatal congestion ErrorFrame (drop-newest).
	DeliverError(direction wire.Direction, message string)
	// Close tears the session down (cancel in-flight work, OnSessionEnd).
	Close()
}

// SessionFactory builds the per-session consumer. ctx is cancelled on teardown
// (End / reconnect / shutdown); the consumer should tie its goroutines to it.
type SessionFactory func(ctx context.Context, sid wire.SessionID, emit Emitter) Session

// runnerHost is the small surface a sessionRunner needs from whatever owns it:
// the multiplexed Agent (many sessions, shared writer + ready queue) or the
// direct per-connection server (one session, dedicated writer). Extracting it
// keeps the entire per-session engine — lanes, feeder, ack-gating, interruption
// — shared across both transports; only the four methods below differ.
type runnerHost interface {
	sessionFactory() SessionFactory
	laneMax() int
	logger() wire.Logger
	// signalReady is called when a session's outbound lanes go empty→non-empty.
	signalReady(sid wire.SessionID)
	// closeSession is called when the session ends (End frame drained).
	closeSession(sid wire.SessionID)
}

const defaultNormalMax = 256
const systemTripwire = 64

type inboundItem struct {
	frame     wire.Frame
	requestID uint64
}

type outItem struct {
	frame wire.Frame
	ackID uint64
	isAck bool
}

// outboundLanes is the per-session send buffer (system priority + normal FIFO),
// drained by the agent's shared writer. Mutex-guarded: many producer goroutines
// (the adapter) and one writer.
type outboundLanes struct {
	mu        sync.Mutex
	system    []outItem
	normal    []outItem
	normalMax int
}

func (o *outboundLanes) empty() bool {
	o.mu.Lock()
	defer o.mu.Unlock()
	return len(o.system) == 0 && len(o.normal) == 0
}

// push enqueues an item. neverDrop items (acks) bypass the normal bound.
// Returns (accepted, wasEmpty). accepted=false means a drop-newest occurred.
func (o *outboundLanes) push(it outItem, isSystem, neverDrop bool) (bool, bool) {
	o.mu.Lock()
	defer o.mu.Unlock()
	wasEmpty := len(o.system) == 0 && len(o.normal) == 0
	if isSystem {
		if len(o.system) >= systemTripwire {
			return false, wasEmpty // tripwire; caller logs
		}
		o.system = append(o.system, it)
		return true, wasEmpty
	}
	if !neverDrop && len(o.normal) >= o.normalMax {
		return false, wasEmpty
	}
	o.normal = append(o.normal, it)
	return true, wasEmpty
}

func (o *outboundLanes) pop() (outItem, bool) {
	o.mu.Lock()
	defer o.mu.Unlock()
	if len(o.system) > 0 {
		it := o.system[0]
		o.system = o.system[1:]
		return it, true
	}
	if len(o.normal) > 0 {
		it := o.normal[0]
		o.normal = o.normal[1:]
		return it, true
	}
	return outItem{}, false
}

// sessionRunner owns one session_id: the inbound lanes + feeder, the outbound
// lanes, and the bridge to the Session consumer. It implements Emitter.
type sessionRunner struct {
	sid    wire.SessionID
	sess   Session
	host   runnerHost
	ctx    context.Context
	cancel context.CancelFunc

	systemCh chan inboundItem
	normalCh chan inboundItem
	out      *outboundLanes

	closeOnce sync.Once
}

func newSessionRunner(parent context.Context, sid wire.SessionID, host runnerHost) *sessionRunner {
	ctx, cancel := context.WithCancel(parent)
	nm := host.laneMax()
	r := &sessionRunner{
		sid:      sid,
		host:     host,
		ctx:      ctx,
		cancel:   cancel,
		systemCh: make(chan inboundItem, systemTripwire),
		normalCh: make(chan inboundItem, nm),
		out:      &outboundLanes{normalMax: nm},
	}
	r.sess = host.sessionFactory()(ctx, sid, r)
	return r
}

func (r *sessionRunner) start() {
	go r.feed()
}

// enqueueInbound routes a decoded inbound frame onto the right lane. Drop-newest
// on the normal lane (with a non-fatal ErrorFrame). Called by the agent reader.
func (r *sessionRunner) enqueueInbound(it inboundItem) {
	if wire.IsSystem(it.frame) {
		select {
		case r.systemCh <- it:
		default:
			r.host.logger().Warnf("cortex: session %s system lane overflow — dropping %T", r.sid, it.frame)
		}
		return
	}
	select {
	case r.normalCh <- it:
	default:
		// Drop newest; surface a non-fatal ErrorFrame DOWNSTREAM to the brain.
		r.sess.DeliverError(wire.Downstream,
			"voqalize: inbound queue full; dropping data frames until consumer catches up")
	}
}

// feed drains inbound lanes (system first), dispatches to the Session, and acks
// frames that carry request_id > 0. End triggers teardown.
func (r *sessionRunner) feed() {
	for {
		// Prefer the system lane.
		select {
		case it := <-r.systemCh:
			r.dispatch(it)
			continue
		default:
		}
		select {
		case <-r.ctx.Done():
			return
		case it := <-r.systemCh:
			r.dispatch(it)
		case it := <-r.normalCh:
			r.dispatch(it)
			if _, ok := it.frame.(wire.End); ok {
				r.host.closeSession(r.sid)
				return
			}
		}
	}
}

func (r *sessionRunner) dispatch(it inboundItem) {
	r.sess.HandleFrame(it.frame)
	if it.requestID != 0 {
		// Ack after the handler returns (response frames it pushed synchronously
		// are already enqueued ahead of this ack — FIFO on the normal lane).
		r.enqueueOut(outItem{ackID: it.requestID, isAck: true}, false, true)
	}
}

// Send implements Emitter: enqueue an outbound frame from the brain adapter.
func (r *sessionRunner) Send(f wire.Frame) {
	isSystem := wire.IsSystem(f)
	accepted, _ := r.enqueueOutReport(outItem{frame: f}, isSystem, false)
	if !accepted {
		r.sess.DeliverError(wire.Upstream,
			"voqalize: outbound queue full; dropping data frames until wire catches up")
	}
}

func (r *sessionRunner) enqueueOut(it outItem, isSystem, neverDrop bool) {
	r.enqueueOutReport(it, isSystem, neverDrop)
}

func (r *sessionRunner) enqueueOutReport(it outItem, isSystem, neverDrop bool) (bool, bool) {
	accepted, wasEmpty := r.out.push(it, isSystem, neverDrop)
	if accepted && wasEmpty {
		r.host.signalReady(r.sid)
	}
	return accepted, wasEmpty
}

func (r *sessionRunner) teardown() {
	r.closeOnce.Do(func() {
		r.cancel()
		r.sess.Close()
	})
}
