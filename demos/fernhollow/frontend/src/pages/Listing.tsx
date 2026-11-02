import { SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import {
  type ListingFilters,
  type Product,
  type SortKey,
  SORTS,
  applyListingFilters,
  categoriesIn,
  facets,
  getCategory,
  getRoom,
  money,
  priceBands,
  products,
  productsIn,
  productsInCategory,
  search,
  sortProducts,
  splitOpt,
} from "../data/catalog";
import { site } from "../data/content";
import { Crumbs } from "../components/bits";
import { ProductGrid } from "../components/ProductCard";
import { emit } from "../voice/events";
import { useTitle, useVisibleProducts } from "./usePage";

const PAGE = 24;

function readFilters(sp: URLSearchParams): ListingFilters & { sort: SortKey } {
  const num = (k: string) => {
    const v = sp.get(k);
    return v != null && v !== "" && !Number.isNaN(Number(v)) ? Number(v) : null;
  };
  return {
    q: sp.get("q") ?? "",
    min: num("min"),
    max: num("max"),
    sale: sp.get("sale") === "1",
    category: sp.get("cat"),
    opts: sp.getAll("opt"),
    sort: (SORTS.some((s) => s.key === sp.get("sort")) ? sp.get("sort") : "featured") as SortKey,
  };
}

interface ListingProps {
  title: string;
  intro?: string;
  crumbs: { label: string; to?: string }[];
  base: Product[];
  /** Category pills along the top (room pages). */
  pills?: { label: string; slug: string }[];
  /** The search page keeps its query in the title, not in the rail. */
  isSearch?: boolean;
  empty?: React.ReactNode;
}

export function ListingView({ title, intro, crumbs, base, pills, isSearch, empty }: ListingProps) {
  const [sp, setSp] = useSearchParams();
  const f = readFilters(sp);
  const [shown, setShown] = useState(PAGE);
  const [railOpen, setRailOpen] = useState(false);

  const scoped = useMemo(() => (isSearch && f.q ? search(f.q, base) : base), [base, isSearch, f.q]);
  const filtered = useMemo(
    () => applyListingFilters(scoped, { ...f, q: isSearch ? "" : f.q }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scoped, sp.toString()],
  );
  const sorted = useMemo(() => (isSearch && f.sort === "featured" ? filtered : sortProducts(filtered, f.sort)), [filtered, f.sort, isSearch]);
  const page = sorted.slice(0, shown);
  useVisibleProducts(page.map((p) => p.id));
  useEffect(() => setShown(PAGE), [sp.toString(), base]);

  const update = (mut: (n: URLSearchParams) => void) => {
    const next = new URLSearchParams(sp);
    mut(next);
    setSp(next, { replace: true, preventScrollReset: true });
    const r = readFilters(next);
    emit("filter_changed", {
      filters: {
        category: r.category,
        price_min: r.min,
        price_max: r.max,
        on_sale: r.sale || null,
        options: r.opts,
        query: r.q || null,
        sort: r.sort,
      },
    });
  };
  const toggleOpt = (key: string) =>
    update((n) => {
      const all = n.getAll("opt");
      n.delete("opt");
      (all.includes(key) ? all.filter((x) => x !== key) : [...all, key]).forEach((v) => n.append("opt", v));
    });
  const setPrice = (min: number | null, max: number | null) =>
    update((n) => {
      min == null ? n.delete("min") : n.set("min", String(min));
      max == null ? n.delete("max") : n.set("max", String(max));
    });

  const active: { label: string; clear: () => void }[] = [
    ...(f.category ? [{ label: getCategory(f.category)?.name ?? f.category, clear: () => update((n) => n.delete("cat")) }] : []),
    ...(f.sale ? [{ label: "On sale", clear: () => update((n) => n.delete("sale")) }] : []),
    ...(f.min != null || f.max != null
      ? [
          {
            label: f.min != null && f.max != null ? `${money(f.min)} – ${money(f.max)}` : f.min != null ? `Over ${money(f.min)}` : `Under ${money(f.max!)}`,
            clear: () => setPrice(null, null),
          },
        ]
      : []),
    ...f.opts.map((o) => ({ label: splitOpt(o)[1], clear: () => toggleOpt(o) })),
    ...(!isSearch && f.q ? [{ label: `“${f.q}”`, clear: () => update((n) => n.delete("q")) }] : []),
  ];
  const clearAll = () =>
    update((n) => {
      ["cat", "sale", "min", "max", "opt"].forEach((k) => n.delete(k));
      if (!isSearch) n.delete("q");
    });

  return (
    <div className="listing">
      <div className="wrap">
        <Crumbs items={crumbs} />
        <header className="listing-head">
          <h1 className="h1">{title}</h1>
          {intro ? <p className="lede">{intro}</p> : null}
        </header>
        {pills?.length ? (
          <div className="pills" role="list">
            {pills.map((c) => (
              <Link role="listitem" key={c.slug} to={`/category/${c.slug}`} className="chip">
                {c.label}
              </Link>
            ))}
          </div>
        ) : null}
        <div className="listing-bar">
          <button type="button" className="btn btn-ghost btn-sm only-mobile" onClick={() => setRailOpen(true)}>
            <SlidersHorizontal size={15} /> Filter{active.length ? ` (${active.length})` : ""}
          </button>
          <p className="small listing-count" aria-live="polite">
            {sorted.length} {sorted.length === 1 ? "piece" : "pieces"}
          </p>
          <label className="sort">
            <span className="small">Sort</span>
            <select className="select select-sm" value={f.sort} onChange={(e) => update((n) => n.set("sort", e.target.value))}>
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {active.length ? (
          <div className="active-filters" data-spot="section:filters">
            {active.map((a) => (
              <button key={a.label} type="button" className="chip is-on" onClick={a.clear} aria-label={`Remove filter ${a.label}`}>
                {a.label} <X size={13} className="x" />
              </button>
            ))}
            <button type="button" className="link small" onClick={clearAll}>
              Clear all
            </button>
          </div>
        ) : null}
        <div className="listing-body">
          <FilterRail
            open={railOpen}
            onClose={() => setRailOpen(false)}
            scoped={scoped}
            f={f}
            isSearch={!!isSearch}
            count={sorted.length}
            onQuery={(q) => update((n) => (q ? n.set("q", q) : n.delete("q")))}
            onSale={() => update((n) => (f.sale ? n.delete("sale") : n.set("sale", "1")))}
            onCategory={(slug) => update((n) => (slug && f.category !== slug ? n.set("cat", slug) : n.delete("cat")))}
            onPrice={setPrice}
            onOpt={toggleOpt}
          />
          <div className="listing-results">
            {sorted.length === 0 ? (
              <div className="empty">
                {empty ?? (
                  <>
                    <p className="h3">No pieces match all of that.</p>
                    <p className="small">Remove a filter to see more, or search the whole store.</p>
                    {active.length ? (
                      <button type="button" className="btn btn-ghost btn-sm" onClick={clearAll}>
                        Clear filters
                      </button>
                    ) : null}
                  </>
                )}
              </div>
            ) : (
              <>
                <ProductGrid products={page} />
                {shown < sorted.length ? (
                  <div className="more">
                    <p className="small">
                      Showing {page.length} of {sorted.length}
                    </p>
                    <button type="button" className="btn btn-ghost" onClick={() => setShown((n) => n + PAGE)}>
                      Show more
                    </button>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FilterRail({
  open,
  onClose,
  scoped,
  f,
  isSearch,
  count,
  onQuery,
  onSale,
  onCategory,
  onPrice,
  onOpt,
}: {
  open: boolean;
  onClose: () => void;
  scoped: Product[];
  f: ListingFilters;
  isSearch: boolean;
  count: number;
  onQuery: (q: string) => void;
  onSale: () => void;
  onCategory: (slug: string | null) => void;
  onPrice: (min: number | null, max: number | null) => void;
  onOpt: (key: string) => void;
}) {
  const [q, setQ] = useState(f.q);
  useEffect(() => setQ(f.q), [f.q]);
  const [min, setMin] = useState(f.min?.toString() ?? "");
  const [max, setMax] = useState(f.max?.toString() ?? "");
  useEffect(() => {
    setMin(f.min?.toString() ?? "");
    setMax(f.max?.toString() ?? "");
  }, [f.min, f.max]);
  const cats = [...new Set(scoped.map((p) => p.categorySlug))].map((s) => getCategory(s)!).filter(Boolean);
  const groups = facets(scoped);
  const bands = priceBands(scoped);
  const saleCount = scoped.filter((p) => p.onSale).length;

  return (
    <aside className={`rail-filters${open ? " is-open" : ""}`} aria-label="Filters">
      <div className="rail-filters-head only-mobile">
        <p className="h3">Filter</p>
        <button type="button" className="icon-btn" aria-label="Close filters" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <div className="rail-filters-body">
        {!isSearch ? (
          <form
            className="filter-group"
            onSubmit={(e) => {
              e.preventDefault();
              onQuery(q.trim());
            }}
          >
            <label className="filter-title" htmlFor="filter-q">
              Search within
            </label>
            <input id="filter-q" className="input input-sm" type="search" placeholder="Oak, linen, round…" value={q} onChange={(e) => setQ(e.target.value)} onBlur={() => q.trim() !== f.q && onQuery(q.trim())} />
          </form>
        ) : null}

        {cats.length > 1 ? (
          <fieldset className="filter-group">
            <legend className="filter-title">Category</legend>
            <ul className="filter-list">
              {cats.map((c) => (
                <li key={c.slug}>
                  <label className="check">
                    <input type="checkbox" checked={f.category === c.slug} onChange={() => onCategory(c.slug)} />
                    <span>{c.name}</span>
                    <span className="check-count">{scoped.filter((p) => p.categorySlug === c.slug).length}</span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        ) : null}

        <fieldset className="filter-group">
          <legend className="filter-title">Price</legend>
          {bands.length ? (
            <div className="band-chips">
              {bands.map((b) => (
                <button
                  type="button"
                  key={b.label}
                  className="chip chip-sm"
                  aria-pressed={f.min === b.min && f.max === b.max}
                  onClick={() => (f.min === b.min && f.max === b.max ? onPrice(null, null) : onPrice(b.min, b.max))}
                >
                  {b.label}
                </button>
              ))}
            </div>
          ) : null}
          <form
            className="price-inputs"
            onSubmit={(e) => {
              e.preventDefault();
              onPrice(min ? Number(min) : null, max ? Number(max) : null);
            }}
          >
            <label>
              <span className="sr-only">Minimum price</span>
              <span className="price-prefix">$</span>
              <input className="input input-sm" inputMode="numeric" placeholder="Min" value={min} onChange={(e) => setMin(e.target.value.replace(/[^\d]/g, ""))} />
            </label>
            <span aria-hidden>–</span>
            <label>
              <span className="sr-only">Maximum price</span>
              <span className="price-prefix">$</span>
              <input className="input input-sm" inputMode="numeric" placeholder="Max" value={max} onChange={(e) => setMax(e.target.value.replace(/[^\d]/g, ""))} />
            </label>
            <button type="submit" className="btn btn-ghost btn-sm">
              Go
            </button>
          </form>
        </fieldset>

        {saleCount ? (
          <div className="filter-group">
            <label className="toggle">
              <input type="checkbox" checked={f.sale} onChange={onSale} />
              <span className="toggle-ui" aria-hidden />
              <span>On sale</span>
              <span className="check-count">{saleCount}</span>
            </label>
          </div>
        ) : null}

        {groups.map((g) => (
          <fieldset key={g.name} className="filter-group">
            <legend className="filter-title">{g.name}</legend>
            <ul className="filter-list">
              {g.values.map((v) => {
                const key = `${g.name}:${v.value}`;
                return (
                  <li key={key}>
                    <label className="check">
                      <input type="checkbox" checked={f.opts.includes(key)} onChange={() => onOpt(key)} />
                      <span>{v.value}</span>
                      <span className="check-count">{v.count}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </fieldset>
        ))}
      </div>
      <div className="rail-filters-foot only-mobile">
        <button type="button" className="btn btn-primary btn-block" onClick={onClose}>
          Show {count} {count === 1 ? "piece" : "pieces"}
        </button>
      </div>
    </aside>
  );
}

// ── Routes ────────────────────────────────────────────────────────────────

export function RoomPage() {
  const { room } = useParams();
  const r = getRoom(room);
  useTitle(r?.name ?? "Room");
  const base = useMemo(() => (r ? productsIn(r.id) : []), [r]);
  if (!r) return <Navigate to="/shop" replace />;
  return (
    <ListingView
      title={r.name}
      intro={site.rooms[r.id]}
      crumbs={[{ label: "Home", to: "/" }, { label: r.name }]}
      base={base}
      pills={categoriesIn(r.id).map((c) => ({ label: c.name, slug: c.slug }))}
    />
  );
}

export function CategoryPage() {
  const { slug } = useParams();
  const c = getCategory(slug);
  const r = getRoom(c?.room);
  useTitle(c?.name ?? "Category");
  const base = useMemo(() => (c ? productsInCategory(c.slug) : []), [c]);
  if (!c || !r) return <Navigate to="/shop" replace />;
  return (
    <ListingView
      title={c.name}
      intro={site.categories[c.slug]}
      crumbs={[{ label: "Home", to: "/" }, { label: r.name, to: `/room/${r.id}` }, { label: c.name }]}
      base={base}
    />
  );
}

export function ShopPage() {
  useTitle("All pieces");
  return <ListingView title="All pieces" intro="Every piece in the store, room by room." crumbs={[{ label: "Home", to: "/" }, { label: "All pieces" }]} base={products} />;
}

const SALE = products.filter((p) => p.onSale);
export function SalePage() {
  useTitle("Sale");
  return (
    <ListingView
      title="Sale"
      intro="Pieces with a real reduction on their usual price. The saving is shown on every one."
      crumbs={[{ label: "Home", to: "/" }, { label: "Sale" }]}
      base={SALE}
    />
  );
}

export function SearchPage() {
  const [sp] = useSearchParams();
  const q = sp.get("q") ?? "";
  useTitle(q ? `Search: ${q}` : "Search");
  return (
    <ListingView
      title={q ? `Results for “${q}”` : "Search"}
      crumbs={[{ label: "Home", to: "/" }, { label: "Search" }]}
      base={products}
      isSearch
      empty={
        <>
          <p className="h3">{q ? `Nothing matches “${q}”.` : "Type a word to search."}</p>
          <p className="small">Try a material, a room or a kind of piece: oak, linen, floor lamp.</p>
          <Link className="btn btn-ghost btn-sm" to="/shop">
            Browse all pieces
          </Link>
        </>
      }
    />
  );
}
