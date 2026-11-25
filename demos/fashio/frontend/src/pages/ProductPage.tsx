/**
 * A product (/p/<id>): the gallery (the dataset's one image at two sizes, and
 * the colour variants' thumbnails), brand, name, price with MRP and discount,
 * sizes with stock (nothing preselected), the size chart drawer, Find my size,
 * Add to bag and wishlist, delivery and returns, the detail's description and
 * attributes, and similar items. The main block is
 * `data-stage-thing="product:<id>"`.
 */
import { Heart, RotateCcw, ShoppingBag, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { FitPanel } from "../components/FitPanel";
import { ProductImage } from "../components/ProductCard";
import { Rail } from "../components/Rail";
import { SizeChartDrawer, chartFor } from "../components/SizeChart";
import { type Product, department, discountPct, getProduct, inr, isOneSize, loadDetail, stockOf, typeLabel, useCatalog, variantsOf } from "../data/catalog";
import { POLICY, addDays, fmtDay, todayIST } from "../data/shop";
import { useStore } from "../state/store";
import { NotFoundBody } from "./NotFound";

/** The department a product's breadcrumb goes through. */
function deptOf(p: Product): string {
  if (p.gender === "boys" || p.gender === "girls") return "kids";
  if (p.gender === "unisex") return department("footwear")?.sections.some((s) => s.types.includes(p.type)) ? "footwear" : "accessories";
  return p.gender;
}

export function ProductPage() {
  const { id = "" } = useParams();
  const ready = useCatalog((s) => !!s.index);
  const p = useCatalog((s) => s.byId.get(Number(id)));
  if (!ready) return <ProductSkeleton />;
  if (!p) return <NotFoundBody what={`We couldn't find product ${id}. It may have sold out of the catalogue, or the link is mistyped.`} />;
  return <ProductView key={p.id} p={p} />;
}

function ProductSkeleton() {
  return (
    <div className="wrap pdp is-loading" aria-busy>
      <div className="pdp-grid">
        <div className="pdp-gallery">
          <div className="pdp-main sk" />
        </div>
        <div className="pdp-info">
          <div className="sk sk-line" style={{ width: "30%" }} />
          <div className="sk sk-line" style={{ width: "80%", height: 28 }} />
          <div className="sk sk-line" style={{ width: "40%" }} />
        </div>
      </div>
    </div>
  );
}

function ProductView({ p }: { p: Product }) {
  const detail = useCatalog((s) => s.details[p.id]);
  const size = useStore((s) => s.size[p.id]);
  const wished = useStore((s) => s.wishlist.includes(p.id));
  const inBag = useStore((s) => s.bag.some((l) => l.product_id === p.id));
  const compare = useStore((s) => s.compare);
  const [shot, setShot] = useState(p.id);
  const [zoom, setZoom] = useState<{ x: number; y: number } | null>(null);
  const [nudge, setNudge] = useState(false);
  const [added, setAdded] = useState(false);
  const navigate = useNavigate();
  useEffect(() => {
    void loadDetail(p.id);
    document.title = `${p.name} · Fashio`;
    return () => {
      document.title = "Fashio: fashion, footwear and accessories";
    };
  }, [p.id, p.name]);

  const d = detail && detail !== "loading" && detail !== "missing" ? detail : null;
  const off = discountPct(p);
  const one = isOneSize(p);
  const variants = variantsOf(p);
  const chart = chartFor(p);
  const dept = deptOf(p);
  const fragrance = POLICY.returns.not_returnable_types.includes(p.type);
  const today = todayIST();
  const chosen = one ? p.sizes[0]?.[0] : size;
  const canAdd = !!chosen && stockOf(p, chosen) > 0;
  const similar = (d?.similar ?? []).map((x) => getProduct(x)).filter((x): x is Product => !!x && x.id !== p.id).slice(0, 12);
  const attrs = Object.entries({ ...(p.attrs ?? {}), ...(d?.attributes ?? {}) }).filter(([, v]) => v && v !== "NA");

  const add = () => {
    if (!chosen) {
      setNudge(true);
      document.querySelector("[data-stage-thing='sizes']")?.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    if (!canAdd) return;
    useStore.getState().addToBag(p.id, chosen);
    setAdded(true);
  };

  return (
    <div className="wrap pdp">
      <Breadcrumbs trail={[{ label: department(dept)?.label ?? "Shop", to: `/shop/${dept}` }, { label: typeLabel(p.type), to: `/shop/${dept}/${p.type}` }, { label: p.brand }]} />
      <div className="pdp-grid" data-stage-thing={`product:${p.id}`}>
        <div className="pdp-gallery">
          <div
            className={`pdp-main${zoom ? " is-zoom" : ""}`}
            onMouseMove={(e) => {
              if (window.matchMedia("(hover: none)").matches) return;
              const r = e.currentTarget.getBoundingClientRect();
              setZoom({ x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 });
            }}
            onMouseLeave={() => setZoom(null)}
            onClick={(e) => {
              if (!window.matchMedia("(hover: none)").matches) return;
              if (zoom) setZoom(null);
              else {
                const r = e.currentTarget.getBoundingClientRect();
                setZoom({ x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 });
              }
            }}
          >
            <ProductImage key={shot} id={shot} alt={getProduct(shot)?.name ?? p.name} w={1080} eager />
            {zoom ? <div className="pdp-zoom" style={{ transformOrigin: `${zoom.x}% ${zoom.y}%` }} aria-hidden>
              <ProductImage id={shot} alt="" w={1080} />
            </div> : null}
          </div>
          {variants.length > 1 ? (
            <div className="pdp-thumbs" aria-label="Colours">
              {variants.slice(0, 8).map((v) => (
                <button key={v.id} type="button" className={`pdp-thumb${shot === v.id ? " is-on" : ""}`} onMouseEnter={() => setShot(v.id)} onFocus={() => setShot(v.id)} onClick={() => (v.id === p.id ? setShot(p.id) : navigate(`/p/${v.id}`))} aria-label={`${v.colour}${v.id === p.id ? " (this one)" : ""}`}>
                  <ProductImage id={v.id} alt="" />
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="pdp-info">
          <p className="pdp-brand">
            <Link to={`/shop?q=${encodeURIComponent(p.brand)}`}>{p.brand}</Link>
          </p>
          <h1 className="pdp-name">{p.name}</h1>
          <p className="pdp-meta">
            {p.colour} <span aria-hidden>/</span> {p.usage} <span aria-hidden>/</span> {p.season} {p.year}
          </p>
          <div className="pdp-price">
            <b>{inr(p.price)}</b>
            {off > 0 ? (
              <>
                <span className="muted">
                  MRP <s>{inr(p.mrp)}</s>
                </span>
                <span className="pdp-off">{off}% off</span>
              </>
            ) : (
              <span className="muted">MRP, inclusive of all taxes</span>
            )}
          </div>

          {variants.length > 1 ? (
            <div className="pdp-colours">
              <p className="pdp-label">
                Colour: <b>{p.colour}</b>
              </p>
              <div className="pdp-colour-row">
                {variants.map((v) => (
                  <Link key={v.id} to={`/p/${v.id}`} className={`pdp-colour${v.id === p.id ? " is-on" : ""}`} aria-current={v.id === p.id ? "true" : undefined} title={v.colour}>
                    <ProductImage id={v.id} alt={v.colour} />
                  </Link>
                ))}
              </div>
            </div>
          ) : null}

          {one ? (
            <p className="pdp-one">One size{stockOf(p, p.sizes[0][0]) === 0 ? ": out of stock" : stockOf(p, p.sizes[0][0]) <= 3 ? `: only ${stockOf(p, p.sizes[0][0])} left` : ""}</p>
          ) : (
            <div className={`pdp-sizes${nudge && !size ? " is-nudge" : ""}`} data-stage-thing="sizes" data-stage-group>
              <div className="pdp-sizes-head">
                <p className="pdp-label">{size ? <>Size: <b>{size}</b></> : "Select a size"}</p>
                {chart ? (
                  <button type="button" className="link-btn" data-stage-part="size-chart" onClick={() => useStore.getState().openSizeChart(p.id)}>
                    Size chart
                  </button>
                ) : null}
              </div>
              <div className="size-row" role="radiogroup" aria-label="Size">
                {p.sizes.map(([label, n]) => (
                  <button
                    key={label}
                    type="button"
                    role="radio"
                    aria-checked={size === label}
                    disabled={n === 0}
                    className={`size-btn${size === label ? " is-on" : ""}${n === 0 ? " is-out" : ""}`}
                    data-stage-part={`size:${label}`}
                    onClick={() => {
                      useStore.getState().pickSize(p.id, label);
                      setNudge(false);
                    }}
                    aria-label={`${label}${n === 0 ? ", out of stock" : n <= 3 ? `, only ${n} left` : ""}`}
                  >
                    {label}
                    {n > 0 && n <= 3 ? <span className="size-left">{n} left</span> : null}
                  </button>
                ))}
              </div>
              {nudge && !size ? <p className="pdp-warn">Pick a size first.</p> : null}
              {p.model ? <p className="pdp-model">The {p.model}.</p> : null}
            </div>
          )}

          <FitPanel product={p} />

          <div className="pdp-actions">
            <button type="button" className="btn primary big" data-stage-part="add-to-bag" data-dock-avoid disabled={!!chosen && !canAdd} onClick={add}>
              <ShoppingBag size={18} aria-hidden /> {chosen && !canAdd ? "Out of stock" : "Add to bag"}
            </button>
            <button type="button" className={`btn ghost big${wished ? " is-wished" : ""}`} data-stage-part={`wishlist:${p.id}`} aria-pressed={wished} onClick={() => useStore.getState().toggleWishlist(p.id)}>
              <Heart size={18} fill={wished ? "currentColor" : "none"} aria-hidden /> {wished ? "Wishlisted" : "Wishlist"}
            </button>
          </div>
          <p className="pdp-compare">
            <button type="button" className="link-btn" aria-pressed={compare.includes(p.id)} onClick={() => useStore.getState().toggleCompare(p.id)}>
              {compare.includes(p.id) ? "Added to compare" : "Add to compare"}
            </button>
            {compare.length >= 2 && compare.includes(p.id) ? <Link to={`/compare?ids=${compare.join(",")}`}>Compare {compare.length} products</Link> : null}
          </p>
          {added || inBag ? (
            <p className="pdp-added" aria-live="polite">
              In your bag. <Link to="/bag">Go to bag</Link>
            </p>
          ) : null}

          <div className="pdp-policy">
            <p>
              <Truck size={17} aria-hidden /> <span>
                Delivered by <b>{fmtDay(addDays(today, POLICY.delivery.days_max))}</b>. Free over ₹{POLICY.delivery.free_over}, else ₹{POLICY.delivery.fee}.
                {POLICY.delivery.cod ? " Cash on delivery available." : ""}
              </span>
            </p>
            <p>
              <RotateCcw size={17} aria-hidden /> <span>{fragrance ? <b>Not returnable: fragrances cannot be returned.</b> : <>Returns within {POLICY.returns.window_days} days of delivery, unused with tags on.</>}</span>
            </p>
          </div>

          {d?.description?.length ? (
            <div className="pdp-desc">
              {d.description.map((s, i) => (
                <details key={i} open={i === 0}>
                  <summary>{s.heading}</summary>
                  <div className="pdp-desc-text">
                    {plain(s.text)
                      .split(/\n+/)
                      .filter(Boolean)
                      .map((line, j) => (
                        <p key={j}>{line}</p>
                      ))}
                  </div>
                </details>
              ))}
            </div>
          ) : detail === "loading" ? (
            <p className="muted">Loading the details…</p>
          ) : null}
          {attrs.length ? (
            <table className="attrs">
              <caption>Specifications</caption>
              <tbody>
                {attrs.map(([k, v]) => (
                  <tr key={k}>
                    <th scope="row">{k}</th>
                    <td>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </div>
      {similar.length ? <Rail title="Similar products" products={similar} /> : null}
      <SizeChartDrawer product={p} />
    </div>
  );
}

/** The dataset's text, sometimes with HTML in it, as plain lines. */
function plain(s: string): string {
  return s
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|div)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&");
}
