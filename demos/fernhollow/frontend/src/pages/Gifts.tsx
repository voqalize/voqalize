/**
 * /gifts — the gift edit. Who it is for, the occasion and a budget chip pick
 * a short list from backend/data/edits.json (the list the agent reads, so what
 * it says is what is shown), each with its reason and an Add to cart button.
 * Works by tap; the agent sets the same controls through `gifts.set`.
 * `?for=sibling&occasion=housewarming&budget=80` sets them from a link.
 */
import { Gift, ShoppingBag } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Crumbs, EmilyTag, Photo, PriceLine } from "../components/bits";
import { getProduct, getVariant, money } from "../data/catalog";
import { GIFTS, giftKey, useEdits, useGifts } from "../frontdesk/edits";
import { persona } from "../persona";
import { useCart } from "../state/cart";
import { pointHandlers } from "../voice/screen";
import { useTitle } from "./usePage";

export function Gifts() {
  useTitle("Gift edit");
  const [params] = useSearchParams();
  const g = useGifts();
  const edits = useEdits();

  // A link's query sets the controls once.
  useEffect(() => {
    const patch: { recipient?: string; occasion?: string; budget?: number } = {};
    const r = params.get("for");
    const o = params.get("occasion");
    const b = Number(params.get("budget"));
    if (r && GIFTS.recipients.some((x) => x.id === r)) patch.recipient = r;
    if (o && GIFTS.occasions.some((x) => x.id === o)) patch.occasion = o;
    if (b && GIFTS.budgets.includes(b)) patch.budget = b;
    if (Object.keys(patch).length) useGifts.getState().set(patch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const picks = edits?.gifts[giftKey(g.recipient, g.occasion, g.budget)] ?? [];
  const who = GIFTS.recipients.find((x) => x.id === g.recipient)?.label ?? "";
  const why = GIFTS.occasions.find((x) => x.id === g.occasion)?.label ?? "";
  const byAgent = g.changed?.by === "emily";

  return (
    <div className="wrap page-pad frontdesk gifts">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Gift edit" }]} />
      <header className="fd-hero">
        <div>
          <p className="fd-eyebrow">
            <Gift size={15} aria-hidden /> The gift edit
          </p>
          <h1 className="h1">Something they will keep</h1>
          <p className="lede">
            Tell us who it is for, the occasion and what you want to spend; we pull a short list from the whole store, with the reason for each. Or tell{" "}
            {persona.name}: “something for my sister’s new flat, under $80”.
          </p>
        </div>
      </header>

      <section className="fd-controls" aria-label="Gift edit controls">
        <Control label="For" name="recipient" value={g.recipient} options={GIFTS.recipients.map((r) => ({ value: r.id, label: r.label }))} />
        <Control label="Occasion" name="occasion" value={g.occasion} options={GIFTS.occasions.map((o) => ({ value: o.id, label: o.label }))} />
        <Control label="Up to" name="budget" value={String(g.budget)} options={GIFTS.budgets.map((b) => ({ value: String(b), label: money(b) }))} />
      </section>

      <div className="fd-results-head" data-emily-start>
        <p className="fd-results-line">
          <strong>{picks.length} ideas</strong> · {who.toLowerCase()} · {why.toLowerCase()} · up to {money(g.budget)} {byAgent ? <EmilyTag /> : null}
        </p>
        <p className="small">Every price is today’s price. Sale prices show the was-price.</p>
      </div>

      {!edits ? (
        <p className="small">Loading the edit…</p>
      ) : picks.length ? (
        <ol className="fd-gift-grid">
          {picks.map((pick, i) => {
            const p = getProduct(pick.product_id);
            if (!p) return null;
            const v = getVariant(p, pick.variant_id);
            return (
              <li key={pick.product_id} className="fd-gift" data-fh-thing={`product:${p.id}`} data-spot={`product:${p.id}`} {...pointHandlers(p.id)}>
                <Link to={`/product/${p.id}?variant=${v.id}`} className="fd-gift-photo" tabIndex={-1} aria-hidden>
                  <Photo file={p.images[0]} alt="" sizes="(min-width: 900px) 30vw, 90vw" />
                  <span className="fd-gift-n">{i + 1}</span>
                </Link>
                <div className="fd-gift-body">
                  <p className="fd-gift-cat">{p.category}</p>
                  <h2 className="fd-gift-title">
                    <Link to={`/product/${p.id}?variant=${v.id}`}>{p.title}</Link>
                  </h2>
                  <PriceLine price={v.price} compare={v.compareAtPrice} />
                  {p.options[0] ? (
                    <p className="small">
                      {p.options[0].name}: {Object.values(v.options)[0]}
                    </p>
                  ) : null}
                  <p className="fd-gift-why">{pick.reason}</p>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    data-stage-part={`gift:add:${p.id}`}
                    onClick={() => useCart.getState().add([{ product_id: p.id, variant_id: v.id, qty: 1 }])}
                  >
                    <ShoppingBag size={15} aria-hidden /> Add to cart
                  </button>
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="lede">Nothing in the store fits that budget for this occasion. Try the next budget up.</p>
      )}
    </div>
  );
}

function Control({ label, name, value, options }: { label: string; name: "recipient" | "occasion" | "budget"; value: string; options: { value: string; label: string }[] }) {
  return (
    <div className="fd-control" role="group" aria-label={label}>
      <span className="fd-control-label">{label}</span>
      <div className="fd-chips">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            className="chip"
            aria-pressed={value === o.value}
            data-stage-part={`gift:${name}:${o.value}`}
            onClick={() => useGifts.getState().set(name === "budget" ? { budget: Number(o.value) } : { [name]: o.value })}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
