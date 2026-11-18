import { ChevronRight, Sparkles } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { type CreditCardProduct, customer } from "../data/bank";
import { useSession } from "../state/session";
import {
  type FormId,
  choiceLabel,
  choicesOf,
  fieldDef,
  invalid,
  maskAadhaar,
  maskPan,
  useForms,
} from "../state/forms";

export function Crumbs({ items }: { items: { to?: string; label: string }[] }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <ol>
        <li>
          <Link to="/">Home</Link>
        </li>
        {items.map((it) => (
          <li key={it.label}>
            <ChevronRight size={13} aria-hidden />
            {it.to ? <Link to={it.to}>{it.label}</Link> : <span aria-current="page">{it.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** A credit card's face, in its own colour. */
export function CardFace({ card, size = "md" }: { card: CreditCardProduct; size?: "sm" | "md" | "lg" }) {
  return (
    <div className={`card-face card-face-${size}`} style={{ ["--card" as string]: card.color }} role="img" aria-label={`${card.name} card`}>
      <div className="cf-top">
        <span className="cf-brand">Anvaya</span>
        <span className="cf-tier">{card.tier}</span>
      </div>
      <div className="cf-chip" aria-hidden />
      <div className="cf-bottom">
        <span className="cf-name">{card.name.replace("Anvaya ", "")}</span>
        <span className="cf-network">{card.network}</span>
      </div>
    </div>
  );
}

/** The signed-in customer's offers of one kind, as a cross-sell banner. */
export function OfferBanner({ kind }: { kind: "loan" | "card" }) {
  const signedIn = useSession((s) => s.signedIn);
  if (!signedIn) return null;
  const offers = customer.offers.filter((o) => o.kind === kind);
  if (!offers.length) return null;
  return (
    <>
      {offers.map((o) => (
        <aside key={o.id} className="offer-banner" data-stage-thing={`offer:${o.id}`} data-stage-label={o.title}>
          <Sparkles size={18} aria-hidden className="offer-icon" />
          <div>
            <p className="offer-title">
              {o.title}, for {customer.profile.first_name}
            </p>
            <p className="offer-line">{o.line}</p>
          </div>
          <Link className="btn btn-sm btn-accent" to={o.kind === "card" ? `/cards/${o.card_id}` : "/app/offers"}>
            {o.kind === "card" ? "See the card" : "View offer"}
          </Link>
        </aside>
      ))}
    </>
  );
}

/** One field of a public form, by its contract name. */
export function FormField({ form, name, wide = false, autoFocus = false }: { form: FormId; name: string; wide?: boolean; autoFocus?: boolean }) {
  const def = fieldDef(form, name)!;
  const value = useForms((s) => s.values[form][name] ?? "");
  const error = useForms((s) => s.errors[form][name]);
  const setField = useForms((s) => s.setField);
  const allValues = useForms((s) => s.values[form]);
  const [focus, setFocus] = useState(false);
  const [touched, setTouched] = useState(false);
  const choices = choicesOf(form, name);
  const id = `${form}-${name}`;
  const live = touched && !focus && value ? invalid(form, name, value, allValues) : null;
  const err = error ?? (live ? live.charAt(0).toUpperCase() + live.slice(1) : null);

  if (choices) {
    const many = choices.length > 4;
    return (
      <div className={`field${wide || many ? " field-wide" : ""}${err ? " has-error" : ""}`} data-stage-part={name} data-stage-thing={`field:${form}:${name}`} data-stage-label={def.label}>
        <span className="field-label" id={`${id}-label`}>
          {def.label}
        </span>
        <div className={`choice-group${many ? " is-wrap" : ""}`} role="radiogroup" aria-labelledby={`${id}-label`}>
          {choices.map((c) => (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={value === c}
              className={`choice${value === c ? " is-on" : ""}`}
              data-stage-part={`${name}:${c}`}
              onClick={() => setField(form, name, c)}
            >
              {choiceLabel(name, c)}
            </button>
          ))}
        </div>
        {err ? <p className="field-error">{err}</p> : def.hint ? <p className="field-hint">{def.hint}</p> : null}
      </div>
    );
  }

  const masked = !focus && value && !invalid(form, name, value) ? (name === "pan" ? maskPan(value) : name === "aadhaar" ? maskAadhaar(value) : null) : null;
  const type = def.kind === "date" ? "date" : name === "email" ? "email" : "text";
  const inputMode = def.kind === "number" || def.kind === "digits" ? "numeric" : name === "email" ? "email" : undefined;
  return (
    <div className={`field${wide ? " field-wide" : ""}${err ? " has-error" : ""}`} data-stage-part={name} data-stage-thing={`field:${form}:${name}`} data-stage-label={def.label}>
      <label className="field-label" htmlFor={id}>
        {def.label}
      </label>
      <div className="input-wrap">
        {def.kind === "number" && name !== "tenure_months" && name !== "gold_grams" ? <span className="input-prefix">₹</span> : null}
        <input
          id={id}
          name={name}
          type={type}
          className={`input${def.kind === "number" && name !== "tenure_months" && name !== "gold_grams" ? " has-prefix" : ""}`}
          inputMode={inputMode}
          autoComplete="off"
          autoFocus={autoFocus}
          placeholder={def.placeholder}
          value={masked ?? value}
          aria-invalid={!!err}
          aria-describedby={err || def.hint ? `${id}-help` : undefined}
          onFocus={() => setFocus(true)}
          onBlur={() => {
            setFocus(false);
            setTouched(true);
          }}
          onChange={(e) => setField(form, name, e.target.value)}
        />
      </div>
      {err ? (
        <p className="field-error" id={`${id}-help`}>
          {err}
        </p>
      ) : def.hint ? (
        <p className="field-hint" id={`${id}-help`}>
          {def.hint}
        </p>
      ) : null}
    </div>
  );
}

/** A labelled slider with its own number box, for the calculators. */
export function SliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
  part,
  suffix,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (n: number) => void;
  format: (n: number) => string;
  part: string;
  suffix?: string;
}) {
  const id = `slider-${part}`;
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  return (
    <div className="slider-row" data-stage-part={part} data-stage-thing={`input:${part}`} data-stage-label={label}>
      <div className="slider-head">
        <label htmlFor={id}>{label}</label>
        <span className="slider-value num">{format(value)}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={Math.min(max, Math.max(min, value))}
        style={{ ["--pct" as string]: `${pct}%` }}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={format(value)}
      />
      <div className="slider-ends">
        <span>{format(min)}</span>
        <span>
          {format(max)}
          {suffix ?? ""}
        </span>
      </div>
    </div>
  );
}

export function Stat({ label, children, thing }: { label: string; children: ReactNode; thing?: string }) {
  return (
    <div className="stat" data-stage-thing={thing} data-stage-label={thing ? label : undefined}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** ₹ in lakh / crore words for big figures: 50,00,000 → ₹50 lakh. */
export function lakh(n: number): string {
  if (n >= 10000000) return `₹${+(n / 10000000).toFixed(2)} crore`;
  if (n >= 100000) return `₹${+(n / 100000).toFixed(2)} lakh`;
  return `₹${n.toLocaleString("en-IN")}`;
}
