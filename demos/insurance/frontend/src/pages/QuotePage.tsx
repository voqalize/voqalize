import { ArrowRight } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";
import { PRODUCT_IDS, isProductId, productById } from "../data";
import { PRODUCT_BLURB, ProductIcon, TalkButton } from "../components/bits";
import { persona } from "../persona";
import { QuoteBuilder, QuoteTabs } from "../quote/QuoteBuilder";

export function QuotePage() {
  const { product } = useParams();
  if (product && !isProductId(product)) return <Navigate to="/quote" replace />;
  if (!product || !isProductId(product)) return <QuoteChooser />;
  return (
    <div className="wrap page quote-page">
      <div className="page-head">
        <div>
          <p className="crumbs">
            <Link to="/">Home</Link> / <Link to="/quote">Get a quote</Link> / {productById(product)!.name}
          </p>
          <h1 className="h1">Get a quote</h1>
        </div>
        <TalkButton className="btn btn-ghost btn-sm" label={`Fill it with ${persona.name}`} />
      </div>
      <QuoteTabs product={product} />
      <QuoteBuilder product={product} />
    </div>
  );
}

function QuoteChooser() {
  return (
    <div className="wrap page">
      <div className="page-head">
        <div>
          <p className="crumbs">
            <Link to="/">Home</Link> / Get a quote
          </p>
          <h1 className="h1">What would you like a quote for?</h1>
          <p className="muted">Pick a plan. Your premium builds line by line as you answer.</p>
        </div>
      </div>
      <div className="chooser-grid" data-stage-part="quote-chooser">
        {PRODUCT_IDS.map((p) => {
          const spec = productById(p)!;
          return (
            <Link key={p} to={`/quote/${p}`} className="chooser-card" data-stage-part={`quote-tab:${p}`}>
              <span className="product-icon"><ProductIcon product={p} size={24} /></span>
              <span>
                <span className="product-name">{spec.name}</span>
                <span className="product-blurb">{PRODUCT_BLURB[p]}</span>
              </span>
              <ArrowRight size={18} aria-hidden className="chooser-go" />
            </Link>
          );
        })}
      </div>
    </div>
  );
}
