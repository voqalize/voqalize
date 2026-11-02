/**
 * The returns desk: a start page, a six-step form Emily helps fill through
 * Stage, and a confirmation. The form works entirely by hand; with a call
 * live, Emily's moves (src/stage/performers.ts) set the same fields as she
 * says them, and the shopper always presses Submit return themselves.
 */
import * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, CheckCircle2, Mic, PackageCheck } from "lucide-react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { watchForms } from "@voqalize/stage";
import { getProduct, money } from "../data/catalog";
import { policies } from "../data/content";
import { Crumbs, EmilyTag, Photo } from "../components/bits";
import {
  CHOICES,
  type ChoiceField,
  type DemoOrder,
  allOrders,
  RETURN_WINDOW_DAYS,
  STEP_FIELDS,
  STEPS,
  eligibility,
  exchangeOptions,
  findOrder,
  labelOf,
  normalOrderNumber,
} from "../returns/orders";
import { type StoredReturn, currentOrder, filledNames, missingInStep, saveReturn, storedReturns, useReturns } from "../returns/store";
import { useVoiceClient } from "../stage/client";
import { useOrders } from "../state/orders";
import { useAppStage, useMove, useSlice } from "../stage/host";
import { returnsPerformers } from "../stage/performers";
import { scene } from "../stage/scene.gen";
import { navigatedBy } from "../voice/controller";
import { voiceReady } from "../voice/VoiceDock";
import { useTitle } from "./usePage";

const R = policies.returns as Record<string, string>;

// ── /returns ───────────────────────────────────────────────────────────────

function EmilyCta({ label = "Start a return with Emily" }: { label?: string }) {
  const begin = useVoiceClient((s) => s.begin);
  const live = useVoiceClient((s) => s.live);
  const ready = voiceReady();
  return (
    <div className="emily-cta">
      <button type="button" className="btn emily-btn" disabled={!ready || !begin || live} onClick={() => begin?.()}>
        <Mic size={18} /> {live ? "Emily is listening" : label}
      </button>
      <p className="small">
        {ready
          ? live
            ? "Tell her your order number. She fills the form with you; you press Submit."
            : "Tell Emily your order number. She checks it against the policy and fills the form with you; you press Submit."
          : "Voice is coming soon on this preview. The form below works by hand."}
      </p>
    </div>
  );
}

