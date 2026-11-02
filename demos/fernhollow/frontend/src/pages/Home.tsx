import { Link } from "react-router-dom";
import { ROOMS, categoriesIn, getCategory, getProduct, productsInCategory, roomCover, sortProducts, products } from "../data/catalog";
import { formatDate, journal, site } from "../data/content";
import { Photo, ProductPrice, SectionHead } from "../components/bits";
import { Rail } from "../components/ProductCard";
import { useTitle } from "./usePage";

/** The three pieces in the opening triptych, by id. */
/** The opening four: a sofa, a bed, a dining table and a desk, by id. */
const HERO_IDS = [
  "hand-stitched-stone-linen-sofa",
  "solid-oak-platform-bed-with-linen-headboard",
  "weathered-oak-dining-table",
  "modern-home-office-desk-with-chestnut-brown-finish",
];
const FEATURED_CATEGORIES = ["sofas", "dining-tables", "beds-bed-frames", "floor-lamps", "rugs"];

export function Home() {
  useTitle(null);
  const feature = productsInCategory("sofas").find((p) => p.images.length > 1) ?? productsInCategory("sofas")[0];
  const hero = HERO_IDS.map((id) => getProduct(id)).filter((p) => !!p);
  const onSale = sortProducts(
    products.filter((p) => p.onSale),
    "sale",
  )
    .filter((p, i, arr) => arr.findIndex((x) => x.categorySlug === p.categorySlug) === i)
    .slice(0, 12);
  const articles = journal.filter((a) => !a.sample).slice(0, 3);
  const teaser = articles.length ? articles : journal.slice(0, 3);
  return (
    <>
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <h1 className="display">{site.hero.headline}</h1>
            <p className="lede">{site.hero.subline}</p>
            <div className="hero-ctas">
              <Link to={site.hero.cta.href} className="btn btn-primary">
                {site.hero.cta.label}
              </Link>
              <Link to="/sale" className="btn btn-ghost">
                Shop the sale
              </Link>
            </div>
          </div>
          <div className="hero-photos">
            {hero.map((p, i) => (
              <Link key={p.id} to={`/product/${p.id}`} className={`hero-photo hero-photo-${i + 1}`}>
                <Photo file={p.images[0]} alt={p.title} eager size={1000} sizes="(min-width: 900px) 16vw, 45vw" />
                <span className="hero-cap">
                  <span>{p.title}</span>
                  <ProductPrice p={p} />
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <SectionHead title="Shop by room" action={<Link className="link" to="/shop">All pieces</Link>} />
          <ul className="rooms-row">
            {ROOMS.map((r) => {
              const cover = roomCover(r.id);
              return (
                <li key={r.id}>
                  <Link to={`/room/${r.id}`} className="room-tile">
                    <span className="room-photo">
                      <Photo file={cover.images[0]} alt="" sizes="(min-width: 900px) 14vw, 40vw" />
                    </span>
                    <span className="room-name">{r.name}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      <section className="section room-feature">
        <div className="wrap room-feature-grid">
          {feature ? (
            <Link to={`/product/${feature.id}`} className="room-feature-photo" tabIndex={-1} aria-hidden>
              <Photo file={feature.images[1] ?? feature.images[0]} alt="" size={1000} sizes="(min-width: 900px) 55vw, 100vw" />
            </Link>
          ) : null}
          <div className="room-feature-copy">
            <h2 className="h1">The living room</h2>
            <p className="lede">{site.rooms.living}</p>
            <ul className="room-feature-cats">
              {categoriesIn("living")
                .slice(0, 6)
                .map((c) => (
                  <li key={c.slug}>
                    <Link to={`/category/${c.slug}`} className="chip">
                      {c.name}
                    </Link>
                  </li>
                ))}
            </ul>
            <div className="hero-ctas">
              <Link to="/room/living" className="btn btn-primary">
                Shop the living room
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <SectionHead title="On sale now" action={<Link className="link" to="/sale">See every saving</Link>}>
            Real reductions on pieces across the house.
          </SectionHead>
        </div>
        <div className="wrap wrap-rail">
          <Rail products={onSale} />
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <SectionHead title="Where to start" />
          <ul className="cat-grid">
            {FEATURED_CATEGORIES.map((slug, i) => {
              const c = getCategory(slug);
              if (!c) return null;
              const cover = sortProducts(productsInCategory(slug), "featured")[0];
              return (
                <li key={slug} className={i === 0 ? "cat-feature" : undefined}>
                  <Link to={`/category/${slug}`} className="cat-tile">
                    <span className="cat-photo">
                      <Photo file={cover.images[0]} alt="" size={i === 0 ? 1000 : 400} sizes={i === 0 ? "(min-width: 900px) 40vw, 100vw" : "(min-width: 900px) 20vw, 50vw"} />
                    </span>
                    <span className="cat-text">
                      <span className="h3">{c.name}</span>
                      <span className="small">{site.categories[slug]}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      {teaser.length ? (
        <section className="section">
          <div className="wrap">
            <SectionHead title="From the journal" action={<Link className="link" to="/journal">All articles</Link>} />
            <ul className="journal-grid">
              {teaser.map((a) => {
                const hero = getProduct(a.hero);
                return (
                  <li key={a.slug}>
                    <Link to={`/journal/${a.slug}`} className="journal-card">
                      {hero ? (
                        <span className="journal-photo">
                          <Photo file={hero.images[hero.images.length > 1 ? 1 : 0]} alt="" sizes="(min-width: 900px) 30vw, 90vw" />
                        </span>
                      ) : null}
                      <span className="journal-meta small">
                        {formatDate(a.date)}
                        {a.readMinutes ? `, ${a.readMinutes} min read` : ""}
                      </span>
                      <span className="h3">{a.title}</span>
                      <span className="small journal-dek">{a.dek}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>
      ) : null}

      <section className="promises" aria-label="Our promises">
        <div className="wrap promises-grid">
          {site.promises.map((p) => (
            <div key={p.title} className="promise">
              <h3 className="promise-title">{p.title}</h3>
              <p className="small">{p.text}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
