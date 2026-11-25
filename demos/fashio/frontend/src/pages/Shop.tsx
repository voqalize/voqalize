/**
 * The listing (/shop, /shop/<dept>, /shop/<dept>/<type>): the filter sidebar
 * (a full-screen sheet on a phone), sort, applied chips, the count and the
 * grid, a page of 48 at a time. The URL and the store's filters follow each
 * other: opening a route by hand seeds the search from it (department, type,
 * `?q=`); changing the search (a click or the agent's `shop.filter`) moves the
 * URL to the search's route (`routeFor`). Filter controls carry the CONTRACT's
 * `data-stage-part` names, each group wrapped in `data-stage-group`.
 */
import { SlidersHorizontal, X } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { CardSkeletons, ProductCard } from "../components/ProductCard";
import { PAGE_SIZE, useShopUi } from "../components/shopUi";
import {
  type Dept,
  type Filters,
  type Sort,
  department,
  facet,
  filtersFromRoute,
  inr,
  routeFor,
  search,
  summarise,
  swatch,
  typeLabel,
  useCatalog,
} from "../data/catalog";
import { useStore } from "../state/store";

export const DEPT_CHOICES: { id: Dept | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "men", label: "Men" },
  { id: "women", label: "Women" },
  { id: "kids", label: "Kids" },
  { id: "boys", label: "Boys" },
  { id: "girls", label: "Girls" },
  { id: "ethnic", label: "Ethnic" },
  { id: "footwear", label: "Footwear" },
  { id: "accessories", label: "Accessories" },
];
export const SORTS: { id: Sort; label: string }[] = [
  { id: "popular", label: "Popular" },
  { id: "new", label: "Newest" },
  { id: "price_asc", label: "Price: low to high" },
  { id: "price_desc", label: "Price: high to low" },
  { id: "discount", label: "Biggest discount" },
];
export const DISCOUNTS = [10, 20, 30, 40, 50];
export const PRICE_RANGES: { label: string; min?: number; max?: number }[] = [
  { label: "Under ₹500", max: 499 },
  { label: "₹500 to ₹999", min: 500, max: 999 },
  { label: "₹1,000 to ₹1,999", min: 1000, max: 1999 },
  { label: "₹2,000 to ₹4,999", min: 2000, max: 4999 },
  { label: "₹5,000 and up", min: 5000 },
];

const here = (pathname: string, search_: string) => pathname + (new URLSearchParams(search_).get("q") ? `?q=${encodeURIComponent(new URLSearchParams(search_).get("q")!)}` : "");

