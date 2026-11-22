/**
 * An order's return form (`/orders/return?order=FH-31042`), its confirmation
 * (`/orders/return/confirmation?ref=RT-31042-1`), and the redirects that keep
 * the old /returns URLs working. The form opens on that order's items — the
 * shopper is signed in, so there is no order or email to look up — and nothing
 * is chosen until someone says so. Five steps; a done step folds to one line
 * with Edit; the order card and the step progress sit beside it, "Policy in
 * short" below. It works entirely by hand; with a call live, the agent's
 * `returns.*` moves (src/stage/orders.ts, registered in the shell) set the same
 * fields, and Submit return is pressed only after the shopper's yes.
 */
import * as React from "react";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowLeft, Check, CheckCircle2, PackageCheck } from "lucide-react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { watchForms } from "@voqalize/stage";
import { Crumbs, EmilyTag, Photo } from "../components/bits";
import { getProduct, money } from "../data/catalog";
import { policies } from "../data/content";
import { type AccountOrder, dayLabel, findOrder, normalOrderNumber, outsideWindowText, RETURN_WINDOW_DAYS, returnable, useAccount } from "../orders/tracking";
import { persona } from "../persona";
import { CHOICES, type ChoiceField, exchangeOptions, LAST_STEP, labelOf, STEP_FIELDS, STEPS } from "../returns/orders";
import { type StoredReturn, filledNames, firstMissing, missingInStep, pressedBy, stepSummary, storedReturns, useReturns } from "../returns/store";
import { useAppStage } from "../stage/host";
import { scene } from "../stage/scene.gen";
import { navigatedBy } from "../voice/controller";
import { PolicyInShort } from "./Orders";
import { useTitle } from "./usePage";

const R = policies.returns as Record<string, string>;

const RETURN_POLICY: [string, string][] = [
  ["Window", R.window],
  ["Condition", R.condition],
  ["Refunds", R.refund],
  ["Exchanges", R.exchanges],
  ["Not returnable", R.notReturnable],
  ["Damaged or faulty", R.damagedOrFaulty],
];

// ── /returns, /returns/start, /returns/confirmation → the new pages ────────

/** The old returns URLs, kept working: each lands on its new page. */
export function ReturnsRedirect() {
  const { pathname, search } = useLocation();
  const sp = new URLSearchParams(search);
  const path = pathname.replace(/\/+$/, "");
  if (path.endsWith("/returns/start")) {
    const order = sp.get("order");
    return <Navigate replace to={order ? `/orders/return?order=${encodeURIComponent(normalOrderNumber(order))}` : "/orders"} />;
  }
  if (path.endsWith("/returns/confirmation")) {
    const ref = sp.get("ref");
    return <Navigate replace to={ref ? `/orders/return/confirmation?ref=${encodeURIComponent(ref)}` : "/orders"} />;
  }
  return <Navigate replace to="/orders" />;
}

// ── /orders/return?order=… ─────────────────────────────────────────────────

export function OrderReturn() {
  const [sp] = useSearchParams();
  const asked = sp.get("order");
  const order = findOrder(asked);
  useTitle(order ? `Return items from ${order.number}` : "Start a return");
  const state = useAccount();
  if (!order) return <Navigate to="/orders" replace />;
  const r = returnable(order, state);
  if (r.kind !== "eligible") return <NotReturnable order={order} />;
  return <ReturnForm key={order.number} order={order} daysLeft={r.daysLeft} />;
}

function Head({ order }: { order: AccountOrder }) {
  return (
    <>
      <Crumbs
        items={[
          { label: "Home", to: "/" },
          { label: "Your orders", to: "/orders" },
          { label: order.number, to: `/orders?order=${order.number}` },
          { label: "Return" },
        ]}
      />
      <header className="fd-hero fd-hero-tight">
        <div>
          <Link to={`/orders?order=${order.number}`} className="fd-back small">
            <ArrowLeft size={14} aria-hidden /> Back to {order.number}
          </Link>
          <h1 className="h1">Return items from {order.number}</h1>
          <p className="lede">Five short steps. Nothing is sent until you press Submit return.</p>
        </div>
      </header>
    </>
  );
}

