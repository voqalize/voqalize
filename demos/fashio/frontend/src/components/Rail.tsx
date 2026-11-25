/** A horizontal scroller of product cards with a title and a "see all" link. */
import { ChevronLeft, ChevronRight } from "lucide-react";
import { type ReactNode, useRef } from "react";
import type { Product } from "../data/catalog";
import { CardSkeletons, ProductCard } from "./ProductCard";

export function Rail({ title, products, more, loading = false }: { title: ReactNode; products: Product[]; more?: ReactNode; loading?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const by = (dir: number) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.85, behavior: "smooth" });
  return (
    <section className="rail" data-stage-group>
      <div className="rail-head">
        <h2 className="rail-title">{title}</h2>
        <div className="rail-tools">
          {more}
          <button type="button" className="rail-arrow hide-phone" aria-label="Scroll back" onClick={() => by(-1)}>
            <ChevronLeft size={18} />
          </button>
          <button type="button" className="rail-arrow hide-phone" aria-label="Scroll on" onClick={() => by(1)}>
            <ChevronRight size={18} />
          </button>
        </div>
      </div>
      <div className="rail-track" ref={ref}>
        {loading ? <CardSkeletons n={6} /> : products.map((p) => <ProductCard key={p.id} product={p} compact />)}
      </div>
    </section>
  );
}
