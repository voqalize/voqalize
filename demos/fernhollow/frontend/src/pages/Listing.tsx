import { SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router-dom";
import { useAppStage, useMove } from "../stage/host";
import { type ListingApi, listingPerformers } from "../stage/listing";
import { type RailFacet, describeFacet, partOf, railModel } from "../data/rail";
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
    // The brain hears this change as listing_viewed once the grid has
    // rendered, with the count the shopper sees. filter_changed is not sent
    // from here: the brain recounted its filters with its own rules and could
    // say "0 products show" over a grid of 24.
  };

  // ── The rail, as one typed definition (src/data/rail.ts) ──
  const rail = useMemo(() => railModel(scoped, sp), [scoped, sp.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const chipLabel = (r: RailFacet, v: string) => (r.kind === "toggle" ? r.name : v);
  const active: { label: string; clear: () => void }[] = [
    ...rail.flatMap((r) => {
      if (r.active.length) return r.active.map((v) => ({ label: chipLabel(r, v), clear: () => update(r.toggle(v)) }));
      if ((r.kind === "bands" || r.kind === "range") && (r.min != null || r.max != null)) {
        const label = r.min != null && r.max != null ? `${money(r.min)} – ${money(r.max)}` : r.min != null ? `Over ${money(r.min)}` : `Under ${money(r.max!)}`;
        return [{ label, clear: () => update(r.clear()) }];
      }
      return [];
    }),
    ...(!isSearch && f.q ? [{ label: `“${f.q}”`, clear: () => update((n) => n.delete("q")) }] : []),
  ];
  const clearAll = () =>
    update((n) => {
      for (const r of rail) r.clear()(n);
      if (!isSearch) n.delete("q");
    });

  const location = useLocation();
  const stage = useAppStage((s) => s.stage);
  const api: ListingApi = {
    facets: rail,
    countAfter(mut) {
      const next = new URLSearchParams(sp);
      mut(next);
      const r = readFilters(next);
      return applyListingFilters(scoped, { ...r, q: isSearch ? "" : r.q }).length;
    },
    apply: update,
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
  useMove(stage, "listing.range", performers["listing.range"]);
  useMove(stage, "listing.price", performers["listing.price"]);
  useMove(stage, "listing.sort", performers["listing.sort"]);

  // listing_viewed: on arrival and after every change, whoever made it, once the grid has the new count.
  const viewed = JSON.stringify([location.pathname, sp.toString(), sorted.length]);
  useEffect(() => {
    const t = window.setTimeout(() => {
      const agent = stage?.agent && Date.now() <= stage.agent.until + 400;
      emit(
        "listing_viewed",
        {
          page: location.pathname + location.search,
          title,
          facets: rail.map(describeFacet),
          sort: { value: SORTS.find((s) => s.key === f.sort)?.label ?? f.sort, options: SORTS.map((s) => s.label) },
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
            rail={rail}
            q={f.q}
            isSearch={!!isSearch}
            count={sorted.length}
            onQuery={(q) => update((n) => (q ? n.set("q", q) : n.delete("q")))}
            onChange={update}
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

/** The rail, drawn from its typed definition: each facet by its kind. */
function FilterRail({
  open,
  onClose,
  rail,
  q: query,
  isSearch,
  count,
  onQuery,
  onChange,
}: {
  open: boolean;
  onClose: () => void;
  rail: RailFacet[];
  q: string;
  isSearch: boolean;
  count: number;
  onQuery: (q: string) => void;
  onChange: (mut: (n: URLSearchParams) => void) => void;
}) {
  const [q, setQ] = useState(query);
  useEffect(() => setQ(query), [query]);

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
            <input id="filter-q" className="input input-sm" type="search" placeholder="Oak, linen, round…" value={q} onChange={(e) => setQ(e.target.value)} onBlur={() => q.trim() !== query && onQuery(q.trim())} />
          </form>
        ) : null}
        {rail.map((r) => (
          <RailGroup key={r.name} r={r} onChange={onChange} />
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

function RailGroup({ r, onChange }: { r: RailFacet; onChange: (mut: (n: URLSearchParams) => void) => void }) {
  if (r.kind === "toggle") {
    return (
      <div className="filter-group">
        <label className="toggle" data-stage-part={partOf(r, r.name)}>
          <input type="checkbox" checked={r.active.length > 0} onChange={() => onChange(r.toggle(r.name))} />
          <span className="toggle-ui" aria-hidden />
          <span>{r.name}</span>
          <span className="check-count">{r.count}</span>
        </label>
      </div>
    );
  }
  if (r.kind === "options") {
    return (
      <fieldset className="filter-group">
        <legend className="filter-title">{r.name}</legend>
        <ul className="filter-list">
          {(r.values ?? []).map((v) => (
            <li key={v.value}>
              <label className="check" data-stage-part={partOf(r, v.value)}>
                <input type="checkbox" checked={r.active.includes(v.value)} onChange={() => onChange(r.toggle(v.value))} />
                <span>{v.value}</span>
                <span className="check-count">{v.count}</span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
    );
  }
  return <RangeGroup r={r} onChange={onChange} />;
}

/** A bands facet's chips and its free min / max (a range facet has only the latter). */
function RangeGroup({ r, onChange }: { r: RailFacet; onChange: (mut: (n: URLSearchParams) => void) => void }) {
  const [min, setMin] = useState(r.min?.toString() ?? "");
  const [max, setMax] = useState(r.max?.toString() ?? "");
  useEffect(() => {
    setMin(r.min?.toString() ?? "");
    setMax(r.max?.toString() ?? "");
  }, [r.min, r.max]);
  const money$ = r.name === "Price";
  return (
    <fieldset className="filter-group" data-stage-thing={`range:${r.name}`} data-stage-label={r.name}>
      <legend className="filter-title">{r.name}</legend>
      {r.bands?.length ? (
        <div className="band-chips">
          {r.bands.map((b) => (
            <button
              type="button"
              key={b.label}
              className="chip chip-sm"
              data-stage-part={partOf(r, b.label)}
              aria-pressed={r.active.includes(b.label)}
              onClick={() => onChange(r.toggle(b.label))}
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
          onChange(r.setRange(min ? Number(min) : null, max ? Number(max) : null));
        }}
      >
        <label>
          <span className="sr-only">Lowest {r.name.toLowerCase()}</span>
          {money$ ? <span className="price-prefix">$</span> : null}
          <input className="input input-sm" inputMode="numeric" placeholder="Min" value={min} onChange={(e) => setMin(e.target.value.replace(/[^\d]/g, ""))} />
        </label>
        <span aria-hidden>–</span>
        <label>
          <span className="sr-only">Highest {r.name.toLowerCase()}</span>
          {money$ ? <span className="price-prefix">$</span> : null}
          <input className="input input-sm" inputMode="numeric" placeholder="Max" value={max} onChange={(e) => setMax(e.target.value.replace(/[^\d]/g, ""))} />
        </label>
        <button type="submit" className="btn btn-ghost btn-sm">
          Go
        </button>
      </form>
    </fieldset>
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
