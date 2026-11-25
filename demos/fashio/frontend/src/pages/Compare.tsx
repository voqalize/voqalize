/**
 * Two to four products side by side (/compare?ids=a,b): image, price,
 * discount, brand, colour, sizes in stock and the fit, fabric and pattern
 * attributes. Each row is `data-stage-part="row:<label>"`, so `compare.show`
 * rings them in turn.
 */
import { X } from "lucide-react";
import { useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { ProductImage } from "../components/ProductCard";
import { type Product, discountPct, getProduct, inr, typeLabel, useCatalog } from "../data/catalog";
import { useStore } from "../state/store";

const ROWS: { label: string; cell: (p: Product) => React.ReactNode }[] = [
  { label: "Price", cell: (p) => <b>{inr(p.price)}</b> },
  { label: "MRP", cell: (p) => inr(p.mrp) },
  { label: "Discount", cell: (p) => (discountPct(p) ? <span className="pdp-off">{discountPct(p)}% off</span> : "None") },
  { label: "Brand", cell: (p) => p.brand },
  { label: "Category", cell: (p) => typeLabel(p.type) },
  { label: "Colour", cell: (p) => p.colour },
  {
    label: "Sizes in stock",
    cell: (p) => {
      const ok = p.sizes.filter(([, n]) => n > 0).map(([l]) => l);
      return ok.length ? ok.join(", ").replace("Onesize", "One size") : <span className="muted">Out of stock</span>;
    },
  },
  { label: "Fit", cell: (p) => p.attrs?.Fit ?? "—" },
  { label: "Fabric", cell: (p) => p.attrs?.Fabric ?? p.attrs?.Material ?? "—" },
  { label: "Pattern", cell: (p) => p.attrs?.Pattern ?? "—" },
  { label: "Occasion", cell: (p) => p.usage },
];

export function Compare() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const ready = useCatalog((s) => !!s.index);
  const stored = useStore((s) => s.compare);
  const fromUrl = (params.get("ids") ?? "").split(",").map((x) => Number(x.trim())).filter((x) => x > 0);
  const ids = fromUrl.length ? fromUrl : stored;
  useEffect(() => {
    if (fromUrl.length && fromUrl.join() !== stored.join()) useStore.getState().setCompare(fromUrl.slice(0, 4));
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps
  const products = ids.map((id) => getProduct(id)).filter((p): p is Product => !!p).slice(0, 4);
  const remove = (id: number) => {
    const next = products.map((p) => p.id).filter((x) => x !== id);
    useStore.getState().setCompare(next);
    navigate(next.length ? `/compare?ids=${next.join(",")}` : "/compare", { replace: true });
  };

  return (
    <div className="wrap compare">
      <Breadcrumbs trail={[{ label: "Compare" }]} />
      <h1 className="page-title">Compare</h1>
      {!ready ? (
        <p className="muted">Loading…</p>
      ) : products.length < 2 ? (
        <div className="empty">
          <h2>Pick two to four products</h2>
          <p>Use “Compare” on a product page, or tick products on your wishlist.</p>
          <Link className="btn primary" to="/wishlist">
            Open the wishlist
          </Link>
        </div>
      ) : (
        <div className="ctable-wrap" data-stage-group>
          <table className="ctable" style={{ ["--cols" as string]: products.length }}>
            <thead>
              <tr data-stage-part="row:Product">
                <th scope="row">Product</th>
                {products.map((p) => (
                  <td key={p.id} data-stage-thing={`product:${p.id}`}>
                    <div className="ccard">
                      <button type="button" className="ccard-x" aria-label={`Remove ${p.name}`} onClick={() => remove(p.id)}>
                        <X size={16} />
                      </button>
                      <Link to={`/p/${p.id}`} className="ccard-img">
                        <ProductImage id={p.id} alt={p.name} />
                      </Link>
                      <Link to={`/p/${p.id}`} className="ccard-name">
                        {p.name}
                      </Link>
                    </div>
                  </td>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.label} data-stage-part={`row:${r.label}`} data-stage-label={r.label}>
                  <th scope="row">{r.label}</th>
                  {products.map((p) => (
                    <td key={p.id}>{r.cell(p)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
