import { Link } from "react-router-dom";
import { ROOMS, getCategory, getProduct, productsInCategory, roomCover, sortProducts, products } from "../data/catalog";
import { formatDate, journal, site } from "../data/content";
import { Photo, ProductPrice, SectionHead } from "../components/bits";
import { Rail } from "../components/ProductCard";
import { useTitle } from "./usePage";

/** The three pieces in the opening triptych, by id. */
const HERO_IDS = ["oak-and-rattan-floor-lamp", "weathered-oak-dining-table", "solid-oak-platform-bed-with-linen-headboard"];
const FEATURED_CATEGORIES = ["sofas", "dining-tables", "beds-bed-frames", "floor-lamps", "rugs"];

export function Home() {
  useTitle(null);
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
              <Link to="/board" className="btn btn-ghost">
                Plan a room with Mira
              </Link>
            </div>
          </div>
          <div className="hero-photos">
            {hero.map((p, i) => (
              <Link key={p.id} to={`/product/${p.id}`} className={`hero-photo hero-photo-${i + 1}`}>
                <Photo file={p.images[0]} alt={p.title} eager size={i === 1 ? 1000 : 400} sizes="(min-width: 900px) 22vw, 33vw" />
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

      <section className="section mira-band">
        <div className="wrap mira-band-grid">
          <div>
            <p className="mira-band-name">
              <span className="mira-dot" aria-hidden /> Mira, design adviser
            </p>
            <h2 className="h1">Tell her the room and the budget. She lays it out while you talk.</h2>
          </div>
          <div className="mira-band-copy">
            <p className="lede">
              Mira knows every piece in the store. Ask for a calm bedroom under two thousand, a desk that suits a small corner, or what goes
              with the sofa you are looking at. Everything she shows you, you can change by hand.
            </p>
            <div className="hero-ctas">
              <Link to="/board" className="btn btn-ghost">
                Plan a room by hand
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
