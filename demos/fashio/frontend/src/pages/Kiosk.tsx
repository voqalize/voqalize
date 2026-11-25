/**
 * /kiosk: the full-screen in-store kiosk (the shell hides the store's header
 * and footer here). A big search over the whole catalogue with quick chips,
 * large result cards, a product view with sizes and stock, colour variants and
 * a QR code that opens the product page on the shopper's phone, a shortlist
 * that leaves by QR (`/wishlist?ids=…`), and a button that calls a floor
 * assistant. Everything works by touch; the agent's moves write the same store.
 */
import qrcode from "qrcode-generator";
import { ArrowLeft, BellRing, Heart, Search, Smartphone, X } from "lucide-react";
import { useEffect, useMemo } from "react";
import { ProductCard, ProductImage } from "../components/ProductCard";
import { type Product, discountPct, getProduct, index, inr, typeLabel, useCatalog, variantsOf } from "../data/catalog";
import { STORE } from "../data/shop";
import { sendEvent } from "../stage/host";
import { QUICK_CHIPS, isEmptySearch, kioskSearch, kioskSummary, productUrl, shortlistUrl, useKiosk } from "../state/kiosk";

const SHOW = 24;

/** A QR code as one SVG path (qrcode-generator does the encoding). */
const NO_COLOURS: Record<string, string> = {};

export function QrCode({ text, label, className }: { text: string; label: string; className?: string }) {
  const { d, n } = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    const count = qr.getModuleCount();
    let path = "";
    for (let r = 0; r < count; r++) for (let c = 0; c < count; c++) if (qr.isDark(r, c)) path += `M${c + 3} ${r + 3}h1v1h-1z`;
    return { d: path, n: count + 6 };
  }, [text]);
  return (
    <svg className={`qr${className ? ` ${className}` : ""}`} viewBox={`0 0 ${n} ${n}`} role="img" aria-label={label} data-url={text} shapeRendering="crispEdges">
      <rect width={n} height={n} fill="#fff" />
      <path d={d} fill="#16121f" />
    </svg>
  );
}