export function ReturnsHome() {
  useTitle("Returns");
  const navigate = useNavigate();
  const [number, setNumber] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const placed = useOrders((s) => s.orders);
  const orders = useMemo(() => allOrders(placed), [placed]);
  const find = (e: React.FormEvent) => {
    e.preventDefault();
    const order = findOrder(number);
    if (!order || order.email.toLowerCase() !== email.trim().toLowerCase()) {
      setError("We could not find an order with that number and email. Check both and try again.");
      return;
    }
    useReturns.getState().reset(order.number);
    useReturns.getState().setEmail(email.trim());
    navigate(`/returns/start?order=${order.number}`);
  };
  return (
    <div className="wrap page-pad returns">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Returns" }]} />
      <header className="returns-hero">
        <div>
          <h1 className="h1">Start a return</h1>
          <p className="lede">
            You have {RETURN_WINDOW_DAYS} days from delivery to send back anything unused. Find your order and we walk you through it,
            one step at a time.
          </p>
        </div>
        <EmilyCta />
      </header>

      <div className="returns-grid">
        <section className="returns-card" aria-labelledby="find-h">
          <h2 className="h3" id="find-h">
            Find your order
          </h2>
          <form className="returns-find" onSubmit={find} noValidate>
            <div className="field">
              <label htmlFor="rf-number">Order number</label>
              <input id="rf-number" className="input" placeholder="FH-20418" value={number} onChange={(e) => setNumber(e.target.value)} autoComplete="off" />
            </div>
            <div className="field">
              <label htmlFor="rf-email">Email used for the order</label>
              <input id="rf-email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </div>
            {error ? (
              <p className="form-error" role="alert">
                <AlertCircle size={15} aria-hidden /> {error}
              </p>
            ) : null}
            <button type="submit" className="btn btn-primary" data-dock-avoid>
              Find order
            </button>
          </form>
          <div className="demo-orders">
            <p className="small">{placed.length ? "Your orders from this browser, then the demo orders:" : "This is a demo store. Try one of these orders:"}</p>
            <ul>
              {orders.map((o) => (
                <li key={o.number}>
                  <button
                    type="button"
                    className="demo-order"
                    onClick={() => {
                      setNumber(o.number);
                      setEmail(o.email);
                      setError("");
                    }}
                  >
                    <span className="demo-order-n">{o.number}</span>
                    {"placed" in o ? <span className="demo-order-yours">Yours</span> : null}
                    <span className="small">{orderHint(o)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="returns-policy" aria-labelledby="policy-h">
          <h2 className="h3" id="policy-h">
            The policy, in short
          </h2>
          <dl className="policy-list">
            <div>
              <dt>Window</dt>
              <dd>{R.window}</dd>
            </div>
            <div>
              <dt>Condition</dt>
              <dd>{R.condition}</dd>
            </div>
            <div>
              <dt>Refunds</dt>
              <dd>{R.refund}</dd>
            </div>
            <div>
              <dt>Not returnable</dt>
              <dd>{R.notReturnable}</dd>
            </div>
            <div>
              <dt>Damaged or faulty</dt>
              <dd>{R.damagedOrFaulty}</dd>
            </div>
          </dl>
          <Link to="/policy/returns" className="link small">
            Read the full returns policy
          </Link>
        </section>
      </div>
    </div>
  );
}

function orderHint(o: DemoOrder): string {
  const e = eligibility(o);
  const items = o.lines.reduce((n, l) => n + l.qty, 0);
  const what = `${items} item${items === 1 ? "" : "s"}`;
  if (e.kind === "not_delivered") return `${what}, on its way`;
  if (e.kind === "outside_window") return `${what}, delivered ${e.days} days ago`;
  return o.delivered_days_ago === 0 ? `${what}, placed today` : `${what}, delivered ${o.delivered_days_ago} days ago`;
}

// ── /returns/start ─────────────────────────────────────────────────────────

export function ReturnsForm() {
  useTitle("Start a return");
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const form = useReturns();
  const placedOrders = useOrders((s) => s.orders);
  const order = currentOrder(form);
  const [emailError, setEmailError] = useState("");
  const [stepError, setStepError] = useState("");

  // A link (or Emily's start_return) names the order: begin with it.
  useEffect(() => {
    const asked = sp.get("order");
    if (asked && normalOrderNumber(asked) !== normalOrderNumber(useReturns.getState().order_number)) {
      useReturns.getState().reset(normalOrderNumber(asked), navigatedBy());
    } else if (!asked && !useReturns.getState().order_number) {
      useReturns.getState().setStep(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp.get("order")]);

  // Stage on the call's client (attached in the shell), when there is one.
  const stage = useAppStage((s) => s.stage);
  const performers = useMemo(() => returnsPerformers(), []);
  useMove(stage, "returns.open_step", performers["returns.open_step"]);
  useMove(stage, "returns.fill", performers["returns.fill"]);
  useMove(stage, "returns.select_item", performers["returns.select_item"]);
  useMove(stage, "returns.submit", performers["returns.submit"]);
  useMove(stage, "returns.find", performers["returns.find"]);
  useMove(stage, "returns.next_step", performers["returns.next_step"]);

  const filled = filledNames(form);
  const slice = useMemo(() => ({ step: form.step, changed: form.changed, filled }), [form.step, form.changed, filled.join(",")]);
  useSlice(stage, slice, (prev, next) => {
    if (!prev) return null;
    if (prev.step !== next.step) return ["returns.step_reached", { step: next.step, filled: next.filled }] as const;
    if (next.changed && next.changed.stamp !== prev.changed?.stamp) {
      return ["returns.field_filled", { field: next.changed.field, filled: next.filled }] as const;
    }
    return null;
  });

  // The watch kit: what the shopper fills, by field name only.
  useEffect(() => {
    if (!stage) return;
    return watchForms((s) => stage.page.send(scene.event("form.changed", s)));
  }, [stage]);

  // A step left untouched for a while: Emily may offer to fill it in.
  const stepEmpty = (STEP_FIELDS[form.step] ?? []).every((f) => !filled.includes(f));
  const offered = useRef(new Set<number>());
  useEffect(() => {
    if (!stage || !stepEmpty || form.step === 6 || offered.current.has(form.step)) return;
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
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("input", typing, true);
    };
  }, [stage, form.step, stepEmpty]);

  const elig = order ? eligibility(order) : null;
  const chosen = order?.lines.filter((l) => form.items[l.product_id]) ?? [];

  /** What each step needs before Continue. */
  const missing = (step: number): string => missingInStep(form, step);

  const go = (step: number) => {
    setStepError("");
    useReturns.getState().setStep(step);
    requestAnimationFrame(() => document.querySelector(`[data-stage-thing="step-${step}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" }));
  };
  const next = (step: number) => {
    const why = missing(step);
    if (why) {
      setStepError(why);
      if (step === 1 && why.includes("email")) setEmailError(why);
      return;
    }
    setEmailError("");
    go(step + 1);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    for (let s = 1; s <= 5; s++) {
      const why = missing(s);
      if (why) {
        go(s);
        setStepError(why);
        return;
      }
    }
    if (!order) return;
    const stored = saveReturn({
      order_number: order.number,
      items: chosen.map((l) => ({
        product_id: l.product_id,
        title: getProduct(l.product_id)?.title ?? l.title,
        variant: l.variant,
        qty: form.items[l.product_id],
        ...(form.resolution === "exchange" && form.exchange[l.product_id] ? { exchange_to: form.exchange[l.product_id] } : {}),
      })),
      reason: form.reason,
      condition: form.condition,
      resolution: form.resolution,
      collection: form.collection,
      pickup_window: form.pickup_window,
    });
    const agent = stage?.agent && Date.now() <= stage.agent.until ? stage.agent : null;
    stage?.page.send(
      scene.event("returns.return_submitted", { reference: stored.reference, filled }, agent ? { by: "agent", callRef: agent.callRef } : { by: "visitor" }),
    );
    useReturns.getState().reset();
    navigate(`/returns/confirmation?ref=${stored.reference}`, { state: stored });
  };

  const tag = (field: string) => (form.by[field] === "emily" ? <EmilyTag /> : null);

  const summary = (step: number): string => {
    switch (step) {
      case 1:
        return order ? `${order.number}, ${order.name}` : "";
      case 2:
        return chosen.map((l) => `${form.items[l.product_id]} × ${getProduct(l.product_id)?.title ?? l.title}`).join(", ");
      case 3:
        return [labelOf("reason", form.reason), labelOf("condition", form.condition)].filter(Boolean).join(", ");
      case 4:
        return [
          labelOf("resolution", form.resolution),
          ...(form.resolution === "exchange" ? chosen.filter((l) => form.exchange[l.product_id]).map((l) => `${l.variant} to ${form.exchange[l.product_id]}`) : []),
        ]
          .filter(Boolean)
          .join(", ");
      case 5:
        return [labelOf("collection", form.collection), labelOf("pickup_window", form.pickup_window)].filter(Boolean).join(", ");
      default:
        return "";
    }
  };

  const choiceGroup = (field: ChoiceField, legend: string) => (
    <fieldset className="choice-group">
      <legend className="option-name">
        {legend} {tag(field)}
      </legend>
      <div className="choice-cards">
        {CHOICES[field].map(([value, label]) => (
          <label key={value} className={`choice${form[field] === value ? " is-on" : ""}`} data-stage-part={`${field}:${value}`}>
            <input type="radio" name={field} value={value} checked={form[field] === value} onChange={() => useReturns.getState().setChoice(field, value)} required />
            <span className="choice-dot" aria-hidden />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );

  const renderStep = (n: number, children: React.ReactNode) => {
    const open = form.step === n;
    const done = n < 6 && !missing(n) && summary(n);
    return (
      <section className={`rstep${open ? " is-open" : ""}${done ? " is-done" : ""}`} data-stage-thing={`step-${n}`} data-stage-label={STEPS[n - 1].title} aria-labelledby={`rstep-${n}`}>
        <header className="rstep-head">
          <span className="rstep-n" aria-hidden>
            {done && !open ? <Check size={14} /> : n}
          </span>
          <div className="rstep-title">
            <h2 className="h3" id={`rstep-${n}`}>
              {STEPS[n - 1].title}
            </h2>
            {!open && summary(n) ? <p className="small">{summary(n)}</p> : null}
          </div>
          {!open && (done || n < form.step) ? (
            <button type="button" className="link small" onClick={() => go(n)} aria-label={`Edit ${STEPS[n - 1].title}`}>
              Edit
            </button>
          ) : null}
        </header>
        {open ? (
          <div className="rstep-body">
            {children}
            {stepError ? (
              <p className="form-error" role="alert">
                <AlertCircle size={15} aria-hidden /> {stepError}
              </p>
            ) : null}
            {n < 6 ? (
              <div className="rstep-actions">
                {n > 1 ? (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => go(n - 1)}>
                    Back
                  </button>
                ) : null}
                <button type="button" className="btn btn-primary btn-sm" data-dock-avoid onClick={() => next(n)}>
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
    <div className="wrap page-pad returns">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Returns", to: "/returns" }, { label: "Start a return" }]} />
      <header className="returns-form-head">
        <h1 className="h1">Start a return</h1>
        <p className="lede">Six short steps. Nothing is sent until you press Submit return.</p>
      </header>
      <div className="returns-layout">
        <form className="rform" data-stage-form="Return" onSubmit={submit} noValidate aria-label="Return">
          {renderStep(1, <>
            <div className="co-grid">
              <div className="field">
                <label htmlFor="r-order">
                  Order number {tag("order_number")}
                </label>
                <input
                  id="r-order"
                  name="order_number"
                  className="input"
                  placeholder="FH-20418"
                  value={form.order_number}
                  onChange={(e) => useReturns.getState().setOrderNumber(e.target.value)}
                  autoComplete="off"
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="r-email">Email used for the order</label>
                <input
                  id="r-email"
                  name="email"
                  type="email"
                  className="input"
                  value={form.email}
                  aria-invalid={!!emailError}
                  onChange={(e) => useReturns.getState().setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>
            </div>
            {order ? <OrderCard order={order} /> : form.order_number.trim().length >= 6 ? <p className="small">No order with that number yet.</p> : null}
            {!order ? (
              <div className="known-orders">
                <p className="small">Your orders from this browser come first, then the demo orders:</p>
                <div className="band-chips">
                  {allOrders(placedOrders).slice(0, 6).map((o) => (
                    <button
                      key={o.number}
                      type="button"
                      className="chip chip-sm"
                      onClick={() => {
                        useReturns.getState().setOrderNumber(o.number);
                        useReturns.getState().setEmail(o.email);
                      }}
                    >
                      {o.number}
                      {"placed" in o ? " (yours)" : ""}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </>)}

          {renderStep(2, <>
            {order ? (
              <ul className="ritems">
                {order.lines.map((l) => {
                  const p = getProduct(l.product_id);
                  const qty = form.items[l.product_id] ?? 0;
                  const ok = elig?.kind === "eligible";
                  return (
                    <li key={l.product_id} className={`ritem${qty ? " is-on" : ""}`} data-stage-part={`items:${l.product_id}`}>
                      <label className="ritem-pick">
                        <input
                          type="checkbox"
                          name="items"
                          value={l.product_id}
                          checked={!!qty}
                          disabled={!ok}
                          onChange={(e) => useReturns.getState().setItem(l.product_id, e.target.checked ? 1 : 0)}
                        />
                        <span className="ritem-check" aria-hidden>
                          <Check size={13} />
                        </span>
                        {p ? <Photo file={p.images[0]} alt="" sizes="72px" /> : null}
                        <span className="ritem-text">
                          <span className="ritem-title">{p?.title ?? l.title}</span>
                          <span className="small">
                            {l.variant}, {money(l.unit_price)}, ordered {l.qty}
                          </span>
                        </span>
                      </label>
                      {qty && l.qty > 1 ? (
                        <label className="ritem-qty">
                          <span className="small">How many</span>
                          <select
                            className="select select-sm"
                            name={`qty_${l.product_id}`}
                            value={qty}
                            onChange={(e) => useReturns.getState().setItem(l.product_id, Number(e.target.value))}
                          >
                            {Array.from({ length: l.qty }, (_, i) => i + 1).map((n) => (
                              <option key={n} value={n}>
                                {n}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                      {qty && form.by[`qty_${l.product_id}`] === "emily" ? <EmilyTag /> : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="small">Find your order first.</p>
            )}
          </>)}

          {renderStep(3, <>
            {choiceGroup("reason", "Why are you returning it?")}
            {form.reason === "arrived_damaged" ? <p className="policy-note">{R.damagedOrFaulty}</p> : null}
            {choiceGroup("condition", "What condition is it in?")}
            <p className="policy-note">{R.condition}</p>
          </>)}

          {renderStep(4, <>
            {choiceGroup("resolution", "What would you like instead?")}
            {form.resolution === "exchange" ? (
              <div className="exchange">
                {chosen.length === 0 ? <p className="small">Choose the items to exchange in step 2.</p> : null}
                {chosen.map((l) => {
                  const options = exchangeOptions(l);
                  const field = `exchange_variant_${l.product_id}`;
                  return (
                    <fieldset key={l.product_id} className="choice-group">
                      <legend className="option-name">
                        {getProduct(l.product_id)?.title ?? l.title}: swap {l.variant} for {tag(field)}
                      </legend>
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
                    </fieldset>
                  );
                })}
              </div>
            ) : null}
            {form.resolution === "refund" ? <p className="policy-note">{R.refund}</p> : null}
          </>)}

          {renderStep(5, <>
            {choiceGroup("collection", "How should it come back to us?")}
            {form.collection === "pickup" ? choiceGroup("pickup_window", "When suits you for collection?") : null}
            <p className="policy-note">{R.howToStart}</p>
          </>)}

          {renderStep(6, <>
            {order ? (
              <dl className="review-list">
                {[1, 2, 3, 4, 5].map((n) => (
                  <div key={n}>
                    <dt>{STEPS[n - 1].title}</dt>
                    <dd>{summary(n) || <span className="missing">Not filled in yet</span>}</dd>
                    <button type="button" className="link small" onClick={() => go(n)}>
                      Edit
                    </button>
                  </div>
                ))}
              </dl>
            ) : null}
            <p className="policy-note">{R.condition}</p>
            <button type="submit" className="btn btn-primary co-next" data-dock-avoid>
              Submit return
            </button>
            <p className="small">Emily only submits after you say yes.</p>
          </>)}
        </form>

        <aside className="returns-aside">
          <EmilyCta label="Fill this in with Emily" />
          <ol className="rprogress" aria-label="Steps">
            {STEPS.map((s) => (
              <li key={s.n} aria-current={form.step === s.n ? "step" : undefined} className={!missing(s.n) && summary(s.n) ? "is-done" : undefined}>
                <button type="button" onClick={() => go(s.n)}>
                  <span className="rstep-n">{s.n}</span> {s.title}
                </button>
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  );
}

function OrderCard({ order }: { order: DemoOrder }) {
  const e = eligibility(order);
  return (
    <div className={`order-card is-${e.kind}`} data-stage-thing="order" data-stage-label={`Order ${order.number}`}>
      <div className="order-card-head">
        <PackageCheck size={18} aria-hidden />
        <p>
          <strong>{order.number}</strong> for {order.name}, {money(order.total)}
        </p>
      </div>
      <p className="small">
        {e.kind === "eligible"
          ? `Delivered ${order.delivered_days_ago} days ago. You have ${e.daysLeft} days left to start a return.`
          : e.kind === "outside_window"
            ? `Delivered ${e.days} days ago, outside the ${RETURN_WINDOW_DAYS}-day window, so it cannot be returned. Our care guides may help, or write to us from the contact page.`
            : "Not delivered yet. You can start a return once it arrives."}
      </p>
      {e.kind === "outside_window" ? (
        <p className="small">
          <Link className="link" to="/policy/care">
            Care guides
          </Link>{" "}
          <Link className="link" to="/contact">
            Contact the studio
          </Link>
        </p>
      ) : null}
    </div>
  );
}

// ── /returns/confirmation ──────────────────────────────────────────────────

export function ReturnsConfirmation() {
  useTitle("Return submitted");
  const location = useLocation();
  const [sp] = useSearchParams();
  const ref = sp.get("ref");
  const r = (location.state as StoredReturn | null) ?? storedReturns().find((x) => x.reference === ref) ?? null;
  if (!r) return <Navigate to="/returns" replace />;
  return (
    <div className="wrap page-pad confirmation">
      <div className="confirm-hero">
        <CheckCircle2 size={34} strokeWidth={1.4} aria-hidden />
        <p className="small">Return reference</p>
        <p className="return-ref">{r.reference}</p>
        <h1 className="h1">Your return is in.</h1>
        <p className="lede">{R.howToStart}</p>
      </div>
      <div className="confirm-grid">
        <section className="summary-card">
          <h2 className="h3">Returning</h2>
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
          <dl className="policy-list policy-list-tight">
            <div>
              <dt>Reason</dt>
              <dd>{labelOf("reason", r.reason)}</dd>
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
          <dl className="policy-list policy-list-tight">
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
            <Link to="/" className="btn btn-ghost">
              Keep shopping
            </Link>
            <Link to="/returns" className="link small">
              Start another return
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