function NotReturnable({ order }: { order: AccountOrder }) {
  const state = useAccount();
  const r = returnable(order, state);
  const why =
    r.kind === "outside_window"
      ? `${outsideWindowText(r.days)}, so it cannot be returned.`
      : r.kind === "cancelled"
        ? "This order was cancelled, so there is nothing to return."
        : "This order has not been delivered yet. You can start a return once it arrives.";
  return (
    <div className="wrap page-pad frontdesk ret-page">
      <Head order={order} />
      <div className="ret-blocked" role="status">
        <AlertCircle size={20} aria-hidden />
        <div>
          <p className="fd-delivery-v">{why}</p>
          {r.kind === "outside_window" ? (
            <p className="small">
              Our{" "}
              <Link className="link" to="/policy/care">
                care guides
              </Link>{" "}
              may help, or{" "}
              <Link className="link" to="/contact">
                write to the studio
              </Link>
              .
            </p>
          ) : null}
          <Link to={`/orders?order=${order.number}`} className="btn btn-ghost btn-sm">
            Back to the order
          </Link>
        </div>
      </div>
      <PolicyInShort rows={RETURN_POLICY} links={[["/policy/returns", "Read the full returns policy"]]} />
    </div>
  );
}

function ReturnForm({ order, daysLeft }: { order: AccountOrder; daysLeft: number }) {
  const navigate = useNavigate();
  const form = useReturns();
  const stage = useAppStage((s) => s.stage);
  const [stepError, setStepError] = useState<{ step: number; why: string } | null>(null);

  // This page is the order's form: begin it (once) when it is not on this order yet.
  useEffect(() => {
    useReturns.getState().start(order.number, navigatedBy());
  }, [order.number]);

  const ready = form.order_number === order.number;
  const filled = filledNames(form);

  // The watch kit: what the shopper fills, by field name only.
  useEffect(() => {
    if (!stage) return;
    return watchForms((s) => stage.page.send(scene.event("form.changed", s)));
  }, [stage]);

  // A step left untouched for a while: the agent may offer to fill it in.
  const stepEmpty = (STEP_FIELDS[form.step] ?? []).every((f) => !filled.includes(f));
  const offered = useRef(new Set<number>());
  useEffect(() => {
    if (!stage || !ready || !stepEmpty || form.step === LAST_STEP || offered.current.has(form.step)) return;
    let t = window.setTimeout(fire, 12000);
    const typing = () => {
      window.clearTimeout(t);
      t = window.setTimeout(fire, 12000);
    };
    function fire() {
      if (!stage) return;
      offered.current.add(form.step);
      stage.page.send(scene.event("view.changed", { thing: `step-${form.step}`, label: STEPS[form.step - 1].title }));
    }
    document.addEventListener("input", typing, true);
    document.addEventListener("change", typing, true);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("input", typing, true);
      document.removeEventListener("change", typing, true);
    };
  }, [stage, ready, form.step, stepEmpty]);

  if (!ready) return null;

  const chosen = order.lines.filter((l) => form.items[l.product_id]);
  const missing = (step: number) => missingInStep(form, step);
  const isDone = (step: number) => step < LAST_STEP && !missing(step) && !!stepSummary(form, step);

  const go = (step: number) => {
    setStepError(null);
    useReturns.getState().setStep(step);
    requestAnimationFrame(() => document.querySelector(`[data-stage-thing="step-${step}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" }));
  };
  const next = (step: number) => {
    const why = missing(step);
    if (why) {
      setStepError({ step, why });
      return;
    }
    go(step + 1);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const gap = firstMissing(useReturns.getState());
    if (gap) {
      go(gap.step);
      setStepError({ step: gap.step, why: gap.why });
      return;
    }
    const stored = useReturns.getState().submit(pressedBy());
    if (stored) navigate(`/orders/return/confirmation?ref=${stored.reference}`, { state: stored });
  };

  const tag = (field: string) => (form.by[field] === "emily" ? <EmilyTag /> : null);

  const choiceGroup = (field: ChoiceField, legend: string) => (
    <fieldset className="ret-choices" data-reveal-group>
      <legend className="ret-legend">
        {legend} {tag(field)}
      </legend>
      <div className="ret-choice-grid">
        {CHOICES[field].map(([value, label]) => (
          <label key={value} className={`ret-choice${form[field] === value ? " is-on" : ""}`} data-stage-part={`${field}:${value}`}>
            <input type="radio" name={field} value={value} checked={form[field] === value} onChange={() => useReturns.getState().setChoice(field, value)} />
            <span className="ret-dot" aria-hidden />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );

  const step = (n: number, body: React.ReactNode) => {
    const open = form.step === n;
    const done = isDone(n);
    const reached = n <= form.reached;
    const summary = stepSummary(form, n);
    const s = STEPS[n - 1];
    return (
      <section
        className={`ret-step${open ? " is-open" : ""}${done ? " is-done" : ""}${!reached && !open ? " is-locked" : ""}`}
        data-stage-thing={`step-${n}`}
        data-stage-label={s.title}
        data-reveal-group
        aria-labelledby={`ret-step-${n}`}
      >
        <header className="ret-step-head">
          <span className="ret-step-n" aria-hidden>
            {done && !open ? <Check size={14} strokeWidth={2.6} /> : n}
          </span>
          <div className="ret-step-title">
            <h2 className="h3" id={`ret-step-${n}`}>
              {s.title}
            </h2>
            <p className="small">{!open && summary ? summary : s.hint}</p>
          </div>
          {!open && reached ? (
            <button type="button" className="link small" onClick={() => go(n)} aria-label={`Edit ${s.title}`}>
              Edit
            </button>
          ) : null}
        </header>
        {open ? (
          <div className="ret-step-body">
            {body}
            {stepError?.step === n ? (
              <p className="ret-error" role="alert">
                <AlertCircle size={15} aria-hidden /> {stepError.why}
              </p>
            ) : null}
            {n < LAST_STEP ? (
              <div className="ret-step-actions">
                {n > 1 ? (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => go(n - 1)}>
                    Back
                  </button>
                ) : null}
                <button type="button" className="btn btn-primary btn-sm" data-continue data-dock-avoid onClick={() => next(n)}>
                  Continue
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    );
  };

  return (
    <div className="wrap page-pad frontdesk ret-page">
      <Head order={order} />
      <div className="ret-layout">
        <form className="ret-form" data-stage-form="Return" data-return-form={order.number} onSubmit={submit} noValidate aria-label={`Return for ${order.number}`}>
          {step(
            1,
            <ul className="ret-items" data-reveal-group>
              {order.lines.map((l) => {
                const p = getProduct(l.product_id);
                const qty = form.items[l.product_id] ?? 0;
                return (
                  <li key={l.product_id} className={`ret-item${qty ? " is-on" : ""}`} data-stage-part={`items:${l.product_id}`}>
                    <label className="ret-item-pick">
                      <input
                        type="checkbox"
                        name="items"
                        value={l.product_id}
                        checked={!!qty}
                        onChange={(e) => useReturns.getState().setItem(l.product_id, e.target.checked ? 1 : 0)}
                      />
                      <span className="ret-check" aria-hidden>
                        <Check size={13} strokeWidth={3} />
                      </span>
                      {p ? <Photo file={p.images[0]} alt="" sizes="64px" /> : null}
                      <span className="ret-item-text">
                        <span className="ret-item-title">{p?.title ?? l.title}</span>
                        <span className="small">
                          {l.variant} · {money(l.unit_price)} · ordered {l.qty}
                        </span>
                      </span>
                    </label>
                    <span className="ret-item-side">
                      {qty && l.qty > 1 ? (
                        <label className="ret-qty">
                          <span className="small">How many</span>
                          <select
                            className="select select-sm"
                            name={`qty_${l.product_id}`}
                            value={qty}
                            onChange={(e) => useReturns.getState().setItem(l.product_id, Number(e.target.value))}
                          >
                            {Array.from({ length: l.qty }, (_, i) => i + 1).map((n) => (
                              <option key={n} value={n}>
                                {n} of {l.qty}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                      {qty ? tag(`qty_${l.product_id}`) : null}
                    </span>
                  </li>
                );
              })}
            </ul>,
          )}

          {step(
            2,
            <>
              {choiceGroup("reason", "Why are you returning it?")}
              {form.reason === "arrived_damaged" ? <p className="ret-note">{R.damagedOrFaulty}</p> : null}
              {choiceGroup("condition", "What condition is it in?")}
              <p className="ret-note">{R.condition}</p>
            </>,
          )}

          {step(
            3,
            <>
              {choiceGroup("resolution", "What would you like instead?")}
              {form.resolution === "exchange" ? (
                <div className="ret-exchange">
                  {chosen.map((l) => {
                    const options = exchangeOptions(l);
                    const field = `exchange_variant_${l.product_id}`;
                    const title = getProduct(l.product_id)?.title ?? l.title;
                    return (
                      <fieldset key={l.product_id} className="ret-choices" data-reveal-group>
                        <legend className="ret-legend">
                          {title}: swap {l.variant} for {tag(field)}
                        </legend>
                        {options.length ? (
                          <div className="option-values">
                            {options.map((o) => (
                              <label key={o} className={`opt${form.exchange[l.product_id] === o ? " is-on" : ""}`} data-stage-part={`${field}:${o}`}>
                                <input
                                  type="radio"
                                  className="sr-only"
                                  name={field}
                                  value={o}
                                  checked={form.exchange[l.product_id] === o}
                                  onChange={() => useReturns.getState().setExchange(l.product_id, o)}
                                />
                                {o}
                              </label>
                            ))}
                          </div>
                        ) : (
                          <p className="small">This piece comes in one option only. {R.exchanges}</p>
                        )}
                      </fieldset>
                    );
                  })}
                </div>
              ) : null}
              {form.resolution === "refund" ? <p className="ret-note">{R.refund}</p> : null}
            </>,
          )}

          {step(
            4,
            <>
              {choiceGroup("collection", "How should it come back to us?")}
              {form.collection === "pickup" ? choiceGroup("pickup_window", "When suits you for collection?") : null}
            </>,
          )}

          {step(
            5,
            <>
              <dl className="ret-review">
                {[1, 2, 3, 4].map((n) => (
                  <div key={n}>
                    <dt>{STEPS[n - 1].title}</dt>
                    <dd>{stepSummary(form, n) || <span className="ret-missing">Not chosen yet</span>}</dd>
                    <button type="button" className="link small" onClick={() => go(n)}>
                      Edit
                    </button>
                  </div>
                ))}
              </dl>
              <p className="ret-note">{R.condition}</p>
              <div className="ret-submit-row">
                <button type="submit" className="btn btn-primary" data-stage-part="return:submit" data-dock-avoid>
                  Submit return
                </button>
                <p className="small">{persona.name} only submits after you say yes.</p>
              </div>
            </>,
          )}
        </form>

        <aside className="ret-aside" aria-label="Your return">
          <div className="ret-order-card" data-stage-thing={`order-card:${order.number}`} data-stage-label={`Order ${order.number}`}>
            <p className="ret-order-k">
              <PackageCheck size={15} aria-hidden /> Order {order.number}
            </p>
            <p className="ret-order-v">Delivered {dayLabel(-(order.delivered_days_ago ?? 0))}</p>
            <p className="small">
              {daysLeft} day{daysLeft === 1 ? "" : "s"} left in the {RETURN_WINDOW_DAYS}-day return window
            </p>
            <ul className="ret-order-thumbs">
              {order.lines.map((l) => {
                const p = getProduct(l.product_id);
                const on = !!form.items[l.product_id];
                return (
                  <li key={l.product_id} className={on ? "is-on" : undefined} title={p?.title ?? l.title}>
                    {p ? <Photo file={p.images[0]} alt={p.title} sizes="56px" /> : null}
                    {on ? <span className="ret-thumb-qty">{form.items[l.product_id]}</span> : null}
                  </li>
                );
              })}
            </ul>
          </div>
          <ol className="ret-progress" aria-label="Steps">
            {STEPS.map((s) => {
              const reached = s.n <= form.reached;
              return (
                <li key={s.n} aria-current={form.step === s.n ? "step" : undefined} className={isDone(s.n) ? "is-done" : reached ? "is-reached" : undefined}>
                  <button type="button" onClick={() => go(s.n)} disabled={!reached}>
                    <span className="ret-step-n">{isDone(s.n) && form.step !== s.n ? <Check size={12} strokeWidth={2.6} /> : s.n}</span>
                    <span>{s.title}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </aside>
      </div>
      <PolicyInShort rows={RETURN_POLICY} links={[["/policy/returns", "Read the full returns policy"]]} />
    </div>
  );
}

// ── /orders/return/confirmation?ref=… ──────────────────────────────────────

export function ReturnConfirmation() {
  useTitle("Return submitted");
  const location = useLocation();
  const [sp] = useSearchParams();
  const ref = sp.get("ref");
  const r = (location.state as StoredReturn | null) ?? storedReturns().find((x) => x.reference === ref) ?? null;
  if (!r) return <Navigate to="/orders" replace />;
  return (
    <div className="wrap page-pad confirmation">
      <div className="confirm-hero">
        <CheckCircle2 size={34} strokeWidth={1.4} aria-hidden />
        <p className="small">Return reference</p>
        <p className="return-ref">{r.reference}</p>
        <h1 className="h1">Your return is in.</h1>
        <p className="lede">We confirm the return and agree how it comes back to us.</p>
      </div>
      <div className="confirm-grid">
        <section className="summary-card">
          <h2 className="h3">Returning from {r.order_number}</h2>
          <ul className="summary-lines">
            {r.items.map((it) => {
              const p = getProduct(it.product_id);
              return (
                <li key={it.product_id}>
                  <span className="summary-thumb">
                    {p ? <Photo file={p.images[0]} alt="" sizes="56px" /> : null}
                    <span className="summary-qty">{it.qty}</span>
                  </span>
                  <span className="summary-title">
                    {it.title}
                    <span className="small">
                      {it.variant}
                      {it.exchange_to ? `, exchanging for ${it.exchange_to}` : ""}
                    </span>
                  </span>
                  <span />
                </li>
              );
            })}
          </ul>
          <dl className="fd-policy-list is-tight">
            <div>
              <dt>Reason</dt>
              <dd>
                {labelOf("reason", r.reason)} · {labelOf("condition", r.condition)}
              </dd>
            </div>
            <div>
              <dt>Resolution</dt>
              <dd>{labelOf("resolution", r.resolution)}</dd>
            </div>
            <div>
              <dt>Collection</dt>
              <dd>{[labelOf("collection", r.collection), labelOf("pickup_window", r.pickup_window)].filter(Boolean).join(", ")}</dd>
            </div>
          </dl>
        </section>
        <section className="summary-card">
          <h2 className="h3">What happens next</h2>
          <dl className="fd-policy-list is-tight">
            <div>
              <dt>Condition</dt>
              <dd>{R.condition}</dd>
            </div>
            <div>
              <dt>Refunds</dt>
              <dd>{R.refund}</dd>
            </div>
          </dl>
          <p className="small">This is a demo store: the return is kept in this browser only and nothing is collected.</p>
          <div className="hero-ctas">
            <Link to={`/orders?order=${r.order_number}`} className="btn btn-ghost">
              Back to your orders
            </Link>
            <Link to="/" className="link small">
              Keep shopping
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}

/** @deprecated The old route names, until App.tsx moves to the new ones. */
/** @deprecated */
/** @deprecated */

