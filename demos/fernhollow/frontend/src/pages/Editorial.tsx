import { marked } from "marked";
import { CheckCircle2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import { getProduct, getVariant, money, productsByIds, roomName } from "../data/catalog";
import { type Doc, INFO_PAGES, formatDate, getArticle, getPage, journal, segments } from "../data/content";
import { Crumbs, Photo, ProductPrice } from "../components/bits";
import { Rail } from "../components/ProductCard";
import type { Order } from "./Checkout";
import { useTitle } from "./usePage";

const md = (text: string) => marked.parse(text, { async: false }) as string;

function InlineProduct({ id }: { id: string }) {
  const p = getProduct(id);
  if (!p) return null;
  return (
    <aside className="inline-product" data-spot={`product:${p.id}`}>
      <Link to={`/product/${p.id}`} className="inline-photo" tabIndex={-1} aria-hidden>
        <Photo file={p.images[0]} alt="" sizes="(min-width: 900px) 220px, 40vw" />
      </Link>
      <div className="inline-body">
        <p className="small">{p.category}</p>
        <Link to={`/product/${p.id}`} className="h3 inline-title">
          {p.title}
        </Link>
        <ProductPrice p={p} />
        <p className="small inline-intro">{p.intro}</p>
        <Link to={`/product/${p.id}`} className="link small">
          View the piece
        </Link>
      </div>
    </aside>
  );
}

function Body({ doc }: { doc: Doc }) {
  const parts = useMemo(() => segments(doc.body), [doc.body]);
  return (
    <div className="prose">
      {parts.map((s, i) =>
        s.kind === "md" ? <div key={i} dangerouslySetInnerHTML={{ __html: md(s.text) }} /> : <InlineProduct key={i} id={s.id} />,
      )}
    </div>
  );
}

export function JournalIndex() {
  useTitle("Journal");
  const [lead, ...rest] = journal;
  return (
    <div className="wrap page-pad journal-index">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Journal" }]} />
      <header className="listing-head">
        <h1 className="h1">Journal</h1>
        <p className="lede">Practical advice for rooms that are lived in: light, materials, tables, shelves and the small decisions that add up.</p>
      </header>
      {!lead ? (
        <p className="small">The first articles are on their way.</p>
      ) : (
        <>
          <ArticleCard a={lead} lead />
          <ul className="journal-grid journal-grid-index">
            {rest.map((a) => (
              <li key={a.slug}>
                <ArticleCard a={a} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function ArticleCard({ a, lead = false }: { a: Doc; lead?: boolean }) {
  const hero = getProduct(a.hero);
  return (
    <Link to={`/journal/${a.slug}`} className={`journal-card${lead ? " journal-lead" : ""}`}>
      {hero ? (
        <span className="journal-photo">
          <Photo file={hero.images[0]} alt="" size={lead ? 1000 : 400} eager={lead} sizes={lead ? "(min-width: 900px) 55vw, 100vw" : "(min-width: 900px) 30vw, 90vw"} />
        </span>
      ) : null}
      <span className="journal-text">
        <span className="journal-meta small">
          {a.room ? `${roomName(a.room)}, ` : ""}
          {formatDate(a.date)}
          {a.readMinutes ? `, ${a.readMinutes} min read` : ""}
        </span>
        <span className={lead ? "h1" : "h3"}>{a.title}</span>
        <span className={lead ? "lede" : "small journal-dek"}>{a.dek}</span>
      </span>
    </Link>
  );
}

export function ArticlePage() {
  const { slug } = useParams();
  const a = getArticle(slug);
  useTitle(a?.title ?? "Journal");
  if (!a) return <Navigate to="/journal" replace />;
  const hero = getProduct(a.hero);
  const featured = productsByIds(a.products);
  const next = journal.filter((x) => x.slug !== a.slug).slice(0, 3);
  return (
    <article className="article">
      <div className="wrap">
        <Crumbs items={[{ label: "Home", to: "/" }, { label: "Journal", to: "/journal" }, { label: a.title }]} />
        <header className="article-head">
          <p className="small">
            {a.room ? (
              <>
                <Link className="link" to={`/room/${a.room}`}>
                  {roomName(a.room)}
                </Link>
                {", "}
              </>
            ) : null}
            {formatDate(a.date)}
            {a.readMinutes ? `, ${a.readMinutes} min read` : ""}
          </p>
          <h1 className="display article-title">{a.title}</h1>
          {a.dek ? <p className="lede article-dek">{a.dek}</p> : null}
        </header>
        {hero ? (
          <figure className="article-hero">
            <div className="article-hero-photos">
              {articlePhotos(hero.id, a.products).map((ph, i) => (
                <Photo key={ph.file} file={ph.file} alt={ph.title} size={1000} eager={i === 0} sizes="(min-width: 900px) 45vw, 50vw" />
              ))}
            </div>
            <figcaption className="small">
              <Link to={`/product/${hero.id}`} className="link">
                {hero.title}
              </Link>
              , {money(getVariant(hero).price)}
            </figcaption>
          </figure>
        ) : null}
        <Body doc={a} />
      </div>
      {featured.length ? (
        <section className="section">
          <div className="wrap">
            <h2 className="h2 rail-title">In this article</h2>
          </div>
          <div className="wrap wrap-rail">
            <Rail products={featured} />
          </div>
        </section>
      ) : null}
      {next.length ? (
        <section className="section">
          <div className="wrap">
            <h2 className="h2 rail-title">Keep reading</h2>
            <ul className="journal-grid">
              {next.map((x) => (
                <li key={x.slug}>
                  <ArticleCard a={x} />
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </article>
  );
}

/** Two portrait photos to open an article: the hero's own, then its second view or the next featured piece. */
function articlePhotos(heroId: string, ids: string[]) {
  const hero = getProduct(heroId)!;
  const out = [{ file: hero.images[0], title: hero.title }];
  const other = hero.images[1] ? { file: hero.images[1], title: hero.title } : (() => {
    const p = productsByIds(ids).find((x) => x.id !== heroId);
    return p ? { file: p.images[0], title: p.title } : null;
  })();
  if (other) out.push(other);
  return out;
}

export function InfoPage({ slug: fixed }: { slug?: string }) {
  const params = useParams();
  const slug = fixed ?? params.topic;
  const page = getPage(slug);
  useTitle(page?.title ?? "Help");
  if (!page) return <Navigate to="/" replace />;
  return (
    <div className="wrap page-pad info">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: page.title }]} />
      <div className="info-grid">
        <nav className="info-nav" aria-label="Help pages">
          <ul>
            {INFO_PAGES.map((p) => (
              <li key={p.slug}>
                <Link to={p.path} aria-current={p.slug === page.slug ? "page" : undefined}>
                  {p.label}
                </Link>
              </li>
            ))}
            <li>
              <Link to="/contact">Contact</Link>
            </li>
          </ul>
        </nav>
        <div>
          <header className="info-head">
            <h1 className="h1">{page.title}</h1>
            {page.dek ? <p className="lede">{page.dek}</p> : null}
          </header>
          {page.slug === "returns" || page.slug === "faq" ? <ReturnsDeskLink /> : null}
          <div className="prose" dangerouslySetInnerHTML={{ __html: md(page.body) }} />
        </div>
      </div>
    </div>
  );
}

function ReturnsDeskLink() {
  return (
    <Link to="/returns" className="returns-link">
      <span>
        <span className="returns-link-title">Start a return online</span>
        <span className="small">Find your order and send it back in six short steps, by hand or with Mira.</span>
      </span>
      <span className="btn btn-primary btn-sm">Returns desk</span>
    </Link>
  );
}

export function ContactPage() {
  useTitle("Contact");
  const [sent, setSent] = useState(false);
  return (
    <div className="wrap page-pad info">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Contact" }]} />
      <div className="info-grid">
        <nav className="info-nav" aria-label="Help pages">
          <ul>
            {INFO_PAGES.map((p) => (
              <li key={p.slug}>
                <Link to={p.path}>{p.label}</Link>
              </li>
            ))}
            <li>
              <Link to="/contact" aria-current="page">
                Contact
              </Link>
            </li>
          </ul>
        </nav>
        <div className="contact">
          <header className="info-head">
            <h1 className="h1">Write to the studio</h1>
            <p className="lede">Questions about a piece, an order or a room you are planning. Mira can answer most of them out loud, too.</p>
          </header>
          {sent ? (
            <div className="thanks" role="status">
              <CheckCircle2 size={22} aria-hidden />
              <div>
                <p className="h3">Thank you, your note is with us.</p>
                <p className="small">This is a demo store, so no one will reply, but this is where a reply would come from.</p>
              </div>
            </div>
          ) : (
            <form
              className="contact-form"
              onSubmit={(e) => {
                e.preventDefault();
                setSent(true);
              }}
            >
              <div className="co-grid">
                <div className="field">
                  <label htmlFor="ct-name">Name</label>
                  <input id="ct-name" className="input" required autoComplete="name" />
                </div>
                <div className="field">
                  <label htmlFor="ct-email">Email</label>
                  <input id="ct-email" className="input" type="email" required autoComplete="email" />
                </div>
              </div>
              <div className="field">
                <label htmlFor="ct-topic">About</label>
                <select id="ct-topic" className="select">
                  <option>A piece in the store</option>
                  <option>An order</option>
                  <option>Delivery or assembly</option>
                  <option>A return</option>
                  <option>Something else</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="ct-msg">Message</label>
                <textarea id="ct-msg" className="textarea" required rows={6} />
              </div>
              <button type="submit" className="btn btn-primary">
                Send message
              </button>
            </form>
          )}
          <dl className="contact-facts">
            <div>
              <dt>Email</dt>
              <dd>hello@fernhollow.example</dd>
            </div>
            <div>
              <dt>Studio</dt>
              <dd>A fictional workshop. Fernhollow has no real address.</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}

export function ConfirmationPage() {
  useTitle("Order placed");
  const location = useLocation();
  const order = (location.state as Order | null) ?? readOrder();
  if (!order) return <Navigate to="/" replace />;
  const total = order.subtotal + order.delivery;
  return (
    <div className="wrap page-pad confirmation">
      <div className="confirm-hero">
        <CheckCircle2 size={34} strokeWidth={1.4} aria-hidden />
        <p className="small">Order {order.number}</p>
        <h1 className="h1">Thank you, {order.address.firstName}. Your order is placed.</h1>
        <p className="lede">
          In a real store a confirmation would now go to {order.address.email}. This is a demo, so nothing was charged and nothing will be
          delivered.
        </p>
      </div>
      <div className="confirm-grid">
        <section className="summary-card">
          <h2 className="h3">What you ordered</h2>
          <ul className="summary-lines">
            {order.lines.map((l) => {
              const p = getProduct(l.product_id);
              if (!p) return null;
              const v = getVariant(p, l.variant_id);
              return (
                <li key={`${l.product_id}:${l.variant_id}`}>
                  <span className="summary-thumb">
                    <Photo file={p.images[0]} alt="" sizes="56px" />
                    <span className="summary-qty">{l.qty}</span>
                  </span>
                  <span className="summary-title">
                    {p.title}
                    <span className="small">{Object.values(v.options).join(", ")}</span>
                  </span>
                  <span className="price">{money(v.price * l.qty)}</span>
                </li>
              );
            })}
          </ul>
          <dl className="totals">
            <div>
              <dt>Subtotal</dt>
              <dd className="price">{money(order.subtotal)}</dd>
            </div>
            {order.saved ? (
              <div className="totals-saved">
                <dt>You saved</dt>
                <dd className="price">{money(order.saved)}</dd>
              </div>
            ) : null}
            <div>
              <dt>Delivery</dt>
              <dd className="price">{order.delivery ? money(order.delivery) : "Free"}</dd>
            </div>
            <div className="totals-grand">
              <dt>Total</dt>
              <dd className="price">{money(total)}</dd>
            </div>
          </dl>
        </section>
        <section className="summary-card">
          <h2 className="h3">Delivering to</h2>
          <address className="review-address">
            {order.address.firstName} {order.address.lastName}
            <br />
            {order.address.address1}
            <br />
            {order.address.city} {order.address.postal}
            <br />
            {order.address.country}
          </address>
          <p className="small">
            We get in touch once an order is on its way; see{" "}
            <Link className="link" to="/policy/delivery">
              how delivery works
            </Link>
            .
          </p>
          <Link to="/" className="btn btn-ghost">
            Keep shopping
          </Link>
          <p className="small">
            Need to send something back later?{" "}
            <Link className="link" to="/returns">
              Start a return
            </Link>
            .
          </p>
        </section>
      </div>
    </div>
  );
}

function readOrder(): Order | null {
  try {
    return JSON.parse(sessionStorage.getItem("fh-order") ?? "null");
  } catch {
    return null;
  }
}

export function NotFound() {
  useTitle("Page not found");
  return (
    <div className="wrap page-pad empty-page">
      <h1 className="h1">This page has moved or never existed.</h1>
      <p className="lede">Try a room, or search for the piece you had in mind.</p>
      <div className="hero-ctas">
        <Link className="btn btn-primary" to="/">
          Go to the home page
        </Link>
        <Link className="btn btn-ghost" to="/shop">
          Browse all pieces
        </Link>
      </div>
    </div>
  );
}