export function Shop() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const ready = useCatalog((s) => !!s.index);
  const filters = useStore((s) => s.filters);
  const sheet = useStore((s) => s.filtersOpen);
  const page = useShopUi((s) => s.page);

  // A route opened by hand seeds the search; a search the store already holds keeps its route.
  useEffect(() => {
    const now = here(location.pathname, location.search);
    if (routeFor(useStore.getState().filters) !== now) {
      useStore.getState().setFilters(filtersFromRoute(params.dept, params.type, new URLSearchParams(location.search).get("q")));
    }
  }, [location.pathname, location.search]); // eslint-disable-line react-hooks/exhaustive-deps
  // The search changed (a click, the agent): the URL follows, and the grid goes back to page one.
  useEffect(() => {
    useShopUi.setState({ page: 0 });
    const want = routeFor(useStore.getState().filters);
    if (want !== here(window.location.pathname.replace(import.meta.env.BASE_URL.replace(/\/$/, ""), "") || "/", window.location.search)) navigate(want, { replace: true });
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => useStore.getState().setFiltersOpen(false), []);

  const results = useMemo(() => (ready ? search(filters) : []), [filters, ready]);
  const pages = Math.max(1, Math.ceil(results.length / PAGE_SIZE));
  const shown = results.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const dept = department(filters.dept);
  const title = titleFor(filters);

  return (
    <div className="wrap shop">
      <Breadcrumbs trail={[{ label: "Shop", to: dept || filters.types?.length ? "/shop" : undefined }, ...(dept ? [{ label: dept.label, to: filters.types?.length === 1 ? `/shop/${dept.id}` : undefined }] : []), ...(dept && filters.types?.length === 1 ? [{ label: typeLabel(filters.types[0]) }] : [])]} />
      <div className="shop-head">
        <div>
          <h1 className="page-title">{ready ? title : "Shop"}</h1>
          <p className="shop-count" data-stage-thing="results">
            {ready ? (
              <>
                <b>{results.length.toLocaleString("en-IN")}</b> {results.length === 1 ? "product" : "products"}
                {Object.keys(filters).length ? <span className="muted">: {summarise(filters)}</span> : null}
              </>
            ) : (
              "Loading the catalogue…"
            )}
          </p>
        </div>
        <div className="shop-tools">
          <button type="button" className="btn ghost only-phone-flex" onClick={() => useStore.getState().setFiltersOpen(true)}>
            <SlidersHorizontal size={16} /> Filters{Object.keys(filters).filter((k) => k !== "sort").length ? ` (${Object.keys(filters).filter((k) => k !== "sort").length})` : ""}
          </button>
          <label className="sort" data-stage-part="sort" data-stage-group>
            <span>Sort by</span>
            <select value={filters.sort ?? "popular"} onChange={(e) => useStore.getState().patchFilters({ sort: e.target.value as Sort })}>
              {SORTS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <Chips filters={filters} />
      <div className="shop-grid">
        <FilterSidebar open={sheet} count={results.length} />
        <div className="shop-results">
          {!ready ? (
            <div className="grid">
              <CardSkeletons n={12} />
            </div>
          ) : results.length === 0 ? (
            <div className="empty">
              <h2>Nothing matches all of that</h2>
              <p>Loosen a filter, or start again with everything.</p>
              <button type="button" className="btn primary" onClick={() => useStore.getState().setFilters(filters.dept ? { dept: filters.dept } : {})}>
                Clear filters
              </button>
            </div>
          ) : (
            <>
              <div className="grid">
                {shown.map((p) => (
                  <ProductCard key={p.id} product={p} />
                ))}
              </div>
              {pages > 1 ? <Pager page={page} pages={pages} /> : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const OWNER: Partial<Record<Dept, string>> = { men: "Men's", women: "Women's", kids: "Kids'", boys: "Boys'", girls: "Girls'", ethnic: "Ethnic" };

/** The listing's heading: "Women's Kurtas", "Footwear", "Results for “silk”". */
export function titleFor(f: Filters): string {
  if (f.types?.length === 1) return `${f.dept && OWNER[f.dept] ? `${OWNER[f.dept]} ` : ""}${typeLabel(f.types[0])}`;
  if (f.query) return `Results for “${f.query}”`;
  return department(f.dept)?.label ?? (f.dept === "boys" ? "Boys" : f.dept === "girls" ? "Girls" : "Shop everything");
}

function Pager({ page, pages }: { page: number; pages: number }) {
  const go = (n: number) => {
    useShopUi.setState({ page: n });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const nums = [...new Set([0, page - 1, page, page + 1, pages - 1].filter((n) => n >= 0 && n < pages))].sort((a, b) => a - b);
  return (
    <nav className="pager" aria-label="Pages">
      <button type="button" className="btn ghost" disabled={page === 0} onClick={() => go(page - 1)}>
        Previous
      </button>
      {nums.map((n, i) => (
        <span key={n} className="pager-num-wrap">
          {i > 0 && n - nums[i - 1] > 1 ? <span className="pager-gap">…</span> : null}
          <button type="button" className={`pager-num${n === page ? " is-on" : ""}`} aria-current={n === page ? "page" : undefined} onClick={() => go(n)}>
            {n + 1}
          </button>
        </span>
      ))}
      <button type="button" className="btn ghost" disabled={page >= pages - 1} onClick={() => go(page + 1)}>
        Next
      </button>
    </nav>
  );
}

function Chips({ filters: f }: { filters: Filters }) {
  const patch = useStore((s) => s.patchFilters);
  const chips: { label: string; clear: () => void }[] = [];
  if (f.dept) chips.push({ label: department(f.dept)?.label ?? f.dept, clear: () => patch({ dept: undefined, types: undefined }) });
  for (const t of f.types ?? []) chips.push({ label: typeLabel(t), clear: () => patch({ types: f.types!.filter((x) => x !== t) }) });
  for (const b of f.brands ?? []) chips.push({ label: b, clear: () => patch({ brands: f.brands!.filter((x) => x !== b) }) });
  for (const c of f.colours ?? []) chips.push({ label: c, clear: () => patch({ colours: f.colours!.filter((x) => x !== c) }) });
  for (const s of f.sizes ?? []) chips.push({ label: `Size ${s}`, clear: () => patch({ sizes: f.sizes!.filter((x) => x !== s) }) });
  if (f.price_min != null || f.price_max != null)
    chips.push({ label: f.price_min != null && f.price_max != null ? `${inr(f.price_min)} to ${inr(f.price_max)}` : f.price_max != null ? `Under ${inr(f.price_max)}` : `${inr(f.price_min!)} and up`, clear: () => patch({ price_min: undefined, price_max: undefined }) });
  if (f.discount_min != null) chips.push({ label: `${f.discount_min}% off or more`, clear: () => patch({ discount_min: undefined }) });
  for (const u of f.usage ?? []) chips.push({ label: u, clear: () => patch({ usage: f.usage!.filter((x) => x !== u) }) });
  for (const s of f.seasons ?? []) chips.push({ label: s, clear: () => patch({ seasons: f.seasons!.filter((x) => x !== s) }) });
  if (f.query) chips.push({ label: `“${f.query}”`, clear: () => patch({ query: undefined }) });
  if (!chips.length) return null;
  return (
    <div className="chips" aria-label="Applied filters">
      {chips.map((c, i) => (
        <button key={i} type="button" className="chip is-applied" onClick={c.clear} aria-label={`Remove ${c.label}`}>
          {c.label} <X size={13} aria-hidden />
        </button>
      ))}
      <button type="button" className="chip-clear" onClick={() => useStore.getState().setFilters(f.sort ? { sort: f.sort } : {})}>
        Clear all
      </button>
    </div>
  );
}

const toggle = (xs: string[] | undefined, v: string) => ((xs ?? []).includes(v) ? (xs ?? []).filter((x) => x !== v) : [...(xs ?? []), v]);

function Group({ name, title, children, part }: { name: string; title: string; children: ReactNode; part?: string }) {
  return (
    <fieldset className="fgroup" data-stage-group={name} data-stage-part={part}>
      <legend>{title}</legend>
      {children}
    </fieldset>
  );
}

function CheckList({ items, picked, onToggle, part, label, scroll = false }: { items: { value: string; count: number }[]; picked: string[]; onToggle: (v: string) => void; part: string; label?: (v: string) => ReactNode; scroll?: boolean }) {
  return (
    <ul className={`checks${scroll ? " is-scroll" : ""}`}>
      {items.map((x) => (
        <li key={x.value}>
          <label className="check" data-stage-part={`${part}:${x.value}`}>
            <input type="checkbox" checked={picked.includes(x.value)} onChange={() => onToggle(x.value)} />
            <span className="check-label">{label ? label(x.value) : x.value}</span>
            <span className="check-count">{x.count}</span>
          </label>
        </li>
      ))}
    </ul>
  );
}

function FilterSidebar({ open, count }: { open: boolean; count: number }) {
  const f = useStore((s) => s.filters);
  const patch = useStore((s) => s.patchFilters);
  const ready = useCatalog((s) => !!s.index);
  const { allBrands, brandQuery } = useShopUi();
  const facets = useMemo(
    () =>
      ready
        ? {
            types: facet("types", f),
            brands: facet("brands", f),
            colours: facet("colours", f),
            sizes: facet("sizes", f),
            usage: facet("usage", f),
            seasons: facet("seasons", f),
          }
        : null,
    [f, ready],
  );
  const [min, setMin] = useState(f.price_min?.toString() ?? "");
  const [max, setMax] = useState(f.price_max?.toString() ?? "");
  useEffect(() => {
    setMin(f.price_min?.toString() ?? "");
    setMax(f.price_max?.toString() ?? "");
  }, [f.price_min, f.price_max]);
  const commitPrice = () => patch({ price_min: min ? Math.max(0, Number(min)) : undefined, price_max: max ? Math.max(0, Number(max)) : undefined });

  const close = () => useStore.getState().setFiltersOpen(false);
  const brands = useMemo(() => {
    if (!facets) return [];
    const q = brandQuery.trim().toLowerCase();
    const all = facets.brands.filter((b) => !q || b.value.toLowerCase().includes(q));
    const top = allBrands || q ? all : all.slice(0, 10);
    const picked = (f.brands ?? []).filter((b) => !top.some((x) => x.value === b)).map((value) => ({ value, count: facets.brands.find((x) => x.value === value)?.count ?? 0 }));
    return [...picked, ...top];
  }, [facets, brandQuery, allBrands, f.brands]);

  return (
    <aside className={`filters${open ? " is-open" : ""}`} data-overlay={open ? "full" : undefined} aria-label="Filters">
      <div className="filters-sheet-head">
        <b>Filters</b>
        <button type="button" className="icon-btn" aria-label="Close filters" onClick={close}>
          <X size={22} />
        </button>
      </div>
      <Group name="dept" title="Department">
        <div className="pills">
          {DEPT_CHOICES.map((d) => (
            <button
              key={d.id}
              type="button"
              className={`pill${(f.dept ?? "all") === d.id ? " is-on" : ""}`}
              aria-pressed={(f.dept ?? "all") === d.id}
              data-stage-part={`dept:${d.id}`}
              onClick={() => patch({ dept: d.id === "all" ? undefined : d.id, types: undefined })}
            >
              {d.label}
            </button>
          ))}
        </div>
      </Group>
      {facets ? (
        <>
          <Group name="type" title="Category">
            <CheckList items={facets.types} picked={f.types ?? []} onToggle={(v) => patch({ types: toggle(f.types, v) })} part="type" label={typeLabel} scroll />
          </Group>
          <Group name="brand" title="Brand">
            <input className="brand-search" type="search" placeholder="Search brands" aria-label="Search brands" value={brandQuery} onChange={(e) => useShopUi.setState({ brandQuery: e.target.value })} />
            <CheckList items={brands} picked={f.brands ?? []} onToggle={(v) => patch({ brands: toggle(f.brands, v) })} part="brand" scroll />
            {!brandQuery && facets.brands.length > 10 ? (
              <button type="button" className="link-btn" onClick={() => useShopUi.setState({ allBrands: !allBrands })}>
                {allBrands ? "Top brands only" : `All ${facets.brands.length} brands`}
              </button>
            ) : null}
          </Group>
          <Group name="colour" title="Colour">
            <div className="swatches">
              {facets.colours.map((c) => {
                const on = (f.colours ?? []).includes(c.value);
                return (
                  <button key={c.value} type="button" className={`swatch${on ? " is-on" : ""}`} aria-pressed={on} title={`${c.value} (${c.count})`} data-stage-part={`colour:${c.value}`} onClick={() => patch({ colours: toggle(f.colours, c.value) })}>
                    <span className="swatch-dot" style={{ background: swatch(c.value) }} />
                    <span className="swatch-name">{c.value}</span>
                  </button>
                );
              })}
            </div>
          </Group>
          {facets.sizes.length ? (
            <Group name="size" title="Size in stock">
              <div className="pills">
                {facets.sizes.map((s) => {
                  const on = (f.sizes ?? []).includes(s.value);
                  return (
                    <button key={s.value} type="button" className={`pill is-size${on ? " is-on" : ""}`} aria-pressed={on} data-stage-part={`size:${s.value}`} onClick={() => patch({ sizes: toggle(f.sizes, s.value) })}>
                      {s.value}
                    </button>
                  );
                })}
              </div>
            </Group>
          ) : null}
          <Group name="price" title="Price" part="price">
            <div className="price-row">
              <label>
                <span className="sr-only">Minimum price</span>
                <input type="number" inputMode="numeric" placeholder="Min ₹" value={min} onChange={(e) => setMin(e.target.value)} onBlur={commitPrice} onKeyDown={(e) => e.key === "Enter" && commitPrice()} />
              </label>
              <span aria-hidden>to</span>
              <label>
                <span className="sr-only">Maximum price</span>
                <input type="number" inputMode="numeric" placeholder="Max ₹" value={max} onChange={(e) => setMax(e.target.value)} onBlur={commitPrice} onKeyDown={(e) => e.key === "Enter" && commitPrice()} />
              </label>
            </div>
            <div className="pills">
              {PRICE_RANGES.map((r) => {
                const on = f.price_min === r.min && f.price_max === r.max;
                return (
                  <button key={r.label} type="button" className={`pill${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => patch(on ? { price_min: undefined, price_max: undefined } : { price_min: r.min, price_max: r.max })}>
                    {r.label}
                  </button>
                );
              })}
            </div>
          </Group>
          <Group name="discount" title="Discount" part="discount">
            <div className="pills">
              {DISCOUNTS.map((d) => {
                const on = f.discount_min === d;
                return (
                  <button key={d} type="button" className={`pill${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => patch({ discount_min: on ? undefined : d })}>
                    {d}% and more
                  </button>
                );
              })}
            </div>
          </Group>
          <Group name="usage" title="Occasion">
            <CheckList items={facets.usage} picked={f.usage ?? []} onToggle={(v) => patch({ usage: toggle(f.usage, v) })} part="usage" />
          </Group>
          <Group name="season" title="Season">
            <CheckList items={facets.seasons} picked={f.seasons ?? []} onToggle={(v) => patch({ seasons: toggle(f.seasons, v) })} part="season" />
          </Group>
        </>
      ) : (
        <p className="muted">Loading filters…</p>
      )}
      <button type="button" className="btn primary filters-done" onClick={close}>
        Show {count.toLocaleString("en-IN")} products
      </button>
    </aside>
  );
}
