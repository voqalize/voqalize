/**
 * Check-in: a five-step wizard (reservation, ID, room, early check-in,
 * review) driven by the store's `checkin`. Only steps the guest has reached
 * are tappable; the ID scan and Complete check-in are the guest's own presses.
 */
import { BadgeCheck, Check, CreditCard, KeyRound, ScanLine, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/Shell";
import { CHECKIN, GUEST } from "../data";
import { clock, money } from "../lib/format";
import { earlyAvailable, earlyOffered } from "../lib/rules";
import {
  CHECKIN_STEPS,
  type CheckinStep,
  checkinNext,
  completeCheckin,
  confirmReservation,
  reachable,
  roomFor,
  setCheckinStep,
  setEarly,
  setPref,
  stayClock,
  useStay,
  verifyId,
} from "../state/store";
import { KeyCard, WifiCard } from "./Home";
import { ReservationCard } from "./Stay";
import "../styles/stay.css";

const STEP_LABEL: Record<CheckinStep, string> = { reservation: "Booking", id: "ID", room: "Room", early: "Early", review: "Review" };
const hhmmId = (id: string) => id.replace(":", "");
const arrivalLabel = (id: string | null) => CHECKIN.arrival_times.find((a) => a.id === id)?.label ?? "Not chosen";
const floorLabel = (id: string | null) => CHECKIN.floors.find((a) => a.id === id)?.label ?? "No preference";
const bedLabel = (id: string | null) => CHECKIN.beds.find((a) => a.id === id)?.label ?? "One king";

/** A tiny door with a room number, for the room preview. */
function Door() {
  return (
    <svg className="st-door" width="40" height="52" viewBox="0 0 40 52" fill="none" aria-hidden>
      <path d="M4 50V16a16 16 0 0 1 32 0v34" stroke="#c9a467" strokeWidth="2" />
      <path d="M10 50V18a10 10 0 0 1 20 0v32" stroke="#c9a467" strokeOpacity="0.5" strokeWidth="1.5" />
      <circle cx="26" cy="34" r="1.8" fill="#c9a467" />
      <path d="M1 50h38" stroke="#c9a467" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/** An ID card in line art, for the scan step. */
function IdArt() {
  return (
    <svg viewBox="0 0 190 120" fill="none" aria-hidden>
      <rect x="1" y="1" width="188" height="118" rx="12" fill="#fffdf9" stroke="#d7cbb9" strokeWidth="1.5" />
      <rect x="16" y="26" width="48" height="60" rx="6" fill="#ece3d5" />
      <circle cx="40" cy="48" r="11" fill="#d7cbb9" />
      <path d="M22 84c3-12 12-17 18-17s15 5 18 17" fill="#d7cbb9" />
      <rect x="78" y="30" width="80" height="7" rx="3.5" fill="#d7cbb9" />
      <rect x="78" y="46" width="56" height="6" rx="3" fill="#ece3d5" />
      <rect x="78" y="60" width="92" height="6" rx="3" fill="#ece3d5" />
      <rect x="78" y="74" width="40" height="6" rx="3" fill="#ece3d5" />
      <rect x="16" y="98" width="158" height="8" rx="4" fill="#f3e8d4" />
    </svg>
  );
}

function Option({ thing, label, sub, on, onClick, disabled, side }: { thing: string; label: string; sub?: string; on: boolean; onClick: () => void; disabled?: boolean; side?: string }) {
  return (
    <button type="button" role="radio" aria-checked={on} className="st-option" onClick={onClick} disabled={disabled} data-stage-thing={thing} data-stage-label={label}>
      <span className="st-radio" />
      <span className="st-option-text">
        <span>{label}</span>
        {sub ? <small>{sub}</small> : null}
      </span>
      {side ? <span className={`st-option-side${side === "Free" ? " is-free" : ""}`}>{side}</span> : null}
    </button>
  );
}

function StepReservation() {
  const confirmed = useStay((s) => s.checkin.confirmed);
  return (
    <>
      <h2 className="st-step-title">Is this your reservation?</h2>
      <ReservationCard />
      <button type="button" className="st-btn is-block" onClick={confirmReservation} data-stage-thing="checkin-confirm" data-stage-label="Yes, that's my reservation">
        {confirmed ? <Check size={17} /> : null} Yes, that's my reservation
      </button>
      <p className="st-note">Something not right? Call the front desk, 24 hours, or ask the concierge.</p>
    </>
  );
}

function StepId() {
  const verified = useStay((s) => s.checkin.idVerified);
  const [scanning, setScanning] = useState(false);
  useEffect(() => {
    if (!scanning) return;
    const t = window.setTimeout(() => {
      setScanning(false);
      verifyId();
    }, 1800);
    return () => window.clearTimeout(t);
  }, [scanning]);
  return (
    <>
      <h2 className="st-step-title">Verify your ID</h2>
      <p className="st-note">We check a photo ID for the guest named on the reservation. Hold your driver's license or passport inside the frame; it takes a couple of seconds.</p>
      <div className={`st-scan${verified ? " is-done" : ""}`}>
        <IdArt />
        {scanning ? <span className="st-scan-beam" /> : null}
      </div>
      {verified ? (
        <span className="st-verified">
          <BadgeCheck size={20} /> ID verified
        </span>
      ) : (
        <button
          type="button"
          className="st-btn is-block"
          onClick={() => setScanning(true)}
          disabled={scanning}
          data-stage-thing="id-scan"
          data-stage-label="Scan ID"
          data-dock-avoid
          data-guest-only
        >
          <ScanLine size={18} /> {scanning ? "Scanning…" : "Scan ID"}
        </button>
      )}
      <div className="st-privacy">
        <ShieldCheck size={18} />
        <span>The scan goes straight to the front desk's secure system. The concierge never sees your ID or its numbers.</span>
      </div>
    </>
  );
}

function StepRoom() {
  const c = useStay((s) => s.checkin);
  const room = roomFor(c);
  const now = stayClock().now;
  const ready = room.ready === "now" ? "Ready now" : `Ready by ${clock(room.ready)}`;
  return (
    <>
      <h2 className="st-step-title">Your room</h2>
      <section className="st-section" data-stage-thing="arrival" data-stage-label="Arrival time" data-stage-group>
        <span className="st-label">When will you arrive?</span>
        <div className="st-chips" role="radiogroup" aria-label="Arrival time">
          {CHECKIN.arrival_times.map((a) => (
            <button
              key={a.id}
              type="button"
              role="radio"
              aria-checked={c.arrival === a.id}
              className="st-chip"
              onClick={() => setPref("arrival", a.id)}
              data-stage-thing={`arrival-${hhmmId(a.id)}`}
              data-stage-label={a.label}
            >
              {a.label}
            </button>
          ))}
        </div>
      </section>
      <section className="st-section" data-stage-thing="floor" data-stage-label="Floor" data-stage-group>
        <span className="st-label">Floor</span>
        <div className="st-options" role="radiogroup" aria-label="Floor">
          {CHECKIN.floors.map((f) => (
            <Option key={f.id} thing={`floor-${f.id}`} label={f.label} on={c.floor === f.id} onClick={() => setPref("floor", f.id)} />
          ))}
        </div>
      </section>
      <section className="st-section" data-stage-thing="bed" data-stage-label="Beds" data-stage-group>
        <span className="st-label">Beds</span>
        <div className="st-chips" role="radiogroup" aria-label="Beds">
          {CHECKIN.beds.map((b) => (
            <button key={b.id} type="button" role="radio" aria-checked={c.bed === b.id} className="st-chip" onClick={() => setPref("bed", b.id)} data-stage-thing={`bed-${b.id}`} data-stage-label={b.label}>
              {b.label}
            </button>
          ))}
        </div>
      </section>
      <button type="button" role="switch" aria-checked={c.quiet === true} className="st-toggle" onClick={() => setPref("quiet", !c.quiet)} data-stage-thing="quiet" data-stage-label="Quiet room">
        <span className="st-option-text">
          <span>Quiet room</span>
          <small>Away from the elevators and the ice machine</small>
        </span>
        <span className="st-switch" />
      </button>
      <div className="st-room-preview" data-stage-thing="room-preview" data-stage-label={`Room ${room.room}`}>
        <Door />
        <div>
          <small>Your room would be</small>
          <b>
            Room {room.room}, floor {room.floor}, {room.note.charAt(0).toLowerCase() + room.note.slice(1)}
          </b>
          <span>
            {room.bed === "king" ? "One king" : "Two queens"}
            {room.quiet ? " · Quiet" : ""} · {ready}
          </span>
        </div>
      </div>
      {c.arrival && earlyOffered(c.arrival, now) ? <p className="st-note">You're arriving before {clock(CHECKIN.early.before)}; next, choose whether you want the room early.</p> : null}
      <button type="button" className="st-btn is-block" onClick={checkinNext} disabled={!c.arrival} data-stage-thing="checkin-continue" data-stage-label="Continue" data-dock-avoid>
        Continue
      </button>
      {!c.arrival ? <p className="st-reason">Choose when you'll arrive.</p> : null}
    </>
  );
}

function StepEarly() {
  const c = useStay((s) => s.checkin);
  const room = roomFor(c);
  const now = stayClock().now;
  const avail = c.arrival ? earlyAvailable(room, c.arrival, now) : false;
  const readyAt = room.ready === "now" ? "now" : clock(room.ready);
  return (
    <>
      <h2 className="st-step-title">Early check-in</h2>
      <div className="st-rule">{CHECKIN.early.rule}</div>
      <p className="st-note">
        Room {room.room} is ready {room.ready === "now" ? "now" : `at ${readyAt}`}.{" "}
        {avail ? "It will be ready when you arrive." : `That's after you arrive (${arrivalLabel(c.arrival)}).`}
      </p>
      <section className="st-section" data-stage-thing="early" data-stage-label="Early check-in" data-stage-group>
        <div className="st-options" role="radiogroup" aria-label="Early check-in">
          <Option
            thing="early-yes"
            label="Yes, I'd like the room when I arrive"
            sub={avail ? "Charged to your room bill" : `Not available: the room is ready at ${readyAt}`}
            side={money(CHECKIN.early.fee)}
            on={c.early === true}
            disabled={!avail}
            onClick={() => setEarly(true)}
          />
          <Option thing="early-no" label={`No, ${clock(CHECKIN.early.before)} is fine`} sub="We'll hold your bags until then" side="Free" on={c.early === false} onClick={() => setEarly(false)} />
        </div>
      </section>
      <button type="button" className="st-btn is-block" onClick={checkinNext} disabled={c.early === null} data-stage-thing="checkin-continue" data-stage-label="Continue" data-dock-avoid>
        Continue
      </button>
      {c.early === null ? <p className="st-reason">Choose yes or no.</p> : null}
    </>
  );
}

function StepReview() {
  const c = useStay((s) => s.checkin);
  const room = roomFor(c);
  const fee = c.early ? CHECKIN.early.fee : 0;
  return (
    <>
      <h2 className="st-step-title">Review and check in</h2>
      <div className="st-card" data-stage-thing="checkin-review" data-stage-label="Check-in summary">
        <dl className="st-rows">
          <div className="st-row">
            <dt>Reservation</dt>
            <dd>{GUEST.reservation}</dd>
          </div>
          <div className="st-row">
            <dt>Photo ID</dt>
            <dd>{c.idVerified ? "Verified" : "Not yet"}</dd>
          </div>
          <div className="st-row">
            <dt>Arrival</dt>
            <dd>{arrivalLabel(c.arrival)}</dd>
          </div>
          <div className="st-row">
            <dt>Floor</dt>
            <dd>{floorLabel(c.floor)}</dd>
          </div>
          <div className="st-row">
            <dt>Beds</dt>
            <dd>{bedLabel(c.bed)}</dd>
          </div>
          <div className="st-row">
            <dt>Quiet room</dt>
            <dd>{c.quiet ? "Yes" : "No preference"}</dd>
          </div>
          <div className="st-row">
            <dt>Room</dt>
            <dd>
              {room.room}, floor {room.floor}
            </dd>
          </div>
          <div className="st-row">
            <dt>Early check-in</dt>
            <dd>{c.early ? money(CHECKIN.early.fee) : c.early === false ? "No" : "Not needed"}</dd>
          </div>
        </dl>
      </div>
      <div className="st-card st-wifi">
        <span className="st-wifi-icon">
          <CreditCard size={20} />
        </span>
        <div>
          <span className="st-label">Card on file</span>
          <b>{GUEST.card}</b>
          <span>Room and incidentals are charged at check-out.</span>
        </div>
      </div>
      <div className="st-final">
        <div className="st-pay">
          <span>Due now</span>
          <b>{fee ? money(fee) : "$0.00"}</b>
        </div>
        <button
          type="button"
          className="st-btn is-block is-brass"
          onClick={completeCheckin}
          disabled={!reachable(c).includes("review")}
          data-stage-thing="checkin-complete"
          data-stage-label="Complete check-in"
          data-dock-avoid
          data-guest-only
        >
          <KeyRound size={18} /> Complete check-in
        </button>
      </div>
    </>
  );
}

export function CheckIn() {
  const s = useStay();
  const c = s.checkin;
  const can = reachable(c);
  const stepIdx = CHECKIN_STEPS.indexOf(c.step);

  return (
    <div className="page st-page" data-stage-place="checkin">
      <PageHeader title="Check in" sub={`Reservation ${GUEST.reservation}`} back="/stay" />
      <div className="st-body">
        {s.checkedIn ? (
          <>
            <div className="st-done">
              <span className="st-done-mark">
                <Check size={28} />
              </span>
              <h2>You're checked in</h2>
              <p>Your digital key is ready. Hold your phone near the door to open it.</p>
            </div>
            <KeyCard />
            <WifiCard />
            <Link to="/" className="st-btn is-ghost is-block">
              Back to home
            </Link>
          </>
        ) : (
          <>
            <nav className="st-steps" aria-label="Check-in steps" data-stage-group>
              {CHECKIN_STEPS.map((step, i) => {
                const ok = can.includes(step);
                return (
                  <button
                    key={step}
                    type="button"
                    className={`st-step${c.step === step ? " is-on" : i < stepIdx || (ok && c.step !== step) ? " is-done" : ""}`}
                    disabled={!ok}
                    aria-current={c.step === step ? "step" : undefined}
                    onClick={() => setCheckinStep(step)}
                    data-stage-thing={`checkin-step-${step}`}
                    data-stage-label={STEP_LABEL[step]}
                  >
                    <span className="st-step-bar" />
                    <span>{STEP_LABEL[step]}</span>
                  </button>
                );
              })}
            </nav>
            {c.step === "reservation" ? <StepReservation /> : null}
            {c.step === "id" ? <StepId /> : null}
            {c.step === "room" ? <StepRoom /> : null}
            {c.step === "early" ? <StepEarly /> : null}
            {c.step === "review" ? <StepReview /> : null}
          </>
        )}
      </div>
    </div>
  );
}
