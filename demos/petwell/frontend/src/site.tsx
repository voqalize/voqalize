/**
 * The Petwell website — a vet hospital chain's site, with Tushar at its front
 * desk.
 *
 * Pages: home, treatments & services, locations, the Health Hub (and its
 * articles), and Petwell@Home. The booking form is a panel over whichever page
 * is open (`booking.tsx`), and the emergency sheet over that. Navigation is
 * plain state (see store.tsx), so the live call is never interrupted.
 *
 * Copy is English or Hindi (`i18n.ts`), following the language Tushar is
 * speaking; the Health Hub articles are in English in both.
 */

import { useState, type ReactNode } from 'react';
import {
  Activity,
  ArrowRight,
  Bird,
  Bone,
  Brain,
  Calendar,
  Clock,
  Droplet,
  Eye,
  HeartPulse,
  Home,
  Languages,
  Lightbulb,
  MapPin,
  Microscope,
  PawPrint,
  Phone,
  Quote,
  Ribbon,
  Scissors,
  ShieldCheck,
  Siren,
  Smile,
  Sparkles,
  Stethoscope,
  Syringe,
  TriangleAlert,
} from 'lucide-react';
import { BookingDrawer, EmergencyPanel } from './booking';
import { BRANCHES, branchesIn, CITIES, formatDate, getService, HELPLINES, OPENING_SOON, SERVICES } from './catalog';
import { ARTICLES, getArticle, type Article, type HubTag } from './hub';
import { cityName, FONT, locale, PICKABLE, serviceBlurb, serviceName, strings } from './i18n';
import { useSite } from './store';
import { BOOKING_CSS } from './styles';
import hero from './assets/hero.webp';
import vetDog from './assets/vet-dog.webp';
import vetCat from './assets/vet-cat.webp';
import vaccination from './assets/vaccination.webp';
import grooming from './assets/grooming.webp';
import atHome from './assets/at-home.webp';
import owner from './assets/owner.webp';

const SERVICE_ICON: Record<string, ReactNode> = {
  'general-consult': <Stethoscope size={22} />,
  vaccination: <Syringe size={22} />,
  grooming: <Scissors size={22} />,
  dental: <Smile size={22} />,
  skin: <Sparkles size={22} />,
  diagnostics: <Microscope size={22} />,
  cardiology: <HeartPulse size={22} />,
  orthopaedics: <Bone size={22} />,
  oncology: <Ribbon size={22} />,
  neurology: <Brain size={22} />,
  'eye-care': <Eye size={22} />,
  'exotic-pets': <Bird size={22} />,
  physiotherapy: <Activity size={22} />,
  'home-vaccination': <Syringe size={22} />,
  'home-consult': <Stethoscope size={22} />,
  'home-blood-sample': <Droplet size={22} />,
  'home-physio': <Activity size={22} />,
};

export function Site({ presence, face }: { presence: ReactNode; face: ReactNode }) {
  const s = useSite();
  return (
    <div className="pw-app" data-lang={s.lang} style={{ fontFamily: FONT[s.lang] }}>
      <style>{BOOKING_CSS}</style>
      <style>{SITE_CSS}</style>
      <Ticker />
      <Header presence={presence} />
      <main className="pw-page" key={`${s.page}-${s.articleId ?? ''}`}>
        {s.page === 'home' && <HomePage />}
        {s.page === 'services' && <ServicesPage />}
        {s.page === 'locations' && <LocationsPage />}
        {s.page === 'health_hub' && <HubPage />}
        {s.page === 'article' && <ArticlePage />}
        {s.page === 'at_home' && <AtHomePage />}
      </main>
      <Footer />
      <div className="pw-dock">{face}</div>
      <BookingDrawer />
      <EmergencyPanel />
    </div>
  );
}

// ── Chrome ────────────────────────────────────────────────────────────────────

function Ticker() {
  const { lang } = useSite();
  const t = strings(lang);
  return (
    <div className="pw-ticker" aria-hidden>
      <span>{t.ticker} ·&nbsp;</span>
      <span>{t.ticker} ·&nbsp;</span>
    </div>
  );
}