function SearchBar() {
  const typed = useKiosk((s) => s.typed);
  const search = useKiosk((s) => s.search);
  const { setTyped, setSearch } = useKiosk.getState();
  return (
    <div className="ks-search-wrap">
      <form
        className="ks-search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          const q = typed.trim();
          setSearch(q ? { query: q } : null);
        }}
      >
        <Search size={28} aria-hidden />
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Search kurtas, sneakers, watches…" aria-label="Search the catalogue" data-stage-part="kiosk:search" />
        <button type="submit" className="ks-btn ks-btn-accent">
          Search
        </button>
      </form>
      <div className="ks-chips" data-stage-group>
        {QUICK_CHIPS.map((c) => (
          <button type="button" key={c.id} className={`ks-chip${search?.chip === c.id ? " is-on" : ""}`} data-stage-part={`kiosk:chip:${c.id}`} onClick={() => setSearch(search?.chip === c.id ? null : { ...c.search, chip: c.id })}>
            {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Attract() {
  useCatalog((s) => s.index);
  const popular = useMemo(() => (index()?.products ?? []).filter((p) => p.sizes.some(([, n]) => n > 0)).sort((a, b) => a.rank - b.rank).slice(0, 6), [index()]);
  const open = useKiosk((s) => s.openProduct);
  return (
    <section className="ks-attract">
      <p className="ks-kicker">{STORE.brand.store.name}</p>
      <h1>{STORE.kiosk.idle_title}</h1>
      <p className="ks-copy">{STORE.kiosk.idle_copy}</p>
      <SearchBar />
      {popular.length ? (
        <div className="ks-popular">
          <p className="ks-label">Popular in store today</p>
          <div className="ks-popular-row">
            {popular.map((p) => (
              <button type="button" key={p.id} className="ks-pop" data-stage-thing={`product:${p.id}`} onClick={() => open(p.id)}>
                <ProductImage id={p.id} alt={p.name} />
                <span>{typeLabel(p.type)}</span>
                <b>{inr(p.price)}</b>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Results({ results }: { results: Product[] }) {
  const search = useKiosk((s) => s.search);
  const { openProduct, home } = useKiosk.getState();
  return (
    <section className="ks-results">
      <SearchBar />
      <header className="ks-results-head">
        <button type="button" className="ks-btn ks-btn-ghost" onClick={home}>
          <ArrowLeft size={20} aria-hidden /> Start again
        </button>
        <h2>
          {results.length ? `${results.length.toLocaleString("en-IN")} ${results.length === 1 ? "product" : "products"}` : "Nothing found"}
          <span>{kioskSummary(search)}</span>
        </h2>
      </header>
      {results.length ? (
        <div className="ks-grid">
          {results.slice(0, SHOW).map((p) => (
            <ProductCard key={p.id} product={p} onOpen={(x) => openProduct(x.id)} />
          ))}
        </div>
      ) : (
        <p className="ks-none">Try fewer words, or one of the chips above. A floor assistant can help too.</p>
      )}
      {results.length > SHOW ? <p className="ks-more">Showing the {SHOW} most popular. Say or type more to narrow it down.</p> : null}
    </section>
  );
}

function ProductView({ p }: { p: Product }) {
  const { openProduct, toggleShortlist, showQr } = useKiosk.getState();
  const listed = useKiosk((s) => s.shortlist.includes(p.id));
  const qr = useKiosk((s) => s.qr);
  const trayOpen = qr?.kind === "shortlist";
  const big = qr?.kind === "product" && qr.id === p.id;
  const off = discountPct(p);
  const variants = variantsOf(p);
  const colours = useCatalog((s) => s.index?.colours) ?? NO_COLOURS;
  const hasSearch = !isEmptySearch(useKiosk((s) => s.search));
  return (
    <section className="ks-product" data-stage-thing={`kiosk-product:${p.id}`}>
      <button type="button" className="ks-btn ks-btn-ghost ks-back" onClick={() => openProduct(null)}>
        <ArrowLeft size={20} aria-hidden /> {hasSearch ? "Back to results" : "Back"}
      </button>
      <div className="ks-product-grid">
        <div className="ks-product-img">
          <ProductImage id={p.id} alt={p.name} w={1080} />
        </div>
        <div className="ks-product-info">
          <p className="ks-brand">{p.brand}</p>
          <h1>{p.name}</h1>
          <p className="ks-price">
            <b>{inr(p.price)}</b>
            {off > 0 ? (
              <>
                <s>MRP {inr(p.mrp)}</s>
                <span className="ks-off">{off}% off</span>
              </>
            ) : null}
          </p>
          <div className="ks-actions">
            <button type="button" className={`ks-btn ${listed ? "ks-btn-on" : "ks-btn-accent"}`} data-stage-part={`kiosk:shortlist:${p.id}`} data-dock-avoid onClick={() => toggleShortlist(p.id)}>
              <Heart size={20} fill={listed ? "currentColor" : "none"} aria-hidden /> {listed ? "On your shortlist" : "Add to shortlist"}
            </button>
          </div>
          <div className={`ks-qr-card${big ? " is-big" : ""}`} data-dock-avoid {...(!trayOpen ? { "data-stage-part": "kiosk:qr" } : {})}>
            <button type="button" className="ks-qr-btn" onClick={() => showQr(big ? null : { kind: "product", id: p.id })} aria-label={big ? "Make the QR code smaller" : "Make the QR code bigger"}>
              <QrCode text={productUrl(p.id)} label={`QR code that opens ${p.name} on your phone`} />
            </button>
            <div>
              <p className="ks-qr-h">
                <Smartphone size={20} aria-hidden /> Buy it on your phone
              </p>
              <p className="ks-qr-p">Scan with your phone camera to open this product on fashio, with every size and delivery to your door.</p>
            </div>
          </div>
        </div>
          <div className="ks-block">
            <p className="ks-label">{p.scale === "one" ? "Size" : "Sizes in store and online"}</p>
            <div className="ks-sizes">
              {p.sizes.map(([l, n]) => (
                <span key={l} className={`ks-size${n === 0 ? " is-out" : ""}`}>
                  {l === "Onesize" ? "One size" : l}
                  <small>{n === 0 ? "Sold out" : n <= 3 ? `Only ${n} left` : "In stock"}</small>
                </span>
              ))}
            </div>
          </div>
          {variants.length > 1 ? (
            <div className="ks-block">
              <p className="ks-label">Colours</p>
              <div className="ks-variants">
                {variants.map((v) => (
                  <button type="button" key={v.id} className={`ks-variant${v.id === p.id ? " is-on" : ""}`} onClick={() => openProduct(v.id)} aria-label={v.colour}>
                    <span style={{ background: colours[v.colour] === "conic" ? "conic-gradient(#d6246e,#f2a400,#1f7a4d,#2f5fb3,#d6246e)" : colours[v.colour] }} />
                    {v.colour}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
      </div>
    </section>
  );
}

function Tray() {
  const qr = useKiosk((s) => s.qr);
  const ids = useKiosk((s) => s.shortlist);
  const { showQr, toggleShortlist, openProduct } = useKiosk.getState();
  if (qr?.kind !== "shortlist") return null;
  const items = ids.map((id) => getProduct(id)).filter((p): p is Product => !!p);
  return (
    <div className="ks-tray-back" onClick={(e) => e.target === e.currentTarget && showQr(null)}>
      <aside className="ks-tray" data-overlay="right" aria-label="Your shortlist">
        <header>
          <h2>Your shortlist</h2>
          <button type="button" className="ks-icon" aria-label="Close the shortlist" onClick={() => showQr(null)}>
            <X size={24} />
          </button>
        </header>
        {items.length ? (
          <>
            <div className="ks-qr-card is-tray" data-stage-part="kiosk:qr">
              <QrCode text={shortlistUrl(ids)} label="QR code that opens your shortlist on your phone" />
              <div>
                <p className="ks-qr-h">
                  <Smartphone size={20} aria-hidden /> Take them with you
                </p>
                <p className="ks-qr-p">{items.length === 1 ? "Scan to open it on your phone, ready to save or buy." : `Scan to open all ${items.length} on your phone, ready to save or buy.`}</p>
              </div>
            </div>
            <ul className="ks-tray-list">
              {items.map((p) => (
                <li key={p.id}>
                  <button type="button" className="ks-tray-item" onClick={() => openProduct(p.id)}>
                    <ProductImage id={p.id} alt={p.name} />
                    <span>
                      <small>{p.brand}</small>
                      {p.name}
                      <b>{inr(p.price)}</b>
                    </span>
                  </button>
                  <button type="button" className="ks-icon" aria-label={`Remove ${p.name}`} onClick={() => toggleShortlist(p.id, false)}>
                    <X size={20} />
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="ks-none">Nothing here yet. Open a product and tap Add to shortlist.</p>
        )}
      </aside>
    </div>
  );
}

export function Kiosk() {
  useCatalog((s) => s.index);
  const search = useKiosk((s) => s.search);
  const open = useKiosk((s) => s.open);
  const count = useKiosk((s) => s.shortlist.length);
  const assistAt = useKiosk((s) => s.assistAt);
  const results = useMemo(() => (search ? kioskSearch(search) : []), [search, index()]);
  const product = open != null ? getProduct(open) : undefined;

  useEffect(() => {
    document.body.classList.add("is-kiosk");
    return () => document.body.classList.remove("is-kiosk");
  }, []);

  // Tell the brain what the kiosk shows, once per burst of changes.
  useEffect(() => {
    let timer = 0;
    const unsub = useKiosk.subscribe((s, prev) => {
      if (s.search === prev.search && s.open === prev.open && s.shortlist === prev.shortlist) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const k = useKiosk.getState();
        const found = k.search ? kioskSearch(k.search) : [];
        sendEvent("kiosk.changed", {
          summary: k.open != null ? `${kioskSummary(k.search)}; product ${k.open} open` : kioskSummary(k.search),
          count: found.length,
          ids: found.slice(0, 12).map((p) => String(p.id)),
          product_id: k.open != null ? String(k.open) : null,
          shortlist: k.shortlist.map(String),
        });
      }, 250);
    });
    return () => {
      window.clearTimeout(timer);
      unsub();
    };
  }, []);

  return (
    <div className="kiosk">
      <header className="ks-top">
        <button type="button" className="ks-logo" onClick={() => useKiosk.getState().home()} aria-label="Fashio kiosk home">
          <span className="ks-mark">F</span>
          <span>
            <b>{STORE.brand.name}</b>
            <small>
              {STORE.brand.store.floor} · {STORE.brand.store.city}
            </small>
          </span>
        </button>
        <div className="ks-top-actions">
          <button type="button" className="ks-btn ks-btn-ghost" onClick={() => useKiosk.getState().showQr({ kind: "shortlist" })}>
            <Heart size={20} aria-hidden /> Shortlist{count ? <span className="ks-count">{count}</span> : null}
          </button>
          <button type="button" className={`ks-btn ${assistAt ? "ks-btn-on" : "ks-btn-light"}`} data-stage-part="kiosk:assist" onClick={() => useKiosk.getState().callAssistant(true)}>
            <BellRing size={20} aria-hidden /> {assistAt ? "Assistant called" : "Call a floor assistant"}
          </button>
        </div>
      </header>
      {assistAt ? (
        <div className="ks-banner" role="status">
          <BellRing size={22} aria-hidden />
          <span>{STORE.kiosk.floor_assistant}</span>
          <button type="button" className="ks-icon" aria-label="Dismiss" onClick={() => useKiosk.getState().callAssistant(false)}>
            <X size={20} />
          </button>
        </div>
      ) : null}
      <div className="ks-body">{product ? <ProductView p={product} /> : search ? <Results results={results} /> : <Attract />}</div>
      <footer className="ks-foot">Products and images: Fashion Product Images Dataset (Param Aggarwal, MIT). Fashio is a demo store.</footer>
      <Tray />
    </div>
  );
}
