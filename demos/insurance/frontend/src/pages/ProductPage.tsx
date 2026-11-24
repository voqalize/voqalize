import { Check, ChevronDown, X } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";
import { isProductId, productById, productContent } from "../data";
import type { ProductContent, ProductId } from "../data/types";
import { PRODUCT_BLURB, ProductIcon } from "../components/bits";
import { QuoteBuilder } from "../quote/QuoteBuilder";

type Item = string | { title?: string; text?: string; body?: string };
const textOf = (x: Item) => (typeof x === "string" ? { title: "", text: x } : { title: x.title ?? "", text: x.text ?? x.body ?? "" });

/** content/products.json for this product, in one shape, with a fallback from products.json. */
function copyFor(id: ProductId) {
  const spec = productById(id)!;
  const c: ProductContent = productContent(id) ?? {};
  const hero = typeof c.hero === "string" ? { title: c.hero } : (c.hero ?? {});
  const explainers = c.addons ?? c.addon_explainers ?? {};
  const addonText = (aid: string): string => {
    const hit = Array.isArray(explainers) ? explainers.find((x) => x.id === aid) : explainers[aid];
    if (!hit) return "";
    return typeof hit === "string" ? hit : (hit.text ?? (hit as { body?: string }).body ?? "");
  };
  return {
    headline: c.headline ?? hero.title ?? hero.headline ?? spec.name,
    subhead: c.subhead ?? hero.subtitle ?? hero.sub ?? hero.lede ?? PRODUCT_BLURB[id],
    note: c.starting_from_note,
    highlights: (c.highlights ?? []).map(textOf),
    covered: (c.covered ?? []).map(textOf),
    notCovered: (c.not_covered ?? []).map(textOf),
    addons: spec.addons.map((a) => ({ id: a.id, label: a.label, text: addonText(a.id) })),
    faqs: (c.faqs ?? []).map((f) => ({ q: f.q ?? f.question ?? "", a: f.a ?? f.answer ?? "" })).filter((f) => f.q),
  };
}

export function ProductPage() {
  const { product } = useParams();
  if (!isProductId(product)) return <Navigate to="/" replace />;
  const spec = productById(product)!;
  const copy = copyFor(product);
  return (
    <div className="product-page">
      <section className={`p-hero pc-${product}`}>
        <div className="wrap p-hero-in">
          <p className="crumbs">
            <Link to="/">Home</Link> / {spec.name}
          </p>
          <div className="p-hero-row">
            <span className="p-hero-icon"><ProductIcon product={product} size={30} /></span>
            <div>
              <p className="eyebrow">{spec.plan}</p>
              <h1 className="display-sm">{copy.headline}</h1>
              <p className="lede">{copy.subhead}</p>
              <div className="hero-ctas">
                <a href="#quote" className="btn btn-primary" data-dock-avoid>{copy.note ?? "See your price"}</a>
              </div>
            </div>
          </div>
          {copy.highlights.length ? (
            <ul className="highlights">
              {copy.highlights.map((h, i) => (
                <li key={i}>
                  <strong>{h.title}</strong>
                  <span>{h.text}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>

      <section className="wrap section" id="quote">
        <QuoteBuilder product={product} title="Build your quote" />
      </section>

      {copy.covered.length || copy.notCovered.length ? (
        <section className="wrap section cover-cols" aria-label="What is and is not covered">
          <div className="cover-col is-yes">
            <h2 className="h3">What’s covered</h2>
            <ul>
              {copy.covered.map((x, i) => (
                <li key={i}>
                  <Check size={16} aria-hidden /> <span>{x.title ? <strong>{x.title}. </strong> : null}{x.text}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="cover-col is-no">
            <h2 className="h3">What’s not covered</h2>
            <ul>
              {copy.notCovered.map((x, i) => (
                <li key={i}>
                  <X size={16} aria-hidden /> <span>{x.title ? <strong>{x.title}. </strong> : null}{x.text}</span>
                </li>
              ))}
            </ul>
            <p className="small muted">The policy wording decides every claim. Ask for the clause and we’ll show it to you.</p>
          </div>
        </section>
      ) : null}

      <section className="wrap section" aria-labelledby="addons-h">
        <h2 id="addons-h" className="h2">Add-ons, explained</h2>
        <div className="explain-grid">
          {copy.addons.map((a) => (
            <div key={a.id} className="explain">
              <h3>{a.label}</h3>
              <p>{a.text || "Priced in the quote builder above; the policy wording sets out exactly what it pays."}</p>
            </div>
          ))}
        </div>
      </section>

      {copy.faqs.length ? (
        <section className="wrap section faq" aria-labelledby="faq-h">
          <h2 id="faq-h" className="h2">Questions people ask</h2>
          <div className="faq-list">
            {copy.faqs.map((f, i) => (
              <details key={i} className="faq-item">
                <summary>
                  {f.q} <ChevronDown size={18} aria-hidden />
                </summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
