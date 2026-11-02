import { SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router-dom";
import { useAppStage, useMove } from "../stage/host";
import { type ListingApi, listingPerformers } from "../stage/listing";
import {
  type ListingFilters,
  type Product,
  type SortKey,
  SORTS,
  applyListingFilters,
  categories,
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
    // In the brain's terms: option values become materials, colours and styles.
    const values = (names: string[]) => r.opts.filter((o) => names.includes(splitOpt(o)[0])).map((o) => splitOpt(o)[1].toLowerCase());
    const rooms = new Set(base.map((p) => p.room));
    const cats = new Set(base.map((p) => p.categorySlug));
    emit("filter_changed", {
      filters: {
        room: rooms.size === 1 ? [...rooms][0] : null,
        category: r.category ?? (cats.size === 1 ? [...cats][0] : null),
        materials: values(["Material", "Finish", "Fabric", "Frame"]),
        colours: values(["Color"]),
        styles: values(["Style"]),
        price_min: r.min,
        price_max: r.max,
        on_sale: r.sale || null,
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

  // ── What the rail offers, by its own labels (for Emily and for listing_viewed) ──
  const rail = useMemo(() => railFacets(scoped), [scoped]);
  const activeMap: Record<string, string[]> = {};
  if (f.category) activeMap.Category = [getCategory(f.category)?.name ?? f.category];
  if (f.sale) activeMap["On sale"] = ["On sale"];
  for (const o of f.opts) {
    const [k, v] = splitOpt(o);
    (activeMap[k] ??= []).push(v);
  }
  const location = useLocation();
  const stage = useAppStage((s) => s.stage);
  const api: ListingApi = {
    facets: rail,
    active: activeMap,
    countAfter(mut) {
      const next = new URLSearchParams(sp);
      mut(next);
      const r = readFilters(next);
      return applyListingFilters(scoped, { ...r, q: isSearch ? "" : r.q }).length;
    },
    toggleMut(facet, value) {
      if (facet === "Category") {
        const slug = categories.find((c) => c.name === value)?.slug ?? value;
        return (n) => (n.get("cat") === slug ? n.delete("cat") : n.set("cat", slug));
      }
      if (facet === "On sale") return (n) => (n.get("sale") === "1" ? n.delete("sale") : n.set("sale", "1"));
      const key = `${facet}:${value}`;
      return (n) => {
        const all = n.getAll("opt");
        n.delete("opt");
        (all.includes(key) ? all.filter((x) => x !== key) : [...all, key]).forEach((v) => n.append("opt", v));
      };
    },
    setPrice,
    setSort: (key) => update((n) => n.set("sort", key)),
    clearAll,
    openSheet: () => setRailOpen(true),
    closeSheet: () => setRailOpen(false),
    sheetOpen: () => railOpen,
  };
  const performers = listingPerformers(api);
  useMove(stage, "listing.filter", performers["listing.filter"]);
  useMove(stage, "listing.unfilter", performers["listing.unfilter"]);
  useMove(stage, "listing.clear_filters", performers["listing.clear_filters"]);
  useMove(stage, "listing.price", performers["listing.price"]);
  useMove(stage, "listing.sort", performers["listing.sort"]);

  // listing_viewed: on arrival and after every change, whoever made it.
  const viewed = JSON.stringify([location.pathname, sp.toString(), sorted.length]);
  useEffect(() => {
    const t = window.setTimeout(() => {
      const agent = stage?.agent && Date.now() <= stage.agent.until + 400;
      emit(
        "listing_viewed",
        {
          page: location.pathname + location.search,
          title,
          facets: rail,
          active: activeMap,
          ...(f.min != null || f.max != null ? { price: { min: f.min, max: f.max } } : {}),
          sort: SORTS.find((s) => s.key === f.sort)?.label ?? f.sort,
          count: sorted.length,
        },
        agent ? "emily" : "visitor",
      );
    }, 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewed]);

  return (
    <div className="listing">
      <div className="wrap">
        <Crumbs items={crumbs} />
        <header className="listing-head">
          <h1 className="h1">{title}</h1>
          {intro ? <p className="lede">{intro}</p> : null}
          {isSearch ? <SearchField /> : null}
        </header>
        {pills?.length ? (
          <div className="pills" role="list">
            {pills.map((c) => (
              <Link role="listitem" key={c.slug} to={`/category/${c.slug}`} className="chip" data-fh-thing={`category:${c.slug}`}>
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
            <select className="select select-sm" data-stage-thing="sort" data-stage-label="Sort" value={f.sort} onChange={(e) => update((n) => n.set("sort", e.target.value))}>
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
            <button type="button" className="link small" data-stage-thing="clear-filters" onClick={clearAll}>
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

function SearchField() {
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState(sp.get("q") ?? "");
  useEffect(() => setQ(sp.get("q") ?? ""), [sp]);
  return (
    <form
      className="search-page-form"
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        const next = new URLSearchParams();
        if (q.trim()) next.set("q", q.trim());
        setSp(next);
      }}
    >
      <label className="sr-only" htmlFor="search-page-q">
        Search the store
      </label>
      <input id="search-page-q" className="input" type="search" placeholder="Search sofas, oak, linen…" value={q} onChange={(e) => setQ(e.target.value)} />
      <button type="submit" className="btn btn-primary">
        Search
      </button>
    </form>
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
                  <label className="check" data-stage-part={`Category:${c.name}`}>
                    <input type="checkbox" checked={f.category === c.slug} onChange={() => onCategory(c.slug)} />
                    <span>{c.name}</span>
                    <span className="check-count">{scoped.filter((p) => p.categorySlug === c.slug).length}</span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        ) : null}

        <fieldset className="filter-group" data-stage-thing="price" data-stage-label="Price">
          <legend className="filter-title">Price</legend>
          {bands.length ? (
            <div className="band-chips">
              {bands.map((b) => (
                <button
                  type="button"
                  key={b.label}
                  className="chip chip-sm"
                  data-stage-part={`Price:${b.label}`}
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
            <label className="toggle" data-stage-part="On sale:On sale">
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
                    <label className="check" data-stage-part={key}>
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

/** The rail's facets and options, by the labels it shows: Category, On sale, then each option facet. */
export function railFacets(scoped: Product[]): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  const cats = [...new Set(scoped.map((p) => p.categorySlug))].map((s) => getCategory(s)!).filter(Boolean);
  if (cats.length > 1) out.Category = cats.map((c) => c.name);
  if (scoped.some((p) => p.onSale)) out["On sale"] = ["On sale"];
  for (const g of facets(scoped)) out[g.name] = g.values.map((v) => v.value);
  return out;
}
