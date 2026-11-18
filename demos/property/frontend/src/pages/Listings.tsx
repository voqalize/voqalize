/**
 * /listings — the search: sidebar filters (each control marked for Stage as
 * `data-stage-part`), the results, and the drawn city map. The visitor's
 * clicks and the agent's `listings.filter` write the same store.
 */
import { Map as MapIcon, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { CityMap } from "../components/CityMap";
import { ListingCard } from "../components/ListingCard";
import {
  ALL_AMENITIES,
  CITIES,
  type CityId,
  type Filters,
  getCity,
  inrShort,
  officesOf,
  summarise,
} from "../data/homes";
import { useResults, useStore } from "../state/store";

const BUY_BUDGETS = [5000000, 7500000, 10000000, 12500000, 15000000, 20000000, 30000000, 40000000];
const RENT_BUDGETS = [25000, 30000, 35000, 40000, 50000, 60000];
const KM = [3, 5, 8, 10, 15];
const SCHOOL_KM = [1, 2, 3, 5];
const METRO_KM = [1, 2, 3];
const TOP_AMENITIES = ["Swimming pool", "Gym", "Clubhouse", "Kids' play area", "EV charging", "Jogging track", "Co-working lounge", "Supermarket", "Pet park", "Concierge"];

export function ListingsPage() {
  const filters = useStore((s) => s.filters);
  const results = useResults();
  const [params, setParams] = useSearchParams();
  const sheet = useStore((s) => s.filtersOpen);
  const mapOpen = useStore((s) => s.mapOpen);

  // A search from the home page (or a footer link) arrives as query params.
  useEffect(() => {
    if (![...params.keys()].length) return;
    const f: Filters = {};
    const city = params.get("city");
    if (city && getCity(city)) f.city = city as CityId;
    const deal = params.get("deal");
    if (deal === "buy" || deal === "rent") f.deal = deal;
    const bhk = params.get("bhk");
    if (bhk) f.bhk = bhk.split(",").map(Number).filter(Boolean);
    const max = Number(params.get("budget_max"));
    if (max) f.budget_max = max;
    const locality = params.get("locality");
    if (locality) f.localities = [locality];
    useStore.getState().setFilters(f);
    setParams({}, { replace: true });
  }, [params, setParams]);

  const mapCity = getCity(filters.city ?? results[0]?.city ?? "bengaluru")!;
  const onMap = results.filter((l) => l.city === mapCity.id);
  const elsewhere = results.length - onMap.length;
  const focus = useStore((s) => s.focus);

  return (
    <div className="wrap listings">
      <div className="listings-head" data-stage-thing="results" data-stage-label={`${results.length} homes`}>
        <div>
          <p className="crumb">Find a home</p>
          <h1>
            {results.length} {results.length === 1 ? "home" : "homes"}
          </h1>
          <p className="listings-summary">{summarise(filters)}</p>
        </div>
        <div className="listings-tools">
          <button type="button" className="btn ghost only-phone" onClick={() => useStore.getState().setFiltersOpen(true)}>
            <SlidersHorizontal size={16} /> Filters
          </button>
          <button type="button" className="btn ghost only-phone" onClick={() => useStore.getState().setMapOpen(!mapOpen)}>
            <MapIcon size={16} /> {mapOpen ? "List" : "Map"}
          </button>
          {Object.keys(filters).length ? (
            <button type="button" className="btn link" onClick={() => useStore.getState().setFilters({})}>
              Clear all
            </button>
          ) : null}
        </div>
      </div>
      <div className={`listings-grid${mapOpen ? " map-first" : ""}`}>
        <aside className={`filters${sheet ? " is-open" : ""}`} aria-label="Filters">
          <div className="filters-sheet-head only-phone">
            <b>Filters</b>
            <button type="button" aria-label="Close filters" onClick={() => useStore.getState().setFiltersOpen(false)}>
              <X size={20} />
            </button>
          </div>
          <FilterPanel />
          <button type="button" className="btn primary only-phone filters-done" onClick={() => useStore.getState().setFiltersOpen(false)}>
            Show {results.length} homes
          </button>
        </aside>
        <section className="results" aria-label="Results">
          {results.length ? (
            results.map((l, i) => <ListingCard key={l.id} l={l} office={filters.office} rank={i + 1} />)
          ) : (
            <div className="empty">
              <h3>No homes match all of that</h3>
              <p>Try a higher budget, another locality, or a longer commute.</p>
            </div>
          )}
        </section>
        <section className="mapcol" aria-label="Map">
          <div className="mapcard">
            <div className="mapcard-head">
              <b>{mapCity.name}</b>
              <span>
                {onMap.length} on the map{elsewhere ? ` · ${elsewhere} in other cities` : ""}
              </span>
            </div>
            <CityMap
              city={mapCity}
              listings={onMap}
              focus={focus}
              office={filters.office}
              officeKm={filters.max_km}
              onHover={(id) => useStore.getState().setFocus(id)}
              onPin={(id) => document.querySelector(`[data-stage-thing="listing:${id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
            />
            <MapLegend city={mapCity.id} />
          </div>
        </section>
      </div>
    </div>
  );
}

function MapLegend({ city }: { city: CityId }) {
  const c = getCity(city)!;
  return (
    <div className="maplegend">
      <span>
        <i className="lg-pin buy" /> To buy
      </span>
      <span>
        <i className="lg-pin rent" /> To rent
      </span>
      <span>
        <i className="lg-sq office" /> Office
      </span>
      <span>
        <i className="lg-sq school" /> School
      </span>
      {c.metro.map((m) => (
        <span key={m.name}>
          <i className="lg-line" style={{ background: m.colour }} /> {m.name}
        </span>
      ))}
    </div>
  );
}

function Chip({ part, on, onClick, children }: { part: string; on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" className={`chip${on ? " is-on" : ""}`} aria-pressed={on} data-stage-part={part} onClick={onClick}>
      {children}
    </button>
  );
}

function FilterPanel() {
  const f = useStore((s) => s.filters);
  const patch = useStore.getState().patchFilters;
  const toggle = <T,>(list: T[] | null | undefined, v: T) => ((list ?? []).includes(v) ? (list ?? []).filter((x) => x !== v) : [...(list ?? []), v]);
  const localities = useMemo(() => (f.city ? getCity(f.city)!.localities.map((l) => l.name) : CITIES.flatMap((c) => c.localities.map((l) => l.name))), [f.city]);
  const offices = officesOf(f.city ?? null);
  const budgets = f.deal === "rent" ? RENT_BUDGETS : BUY_BUDGETS;

  return (
    <div className="filters-body">
      <fieldset>
        <legend>City</legend>
        <div className="chips">
          <Chip part="city:any" on={!f.city} onClick={() => patch({ city: null, localities: null, office: null, max_km: null })}>
            All
          </Chip>
          {CITIES.map((c) => (
            <Chip key={c.id} part={`city:${c.id}`} on={f.city === c.id} onClick={() => patch({ city: c.id, localities: null, office: null, max_km: null })}>
              {c.name}
            </Chip>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Looking to</legend>
        <div className="seg">
          <Chip part="deal:any" on={!f.deal} onClick={() => patch({ deal: null, budget_min: null, budget_max: null })}>
            Any
          </Chip>
          <Chip part="deal:buy" on={f.deal === "buy"} onClick={() => patch({ deal: "buy", budget_min: null, budget_max: null })}>
            Buy
          </Chip>
          <Chip part="deal:rent" on={f.deal === "rent"} onClick={() => patch({ deal: "rent", budget_min: null, budget_max: null, possession: null })}>
            Rent
          </Chip>
        </div>
      </fieldset>
      <fieldset>
        <legend>BHK</legend>
        <div className="chips">
          {[1, 2, 3, 4].map((n) => (
            <Chip key={n} part={`bhk:${n}`} on={(f.bhk ?? []).includes(n)} onClick={() => patch({ bhk: toggle(f.bhk, n) })}>
              {n} BHK
            </Chip>
          ))}
        </div>
      </fieldset>
      <fieldset data-stage-part="budget">
        <legend>Budget{f.deal === "rent" ? " (rent a month)" : ""}</legend>
        <div className="row2">
          <label>
            <span>Min</span>
            <select value={f.budget_min ?? ""} onChange={(e) => patch({ budget_min: e.target.value ? Number(e.target.value) : null })}>
              <option value="">No min</option>
              {budgets.map((b) => (
                <option key={b} value={b}>
                  {inrShort(b)}
                </option>
              ))}
              {f.budget_min && !budgets.includes(f.budget_min) ? <option value={f.budget_min}>{inrShort(f.budget_min)}</option> : null}
            </select>
          </label>
          <label>
            <span>Max</span>
            <select value={f.budget_max ?? ""} onChange={(e) => patch({ budget_max: e.target.value ? Number(e.target.value) : null })}>
              <option value="">No max</option>
              {budgets.map((b) => (
                <option key={b} value={b}>
                  {inrShort(b)}
                </option>
              ))}
              {f.budget_max && !budgets.includes(f.budget_max) ? <option value={f.budget_max}>{inrShort(f.budget_max)}</option> : null}
            </select>
          </label>
        </div>
      </fieldset>
      <fieldset>
        <legend>Possession</legend>
        <div className="seg">
          <Chip part="possession:any" on={!f.possession} onClick={() => patch({ possession: null })}>
            Any
          </Chip>
          <Chip part="possession:ready" on={f.possession === "ready"} onClick={() => patch({ possession: "ready" })}>
            Ready to move
          </Chip>
          <Chip part="possession:under_construction" on={f.possession === "under_construction"} onClick={() => patch({ possession: "under_construction" })}>
            Under construction
          </Chip>
        </div>
      </fieldset>
      <fieldset data-stage-part="office">
        <legend>Commute to an office</legend>
        <select aria-label="Office" value={f.office ?? ""} onChange={(e) => patch({ office: e.target.value || null, max_km: e.target.value ? (f.max_km ?? 8) : null })}>
          <option value="">Any office</option>
          {offices.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
              {f.city ? "" : ` (${getCity(o.city)!.name})`}
            </option>
          ))}
        </select>
        <div className="chips">
          {KM.map((k) => (
            <Chip key={k} part={`max_km:${k}`} on={f.max_km === k} onClick={() => patch({ max_km: f.max_km === k ? null : k })}>
              ≤ {k} km
            </Chip>
          ))}
        </div>
      </fieldset>
      <fieldset data-stage-part="school">
        <legend>A school nearby</legend>
        <div className="chips">
          {SCHOOL_KM.map((k) => (
            <Chip key={k} part={`school_km:${k}`} on={f.school_km === k} onClick={() => patch({ school_km: f.school_km === k ? null : k })}>
              ≤ {k} km
            </Chip>
          ))}
        </div>
      </fieldset>
      <fieldset data-stage-part="metro">
        <legend>Metro station</legend>
        <div className="chips">
          {METRO_KM.map((k) => (
            <Chip key={k} part={`metro_km:${k}`} on={f.metro_km === k} onClick={() => patch({ metro_km: f.metro_km === k ? null : k })}>
              ≤ {k} km
            </Chip>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Locality</legend>
        <div className="checks">
          {localities.map((name) => (
            <label key={name} className={`check${(f.localities ?? []).includes(name) ? " is-on" : ""}`} data-stage-part={`locality:${name}`}>
              <input type="checkbox" checked={(f.localities ?? []).includes(name)} onChange={() => patch({ localities: toggle(f.localities, name) })} /> {name}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Amenities</legend>
        <div className="checks">
          {[...TOP_AMENITIES.filter((a) => ALL_AMENITIES.includes(a)), ...(f.amenities ?? []).filter((a) => !TOP_AMENITIES.includes(a))].map((name) => (
            <label key={name} className={`check${(f.amenities ?? []).includes(name) ? " is-on" : ""}`} data-stage-part={`amenity:${name}`}>
              <input type="checkbox" checked={(f.amenities ?? []).includes(name)} onChange={() => patch({ amenities: toggle(f.amenities, name) })} /> {name}
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
