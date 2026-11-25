/**
 * The home page: the campaigns from store.json (each art made of the
 * catalogue's own top products for its filter, linking to the listing with
 * that filter), the trust strip, the departments, and the home rails.
 */
import { BadgePercent, Banknote, RotateCcw, Truck } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ProductImage } from "../components/ProductCard";
import { Rail } from "../components/Rail";
import { type Filters, type Product, cleanFilters, routeFor, search, useCatalog } from "../data/catalog";
import { type Campaign, POLICY, STORE } from "../data/shop";
import { useStore } from "../state/store";

const asFilters = (f: Record<string, unknown>) => cleanFilters(f as Filters);

/** A link to the listing with this search (the store first, so the listing keeps it). */
function ShopLink({ filter, className, children, label }: { filter: Filters; className?: string; children: React.ReactNode; label?: string }) {
  return (
    <Link className={className} to={routeFor(filter)} aria-label={label} onClick={() => useStore.getState().setFilters(filter)}>
      {children}
    </Link>
  );
}

function picks(f: Filters, n: number, offset = 0): Product[] {
  return search(f)
    .filter((p) => p.sizes.some(([, s]) => s > 0))
    .slice(offset, offset + n);
}

function CampaignArt({ items, big = false }: { items: Product[]; big?: boolean }) {
  return (
    <div className={`camp-art${big ? " is-big" : ""}`} aria-hidden>
      {items.map((p, i) => (
        <div key={p.id} className={`camp-shot shot-${i}`}>
          <ProductImage id={p.id} alt="" w={big && i === 0 ? 1080 : 400} eager={big} />
        </div>
      ))}
    </div>
  );
}

function Hero({ c }: { c: Campaign }) {
  const f = asFilters(c.filter);
  const ready = useCatalog((s) => !!s.index);
  const items = useMemo(() => (ready ? picks(f, 3) : []), [ready, c.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <section className={`hero tone-${c.tone}`}>
      <div className="hero-copy">
        <p className="hero-kicker">{c.kicker}</p>
        <h1 className="hero-title">{c.title}</h1>
        <p className="hero-text">{c.copy}</p>
        <ShopLink filter={f} className="btn hero-cta">
          Shop the edit
        </ShopLink>
      </div>
      {ready ? <CampaignArt items={items} big /> : <div className="camp-art is-big sk" />}
    </section>
  );
}

function CampaignTile({ c }: { c: Campaign }) {
  const f = asFilters(c.filter);
  const ready = useCatalog((s) => !!s.index);
  const items = useMemo(() => (ready ? picks(f, 2) : []), [ready, c.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <ShopLink filter={f} className={`camp tone-${c.tone}`} label={`${c.title}: ${c.copy}`}>
      <div className="camp-copy">
        <p className="camp-kicker">{c.kicker}</p>
        <h2 className="camp-title">{c.title}</h2>
        <p className="camp-text">{c.copy}</p>
      </div>
      {ready ? <CampaignArt items={items} /> : <div className="camp-art sk" />}
    </ShopLink>
  );
}

export function Home() {
  const ix = useCatalog((s) => s.index);
  const [lead, ...rest] = STORE.campaigns;
  const depts = useMemo(() => {
    const used = new Set<number>();
    return (ix?.departments ?? []).map((d) => {
        const f = asFilters({ dept: d.id });
        // The tile's picture: the most popular product of the department's first section (clothes for Men, shoes for Footwear).
        const lead = d.sections[0]?.types ?? [];
        const p = ix ? picks({ ...f, types: lead }, 6).find((x) => !used.has(x.id)) : undefined;
        if (p) used.add(p.id);
        return { d, f, p, count: ix ? search(f).length : 0 };
    });
  }, [ix]);
  const rails = useMemo(() => STORE.home_rails.map((r) => ({ ...r, f: asFilters(r.filter), items: ix ? search(asFilters(r.filter)).slice(0, 16) : [] })), [ix]);

  return (
    <div className="home">
      <div className="wrap">
        <div className="campaigns">
          {lead ? <Hero c={lead} /> : null}
          <div className="camp-row">
            {rest.map((c) => (
              <CampaignTile key={c.id} c={c} />
            ))}
          </div>
        </div>
      </div>

      <div className="trust">
        <div className="wrap trust-row">
          <p>
            <Truck size={20} aria-hidden /> <span>
              <b>Free delivery</b> on orders over ₹{POLICY.delivery.free_over}
            </span>
          </p>
          <p>
            <RotateCcw size={20} aria-hidden /> <span>
              <b>{POLICY.returns.window_days}-day returns</b> on unused items, tags on
            </span>
          </p>
          <p>
            <Banknote size={20} aria-hidden /> <span>
              <b>Cash on delivery</b> on every order
            </span>
          </p>
          <p>
            <BadgePercent size={20} aria-hidden /> <span>
              <b>Real markdowns</b>, MRP shown on every product
            </span>
          </p>
        </div>
      </div>

      <div className="wrap">
        <section className="depts" aria-labelledby="depts-title">
          <h2 id="depts-title" className="section-title">
            Shop by department
          </h2>
          <div className="dept-grid">
            {depts.map(({ d, f, p, count }) => (
              <ShopLink key={d.id} filter={f} className="dept-tile">
                <div className="dept-img">{p ? <ProductImage id={p.id} alt="" /> : null}</div>
                <p className="dept-name">{d.label}</p>
                <p className="dept-count">{count ? `${count.toLocaleString("en-IN")} styles` : " "}</p>
              </ShopLink>
            ))}
            <Link to="/gifts" className="dept-tile is-gifts">
              <div className="dept-img dept-gift-art" aria-hidden>
                <span>Gift</span>
              </div>
              <p className="dept-name">Gift finder</p>
              <p className="dept-count">Who, the occasion, a budget</p>
            </Link>
          </div>
        </section>

        {rails.map((r) => (
          <Rail
            key={r.title}
            title={r.title}
            products={r.items}
            loading={!ix}
            more={
              <ShopLink filter={r.f} className="rail-more">
                See all
              </ShopLink>
            }
          />
        ))}
      </div>
    </div>
  );
}
