/**
 * In-room dining and drinks: one page for both outlets (`/dining`, `/bar`).
 * Section chips, the section's hours and delivery estimate, item cards that
 * open the item sheet, and the sticky "View order" bar.
 */
import { Clock3, ShoppingBag, Wine } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { PageHeader, Pill, Segments } from "../components/Shell";
import { BAR, DINING, type MenuItem, type Outlet, type Period } from "../data";
import { clock, money, price } from "../lib/format";
import { alcoholServed, openPeriod, orderTotals, periodOpen } from "../lib/rules";
import { openCart, openItem, setSection, stayClock, useStay } from "../state/store";
import "../styles/dining.css";

const DIET: Record<string, string> = { "gluten-free": "GF", vegetarian: "V", vegan: "VG" };
const DIET_NAME: Record<string, string> = { "gluten-free": "Gluten-free", vegetarian: "Vegetarian", vegan: "Vegan" };

export const dietPills = (diet: string[]) =>
  diet.map((d) => (
    <span key={d} className="dn-diet" title={DIET_NAME[d] ?? d}>
      {DIET[d] ?? d}
    </span>
  ));
export const allergenLine = (a: string[]) => (a.length ? `Contains: ${a.join(", ")}` : "");

/** Open now? `from`/`to` as HH:MM, `to` may be 24:00 or wrap past midnight. */
export const openAt = (from: string, to: string, now: string) => periodOpen({ from, to } as Period, now);

