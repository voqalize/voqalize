/**
 * /gifts: the gift finder. The brief (who it is for, the occasion, budget,
 * their size, colours, patterns, material) starts empty; "Show gift ideas"
 * runs the shared pick (`pickGifts`) by hand, or the agent shows its own
 * shortlist with a reason per card. Each idea goes to the bag (in their size,
 * when it is sized) and can be gift wrapped with a note there and then.
 */
import { Check, Gift, RotateCcw, ShoppingBag, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ProductCard } from "../components/ProductCard";
import { type Product, getProduct, index, inr, typeLabel, useCatalog } from "../data/catalog";
import { MATERIALS, PATTERNS } from "../data/gifts";
import { POLICY, STORE, lineKey } from "../data/shop";
import { sendEvent } from "../stage/host";
import { briefKey, useGifts } from "../state/gifts";
import { useStore } from "../state/store";

const SIZES = ["XS", "S", "M", "L", "XL", "XXL"];

/** The bag size label for a gift: the product's own label for their size, or its one size. */
const NO_COLOURS: Record<string, string> = {};

export function giftSize(p: Product, size?: string): string | null {
  if (p.scale === "one") return p.sizes.find(([, n]) => n > 0)?.[0] ?? p.sizes[0]?.[0] ?? null;
  if (!size) return null;
  const hit = p.sizes.find(([l, n]) => n > 0 && l.toUpperCase() === size.toUpperCase());
  return hit ? hit[0] : null;
}

function Chips({ field, options, value, onPick, label }: { field: string; options: string[]; value: string | undefined; onPick: (v: string | undefined) => void; label?: (v: string) => string }) {
  return (
    <div className="gf-chips" data-stage-part={`gifts:${field}`} role="radiogroup">
      {options.map((o) => (
        <button type="button" key={o} role="radio" aria-checked={value === o} data-value={o} className={`chip${value === o ? " is-on" : ""}`} onClick={() => onPick(value === o ? undefined : o)}>
          {label ? label(o) : o}
        </button>
      ))}
    </div>
  );
}

