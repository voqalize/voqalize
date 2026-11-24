/**
 * The quote builder: the product's fields, its add-ons as toggle cards, and the
 * live breakdown. Every control calls the quote store's actions, the same ones
 * the `quote.*` performers call.
 */
import { Check, Info, Lock, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { PRODUCT_IDS, PRODUCT_SHORT, productById, quoteOptions } from "../data";
import type { ProductId, QuoteField } from "../data/types";
import { ProductIcon } from "../components/bits";
import { groupIndian, inWords, inr } from "../lib/format";
import { addonImpact, checkValue, openQuote, quoteFor, resetQuote, setAddon, setAnswer, useQuote } from "../state/quote";

export function QuoteTabs({ product }: { product: ProductId }) {
  return (
    <div className="quote-tabs" role="tablist" aria-label="Product">
      {PRODUCT_IDS.map((p) => (
        <Link
          key={p}
          to={`/quote/${p}`}
          role="tab"
          aria-selected={p === product}
          className={`quote-tab${p === product ? " is-on" : ""}`}
          data-stage-part={`quote-tab:${p}`}
        >
          <ProductIcon product={p} size={18} /> <span>{PRODUCT_SHORT[p]}</span>
        </Link>
      ))}
    </div>
  );
}

export function QuoteBuilder({ product, title }: { product: ProductId; title?: string }) {
  const spec = productById(product)!;
  useEffect(() => openQuote(product), [product]);
  const state = useQuote();
  const answers = state.answers[product];
  const on = state.addons[product];
  const q = quoteFor(product, state);
  const flash = state.last && state.last.product === product ? state.last : null;
  const required = spec.fields.filter((f) => !f.optional);
  const done = required.filter((f) => !q.missing.includes(f.id)).length;

  return (
    <div className="builder" data-stage-part="quote-builder">
      <div className="builder-main">
        <div className="builder-head">
          <div>
            <p className="eyebrow">{spec.plan}</p>
            <h2 className="h3">{title ?? `Your ${spec.name.toLowerCase()} quote`}</h2>
          </div>
          <div className="builder-progress" aria-label={`${done} of ${required.length} details given`}>
            <span className="meter"><span style={{ width: `${(done / required.length) * 100}%` }} /></span>
            <span className="small muted">
              {done}/{required.length} details
            </span>
            <button type="button" className="link-btn small" onClick={() => resetQuote(product)}>
              <RotateCcw size={13} aria-hidden /> Start over
            </button>
          </div>
        </div>
        <div className="field-grid">
          {spec.fields.map((f) => (
            <FieldControl
              key={f.id}
              product={product}
              field={f}
              value={answers[f.id] ?? ""}
              flash={flash?.id === f.id ? flash.n : 0}
            />
          ))}
        </div>
        <h3 className="addons-h">
          Add-ons <span className="muted small">{product === "term" ? "riders, priced per year" : "switch on what you need"}</span>
        </h3>
        <div className="addon-grid" data-stage-group>
          {spec.addons.map((a) => {
            const isOn = on.includes(a.id);
            const why = q.unavailable[a.id];
            const price = why ? null : addonImpact(product, a.id, state);
            return (
              <button
                key={a.id}
                type="button"
                role="switch"
                aria-checked={isOn && !why}
                disabled={!!why}
                className={`addon${isOn && !why ? " is-on" : ""}${why ? " is-off" : ""}${flash?.id === a.id ? " is-flash" : ""}`}
                data-stage-part={`addon:${a.id}`}
                onClick={() => setAddon(product, a.id, !isOn)}
              >
                <span className="addon-toggle" aria-hidden>
                  {why ? <Lock size={12} /> : isOn ? <Check size={13} strokeWidth={3} /> : null}
                </span>
                <span className="addon-text">
                  <span className="addon-label">{a.label}</span>
                  {why ? (
                    <span className="addon-why">Not available: {why}</span>
                  ) : (
                    <span className="addon-price">
                      {price === null ? "Priced once your details are in" : `${isOn ? "" : "+"}${inr(price)} a year`}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <Breakdown product={product} />
    </div>
  );
}

function FieldControl({ product, field: f, value, flash }: { product: ProductId; field: QuoteField; value: string; flash: number }) {
  const checked = value ? checkValue(f, value) : null;
  const error = checked && !checked.ok ? checked.why : null;
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!flash || !ref.current) return;
    ref.current.classList.remove("is-flash");
    void ref.current.offsetWidth;
    ref.current.classList.add("is-flash");
  }, [flash]);
  const id = `qf-${product}-${f.id}`;
  const small = f.type === "integer" && f.min !== undefined && f.max !== undefined && f.max - f.min <= 5;
  const opts = small
    ? Array.from({ length: f.max! - f.min! + 1 }, (_, i) => {
        const v = String(f.min! + i);
        return { value: v, label: f.id === "claim_free_years" && f.max === f.min! + i ? `${v}+` : v };
      })
    : quoteOptions(f);
  const segmented = small || (f.type === "select" && !f.options_from && opts.length <= 4);
  const wide = f.type === "text" || (segmented && opts.length >= 4 && opts.some((o) => o.label.length > 14));
  return (
    <div ref={ref} className={`field${wide ? " field-wide" : ""}${error ? " has-error" : ""}${value ? " is-filled" : ""}`} data-stage-part={`quote-field:${f.id}`}>
      <label className="field-label" htmlFor={segmented ? undefined : id} id={`${id}-l`}>
        {f.label}
        {f.optional ? <span className="muted"> (optional)</span> : null}
      </label>
      {segmented ? (
        <div className="seg" role="radiogroup" aria-labelledby={`${id}-l`}>
          {opts.map((o) => (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={value === o.value}
              className={`seg-btn${value === o.value ? " is-on" : ""}`}
              onClick={() => setAnswer(product, f.id, o.value)}
            >
              {o.label}
            </button>
          ))}
        </div>
      ) : f.type === "select" ? (
        <select id={id} className="input" value={value} onChange={(e) => setAnswer(product, f.id, e.target.value)}>
          <option value="" disabled>
            Choose…
          </option>
          {opts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : f.type === "money" ? (
        <div className="input-affix">
          <span aria-hidden>₹</span>
          <input
            id={id}
            className="input"
            inputMode="numeric"
            autoComplete="off"
            value={value ? groupIndian(Number(value)) : ""}
            placeholder={f.min ? groupIndian(f.min) : "0"}
            onChange={(e) => setAnswer(product, f.id, e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, ""))}
          />
        </div>
      ) : f.type === "integer" ? (
        <input
          id={id}
          className="input"
          inputMode="numeric"
          autoComplete="off"
          value={value}
          placeholder={f.min !== undefined && f.max !== undefined ? `${f.min}–${f.max}` : ""}
          onChange={(e) => setAnswer(product, f.id, e.target.value.replace(/\D/g, ""))}
        />
      ) : (
        <input id={id} className="input" value={value} autoComplete="off" onChange={(e) => setAnswer(product, f.id, e.target.value)} />
      )}
      {error ? (
        <p className="field-error">{error}</p>
      ) : f.type === "money" && value ? (
        <p className="field-hint">{inWords(Number(value))}</p>
      ) : null}
    </div>
  );
}

/** A number that counts to its new value. */
function Count({ value }: { value: number }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || a === value) {
      setShown(value);
      from.current = value;
      return;
    }
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / 520);
      const e = 1 - (1 - k) ** 3;
      setShown(Math.round(a + (value - a) * e));
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      from.current = value;
    };
  }, [value]);
  return <>{inr(shown)}</>;
}

