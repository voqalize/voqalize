/**
 * The wishlist: saved products as cards, with a tick to compare two to four of
 * them. `?ids=a,b,c` (the kiosk shortlist's QR code) shows those products on
 * top as "Shortlist from the kiosk", with a button to save them all.
 */
import { Heart } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { CardSkeletons, ProductCard } from "../components/ProductCard";
import { type Product, getProduct, useCatalog } from "../data/catalog";
import { useStore } from "../state/store";

export function Wishlist() {
  const ready = useCatalog((s) => !!s.index);
  const ids = useStore((s) => s.wishlist);
  const compare = useStore((s) => s.compare);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const shared = (params.get("ids") ?? "")
    .split(",")
    .map((x) => getProduct(x.trim()))
    .filter((p): p is Product => !!p);
  const unsaved = shared.filter((p) => !ids.includes(p.id));
  const items = ids.map((id) => getProduct(id)).filter((p): p is Product => !!p);
  const picked = compare.filter((id) => ids.includes(id));
  return (
    <div className="wrap wishlist">
      <Breadcrumbs trail={[{ label: "Wishlist" }]} />
      <div className="shop-head">
        <h1 className="page-title">
          Wishlist <span className="muted title-count">{ids.length ? `${ids.length} saved` : ""}</span>
        </h1>
        {items.length >= 2 ? (
          <button type="button" className="btn primary" disabled={picked.length < 2} onClick={() => navigate(`/compare?ids=${picked.join(",")}`)}>
            Compare {picked.length >= 2 ? picked.length : ""} {picked.length < 2 ? "(tick two to four)" : "products"}
          </button>
        ) : null}
      </div>
      {ready && shared.length ? (
        <section className="kiosk-list" data-stage-group>
          <div className="shop-head">
            <h2 className="section-title">Shortlist from the kiosk</h2>
            <button type="button" className="btn ghost" disabled={!unsaved.length} onClick={() => unsaved.forEach((p) => useStore.getState().toggleWishlist(p.id, true))}>
              <Heart size={16} aria-hidden /> {unsaved.length ? `Save ${unsaved.length === shared.length ? "all" : unsaved.length} to wishlist` : "All saved"}
            </button>
          </div>
          <div className="grid">
            {shared.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        </section>
      ) : null}
      {!ready ? (
        <div className="grid">
          <CardSkeletons n={4} />
        </div>
      ) : items.length === 0 && shared.length ? null : items.length === 0 ? (
        <div className="empty">
          <Heart size={32} aria-hidden />
          <h2>Nothing saved yet</h2>
          <p>Tap the heart on any product to keep it here.</p>
          <Link className="btn primary" to="/shop">
            Browse the store
          </Link>
        </div>
      ) : (
        <div className="grid" data-stage-group>
          {items.map((p) => (
            <div key={p.id} className="wish-cell">
              <ProductCard product={p} />
              <label className="wish-compare">
                <input type="checkbox" checked={compare.includes(p.id)} onChange={() => useStore.getState().toggleCompare(p.id)} /> Compare
              </label>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