function Brief() {
  const { brief, noLimit, setBrief, setNoLimit, toggleIn, showByHand, reset } = useGifts();
  const colours = useCatalog((s) => s.index?.colours) ?? NO_COLOURS;
  const [custom, setCustom] = useState("");
  const preset = STORE.gifts.budgets.includes(brief.budget_max ?? -1);
  useEffect(() => {
    if (!brief.budget_max || preset) setCustom("");
    else setCustom(String(brief.budget_max));
  }, [brief.budget_max, preset]);
  const otherSize = brief.size && !SIZES.includes(brief.size) ? brief.size : "";
  const ready = !!brief.recipient;

  return (
    <form
      className="gf-brief"
      aria-label="Gift brief"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) showByHand();
      }}
    >
      <fieldset className="gf-field" data-stage-group>
        <legend>Who is it for?</legend>
        <Chips field="recipient" options={STORE.gifts.recipients} value={brief.recipient} onPick={(v) => setBrief({ recipient: v })} />
      </fieldset>
      <fieldset className="gf-field" data-stage-group>
        <legend>What's the occasion?</legend>
        <Chips field="occasion" options={STORE.gifts.occasions} value={brief.occasion} onPick={(v) => setBrief({ occasion: v })} />
      </fieldset>
      <fieldset className="gf-field" data-stage-group>
        <legend>Budget</legend>
        <div className="gf-chips" data-stage-part="gifts:budget" role="radiogroup">
          {STORE.gifts.budgets.map((b) => (
            <button type="button" key={b} role="radio" aria-checked={brief.budget_max === b} data-value={b} className={`chip${brief.budget_max === b ? " is-on" : ""}`} onClick={() => setBrief({ budget_max: brief.budget_max === b ? undefined : b })}>
              Under {inr(b)}
            </button>
          ))}
          <button type="button" role="radio" aria-checked={noLimit} data-value="0" className={`chip${noLimit ? " is-on" : ""}`} onClick={() => setNoLimit(!noLimit)}>
            No limit
          </button>
          <label className={`gf-amount${custom ? " is-on" : ""}`}>
            <span>₹</span>
            <input
              inputMode="numeric"
              placeholder="Other amount"
              aria-label="Other budget in rupees"
              value={custom}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 6);
                setCustom(v);
                setBrief({ budget_max: v ? Number(v) : undefined });
              }}
            />
          </label>
        </div>
      </fieldset>
      <fieldset className="gf-field" data-stage-group>
        <legend>
          Their size <span className="gf-opt">optional, for clothes and shoes</span>
        </legend>
        <div className="gf-chips" data-stage-part="gifts:size" role="radiogroup">
          {SIZES.map((s) => (
            <button type="button" key={s} role="radio" aria-checked={brief.size === s} data-value={s} className={`chip chip-sq${brief.size === s ? " is-on" : ""}`} onClick={() => setBrief({ size: brief.size === s ? undefined : s })}>
              {s}
            </button>
          ))}
          <input className={`gf-size-other${otherSize ? " is-on" : ""}`} placeholder="UK 7, 32…" aria-label="Other size" value={otherSize} onChange={(e) => setBrief({ size: e.target.value.slice(0, 8) || undefined })} />
        </div>
      </fieldset>
      <fieldset className="gf-field" data-stage-group>
        <legend>
          Colours they like <span className="gf-opt">{brief.colours?.length ? brief.colours.join(", ") : "any"}</span>
        </legend>
        <div className="gf-swatches" data-stage-part="gifts:colours">
          {Object.entries(colours)
            .filter(([name]) => name !== "NA")
            .map(([name, hex]) => {
              const on = !!brief.colours?.includes(name);
              return (
                <button
                  type="button"
                  key={name}
                  data-value={name}
                  title={name}
                  aria-label={name}
                  aria-pressed={on}
                  className={`gf-swatch${on ? " is-on" : ""}`}
                  style={{ background: hex === "conic" ? "conic-gradient(#d6246e, #f2a400, #1f7a4d, #2f5fb3, #d6246e)" : hex }}
                  onClick={() => toggleIn("colours", name)}
                >
                  {on ? <Check size={14} strokeWidth={3} /> : null}
                </button>
              );
            })}
        </div>
      </fieldset>
      <fieldset className="gf-field" data-stage-group>
        <legend>Patterns</legend>
        <div className="gf-chips" data-stage-part="gifts:patterns">
          {PATTERNS.map((p) => {
            const on = !!brief.patterns?.includes(p);
            return (
              <button type="button" key={p} aria-pressed={on} data-value={p} className={`chip${on ? " is-on" : ""}`} onClick={() => toggleIn("patterns", p)}>
                {p}
              </button>
            );
          })}
        </div>
      </fieldset>
      <fieldset className="gf-field" data-stage-group>
        <legend>Material</legend>
        <Chips field="material" options={MATERIALS} value={brief.material} onPick={(v) => setBrief({ material: v })} />
      </fieldset>
      <div className="gf-go">
        <button type="submit" className="btn btn-primary btn-lg" data-stage-part="gifts:show" data-dock-avoid disabled={!ready}>
          <Sparkles size={18} aria-hidden /> Show gift ideas
        </button>
        <button type="button" className="btn btn-ghost" onClick={reset}>
          <RotateCcw size={16} aria-hidden /> Start over
        </button>
        {!ready ? <p className="svc-muted small">Choose who it is for first.</p> : null}
      </div>
    </form>
  );
}

function GiftActions({ p }: { p: Product }) {
  const size = useGifts((s) => s.brief.size);
  const label = giftSize(p, size);
  const line = useStore((s) => (label ? s.bag.find((l) => lineKey(l.product_id, l.size) === lineKey(p.id, label)) : undefined));
  const add = useStore((s) => s.addToBag);
  const setGift = useStore((s) => s.setGift);
  if (!label) return <p className="gf-need">Add their size above to buy this one.</p>;
  if (!line) {
    return (
      <button type="button" className="btn btn-sm btn-dark gf-add" data-stage-part={`gift-add:${p.id}`} onClick={() => add(p.id, label)}>
        <ShoppingBag size={15} aria-hidden /> Add to bag{p.scale === "one" ? "" : ` · ${label}`}
      </button>
    );
  }
  return (
    <div className="gf-wrap">
      <p className="gf-in">
        <Check size={14} aria-hidden /> In your bag{p.scale === "one" ? "" : ` · size ${label}`}
      </p>
      <label className="gf-wrap-toggle" data-stage-part={`gift:${p.id}|${label}`}>
        <input type="checkbox" checked={line.gift} onChange={(e) => setGift(p.id, label, e.target.checked)} />
        <Gift size={15} aria-hidden /> Gift wrap +{inr(POLICY.gift_wrap.price)}
      </label>
      {line.gift ? (
        <textarea
          className="gf-note"
          rows={2}
          maxLength={POLICY.gift_wrap.note_max}
          placeholder={`A note, up to ${POLICY.gift_wrap.note_max} characters`}
          aria-label="Gift note"
          value={line.note}
          onChange={(e) => setGift(p.id, label, true, e.target.value)}
        />
      ) : null}
    </div>
  );
}