export function Dining({ outlet }: { outlet: Outlet }) {
  const nav = useNavigate();
  useStay((s) => s.scenario);
  const now = stayClock().now;
  const sectionState = useStay((s) => s.section[outlet]);
  const cart = useStay((s) => s.carts[outlet]);
  const totals = orderTotals(outlet, cart, 0);
  const count = cart.reduce((n, l) => n + l.qty, 0);

  const tabs = (
    <Segments
      items={[
        { id: "dining", label: "In-room dining", thing: "outlet-dining" },
        { id: "bar", label: "Drinks", thing: "outlet-bar" },
      ]}
      value={outlet}
      onChange={(id) => nav(id === "bar" ? "/bar" : "/dining")}
    />
  );

  return (
    <div className="page" data-stage-place={outlet}>
      <PageHeader title={outlet === "dining" ? "In-room dining" : "Drinks"} sub={outlet === "dining" ? "Delivered to your room, day and night" : "To your room or a pool cabana"} tabs={tabs} />
      <div className="dn-wrap">{outlet === "dining" ? <DiningMenu sectionId={sectionState || openPeriod(now)} now={now} /> : <BarMenu sectionId={sectionState || BAR.sections[0].id} now={now} />}</div>
      {count > 0 ? (
        <div className="dn-cartbar-slot">
          <button type="button" className="dn-cartbar" onClick={() => openCart(outlet)} data-stage-thing="cart-bar" data-stage-label="View order">
            <span className="dn-cartbar-count">
              <ShoppingBag size={16} />
              {count}
            </span>
            <span className="dn-cartbar-label">View order</span>
            <span className="dn-cartbar-sum">{money(totals.subtotal)}</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}

function DiningMenu({ sectionId, now }: { sectionId: string; now: string }) {
  const period = DINING.periods.find((p) => p.id === sectionId) ?? DINING.periods[0];
  const open = periodOpen(period, now);
  return (
    <>
      <div className="dn-chips" data-stage-group role="tablist" aria-label="Menu">
        {DINING.periods.map((p) => {
          const on = p.id === period.id;
          const live = periodOpen(p, now);
          return (
            <button key={p.id} type="button" role="tab" aria-selected={on} className={`dn-chip${on ? " is-on" : ""}`} onClick={() => setSection("dining", p.id)} data-stage-thing={`section-${p.id}`} data-stage-label={p.label}>
              {live ? <span className="dn-live" aria-hidden /> : null}
              {p.label}
            </button>
          );
        })}
      </div>

      <section className="dn-banner">
        <div className="dn-banner-text">
          <span className="dn-eyebrow">{open ? "Serving now" : "Not serving now"}</span>
          <h2>{period.label}</h2>
          <p className="dn-banner-meta">
            <Clock3 size={14} /> {period.hours}
          </p>
          <p className="dn-banner-meta">{open ? `Arrives in ${period.eta}` : `Orderable ${period.hours}. Delivery ${period.eta}.`}</p>
        </div>
        <Cloche />
      </section>

      {!open ? <p className="dn-note is-closed">This menu is served {period.hours}. You can browse it now and order once it opens.</p> : null}

      <div className="dn-items">
        {period.items.map((i) => (
          <ItemCard key={i.id} outlet="dining" item={i} closed={!open} closedNote={`Served ${period.hours}`} />
        ))}
      </div>

      <p className="dn-policy">{DINING.policy}</p>
    </>
  );
}

function BarMenu({ sectionId, now }: { sectionId: string; now: string }) {
  const section = BAR.sections.find((s) => s.id === sectionId) ?? BAR.sections[0];
  const served = alcoholServed(now);
  return (
    <>
      <section className="dn-banner is-bar">
        <div className="dn-banner-text">
          <span className="dn-eyebrow">Delivered in {BAR.eta}</span>
          <h2>The bars</h2>
          <ul className="dn-bars">
            {BAR.bars.map((b) => {
              const open = openAt(b.from, b.to, now);
              return (
                <li key={b.id}>
                  <span>
                    <b>{b.name}</b>
                    <small>{b.hours}</small>
                  </span>
                  <Pill tone={open ? "ok" : "plain"}>{open ? "Open" : "Closed"}</Pill>
                </li>
              );
            })}
          </ul>
        </div>
        <Coupe />
      </section>

      <p className="dn-note is-age">
        <Wine size={16} aria-hidden />
        <span>
          <b>21+</b> {BAR.age_rule}
        </span>
      </p>
      {!served ? <p className="dn-note is-closed">California law: no alcohol is sold from {clock("02:00")} to {clock("06:00")}. Zero proof drinks and bites are available.</p> : null}

      <div className="dn-chips" data-stage-group role="tablist" aria-label="Drinks menu">
        {BAR.sections.map((s) => {
          const on = s.id === section.id;
          return (
            <button key={s.id} type="button" role="tab" aria-selected={on} className={`dn-chip${on ? " is-on" : ""}`} onClick={() => setSection("bar", s.id)} data-stage-thing={`section-${s.id}`} data-stage-label={s.label}>
              {s.label}
            </button>
          );
        })}
      </div>

      <div className="dn-items">
        {section.items.map((i) => (
          <ItemCard key={i.id} outlet="bar" item={i} closed={!!i.alcohol && !served} closedNote={`Alcohol from ${clock("06:00")}`} />
        ))}
      </div>

      <p className="dn-policy">{BAR.policy}</p>
    </>
  );
}

function ItemCard({ outlet, item, closed, closedNote }: { outlet: Outlet; item: MenuItem; closed: boolean; closedNote: string }) {
  const inCart = useStay((s) => s.carts[outlet].filter((l) => l.item_id === item.id).reduce((n, l) => n + l.qty, 0));
  return (
    <button type="button" className={`dn-item${closed ? " is-closed" : ""}`} onClick={() => openItem(outlet, item.id)} data-stage-thing={`item-${item.id}`} data-stage-label={item.name}>
      <span className="dn-item-main">
        <span className="dn-item-name">
          {item.name}
          {inCart ? <span className="dn-incart">{inCart} in order</span> : null}
        </span>
        <span className="dn-item-desc">{item.desc}</span>
        <span className="dn-item-tags">
          {dietPills(item.diet)}
          {item.alcohol ? <span className="dn-diet is-age">21+</span> : null}
          {item.allergens.length ? <span className="dn-allergens">{allergenLine(item.allergens)}</span> : null}
        </span>
        {closed ? <span className="dn-served">{closedNote}</span> : null}
      </span>
      <span className="dn-item-price">
        {item.bottle !== undefined ? (
          <>
            <b>{price(item.price)}</b>
            <small>glass</small>
            <b>{price(item.bottle)}</b>
            <small>bottle</small>
          </>
        ) : (
          <b>{price(item.price)}</b>
        )}
        {item.options.length ? <small className="dn-options-hint">Options</small> : null}
      </span>
    </button>
  );
}

/** A silver cloche on a tray. */
function Cloche() {
  return (
    <svg className="dn-banner-art" viewBox="0 0 120 96" aria-hidden>
      <defs>
        <linearGradient id="dn-cloche" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#fffdf9" />
          <stop offset="0.55" stopColor="#e8dcc6" />
          <stop offset="1" stopColor="#c9a467" />
        </linearGradient>
      </defs>
      <circle cx="78" cy="30" r="22" fill="#f3e8d4" opacity="0.8" />
      <path d="M20 70a40 40 0 0 1 80 0Z" fill="url(#dn-cloche)" stroke="#a67c3d" strokeWidth="1.4" />
      <path d="M34 56a28 28 0 0 1 18-18" stroke="#fffdf9" strokeWidth="3" strokeLinecap="round" fill="none" opacity="0.9" />
      <circle cx="60" cy="27" r="4.5" fill="#a67c3d" />
      <rect x="10" y="70" width="100" height="6" rx="3" fill="#13212b" />
      <path d="M22 82c6 0 6-3 12-3s6 3 12 3 6-3 12-3 6 3 12 3 6-3 12-3 6 3 12 3" stroke="#2c5a5e" strokeWidth="1.6" fill="none" strokeLinecap="round" opacity="0.5" />
    </svg>
  );
}

/** A coupe with a blood orange wheel. */
function Coupe() {
  return (
    <svg className="dn-banner-art" viewBox="0 0 120 120" aria-hidden>
      <circle cx="70" cy="40" r="26" fill="#f8e4da" opacity="0.7" />
      <path d="M26 34h60c0 18-13 30-30 30S26 52 26 34Z" fill="#c0603a" opacity="0.85" />
      <path d="M26 34h60c0 18-13 30-30 30S26 52 26 34Z" fill="none" stroke="#13212b" strokeWidth="1.6" />
      <path d="M33 42c6 6 14 9 23 9" stroke="#fffdf9" strokeWidth="2.4" strokeLinecap="round" fill="none" opacity="0.7" />
      <path d="M56 64v36M40 102h32" stroke="#13212b" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="86" cy="32" r="13" fill="#f3e8d4" stroke="#a67c3d" strokeWidth="1.4" />
      <circle cx="86" cy="32" r="9" fill="#c0603a" opacity="0.75" />
      <path d="M86 23v18M77 32h18M80 26l12 12M92 26 80 38" stroke="#f3e8d4" strokeWidth="1" />
      <circle cx="44" cy="22" r="2" fill="#a67c3d" opacity="0.6" />
      <circle cx="52" cy="14" r="1.4" fill="#a67c3d" opacity="0.5" />
    </svg>
  );
}
