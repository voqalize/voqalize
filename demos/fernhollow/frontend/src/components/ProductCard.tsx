import { Heart } from "lucide-react";
import { Link } from "react-router-dom";
import { type Product, bestSaving } from "../data/catalog";
import { useShortlist } from "../state/shortlist";
import { Photo, ProductPrice } from "./bits";

export function ProductCard({
  p,
  eager = false,
  badges,
  note,
  sizes,
}: {
  p: Product;
  eager?: boolean;
  /** Extra badges over the photo (e.g. look-alike differences). */
  badges?: React.ReactNode;
  /** A line under the price (e.g. Mira's reason). */
  note?: React.ReactNode;
  sizes?: string;
}) {
  const saving = bestSaving(p);
  const saved = useShortlist((s) => s.ids.includes(p.id));
  const toggle = useShortlist((s) => s.toggle);
  const second = p.images[1];
  const values = p.options.flatMap((o) => o.values);
  return (
    <article className="card" data-spot={`product:${p.id}`}>
      <div className="card-media">
        <Link to={`/product/${p.id}`} className="card-photo" tabIndex={-1} aria-hidden>
          <Photo file={p.images[0]} alt="" eager={eager} sizes={sizes} />
          {second ? <Photo file={second} alt="" className="card-alt" sizes={sizes} /> : null}
        </Link>
        <div className="card-badges">
          {saving.pct ? <span className="badge badge-sale">Save {saving.pct}%</span> : null}
          {badges}
        </div>
        <button
          type="button"
          className={`card-save${saved ? " is-on" : ""}`}
          aria-pressed={saved}
          aria-label={saved ? `Remove ${p.title} from saved` : `Save ${p.title}`}
          onClick={() => toggle(p.id)}
        >
          <Heart size={17} strokeWidth={1.6} fill={saved ? "currentColor" : "none"} />
        </button>
      </div>
      <div className="card-body">
        <h3 className="card-title">
          <Link to={`/product/${p.id}`}>{p.title}</Link>
        </h3>
        <div className="card-meta">
          <ProductPrice p={p} />
          {values.length ? <span className="card-opts">{values.slice(0, 2).join(", ")}</span> : null}
        </div>
        {note ? <div className="card-note">{note}</div> : null}
      </div>
    </article>
  );
}

export function ProductGrid({ products, eagerCount = 4 }: { products: Product[]; eagerCount?: number }) {
  return (
    <div className="grid">
      {products.map((p, i) => (
        <ProductCard key={p.id} p={p} eager={i < eagerCount} />
      ))}
    </div>
  );
}

export function Rail({ products, children }: { products?: Product[]; children?: React.ReactNode }) {
  return (
    <div className="rail" role="list">
      {products?.map((p) => (
        <div role="listitem" className="rail-item" key={p.id}>
          <ProductCard p={p} sizes="(min-width: 900px) 20vw, 60vw" />
        </div>
      ))}
      {children}
    </div>
  );
}