function Shortlist() {
  useCatalog((s) => s.index);
  const shown = useGifts((s) => s.shown);
  const brief = useGifts((s) => s.brief);
  const noLimit = useGifts((s) => s.noLimit);
  const showByHand = useGifts((s) => s.showByHand);
  const stale = shown && shown.brief !== briefKey(brief);
  const products = useMemo(() => (shown ? shown.ids.map((id) => getProduct(id)).filter((p): p is Product => !!p) : []), [shown, index()]);

  if (!shown) {
    return (
      <div className="gf-empty">
        <Gift size={30} aria-hidden />
        <h2>Ideas appear here</h2>
        <ol>
          <li>Tell us who it's for and the occasion.</li>
          <li>Set a budget, or don't worry about it.</li>
          <li>Add their size, colours, patterns or material if you know them.</li>
        </ol>
        <p className="svc-muted small">{POLICY.gift_wrap.summary}</p>
      </div>
    );
  }
  const title = [brief.recipient ? `for ${brief.recipient}` : null, brief.occasion, brief.budget_max ? `under ${inr(brief.budget_max)}` : noLimit ? "no limit" : null].filter(Boolean).join(" · ");
  return (
    <section className="gf-results" aria-live="polite" data-stage-thing="gifts:results">
      <header className="gf-results-head">
        <h2>
          {products.length ? `${products.length} gift ${products.length === 1 ? "idea" : "ideas"}` : "No ideas yet"} <span>{title}</span>
        </h2>
        {stale ? (
          <button type="button" className="btn btn-sm btn-outline" onClick={showByHand}>
            Brief changed: refresh ideas
          </button>
        ) : null}
      </header>
      {products.length ? (
        <div className="gf-grid">
          {products.map((p) => (
            <div className="gf-card" key={p.id}>
              <ProductCard product={p} reason={shown.reasons[shown.ids.indexOf(p.id)] || typeLabel(p.type)} />
              <GiftActions p={p} />
            </div>
          ))}
        </div>
      ) : (
        <p className="gf-none">Nothing fits every part of this brief. Try a bigger budget, no size, or fewer colours.</p>
      )}
      {products.length ? (
        <p className="svc-muted small gf-foot">
          Gift wrap and the note can also be changed in your <Link to="/bag">bag</Link>. Gift-wrapped items ship without a price on the slip.
        </p>
      ) : null}
    </section>
  );
}

export function Gifts() {
  // Tell the brain the brief and the shortlist, once per burst of changes.
  useEffect(() => {
    let timer = 0;
    const unsub = useGifts.subscribe((s, prev) => {
      if (s.brief === prev.brief && s.shown === prev.shown && s.noLimit === prev.noLimit) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const g = useGifts.getState();
        const b = g.brief;
        sendEvent("gifts.changed", {
          recipient: b.recipient ?? null,
          occasion: b.occasion ?? null,
          budget_max: b.budget_max ?? (g.noLimit ? 0 : null),
          size: b.size ?? null,
          colours: b.colours ?? null,
          patterns: b.patterns ?? null,
          material: b.material ?? null,
          ids: g.shown ? g.shown.ids.map(String) : null,
        });
      }, 250);
    });
    return () => {
      window.clearTimeout(timer);
      unsub();
    };
  }, []);

  return (
    <div className="svc svc-gifts">
      <header className="gf-hero">
        <p className="svc-kicker">
          <Gift size={16} aria-hidden /> Gift finder
        </p>
        <h1>
          A gift they'll <em>actually</em> wear
        </h1>
        <p>Tell us who it's for and what you know about them. We'll pull a short list from the whole store, each with a reason.</p>
      </header>
      <div className="gf-layout">
        <Brief />
        <Shortlist />
      </div>
    </div>
  );
}
