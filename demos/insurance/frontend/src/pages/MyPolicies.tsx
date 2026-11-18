import { ArrowRight, CalendarClock, FileText, MessageCircle, ShieldAlert } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { customer, policies, policyById } from "../data";
import type { PolicyDoc } from "../data/types";
import { ProductIcon } from "../components/bits";
import { daysUntil, fmtDate, inr } from "../lib/format";
import { persona } from "../persona";
import { useVoiceClient } from "../stage/client";
import { startClaim } from "../state/claim";

/** The schedule rows worth a glance on the card, per product. */
const KEY_ROWS: Record<string, RegExp[]> = {
  car: [/^Insured vehicle/, /IDV/, /No Claim Bonus/],
  bike: [/^Insured vehicle/, /IDV/, /No Claim Bonus/],
  health: [/^Sum insured/, /^Insured members/, /^Cumulative bonus/],
  term: [/^Sum assured/, /^Cover till/, /^Nominee/],
  home: [/^Building sum insured/, /^Contents sum insured/, /^Address/],
  travel: [/^Trip/, /^Emergency medical/, /^Travellers/],
};

export function keyNumbers(p: PolicyDoc) {
  const rows = (KEY_ROWS[p.product] ?? [])
    .map((re) => p.schedule.find((r) => re.test(r.label)))
    .filter((r): r is { label: string; value: string } => !!r);
  if (rows.length) return rows;
  return p.schedule.filter((r) => !/Policy number|Period/.test(r.label)).slice(0, 3);
}

export function MyPolicies() {
  const navigate = useNavigate();
  const begin = useVoiceClient((s) => s.begin);
  const active = policies.filter((p) => p.status === "active").length;
  const renewals = [...policies]
    .filter((p) => p.product !== "term" && daysUntil(p.end) >= 0)
    .sort((a, b) => a.end.localeCompare(b.end))
    .slice(0, 3);
  return (
    <div className="wrap page dashboard">
      <div className="page-head">
        <div>
          <p className="crumbs">
            <Link to="/">Home</Link> / My policies
          </p>
          <h1 className="h1">Namaste, {customer.first_name}</h1>
          <p className="muted">
            Customer ID {customer.id} · {active} active {active === 1 ? "policy" : "policies"}
            {policies.length > active ? `, ${policies.length - active} starting soon` : ""}
          </p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn btn-ghost" disabled={!begin} title={begin ? undefined : "Voice is not switched on for this preview"} onClick={() => begin?.()}>
            <MessageCircle size={16} aria-hidden /> Ask about my cover
          </button>
          <Link to="/claim" className="btn btn-primary">
            <ShieldAlert size={16} aria-hidden /> Make a claim
          </Link>
        </div>
      </div>

      <div className="dash-grid">
        <div className="policy-list">
          {policies.map((p) => (
            <article key={p.id} className={`policy-card pc-${p.product}`} data-stage-part={`policy-card:${p.id}`}>
              <header className="policy-card-head">
                <span className="product-icon"><ProductIcon product={p.product} size={22} /></span>
                <div className="policy-card-title">
                  <h2>{p.plan}</h2>
                  <p className="muted small">
                    {p.title} · <span className="mono">{p.policy_number}</span>
                  </p>
                </div>
                <span className={`status status-${p.status}`}>{p.status === "active" ? "Active" : p.status === "upcoming" ? "Starts soon" : p.status}</span>
              </header>
              <p className="policy-card-summary">{p.summary}</p>
              <dl className="key-rows">
                {keyNumbers(p).map((r) => (
                  <div key={r.label}>
                    <dt>{r.label}</dt>
                    <dd>{r.value}</dd>
                  </div>
                ))}
                <div>
                  <dt>{p.status === "upcoming" ? "Cover starts" : p.product === "term" ? "Cover runs till" : "Renews on"}</dt>
                  <dd>{fmtDate(p.status === "upcoming" ? p.start : p.end)}</dd>
                </div>
                <div>
                  <dt>Premium paid</dt>
                  <dd>{inr(p.premium_paid)}</dd>
                </div>
              </dl>
              <footer className="policy-card-actions">
                <Link to={`/my-policies/${p.id}`} className="btn btn-ghost btn-sm">
                  <FileText size={15} aria-hidden /> Read policy
                </Link>
                {p.product === "car" || p.product === "bike" || p.product === "health" ? (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      startClaim(p.product === "health" ? "health" : "motor", p.id);
                      navigate("/claim");
                    }}
                  >
                    Make a claim
                  </button>
                ) : null}
                <button type="button" className="link-btn small" disabled={!begin} onClick={() => begin?.()}>
                  Ask {persona.name}
                </button>
              </footer>
            </article>
          ))}
        </div>

        <aside className="dash-side">
          <section className="side-card">
            <h2 className="side-h">
              <CalendarClock size={16} aria-hidden /> Coming up
            </h2>
            <ul className="renewals">
              {renewals.map((p) => (
                <li key={p.id}>
                  <span>
                    <strong>{p.plan}</strong>
                    <span className="muted small">{p.status === "upcoming" ? "trip cover ends" : "renews"} {fmtDate(p.end)}</span>
                  </span>
                  <span className="days">{daysUntil(p.end)} days</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="side-card">
            <h2 className="side-h">Past claims</h2>
            {customer.past_claims.length ? (
              <ul className="past-claims">
                {customer.past_claims.map((c) => (
                  <li key={c.reference}>
                    <div className="past-top">
                      <span className="mono small">{c.reference}</span>
                      <span className={`status status-${c.status}`}>{c.status === "settled" ? "Settled" : c.status}</span>
                    </div>
                    <p className="small">{c.summary}</p>
                    <p className="small muted">
                      {inr(c.amount)} · {fmtDate(c.date)} · {policyById(c.policy_id)?.plan ?? c.policy_id}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">No claims yet.</p>
            )}
          </section>
          <section className="side-card">
            <h2 className="side-h">Your details</h2>
            <dl className="details">
              <div><dt>Mobile</dt><dd>{customer.phone}</dd></div>
              <div><dt>Email</dt><dd>{customer.email}</dd></div>
              <div><dt>Address</dt><dd>{customer.address}</dd></div>
              <div><dt>Bank for payouts</dt><dd>{customer.bank_on_file.bank_name} {customer.bank_on_file.masked}</dd></div>
            </dl>
          </section>
        </aside>
      </div>
      <p className="muted small dash-foot">
        Looking for something else? <Link to="/quote">Get a quote</Link> for a new plan <ArrowRight size={12} aria-hidden />
      </p>
    </div>
  );
}
