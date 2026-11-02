import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { type Product, bestSaving, imgUrl, money } from "../data/catalog";
import { useMarked } from "../voice/controller";

/** A product photo from our own origin: 400w in grids, 1000w on the product page. */
export function Photo({
  file,
  alt,
  size = 400,
  eager = false,
  className,
  sizes,
}: {
  file: string;
  alt: string;
  size?: 400 | 1000;
  eager?: boolean;
  className?: string;
  sizes?: string;
}) {
  return (
    <img
      className={className}
      src={imgUrl(file, size)}
      srcSet={`${imgUrl(file, 400)} 400w, ${imgUrl(file, 1000)} 768w`}
      sizes={sizes ?? (size === 1000 ? "(min-width: 900px) 50vw, 100vw" : "(min-width: 900px) 25vw, 50vw")}
      alt={alt}
      width={768}
      height={1344}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      fetchPriority={eager ? "high" : undefined}
    />
  );
}

export function EmilyTag({ label = "Emily" }: { label?: string }) {
  return (
    <span className="emily-tag" title="Emily, our design adviser, made this change">
      {label}
    </span>
  );
}

/** Shows the Emily tag while a mark is fresh. */
export function EmilyMark({ k, label }: { k: string; label?: string }) {
  return useMarked(k) ? <EmilyTag label={label} /> : null;
}

export function PriceLine({ price, compare, from = false }: { price: number; compare?: number | null; from?: boolean }) {
  const onSale = compare != null && compare > price;
  return (
    <span className="price-line">
      <span className="price">
        {from ? "From " : ""}
        {money(price)}
      </span>
      {onSale ? (
        <>
          <span className="sr-only">, was </span>
          <span className="price-was">{money(compare)}</span>
        </>
      ) : null}
    </span>
  );
}

export function ProductPrice({ p }: { p: Product }) {
  const s = bestSaving(p);
  if (s.pct) return <PriceLine price={s.price} compare={s.compare} from={p.priceMin !== p.priceMax} />;
  return <PriceLine price={p.priceMin} from={p.priceMin !== p.priceMax} />;
}

export function Crumbs({ items }: { items: { label: string; to?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="crumbs">
      <ol>
        {items.map((c, i) => (
          <li key={`${c.label}${i}`}>
            {c.to ? <Link to={c.to}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
            {i < items.length - 1 ? <ChevronRight size={12} aria-hidden /> : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function SectionHead({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="section-head">
      <div>
        <h2 className="h2">{title}</h2>
        {children ? <p className="section-sub">{children}</p> : null}
      </div>
      {action ? <div className="section-action">{action}</div> : null}
    </div>
  );
}