function Header({ presence }: { presence: ReactNode }) {
  const s = useSite();
  const t = strings(s.lang);
  const nav: [Parameters<typeof s.openPage>[0], string][] = [
    ['at_home', t.navAtHome],
    ['services', t.navServices],
    ['locations', t.navLocations],
    ['health_hub', t.navHub],
  ];
  const current = s.page === 'article' ? 'health_hub' : s.page;
  return (
    <header className="pw-header">
      <div className="pw-header-row">
        <button className="pw-logo" onClick={() => s.openPage('home')} title={t.navHome}>
          <span className="pw-logo-mark">
            <PawPrint size={18} />
          </span>
          <span>
            <span className="pw-logo-name">Petwell</span>
            <span className="pw-logo-sub">{t.hospitals}</span>
          </span>
        </button>
        <nav className="pw-nav">
          {nav.map(([page, label]) => (
            <button
              key={page}
              data-page={page}
              className={current === page ? 'is-current' : ''}
              onClick={() => s.openPage(page)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="pw-header-actions">
          <LanguagePicker />
          <button className="pw-sos" onClick={s.openEmergency} title={t.emergency}>
            <Siren size={15} /> <span>{t.emergency}</span>
          </button>
          <button className="pw-cta" onClick={() => s.openBooking()}>
            {t.book}
          </button>
          {presence}
        </div>
      </div>
    </header>
  );
}

function LanguagePicker() {
  const s = useSite();
  return (
    <div className="pw-lang" role="group" aria-label="Language">
      <Languages size={15} />
      {PICKABLE.map((p) => (
        <button
          key={p.lang}
          data-lang={p.lang}
          className={s.lang === p.lang ? 'is-on' : ''}
          onClick={() => s.lang !== p.lang && s.pickLanguage(p.lang)}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}

function SectionHead({ title, lead, action }: { title: string; lead?: string; action?: ReactNode }) {
  return (
    <div className="pw-section-head">
      <div>
        <h2>{title}</h2>
        {lead && <p>{lead}</p>}
      </div>
      {action}
    </div>
  );
}

// ── Home ──────────────────────────────────────────────────────────────────────

function HomePage() {
  const s = useSite();
  const t = strings(s.lang);
  return (
    <>
      <section className="pw-hero">
        <div className="pw-hero-text">
          <span className="pw-kicker">{t.heroKicker}</span>
          <h1>{t.heroTitle}</h1>
          <p className="pw-hero-lead">{t.heroLead}</p>
          <div className="pw-hero-actions">
            <button className="pw-cta pw-cta-lg" onClick={() => s.openBooking()}>
              <Calendar size={18} /> {t.book}
            </button>
            <button className="pw-ghost pw-cta-lg" onClick={s.openEmergency}>
              <Siren size={18} /> {t.emergency}
            </button>
          </div>
          <p className="pw-hero-voice">
            <Languages size={16} /> {t.heroVoice}
          </p>
          <dl className="pw-stats">
            <div>
              <dt>50+</dt>
              <dd>{t.statVets}</dd>
            </div>
            <div>
              <dt>15</dt>
              <dd>{t.statBranches}</dd>
            </div>
            <div>
              <dt>9</dt>
              <dd>{t.statCities}</dd>
            </div>
            <div>
              <dt>24x7</dt>
              <dd>{t.statOpen}</dd>
            </div>
          </dl>
        </div>
        <div className="pw-hero-art">
          <img src={hero} alt="" />
          <div className="pw-hero-badge">
            <ShieldCheck size={18} />
            <span>
              <strong>{t.emergency}</strong>
              <small>{HELPLINES[0].phone}</small>
            </span>
          </div>
        </div>
      </section>

      <CareSection />
      <NearYou />

      <section className="pw-band">
        <img src={atHome} alt="" />
        <div>
          <span className="pw-kicker">{t.navAtHome}</span>
          <h2>{t.homeTitle}</h2>
          <p>{t.homeLead}</p>
          <button className="pw-cta" onClick={() => bookHome(s)}>
            <Home size={17} /> {t.homeBook}
          </button>
        </div>
      </section>

      <section className="pw-section pw-testimonial">
        <img src={owner} alt="" />
        <figure>
          <Quote size={28} />
          <blockquote>{t.quote}</blockquote>
          <figcaption>{t.quoteBy}</figcaption>
        </figure>
      </section>

      <section className="pw-section">
        <SectionHead
          title={t.hubTitle}
          lead={t.hubLead}
          action={
            <button className="pw-link" onClick={() => s.openPage('health_hub')}>
              {t.viewAll} <ArrowRight size={15} />
            </button>
          }
        />
        <div className="pw-articles">
          {ARTICLES.slice(0, 3).map((a) => (
            <ArticleCard key={a.id} a={a} />
          ))}
        </div>
      </section>
    </>
  );
}

function bookHome(s: ReturnType<typeof useSite>) {
  s.openBooking();
  s.pickVisitType('home');
}

function CareSection() {
  const s = useSite();
  const t = strings(s.lang);
  const [tab, setTab] = useState<'primary' | 'specialty'>('primary');
  const group = tab === 'primary' ? 'Everyday care' : 'Specialty care';
  const photos = tab === 'primary' ? [vaccination, vetDog, grooming] : [vetCat, vetDog, vaccination];
  return (
    <section className="pw-section">
      <SectionHead
        title={t.careTitle}
        action={
          <div className="pw-tabs">
            <button className={tab === 'primary' ? 'is-on' : ''} onClick={() => setTab('primary')}>
              {t.primary}
            </button>
            <button className={tab === 'specialty' ? 'is-on' : ''} onClick={() => setTab('specialty')}>
              {t.specialty}
            </button>
          </div>
        }
      />
      <div className="pw-care">
        <div className="pw-care-photos">
          {photos.map((p, i) => (
            <img key={i} src={p} alt="" />
          ))}
        </div>
        <div className="pw-care-list">
          {SERVICES.filter((x) => x.group === group).map((x) => (
            <ServiceCard key={x.id} id={x.id} />
          ))}
          <button className="pw-link" onClick={() => s.openPage('services')}>
            {t.viewAll} <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </section>
  );
}

function ServiceCard({ id }: { id: string }) {
  const s = useSite();
  const t = strings(s.lang);
  const service = getService(id)!;
  return (
    <div className="pw-svc" data-service-card={id}>
      <span className="pw-svc-icon">{SERVICE_ICON[id]}</span>
      <span className="pw-svc-text">
        <strong>{serviceName(service, s.lang)}</strong>
        <small>{serviceBlurb(service, s.lang)}</small>
      </span>
      <button className="pw-svc-book" onClick={() => s.openBooking(id)}>
        {t.bookThis}
      </button>
    </div>
  );
}

function NearYou() {
  const s = useSite();
  const t = strings(s.lang);
  const city = s.browseCity ?? 'Mumbai';
  return (
    <section className="pw-section pw-near">
      <SectionHead title={t.nearTitle} lead={t.nearLead} />
      <CityChips value={city} onPick={(c) => s.browse(c)} />
      <BranchGrid city={city} />
    </section>
  );
}

function CityChips({ value, onPick, all }: { value: string | null; onPick: (c: string | null) => void; all?: boolean }) {
  const s = useSite();
  const t = strings(s.lang);
  return (
    <div className="pw-cities pw-cities-site">
      {all && (
        <button className={`pw-chip${value === null ? ' is-chosen' : ''}`} onClick={() => onPick(null)}>
          {t.allCities}
        </button>
      )}
      {CITIES.map((c) => (
        <button
          key={c}
          data-browse-city={c}
          className={`pw-chip${value === c ? ' is-chosen' : ''}${OPENING_SOON.has(c) ? ' is-soon' : ''}`}
          onClick={() => onPick(c)}
        >
          {cityName(c, s.lang)}
          {OPENING_SOON.has(c) && <em>{t.openingSoon}</em>}
        </button>
      ))}
    </div>
  );
}

function BranchGrid({ city }: { city: string | null }) {
  const s = useSite();
  const t = strings(s.lang);
  const list = city ? branchesIn(city) : BRANCHES;
  return (
    <div className="pw-branches">
      {list.map((b) => {
        const soon = OPENING_SOON.has(b.city);
        return (
          <article key={b.id} className={`pw-branch${s.browseCity === b.city ? ' is-lit' : ''}`} data-branch-card={b.id}>
            <h3>
              {b.name}
              {b.emergency && <span className="pw-tag">{t.emergencyBranch}</span>}
              {soon && <span className="pw-tag pw-tag-soon">{t.openingSoon}</span>}
            </h3>
            <p>
              <MapPin size={15} /> {b.address}
            </p>
            <p>
              <Clock size={15} /> {b.emergency ? '24x7' : '9:00 AM – 8:00 PM'}
            </p>
            {!soon && (
              <button
                className="pw-link"
                onClick={() => {
                  s.openBooking();
                  s.pickBranch(b.id);
                }}
              >
                {t.bookHere} <ArrowRight size={15} />
              </button>
            )}
          </article>
        );
      })}
    </div>
  );
}

// ── Pages ─────────────────────────────────────────────────────────────────────

function PageHero({ title, lead, image }: { title: string; lead: string; image?: string }) {
  return (
    <section className={`pw-page-hero${image ? ' has-image' : ''}`}>
      <div>
        <h1>{title}</h1>
        <p>{lead}</p>
      </div>
      {image && <img src={image} alt="" />}
    </section>
  );
}

function ServicesPage() {
  const s = useSite();
  const t = strings(s.lang);
  return (
    <>
      <PageHero title={t.servicesTitle} lead={t.servicesLead} image={vetDog} />
      {(['Everyday care', 'Specialty care'] as const).map((g) => (
        <section key={g} className="pw-section">
          <SectionHead title={g === 'Everyday care' ? t.primary : t.specialty} />
          <div className="pw-svc-grid">
            {SERVICES.filter((x) => x.group === g).map((x) => (
              <ServiceCard key={x.id} id={x.id} />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

function LocationsPage() {
  const s = useSite();
  const t = strings(s.lang);
  return (
    <>
      <PageHero title={t.locationsTitle} lead={t.nearLead} />
      <section className="pw-section">
        <CityChips value={s.browseCity} onPick={(c) => s.browse(c)} all />
        <BranchGrid city={s.browseCity} />
      </section>
    </>
  );
}

const TAGS: HubTag[] = ['Dogs', 'Cats', 'Seasonal', 'Prevention'];

function HubPage() {
  const s = useSite();
  const t = strings(s.lang);
  const [tag, setTag] = useState<HubTag | null>(null);
  const list = tag ? ARTICLES.filter((a) => a.tags.includes(tag)) : ARTICLES;
  return (
    <>
      <PageHero title={t.hubPageTitle} lead={t.hubPageLead} />
      <section className="pw-section">
        <div className="pw-cities pw-cities-site">
          <button className={`pw-chip${tag === null ? ' is-chosen' : ''}`} onClick={() => setTag(null)}>
            {t.all} <em className="pw-count">{ARTICLES.length}</em>
          </button>
          {TAGS.map((x) => (
            <button key={x} className={`pw-chip${tag === x ? ' is-chosen' : ''}`} onClick={() => setTag(x)}>
              {x} <em className="pw-count">{ARTICLES.filter((a) => a.tags.includes(x)).length}</em>
            </button>
          ))}
        </div>
        <div className="pw-articles">
          {list.map((a) => (
            <ArticleCard key={a.id} a={a} />
          ))}
        </div>
      </section>
    </>
  );
}

function ArticleCard({ a }: { a: Article }) {
  const s = useSite();
  const t = strings(s.lang);
  return (
    <button className="pw-article-card" data-article-id={a.id} onClick={() => s.openArticle(a.id)}>
      <img src={a.image} alt="" />
      <span className="pw-article-meta">
        {formatDate(a.date, { weekday: undefined, year: 'numeric' }, locale(s.lang))} · {a.readMins} {t.minRead}
      </span>
      <strong>{a.title}</strong>
      <small>{a.dek}</small>
      <span className="pw-link">
        {t.readMore} <ArrowRight size={15} />
      </span>
    </button>
  );
}

function ArticlePage() {
  const s = useSite();
  const t = strings(s.lang);
  const a = getArticle(s.articleId);
  if (!a) return null;
  const service = getService(a.serviceId);
  const anchor = (i: number) => `pw-sec-${i}`;
  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  return (
    <article className="pw-article" data-article={a.id}>
      <button className="pw-crumb" onClick={() => s.openPage('health_hub')}>
        {t.backToHub} / <span>{a.tags.join(' · ')}</span>
      </button>
      <h1>{a.title}</h1>
      <p className="pw-article-dek">{a.dek}</p>
      <p className="pw-article-meta">
        Petwell · {formatDate(a.date, { weekday: undefined, year: 'numeric' }, locale(s.lang))} · {a.readMins}{' '}
        {t.minRead}
      </p>
      <div className="pw-article-layout">
        <aside className="pw-toc">
          <strong>{t.onThisPage}</strong>
          {a.sections.map((sec, i) => (
            <button key={i} onClick={() => jump(anchor(i))}>
              {sec.heading}
            </button>
          ))}
          <button onClick={() => jump('pw-faqs')}>{t.faqs}</button>
          {service && (
            <div className="pw-toc-cta">
              <PawPrint size={18} />
              <span>{serviceName(service, s.lang)}</span>
              <button className="pw-cta" onClick={() => s.openBooking(service.id)}>
                {t.bookThis}
              </button>
            </div>
          )}
        </aside>
        <div className="pw-article-body">
          <img className="pw-article-img" src={a.image} alt="" />
          {a.sections.map((sec, i) => (
            <section key={i} id={anchor(i)}>
              <h2>{sec.heading}</h2>
              {sec.body?.map((p, j) => (
                <p key={j}>{p}</p>
              ))}
              {sec.bullets && (
                <ul>
                  {sec.bullets.map((x, j) => (
                    <li key={j}>{x}</li>
                  ))}
                </ul>
              )}
              {sec.table && (
                <table>
                  <thead>
                    <tr>
                      <th>{sec.table.head[0]}</th>
                      <th>{sec.table.head[1]}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sec.table.rows.map(([k, v]) => (
                      <tr key={k}>
                        <td>{k}</td>
                        <td>{v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {sec.callout && (
                <div className={`pw-callout is-${sec.callout.kind}`}>
                  {sec.callout.kind === 'warning' ? <TriangleAlert size={18} /> : <Lightbulb size={18} />}
                  <span>
                    <strong>{sec.callout.kind === 'warning' ? 'Warning' : 'Tip'}:</strong> {sec.callout.text}
                  </span>
                </div>
              )}
            </section>
          ))}
          <section id="pw-faqs">
            <h2>{t.faqs}</h2>
            {a.faqs.map((f, i) => (
              <details key={i} className="pw-faq" open={i === 0}>
                <summary>{f.q}</summary>
                <p>{f.a}</p>
              </details>
            ))}
          </section>
          {service && (
            <div className="pw-article-cta">
              <div>
                <strong>
                  {t.bookThis} {serviceName(service, s.lang)}
                </strong>
                <span>{t.willCall}</span>
              </div>
              <button className="pw-cta" onClick={() => s.openBooking(service.id)}>
                <Calendar size={17} /> {t.book}
              </button>
            </div>
          )}
          <p className="pw-small">{t.notAdvice}</p>
        </div>
      </div>
    </article>
  );
}

function AtHomePage() {
  const s = useSite();
  const t = strings(s.lang);
  const why: [ReactNode, string, string][] = [
    [<ShieldCheck size={22} />, t.stressFree, t.stressFreeText],
    [<Clock size={22} />, t.convenient, t.convenientText],
    [<PawPrint size={22} />, t.personal, t.personalText],
    [<Stethoscope size={22} />, t.trusted, t.trustedText],
  ];
  return (
    <>
      <PageHero title={t.atHomeTitle} lead={t.atHomeLead} image={atHome} />
      <section className="pw-section">
        <div className="pw-why">
          {why.map(([icon, title, text]) => (
            <div key={title}>
              <span className="pw-svc-icon">{icon}</span>
              <strong>{title}</strong>
              <small>{text}</small>
            </div>
          ))}
        </div>
      </section>
      <section className="pw-section">
        <SectionHead
          title={t.atHomeGroup}
          action={
            <button className="pw-cta" onClick={() => bookHome(s)}>
              <Home size={17} /> {t.homeBook}
            </button>
          }
        />
        <div className="pw-svc-grid">
          {SERVICES.filter((x) => x.visit === 'home').map((x) => (
            <ServiceCard key={x.id} id={x.id} />
          ))}
        </div>
      </section>
    </>
  );
}

function Footer() {
  const s = useSite();
  const t = strings(s.lang);
  return (
    <footer className="pw-footer">
      <div className="pw-footer-grid">
        <div>
          <div className="pw-logo is-light">
            <span className="pw-logo-mark">
              <PawPrint size={18} />
            </span>
            <span>
              <span className="pw-logo-name">Petwell</span>
              <span className="pw-logo-sub">{t.hospitals}</span>
            </span>
          </div>
          <p>{t.footerAbout}</p>
        </div>
        <div>
          <strong>{t.navServices}</strong>
          {SERVICES.slice(0, 5).map((x) => (
            <button key={x.id} onClick={() => s.openBooking(x.id)}>
              {serviceName(x, s.lang)}
            </button>
          ))}
        </div>
        <div>
          <strong>{t.navLocations}</strong>
          {CITIES.map((c) => (
            <button key={c} onClick={() => s.browse(c)}>
              {cityName(c, s.lang)}
            </button>
          ))}
        </div>
        <div>
          <strong>{t.emergency}</strong>
          {HELPLINES.map((h) => (
            <span key={h.region}>
              <Phone size={13} /> {h.region}: {h.phone}
            </span>
          ))}
        </div>
      </div>
      <p className="pw-footer-small">
        © 2026 Petwell · {t.photos} (Wade Austin Ellis, Alexander Mass, Judy Beth Morris, Buddy AN, Jamie Street,
        Nicholas Brownlow, Bill Stephan, Cédric VT, Robert Larsson)
      </p>
    </footer>
  );
}

const SITE_CSS = `
.pw-app { scroll-behavior: smooth; }
.pw-ticker { position: relative; z-index: 6; }
.pw-header { position: sticky; top: 0; z-index: 8; background: rgba(255,255,255,.96); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--pw-line); }
.pw-header-row { max-width: 1240px; margin: 0 auto; display: flex; flex-wrap: wrap; align-items: center; gap: 6px 18px; padding: 10px 20px; }
.pw-nav { display: flex; gap: 2px; flex: 1; min-width: 0; overflow-x: auto; scrollbar-width: none; }
.pw-nav button { background: none; border: 0; padding: 8px 12px; border-radius: 10px; font-weight: 600; font-size: 14px;
  color: var(--ink) !important; cursor: pointer; white-space: nowrap; }
.pw-nav button:hover { background: var(--pw-tint); }
.pw-nav button.is-current { color: var(--pw) !important; background: var(--pw-tint); }
.pw-header-actions { display: flex; align-items: center; gap: 10px; margin-left: auto; min-width: 0; }
.pw-lang { display: flex; align-items: center; gap: 2px; padding: 3px 3px 3px 9px; border: 1.5px solid var(--pw-line);
  border-radius: 999px; color: var(--muted); }
.pw-lang button { border: 0; background: none; padding: 4px 9px; border-radius: 999px; font-size: 12.5px; font-weight: 700;
  cursor: pointer; color: var(--muted) !important; }
.pw-lang button.is-on { background: var(--pw); color: #fff !important; }
.pw-cta { display: inline-flex; align-items: center; justify-content: center; gap: 8px; border: 0; background: var(--pw);
  color: #fff !important; font-weight: 700; font-size: 14px; padding: 10px 16px; border-radius: 12px; cursor: pointer;
  white-space: nowrap; transition: background .15s, transform .15s; }
.pw-cta:hover { background: var(--pw-dark); }
.pw-cta-lg { padding: 14px 22px; font-size: 15.5px; border-radius: 14px; }
.pw-ghost { display: inline-flex; align-items: center; gap: 8px; border: 1.5px solid var(--sos); background: #fff;
  color: var(--sos) !important; font-weight: 700; cursor: pointer; }
.pw-link { display: inline-flex; align-items: center; gap: 6px; background: none; border: 0; color: var(--pw) !important;
  font-weight: 700; font-size: 14px; cursor: pointer; padding: 0; }

.pw-page { max-width: 1240px; margin: 0 auto; padding: 0 20px; animation: pw-in .25s ease; }
.pw-section { padding: 44px 0 8px; }
.pw-section-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.pw-section-head h2 { margin: 0; font-size: 30px; letter-spacing: -.02em; color: var(--pw-dark); }
.pw-section-head p { margin: 6px 0 0; color: var(--muted); }
.pw-kicker { display: inline-block; font-size: 12.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
  color: var(--pw); background: #fff; border: 1px solid var(--pw-line); padding: 5px 10px; border-radius: 999px; }

.pw-hero { display: grid; grid-template-columns: 1.05fr .95fr; gap: 40px; align-items: center; padding: 40px 0 16px; }
.pw-hero h1 { font-size: 50px; line-height: 1.05; letter-spacing: -.03em; color: var(--pw-dark); margin: 16px 0 14px; }
.pw-app[data-lang="hi"] .pw-hero h1 { font-size: 42px; line-height: 1.3; letter-spacing: 0; }
.pw-hero-lead { font-size: 18px; color: var(--muted); line-height: 1.55; margin: 0 0 22px; }
.pw-hero-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.pw-hero-voice { display: flex; align-items: center; gap: 8px; color: var(--pw-dark); font-weight: 600; font-size: 14px; margin: 16px 0 0; }
.pw-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 28px 0 0; }
.pw-stats div { background: #fff; border-radius: 14px; padding: 12px 14px; box-shadow: 0 2px 12px rgba(74,53,150,.06); }
.pw-stats dt { font-size: 24px; font-weight: 800; color: var(--pw); }
.pw-stats dd { margin: 2px 0 0; font-size: 12.5px; color: var(--muted); }
.pw-hero-art { position: relative; }
.pw-hero-art img { width: 100%; aspect-ratio: 5 / 4.4; object-fit: cover; border-radius: 28px 28px 28px 120px; display: block;
  box-shadow: 0 20px 60px rgba(74,53,150,.18); }
.pw-hero-badge { position: absolute; left: -18px; bottom: 28px; display: flex; gap: 10px; align-items: center; background: #fff;
  padding: 12px 16px; border-radius: 16px; box-shadow: 0 10px 30px rgba(31,27,46,.15); color: var(--sos); }
.pw-hero-badge strong { display: block; color: var(--ink); font-size: 14px; }
.pw-hero-badge small { color: var(--muted); }

.pw-tabs { display: flex; background: #fff; border: 1.5px solid var(--pw-line); border-radius: 999px; padding: 3px; }
.pw-tabs button { border: 0; background: none; padding: 8px 16px; border-radius: 999px; font-weight: 700; cursor: pointer;
  color: var(--muted) !important; }
.pw-tabs button.is-on { background: var(--pw); color: #fff !important; }
.pw-care { display: grid; grid-template-columns: .9fr 1.1fr; gap: 28px; }
.pw-care-photos { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 12px; min-height: 380px; }
.pw-care-photos img { width: 100%; height: 100%; object-fit: cover; border-radius: 20px; }
.pw-care-photos img:first-child { grid-row: span 2; }
.pw-care-list { display: flex; flex-direction: column; gap: 10px; }
.pw-svc { display: flex; align-items: center; gap: 14px; background: #fff; border-radius: 16px; padding: 14px 16px;
  border: 1.5px solid transparent; transition: border-color .15s, box-shadow .15s; }
.pw-svc:hover { border-color: var(--pw-line); box-shadow: 0 6px 20px rgba(74,53,150,.08); }
.pw-svc-icon { width: 46px; height: 46px; border-radius: 14px; background: var(--pw-tint); color: var(--pw); display: grid;
  place-items: center; flex: 0 0 auto; }
.pw-svc-text { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.pw-svc-text strong { font-size: 15.5px; }
.pw-svc-text small { color: var(--muted); font-size: 13px; }
.pw-svc-book { border: 1.5px solid var(--pw-line); background: #fff; color: var(--pw) !important; font-weight: 700;
  padding: 7px 14px; border-radius: 10px; cursor: pointer; }
.pw-svc-book:hover { background: var(--pw); border-color: var(--pw); color: #fff !important; }
.pw-svc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }

.pw-cities-site { margin-bottom: 18px; }
.pw-count { font-style: normal; font-size: 11px; opacity: .7; background: none !important; color: inherit !important; padding: 0 !important; }
.pw-branches { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.pw-branch { background: #fff; border-radius: 16px; padding: 16px 18px; border: 1.5px solid transparent; }
.pw-branch.is-lit { border-color: var(--pw-line); }
.pw-branch h3 { margin: 0 0 8px; font-size: 16px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.pw-branch p { display: flex; gap: 8px; align-items: flex-start; margin: 0 0 6px; color: var(--muted); font-size: 13.5px; }
.pw-branch p svg { color: var(--pw); flex: 0 0 auto; margin-top: 2px; }
.pw-tag-soon { color: #b54708 !important; background: #fff4e5 !important; }

.pw-band { display: grid; grid-template-columns: 1fr 1fr; gap: 0; margin: 48px 0 8px; border-radius: 28px; overflow: hidden;
  background: var(--pw-dark); color: #fff; }
.pw-band img { width: 100%; height: 100%; min-height: 320px; object-fit: cover; }
.pw-band > div { padding: 40px; display: flex; flex-direction: column; align-items: flex-start; gap: 14px; justify-content: center; }
.pw-band h2 { margin: 0; font-size: 30px; letter-spacing: -.02em; }
.pw-band p { margin: 0; opacity: .88; line-height: 1.55; }
.pw-band .pw-kicker { background: rgba(255,255,255,.12); color: #fff; border-color: transparent; }
.pw-band .pw-cta { background: #fff; color: var(--pw-dark) !important; }

.pw-testimonial { display: grid; grid-template-columns: 260px 1fr; gap: 32px; align-items: center; }
.pw-testimonial img { width: 260px; height: 260px; object-fit: cover; border-radius: 50%; border: 8px solid #fff;
  box-shadow: 0 10px 30px rgba(74,53,150,.15); }
.pw-testimonial figure { margin: 0; color: var(--pw); }
.pw-testimonial blockquote { margin: 8px 0 12px; font-size: 22px; line-height: 1.5; color: var(--ink); font-weight: 500; }
.pw-testimonial figcaption { color: var(--muted); font-weight: 700; }

.pw-articles { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.pw-article-card { display: flex; flex-direction: column; gap: 8px; text-align: left; background: #fff; border: 0; border-radius: 20px;
  padding: 0 0 18px; overflow: hidden; cursor: pointer; transition: transform .15s, box-shadow .15s; }
.pw-article-card:hover { transform: translateY(-2px); box-shadow: 0 12px 30px rgba(74,53,150,.12); }
.pw-article-card img { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }
.pw-article-card > :not(img) { margin: 0 18px; }
.pw-article-card strong { font-size: 17px; line-height: 1.35; }
.pw-article-card small { color: var(--muted); line-height: 1.45; }
.pw-article-meta { color: var(--muted); font-size: 12.5px; font-weight: 600; }

.pw-page-hero { display: grid; grid-template-columns: 1fr; gap: 28px; align-items: center; padding: 40px 0 0; }
.pw-page-hero.has-image { grid-template-columns: 1.2fr .8fr; }
.pw-page-hero h1 { font-size: 40px; letter-spacing: -.02em; margin: 0 0 10px; color: var(--pw-dark); }
.pw-page-hero p { margin: 0; color: var(--muted); font-size: 17px; line-height: 1.55; max-width: 640px; }
.pw-page-hero img { width: 100%; height: 260px; object-fit: cover; border-radius: 24px; }
.pw-why { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.pw-why div { background: #fff; border-radius: 16px; padding: 18px; display: flex; flex-direction: column; gap: 8px; }
.pw-why small { color: var(--muted); }

.pw-article { max-width: 1080px; margin: 0 auto; padding: 32px 0 8px; }
.pw-crumb { background: none; border: 0; padding: 0; color: var(--pw) !important; font-weight: 700; cursor: pointer; font-size: 13.5px; }
.pw-crumb span { color: var(--muted); font-weight: 600; }
.pw-article h1 { font-size: 38px; line-height: 1.15; letter-spacing: -.02em; color: var(--pw-dark); margin: 12px 0 10px; }
.pw-article-dek { font-size: 18px; color: var(--muted); margin: 0 0 8px; line-height: 1.5; }
.pw-article-layout { display: grid; grid-template-columns: 240px 1fr; gap: 36px; margin-top: 20px; align-items: start; }
.pw-toc { position: sticky; top: 90px; display: flex; flex-direction: column; gap: 2px; }
.pw-toc > strong { font-size: 12.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 6px; }
.pw-toc > button { text-align: left; background: none; border: 0; border-left: 2px solid var(--pw-line); padding: 6px 12px;
  cursor: pointer; color: var(--ink) !important; font-size: 14px; }
.pw-toc > button:hover { border-left-color: var(--pw); color: var(--pw) !important; }
.pw-toc-cta { margin-top: 16px; background: #fff; border-radius: 16px; padding: 14px; display: flex; flex-direction: column;
  gap: 8px; color: var(--pw); }
.pw-toc-cta span { color: var(--ink); font-weight: 700; }
.pw-article-body { background: #fff; border-radius: 24px; padding: 28px 32px; font-size: 16px; line-height: 1.7; }
.pw-article-img { width: 100%; aspect-ratio: 16 / 8; object-fit: cover; border-radius: 16px; margin-bottom: 8px; }
.pw-article-body h2 { font-size: 22px; color: var(--pw-dark); margin: 26px 0 8px; scroll-margin-top: 90px; }
.pw-article-body ul { padding-left: 20px; }
.pw-article-body table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 15px; }
.pw-article-body th, .pw-article-body td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--pw-line); }
.pw-article-body th { background: var(--pw-tint); color: var(--pw-dark); }
.pw-callout { display: flex; gap: 10px; padding: 12px 14px; border-radius: 12px; margin: 14px 0; font-size: 15px; line-height: 1.55; }
.pw-callout svg { flex: 0 0 auto; margin-top: 3px; }
.pw-callout.is-warning { background: #fef3f2; color: #912018; }
.pw-callout.is-tip { background: #ecfdf3; color: #05603a; }
.pw-faq { border: 1.5px solid var(--pw-line); border-radius: 12px; padding: 12px 16px; margin: 8px 0; }
.pw-faq summary { font-weight: 700; cursor: pointer; }
.pw-faq p { margin: 8px 0 0; color: var(--muted); }
.pw-article-cta { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  margin: 24px 0 8px; padding: 18px 20px; border-radius: 16px; background: var(--pw-dark); color: #fff; }
.pw-article-cta strong { display: block; font-size: 17px; }
.pw-article-cta span { opacity: .85; font-size: 14px; }
.pw-article-cta .pw-cta { background: #fff; color: var(--pw-dark) !important; }

.pw-footer { margin-top: 56px; background: #1f1b2e; color: #c9c4dc; padding: 40px 20px 24px; }
.pw-footer-grid { max-width: 1240px; margin: 0 auto; display: grid; grid-template-columns: 1.4fr 1fr 1fr 1.2fr; gap: 28px; }
.pw-footer-grid > div { display: flex; flex-direction: column; gap: 6px; font-size: 14px; }
.pw-footer-grid strong { color: #fff; margin-bottom: 4px; }
.pw-footer-grid button { background: none; border: 0; padding: 0; text-align: left; color: #c9c4dc !important; cursor: pointer; }
.pw-footer-grid button:hover { color: #fff !important; }
.pw-footer-grid span { display: flex; gap: 6px; align-items: center; }
.pw-logo.is-light .pw-logo-name { color: #fff; }
.pw-logo.is-light .pw-logo-sub { color: #c9c4dc; }
.pw-footer-small { max-width: 1240px; margin: 24px auto 0; font-size: 11.5px; opacity: .7; }

/* Booking drawer */
.pw-drawer-wrap { position: fixed; inset: 0; z-index: 30; background: rgba(31,27,46,.35); animation: pw-in .2s; }
.pw-drawer { position: absolute; top: 0; right: 0; bottom: 0; width: min(640px, 100%); background: #fff; display: flex;
  flex-direction: column; box-shadow: -10px 0 40px rgba(31,27,46,.2); animation: pw-slide .25s ease; }
@keyframes pw-slide { from { transform: translateX(40px); opacity: 0; } }
.pw-drawer-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 22px; border-bottom: 1px solid var(--pw-line); }
.pw-drawer-head h2 { margin: 0; font-size: 20px; color: var(--pw-dark); }
.pw-drawer-body { flex: 1; overflow-y: auto; padding: 20px 22px 28px; }
.pw-icon-btn { background: none; border: 0; cursor: pointer; color: var(--muted) !important; padding: 4px; }

/* Tushar's dock — over the page, beside the booking drawer when it is open. */
.pw-dock { position: fixed; right: 20px; bottom: 20px; z-index: 40; width: 204px; }

/* Below a wide desktop the nav takes a row of its own, and the mic speaks for
   itself — its label yields first. */
@media (max-width: 1439px) {
  .pw-nav { order: 3; flex-basis: 100%; margin: 0 -12px; }
  .pw-presence-label { display: none !important; }
}
@media (max-width: 900px) {
  .pw-hero, .pw-care, .pw-band, .pw-testimonial, .pw-page-hero.has-image, .pw-article-layout { grid-template-columns: 1fr; }
  .pw-hero h1 { font-size: 36px; }
  .pw-toc { position: static; }
  .pw-why { grid-template-columns: 1fr 1fr; }
  .pw-footer-grid { grid-template-columns: 1fr 1fr; }
  .pw-testimonial img { width: 160px; height: 160px; }
}
@media (max-width: 640px) {
  .pw-header-row { padding: 8px 12px; gap: 8px; }
  .pw-header-actions { gap: 6px; }
  .pw-header-actions .pw-cta, .pw-lang svg, .pw-logo-sub { display: none; }
  .pw-lang { padding: 2px; }
  .pw-lang button { padding: 4px 7px; }
  .pw-sos { padding: 6px 8px; }
  .pw-nav { margin: 0 -4px; }
  .pw-nav button { padding: 6px 9px; font-size: 13px; }
  .pw-page { padding: 0 14px; }
  .pw-hero { padding-top: 22px; gap: 24px; }
  .pw-hero h1, .pw-app[data-lang="hi"] .pw-hero h1 { font-size: 30px; }
  .pw-stats { grid-template-columns: 1fr 1fr; }
  .pw-hero-badge { left: 10px; }
  .pw-section-head h2 { font-size: 24px; }
  .pw-care-photos { min-height: 220px; }
  .pw-band > div { padding: 24px; }
  .pw-article-body { padding: 20px 18px; }
  .pw-article h1, .pw-page-hero h1 { font-size: 28px; }
  .pw-svc-grid, .pw-articles, .pw-branches { grid-template-columns: 1fr; }
  .pw-footer-grid { grid-template-columns: 1fr; }
  .pw-dock { right: 12px; bottom: 12px; width: 104px; }
  .pw-footer { padding-bottom: 150px; }
}
`;