export function Breakdown({ product }: { product: ProductId }) {
  const spec = productById(product)!;
  const state = useQuote();
  const q = quoteFor(product, state);
  const labelOf = (id: string) => spec.fields.find((f) => f.id === id)?.label ?? id;
  return (
    <aside className="breakdown" data-stage-part="breakdown" aria-live="polite" aria-label="Premium breakdown">
      <div className="bd-head">
        <p className="bd-title">Premium breakdown</p>
        <p className="small muted">{spec.plan} · 1 year</p>
      </div>
      {q.idv !== undefined ? (
        <div className="bd-idv">
          <span>
            Insured declared value (IDV)
            <span className="tip" title="What we would pay if the vehicle were stolen or a total loss: the ex-showroom price less depreciation for its age.">
              <Info size={13} aria-hidden />
            </span>
          </span>
          <strong>
            <Count value={q.idv} />
          </strong>
        </div>
      ) : null}
      {q.error ? (
        <div className="bd-error" role="alert">
          <strong>We can’t price this yet.</strong> {q.error.charAt(0).toUpperCase() + q.error.slice(1)}.
        </div>
      ) : null}
      <ul className="bd-lines">
        {q.lines.map((l) => (
          <li key={l.id} className={`bd-line${l.amount < 0 ? " is-discount" : ""}${l.id.startsWith("addon:") ? " is-addon" : ""}`}>
            <span>{l.label}</span>
            <span className="num">
              <Count value={l.amount} />
            </span>
          </li>
        ))}
        {!q.complete && !q.error ? <li className="bd-placeholder">Lines appear as you fill in your details.</li> : null}
      </ul>
      {q.complete ? (
        <>
          <div className="bd-sub">
            <span>Net premium</span>
            <span className="num">
              <Count value={q.net} />
            </span>
          </div>
          {q.gst_percent ? (
            <div className="bd-sub">
              <span>GST ({q.gst_percent}%)</span>
              <span className="num">
                <Count value={q.gst} />
              </span>
            </div>
          ) : (
            <p className="bd-note">GST: nil — individual {product === "term" ? "life" : "health"} premiums are exempt</p>
          )}
          <div className="bd-total">
            <span>Total payable (1 year)</span>
            <strong className="num">
              <Count value={q.total} />
            </strong>
          </div>
          <button type="button" className="btn btn-primary btn-block" data-dock-avoid disabled title="Chhatri Insurance is fictional and sells no policies">
            Continue to buy
          </button>
          <p className="bd-fine">Illustrative premium from the demo’s rating tables. Not an offer of insurance.</p>
        </>
      ) : (
        <div className="bd-missing">
          <p className="bd-missing-h">Still needed</p>
          <ul>
            {q.missing.map((id) => (
              <li key={id}>{labelOf(id)}</li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}
