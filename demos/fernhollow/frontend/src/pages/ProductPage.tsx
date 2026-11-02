import { Heart, Minus, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  type Product,
  collectionName,
  getProduct,
  getVariant,
  moreFromRoom,
  money,
  roomName,
  sameCollection,
  savePct,
  variantForOptions,
} from "../data/catalog";
import { POLICY_TOPICS, getPage } from "../data/content";
import { Crumbs, EmilyMark, EmilyTag, Photo, PriceLine, SectionHead } from "../components/bits";
import { ProductCard, Rail } from "../components/ProductCard";
import { AddButton } from "../components/Overlays";
import { useShortlist } from "../state/shortlist";
import { emily, navigatedBy, useEmily } from "../voice/controller";
import { emit } from "../voice/events";
import { goesWith, moreLike } from "../voice/local";
import { pointHandlers } from "../voice/screen";
import { useTitle } from "./usePage";

export function ProductPage() {
  const { id } = useParams();
  const p = getProduct(id);
  if (!p) return <Navigate to="/shop" replace />;
  return <ProductView key={p.id} p={p} />;
}

function ProductView({ p }: { p: Product }) {
  useTitle(p.title);
  const commanded = useEmily((s) => s.variants[p.id]);
  const focus = useEmily((s) => s.focus);
  const [variantId, setVariantId] = useState(() => getVariant(p, commanded?.id).id);
  const [qty, setQty] = useState(1);
  const [shot, setShot] = useState(0);
  const saved = useShortlist((s) => s.ids.includes(p.id));
  const toggleSaved = useShortlist((s) => s.toggle);
  const variant = getVariant(p, variantId);

  // A command (select_variant / open_product) moves the picker.
  useEffect(() => {
    if (commanded && commanded.id !== variantId) setVariantId(getVariant(p, commanded.id).id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commanded?.stamp]);

  useEffect(() => {
    emit("product_viewed", { product_id: p.id, variant_id: variantId }, navigatedBy());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.id]);

  useEffect(() => {
    if (focus && focus.productId === p.id && Date.now() - focus.stamp < 4000) {
      const t = window.setTimeout(() => void emily.highlight({ target: `section:${focus.section}` }), 250);
      return () => window.clearTimeout(t);
    }
  }, [focus, p.id]);

  const choose = (name: string, value: string) => {
    const next = variantForOptions(p, { ...variant.options, [name]: value }) ?? variantForOptions(p, { [name]: value });
    if (!next) return;
    setVariantId(next.id);
    void emily.select_variant({ product_id: p.id, variant_id: next.id }, "visitor");
  };

  const pct = savePct(variant.price, variant.compareAtPrice);
  const lines = [{ product_id: p.id, variant_id: variant.id, qty }];

  return (
    <div className="pdp">
      <div className="wrap">
        <Crumbs
          items={[
            { label: "Home", to: "/" },
            { label: roomName(p.room), to: `/room/${p.room}` },
            { label: p.category, to: `/category/${p.categorySlug}` },
            { label: p.title },
          ]}
        />
        <div className="pdp-grid" {...pointHandlers(p.id)}>
          <div className="gallery">
            {p.images.length > 1 ? (
              <div className="gallery-thumbs" role="tablist" aria-label="Photos">
                {p.images.map((file, i) => (
                  <button
                    type="button"
                    role="tab"
                    key={file}
                    aria-selected={shot === i}
                    aria-label={`Photo ${i + 1} of ${p.images.length}`}
                    className="gallery-thumb"
                    onClick={() => setShot(i)}
                  >
                    <Photo file={file} alt="" sizes="88px" />
                  </button>
                ))}
              </div>
            ) : null}
            <div className="gallery-main">
              <Photo key={p.images[shot]} file={p.images[shot]} alt={p.title} size={1000} eager className="gallery-img" />
              {pct ? <span className="badge badge-sale gallery-badge">Save {pct}%</span> : null}
            </div>
          </div>

          <div className="pdp-info">
            <div className="pdp-sticky">
              <Link to={`/category/${p.categorySlug}`} className="small pdp-cat">
                {p.category}
              </Link>
              <h1 className="h1 pdp-title">{p.title}</h1>
              <div className="pdp-price" data-spot="section:price">
                <PriceLine price={variant.price} compare={variant.compareAtPrice} />
                {pct ? <span className="pdp-save">You save {money(Math.round(((variant.compareAtPrice ?? 0) - variant.price) * 100) / 100)}</span> : null}
              </div>
              <p className="pdp-intro">{p.intro}</p>

              <div className="pdp-options" data-spot="section:options">
                {p.options.map((o) => (
                  <fieldset key={o.name} className="option">
                    <legend className="option-name">
                      {o.name}: <span>{variant.options[o.name]}</span> <EmilyMark k={`variant:${p.id}`} />
                    </legend>
                    <div className="option-values">
                      {o.values.map((v) => {
                        const on = variant.options[o.name] === v;
                        const vv = variantForOptions(p, { ...variant.options, [o.name]: v }) ?? variantForOptions(p, { [o.name]: v });
                        return (
                          <button
                            type="button"
                            key={v}
                            className={`opt${on ? " is-on" : ""}`}
                            aria-pressed={on}
                            onClick={() => choose(o.name, v)}
                          >
                            <span>{v}</span>
                            {vv && vv.price !== variant.price ? <span className="opt-price">{money(vv.price)}</span> : null}
                          </button>
                        );
                      })}
                    </div>
                  </fieldset>
                ))}
              </div>

              <div className="pdp-buy">
                <div className="qty qty-lg" role="group" aria-label="Quantity">
                  <button type="button" aria-label="One fewer" onClick={() => setQty((n) => Math.max(1, n - 1))}>
                    <Minus size={15} />
                  </button>
                  <span aria-live="polite">{qty}</span>
                  <button type="button" aria-label="One more" onClick={() => setQty((n) => Math.min(99, n + 1))}>
                    <Plus size={15} />
                  </button>
                </div>
                <AddButton lines={lines} label={`Add to cart, ${money(variant.price * qty)}`} claimsFor={[p.id]} />
                <button
                  type="button"
                  className={`icon-btn save-btn${saved ? " is-on" : ""}`}
                  aria-pressed={saved}
                  aria-label={saved ? "Remove from saved" : "Save for later"}
                  onClick={() => toggleSaved(p.id)}
                >
                  <Heart size={19} strokeWidth={1.6} fill={saved ? "currentColor" : "none"} />
                </button>
              </div>

              {p.highlights.length ? (
                <div className="pdp-highlights" data-spot="section:highlights">
                  <h2 className="pdp-sub">Details</h2>
                  <ul>
                    {p.highlights.map((h) => (
                      <li key={h}>{h}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <ul className="pdp-policies" aria-label="Store policies">
                {POLICY_TOPICS.map((t) => (
                  <li key={t}>
                    <button type="button" className="policy-link" onClick={() => emily.open_policy({ topic: t })}>
                      <span>{getPage(t)?.title ?? t}</span>
                      <span className="small">{getPage(t)?.dek}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <p className="small pdp-collection">
                Part of the{" "}
                <Link className="link" to={`/search?q=${encodeURIComponent(collectionName(p.collections[0]))}`}>
                  {collectionName(p.collections[0])}
                </Link>{" "}
                collection
              </p>
            </div>
          </div>
        </div>
      </div>
      <ProductRails p={p} />
    </div>
  );
}

function ProductRails({ p }: { p: Product }) {
  const gw = useEmily((s) => s.goesWith);
  const ml = useEmily((s) => s.moreLike);
  const goes = useMemo(() => (gw && gw.anchorId === p.id ? gw : { ...goesWith(p), anchorId: p.id, by: "visitor" as const }), [gw, p]);
  const like = useMemo(() => (ml && ml.anchorId === p.id ? ml : { ...moreLike(p), anchorId: p.id, by: "visitor" as const }), [ml, p]);
  const room = moreFromRoom(p);
  const coll = sameCollection(p, 20).filter((x) => !goes.items.some((g) => g.product_id === x.id)).slice(0, 8);
  return (
    <>
      {goes.items.length ? (
        <section className="section strip" data-spot="section:goes-with">
          <div className="wrap">
            <SectionHead title="Goes with" action={goes.by === "emily" ? <EmilyTag label="Picked by Emily" /> : undefined}>
              Pieces that sit well beside the {p.title.toLowerCase()}.
            </SectionHead>
          </div>
          <div className="wrap wrap-rail">
            <div className="rail" role="list">
              {goes.items.map((it) => {
                const x = getProduct(it.product_id);
                return x ? (
                  <div role="listitem" className="rail-item" key={x.id}>
                    <ProductCard p={x} note={<span className="reason">{it.reason}</span>} sizes="(min-width: 900px) 20vw, 60vw" />
                  </div>
                ) : null;
              })}
            </div>
          </div>
        </section>
      ) : null}
      {like.items.length ? (
        <section className="section strip" data-spot="section:more-like">
          <div className="wrap">
            <SectionHead title="Similar, and how they differ" action={like.by === "emily" ? <EmilyTag label="Picked by Emily" /> : undefined}>
              Other {p.category.toLowerCase()}, closest in price first.
            </SectionHead>
          </div>
          <div className="wrap wrap-rail">
            <div className="rail" role="list">
              {like.items.map((it) => {
                const x = getProduct(it.product_id);
                return x ? (
                  <div role="listitem" className="rail-item" key={x.id}>
                    <ProductCard
                      p={x}
                      sizes="(min-width: 900px) 20vw, 60vw"
                      note={
                        it.differences.length ? (
                          <span className="diffs">
                            {it.differences.map((d) => (
                              <span key={d} className="diff">
                                {d}
                              </span>
                            ))}
                          </span>
                        ) : null
                      }
                    />
                  </div>
                ) : null;
              })}
            </div>
          </div>
        </section>
      ) : null}
      <section className="section">
        <div className="wrap">
          <SectionHead title={`More for the ${roomName(p.room).toLowerCase()}`} action={<Link className="link" to={`/room/${p.room}`}>Shop the room</Link>} />
        </div>
        <div className="wrap wrap-rail">
          <Rail products={room} />
        </div>
      </section>
      {coll.length ? (
        <section className="section">
          <div className="wrap">
            <SectionHead title={`The ${collectionName(p.collections[0])} collection`} />
          </div>
          <div className="wrap wrap-rail">
            <Rail products={coll} />
          </div>
        </section>
      ) : null}
    </>
  );
}
