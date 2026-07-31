/**
 * The Voqal Mobile shopping app UI — a mobile-first phone store.
 *
 * Every page is plain state-driven (see store.tsx), so the live voice call is
 * never interrupted by navigation. Product cards, spec sections and FAQ topics
 * carry stable `data-*` hooks (`data-product-id`, `data-feature`, `data-topic`)
 * and semantic class names so the agent's screen-driving stays robust.
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  BRANDS,
  CATALOG,
  CATEGORIES,
  SORT_LABELS,
  getPhone,
  phoneAccent,
  sortPhones,
  type Phone,
  type SortKey,
} from './catalog';
import { useMobileShop } from './store';

const BRAND_COLOR = '#4f46e5';
const BRAND_DARK = '#312e81';
const STAR = '#f59e0b';

// ── Small formatting helpers ──────────────────────────────────────────────────
const price = (n: number) => `$${n.toLocaleString()}`;

function displaySize(p: Phone): string | null {
  const m = p.display.match(/([\d.]+)"/);
  return m ? `${m[1]}"` : null;
}
function mainCameraMp(p: Phone): string | null {
  const m = p.rearCamera.match(/(\d+)\s?MP/);
  return m ? `${m[1]}MP` : null;
}
/** Three short spec chips for a card: display size, main camera, battery. */
function specChips(p: Phone): string[] {
  return [displaySize(p), mainCameraMp(p), `${p.batteryMah.toLocaleString()} mAh`].filter(
    (x): x is string => !!x,
  );
}

// ── Star rating ───────────────────────────────────────────────────────────────
function Stars({ rating, size = 13 }: { rating: number; size?: number }) {
  const pct = Math.max(0, Math.min(100, (rating / 5) * 100));
  return (
    <span
      aria-label={`${rating} out of 5`}
      style={{ position: 'relative', display: 'inline-block', fontSize: size, lineHeight: 1, letterSpacing: 1 }}
    >
      <span style={{ color: '#d1d5db' }}>★★★★★</span>
      <span style={{ position: 'absolute', left: 0, top: 0, width: `${pct}%`, overflow: 'hidden', color: STAR, whiteSpace: 'nowrap' }}>
        ★★★★★
      </span>
    </span>
  );
}

function RatingLine({ phone, size = 13 }: { phone: Phone; size?: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <Stars rating={phone.rating} size={size} />
      <span className="ms-rating-value" style={{ fontSize: size - 1, fontWeight: 700, color: '#374151' }}>{phone.rating.toFixed(1)}</span>
      <span className="ms-rating-count" style={{ fontSize: size - 1.5, color: '#9ca3af' }}>({phone.reviewCount.toLocaleString()})</span>
    </span>
  );
}

// Tracks whether the viewport is desktop-width, so the layout can switch
// between the mobile single-column store and a wider desktop store.
function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const on = () => setIsDesktop(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return isDesktop;
}

// Centers page content with a responsive max-width on desktop.
function Container({ children, narrow }: { children: React.ReactNode; narrow?: boolean }) {
  return (
    <div style={{ width: '100%', maxWidth: narrow ? 820 : 1180, margin: '0 auto' }}>{children}</div>
  );
}

// ── Faux product image — a clean phone render on a soft studio backdrop ────────
function PhoneImage({ phone, height = 150 }: { phone: Phone; height?: number }) {
  const accent = phoneAccent(phone.id);
  const dW = Math.round(height * 0.5);
  const dH = Math.round(height * 0.9);
  const radius = Math.round(dW * 0.2);
  return (
    <div
      className="ms-phone-image"
      style={{
        height,
        borderRadius: 14,
        background: 'linear-gradient(160deg, #ffffff 0%, #eef2f7 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* device body (accent frame) */}
      <div
        style={{
          width: dW,
          height: dH,
          borderRadius: radius,
          background: `linear-gradient(155deg, ${accent} 0%, #11131a 135%)`,
          padding: Math.max(3, Math.round(dW * 0.04)),
          boxShadow: '0 8px 20px rgba(15,23,42,.22)',
          position: 'relative',
        }}
      >
        {/* screen */}
        <div
          style={{
            width: '100%',
            height: '100%',
            borderRadius: Math.round(radius * 0.78),
            background: 'linear-gradient(160deg, rgba(255,255,255,.16) 0%, rgba(0,0,0,.28) 100%)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {/* punch-hole camera */}
          <span
            style={{
              position: 'absolute',
              top: Math.round(dH * 0.05),
              left: '50%',
              transform: 'translateX(-50%)',
              width: Math.max(3, Math.round(dW * 0.07)),
              height: Math.max(3, Math.round(dW * 0.07)),
              borderRadius: '50%',
              background: 'rgba(0,0,0,.55)',
            }}
          />
          {/* diagonal screen reflection */}
          <span
            style={{
              position: 'absolute',
              top: -dH * 0.2,
              left: -dW * 0.3,
              width: dW * 0.6,
              height: dH * 1.6,
              background: 'linear-gradient(180deg, rgba(255,255,255,.28), rgba(255,255,255,0))',
              transform: 'rotate(20deg)',
            }}
          />
        </div>
      </div>
    </div>
  );
}

// ── Wishlist heart ─────────────────────────────────────────────────────────────
function WishlistHeart({ phone, size = 30 }: { phone: Phone; size?: number }) {
  const { wishlist, toggleWishlist } = useMobileShop();
  const saved = wishlist.includes(phone.id);
  return (
    <button
      className="ms-wishlist-heart"
      data-product-id={phone.id}
      data-saved={saved}
      title={saved ? 'Saved' : 'Save for later'}
      onClick={(e) => {
        e.stopPropagation();
        toggleWishlist(phone.id);
      }}
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        border: '1px solid #e5e7eb',
        background: 'rgba(255,255,255,.92)',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: size * 0.46,
        lineHeight: 1,
        boxShadow: '0 1px 3px rgba(0,0,0,.08)',
        color: saved ? '#e11d48' : '#9ca3af',
      }}
    >
      {saved ? '♥' : '♡'}
    </button>
  );
}

// ── Product card ──────────────────────────────────────────────────────────────
function PhoneCard({ phone }: { phone: Phone }) {
  const { openProduct } = useMobileShop();
  const chips = specChips(phone);
  return (
    <div
      className="ms-product-card"
      data-product-id={phone.id}
      onClick={() => openProduct(phone.id)}
      style={{
        position: 'relative',
        textAlign: 'left',
        background: 'white',
        border: '1px solid #e5e7eb',
        borderRadius: 16,
        padding: 12,
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 9,
        width: '100%',
        boxShadow: '0 1px 2px rgba(0,0,0,.04)',
        transition: 'box-shadow .2s, transform .2s, border-color .2s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 8px 24px rgba(15,23,42,.10)';
        e.currentTarget.style.borderColor = '#d1d5db';
        e.currentTarget.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = '0 1px 2px rgba(0,0,0,.04)';
        e.currentTarget.style.borderColor = '#e5e7eb';
        e.currentTarget.style.transform = 'none';
      }}
    >
      <div style={{ position: 'absolute', top: 18, right: 18, zIndex: 1 }}>
        <WishlistHeart phone={phone} />
      </div>
      <PhoneImage phone={phone} height={132} />
      <div>
        <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>{phone.brand}</div>
        <div className="ms-card-name" style={{ fontWeight: 700, fontSize: 13.5, color: '#111827', lineHeight: 1.25 }}>
          {phone.name}
        </div>
      </div>
      <RatingLine phone={phone} size={12} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {chips.map((c) => (
          <span key={c} className="ms-spec-chip" style={{ background: '#f3f4f6', color: '#4b5563', borderRadius: 7, padding: '2px 7px', fontSize: 10.5, fontWeight: 600 }}>
            {c}
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 'auto' }}>
        <span className="ms-card-price" style={{ fontWeight: 800, fontSize: 16, color: BRAND_DARK }}>
          {price(phone.price)}
        </span>
        <span style={{ fontSize: 11, color: BRAND_COLOR, fontWeight: 700 }}>View →</span>
      </div>
    </div>
  );
}

function PhoneGrid({ phones }: { phones: Phone[] }) {
  return (
    <div
      className="ms-product-grid"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
        gap: 14,
      }}
    >
      {phones.map((p) => (
        <PhoneCard key={p.id} phone={p} />
      ))}
    </div>
  );
}

function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '4px 2px 12px' }}>
      <h2 style={{ fontSize: 16, fontWeight: 800, color: '#111827' }}>{children}</h2>
      {action}
    </div>
  );
}

// ── Home ──────────────────────────────────────────────────────────────────────
function HomePage() {
  const { showSearch } = useMobileShop();
  const featured = ['galaxy-s24-ultra', 'iphone-15-pro-max', 'pixel-8-pro'].map(getPhone).filter(Boolean) as Phone[];
  const topRated = sortPhones(CATALOG, 'rating').slice(0, 4);
  const popular = ['oneplus-12', 'pixel-8a', 'nothing-phone-2a', 'galaxy-a55'].map(getPhone).filter(Boolean) as Phone[];

  const categories: { label: string; query: string }[] = [
    { label: '📷 Best cameras', query: 'best camera' },
    { label: '🔋 Long battery', query: 'long battery' },
    { label: '💸 Under $400', query: '' },
    { label: '⚡ Fast charging', query: 'fast charging' },
    { label: '📱 Compact', query: 'compact small' },
    { label: '🎮 Gaming', query: 'performance gaming' },
  ];

  const trust = ['🚚 Free 2-day delivery', '↩️ 30-day returns', '🛡️ 1-year warranty', '💳 0% EMI available'];

  return (
    <div className="ms-home" style={{ padding: 14 }}>
      {/* Hero */}
      <div
        className="ms-hero"
        style={{
          borderRadius: 20,
          background: `linear-gradient(135deg, ${BRAND_COLOR} 0%, ${BRAND_DARK} 100%)`,
          color: 'white',
          padding: '24px 20px',
          marginBottom: 16,
        }}
      >
        <div className="ms-hero-title" style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.2 }}>Find your perfect phone</div>
        <div style={{ fontSize: 13.5, opacity: 0.88, marginTop: 6, maxWidth: 460 }}>
          {CATALOG.length} phones from {BRANDS.length} brands, budget to flagship. Not sure which? Tap the mic up top and
          just ask the Mobile Expert.
        </div>
        <button
          className="ms-hero-cta"
          onClick={() => showSearch()}
          style={{
            marginTop: 16,
            background: 'white',
            color: BRAND_DARK,
            border: 'none',
            borderRadius: 10,
            padding: '10px 18px',
            fontWeight: 700,
            fontSize: 13.5,
            cursor: 'pointer',
          }}
        >
          Browse all phones
        </button>
      </div>

      {/* Trust strip */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          flexWrap: 'wrap',
          marginBottom: 20,
        }}
      >
        {trust.map((t) => (
          <span
            key={t}
            style={{
              flex: '1 1 auto',
              textAlign: 'center',
              background: '#f8fafc',
              border: '1px solid #eef0f3',
              borderRadius: 10,
              padding: '8px 10px',
              fontSize: 11.5,
              fontWeight: 600,
              color: '#475569',
              whiteSpace: 'nowrap',
            }}
          >
            {t}
          </span>
        ))}
      </div>

      {/* Category chips */}
      <SectionTitle>Shop by need</SectionTitle>
      <div className="ms-category-chips" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 22 }}>
        {categories.map((c) => (
          <button
            key={c.label}
            className="ms-category-chip"
            onClick={() => (c.label.includes('400') ? showSearch({ maxPrice: 400 }) : showSearch({ query: c.query }))}
            style={{
              background: '#eef2ff',
              color: BRAND_DARK,
              border: '1px solid #e0e7ff',
              borderRadius: 20,
              padding: '8px 14px',
              fontSize: 12.5,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Featured */}
      <SectionTitle>Featured flagships</SectionTitle>
      <div className="ms-featured-row" style={{ display: 'flex', gap: 14, overflowX: 'auto', paddingBottom: 6, marginBottom: 22 }}>
        {featured.map((p) => (
          <div key={p.id} className="ms-featured-card" style={{ flex: '0 0 190px' }}>
            <PhoneCard phone={p} />
          </div>
        ))}
      </div>

      {/* Top rated */}
      <SectionTitle action={<button onClick={() => showSearch({ sort: 'rating' })} style={linkBtn}>See all →</button>}>
        Top rated
      </SectionTitle>
      <div style={{ marginBottom: 22 }}>
        <PhoneGrid phones={topRated} />
      </div>

      {/* Popular */}
      <SectionTitle>Popular right now</SectionTitle>
      <PhoneGrid phones={popular} />
    </div>
  );
}

const linkBtn: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: BRAND_COLOR,
  fontWeight: 700,
  fontSize: 12.5,
  cursor: 'pointer',
};

// ── Search ──────────────────────────────────────────────────────────────────────
function SearchPage() {
  const { query, filters, sortBy, results, setQuery, toggleBrand, setMaxPrice, setCategory, setSort, clearFilters } =
    useMobileShop();
  const priceCaps = [400, 600, 1000];
  const hasFilters = !!(filters.brand || filters.maxPrice || filters.category || query || sortBy);

  return (
    <div className="ms-search" style={{ padding: 14 }}>
      <div style={{ position: 'relative', marginBottom: 12 }}>
        <span style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af', fontSize: 15 }}>🔍</span>
        <input
          className="ms-search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search phones, brands, features…"
          style={{
            width: '100%',
            padding: '12px 14px 12px 38px',
            borderRadius: 12,
            border: '1.5px solid #d1d5db',
            fontSize: 14,
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Filters */}
      <div className="ms-filters" style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 7, overflowX: 'auto', paddingBottom: 8 }}>
          {BRANDS.map((b) => (
            <button
              key={b}
              className="ms-filter-brand"
              data-brand={b}
              data-active={filters.brand === b}
              onClick={() => toggleBrand(b)}
              style={chipStyle(filters.brand === b)}
            >
              {b}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 4 }}>
          {priceCaps.map((p) => (
            <button
              key={p}
              className="ms-filter-price"
              data-max-price={p}
              data-active={filters.maxPrice === p}
              onClick={() => setMaxPrice(filters.maxPrice === p ? undefined : p)}
              style={chipStyle(filters.maxPrice === p)}
            >
              Under ${p}
            </button>
          ))}
          {CATEGORIES.map((c) => (
            <button
              key={c}
              className="ms-filter-category"
              data-category={c}
              data-active={filters.category === c}
              onClick={() => setCategory(filters.category === c ? undefined : c)}
              style={chipStyle(filters.category === c)}
            >
              {c}
            </button>
          ))}
          {hasFilters && (
            <button className="ms-filter-clear" onClick={clearFilters} style={{ ...chipStyle(false), color: '#dc2626', borderColor: '#fecaca' }}>
              Clear ✕
            </button>
          )}
        </div>
      </div>

      {/* Result count + sort */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '2px 2px 12px' }}>
        <div className="ms-result-count" style={{ fontSize: 12.5, color: '#6b7280', fontWeight: 600 }}>
          {results.length} {results.length === 1 ? 'phone' : 'phones'}
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#6b7280' }}>
          Sort
          <select
            className="ms-sort"
            data-sort={sortBy ?? ''}
            value={sortBy ?? ''}
            onChange={(e) => setSort((e.target.value || undefined) as SortKey | undefined)}
            style={{
              border: '1.5px solid #e5e7eb',
              borderRadius: 9,
              padding: '6px 9px',
              fontSize: 12.5,
              fontWeight: 600,
              color: '#374151',
              background: 'white',
              cursor: 'pointer',
            }}
          >
            <option value="">Recommended</option>
            {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => (
              <option key={k} value={k}>
                {SORT_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {results.length ? (
        <PhoneGrid phones={results} />
      ) : (
        <div style={{ textAlign: 'center', color: '#9ca3af', padding: '40px 0', fontSize: 13 }}>
          No phones match. Try clearing a filter.
        </div>
      )}
    </div>
  );
}

function chipStyle(active: boolean): React.CSSProperties {
  return {
    flex: '0 0 auto',
    background: active ? BRAND_COLOR : 'white',
    color: active ? 'white' : '#374151',
    border: `1.5px solid ${active ? BRAND_COLOR : '#e5e7eb'}`,
    borderRadius: 20,
    padding: '6px 13px',
    fontSize: 12.5,
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  };
}

// ── Product detail ────────────────────────────────────────────────────────────
const FEATURE_LABELS: Record<string, string> = {
  display: 'Display',
  camera: 'Camera',
  battery: 'Battery',
  performance: 'Performance',
  charging: 'Charging',
  colors: 'Colors',
  specs: 'Highlights',
};

function SpecRow({ feature, label, children }: { feature: string; label: string; children: React.ReactNode }) {
  return (
    <div
      className="ms-spec"
      data-feature={feature}
      id={`feature-${feature}`}
      style={{ padding: '12px 14px', borderRadius: 12, border: '1px solid #eef0f3', marginBottom: 8, transition: 'background .3s, box-shadow .3s' }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, color: BRAND_COLOR, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 13.5, color: '#1f2937', lineHeight: 1.45 }}>{children}</div>
    </div>
  );
}

// Trust + delivery box shown on the product page.
function DeliveryBox({ phone }: { phone: Phone }) {
  const deliveryDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + 2);
    return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  }, []);
  const emi = Math.round(phone.price / 12);
  const rows = [
    { icon: '🚚', main: 'Free 2-day delivery', sub: `Get it by ${deliveryDate}` },
    { icon: '💳', main: `From $${emi}/mo`, sub: '0% APR financing over 12 months' },
    { icon: '🛡️', main: '1-year warranty', sub: '30-day free returns included' },
  ];
  return (
    <div style={{ border: '1px solid #eef0f3', borderRadius: 12, padding: 12, margin: '12px 0' }}>
      {rows.map((r, i) => (
        <div
          key={r.main}
          style={{
            display: 'flex',
            gap: 10,
            alignItems: 'center',
            padding: '7px 0',
            borderTop: i ? '1px solid #f1f3f5' : undefined,
          }}
        >
          <span style={{ fontSize: 17 }}>{r.icon}</span>
          <div>
            <div style={{ fontSize: 12.5, fontWeight: 700, color: '#111827' }}>{r.main}</div>
            <div style={{ fontSize: 11.5, color: '#6b7280' }}>{r.sub}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Synthesized reviews (deterministic from product data) ─────────────────────
const REVIEWER_NAMES = ['Arjun M.', 'Priya S.', 'Daniel K.', 'Mei L.', 'Sofia R.', 'Liam P.', 'Ananya R.', 'Marco V.', 'Hana T.'];

function hashId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h;
}

function reviewsFor(phone: Phone): { name: string; stars: number; title: string; body: string }[] {
  const h = hashId(phone.id);
  const n = REVIEWER_NAMES.length;
  const name = (k: number) => REVIEWER_NAMES[(h >> (k * 3)) % n];
  const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
  return [
    {
      name: name(0),
      stars: 5,
      title: 'Exactly what I hoped for',
      body: `${phone.pros[0]}. ${phone.pros[1]} too — really happy with this one.`,
    },
    {
      name: name(1),
      stars: phone.rating >= 4.5 ? 5 : 4,
      title: 'Great value',
      body: `${phone.pros[2] ?? phone.pros[0]}. ${phone.bestFor}`,
    },
    {
      name: name(2),
      stars: 4,
      title: 'Very good, a couple of niggles',
      body: `Love it overall — ${lower(phone.pros[3] ?? phone.pros[0])}. Only downside: ${lower(phone.cons[0])}.`,
    },
  ];
}

function ratingHistogram(rating: number): number[] {
  const p5 = Math.min(93, Math.round(((rating - 3) / 2) * 100));
  const rest = 100 - p5;
  const p4 = Math.round(rest * 0.55);
  const p3 = Math.round(rest * 0.25);
  const p2 = Math.round(rest * 0.12);
  const p1 = Math.max(0, 100 - p5 - p4 - p3 - p2);
  return [p5, p4, p3, p2, p1];
}

function ReviewsSection({ phone }: { phone: Phone }) {
  const hist = ratingHistogram(phone.rating);
  const reviews = reviewsFor(phone);
  return (
    <div
      className="ms-reviews"
      data-feature="reviews"
      id="feature-reviews"
      style={{ border: '1px solid #eef0f3', borderRadius: 12, padding: 14, marginTop: 10, transition: 'background .3s, box-shadow .3s' }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, color: BRAND_COLOR, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 10 }}>
        Ratings &amp; reviews
      </div>

      {/* Summary */}
      <div style={{ display: 'flex', gap: 18, alignItems: 'center', marginBottom: 14 }}>
        <div style={{ textAlign: 'center', flex: '0 0 auto' }}>
          <div style={{ fontSize: 32, fontWeight: 900, color: '#111827', lineHeight: 1 }}>{phone.rating.toFixed(1)}</div>
          <Stars rating={phone.rating} size={14} />
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 3 }}>{phone.reviewCount.toLocaleString()} reviews</div>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {hist.map((pct, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
              <span style={{ fontSize: 11, color: '#6b7280', width: 10, textAlign: 'right' }}>{5 - i}</span>
              <span style={{ color: STAR, fontSize: 11 }}>★</span>
              <span style={{ flex: 1, height: 7, background: '#f1f3f5', borderRadius: 4, overflow: 'hidden' }}>
                <span style={{ display: 'block', width: `${pct}%`, height: '100%', background: STAR }} />
              </span>
              <span className="ms-hist-pct" style={{ fontSize: 10.5, color: '#9ca3af', width: 28, textAlign: 'right' }}>{pct}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* Individual reviews */}
      {reviews.map((r) => (
        <div key={r.name} style={{ borderTop: '1px solid #f1f3f5', padding: '10px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
            <Stars rating={r.stars} size={11} />
            <span style={{ fontSize: 12.5, fontWeight: 700, color: '#111827' }}>{r.title}</span>
          </div>
          <div style={{ fontSize: 12.5, color: '#4b5563', lineHeight: 1.5 }}>{r.body}</div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 3 }}>{r.name} · Verified purchase</div>
        </div>
      ))}
    </div>
  );
}

function ProductPage({ isDesktop }: { isDesktop: boolean }) {
  const { productId, highlight, addToCart, cart, wishlist, toggleWishlist } = useMobileShop();
  const phone = productId ? getPhone(productId) : undefined;

  // Highlight: scroll the named spec into view and flash it.
  useEffect(() => {
    if (!highlight || !phone || highlight.productId !== phone.id) return;
    const el = document.getElementById(`feature-${highlight.feature}`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.style.background = '#fef9c3';
    el.style.boxShadow = `0 0 0 2px ${BRAND_COLOR}`;
    const t = setTimeout(() => {
      el.style.background = '';
      el.style.boxShadow = '';
    }, 1800);
    return () => clearTimeout(t);
  }, [highlight, phone]);

  // Reset scroll when switching products (the body element is the scroller).
  useEffect(() => {
    document.querySelector('.ms-body')?.scrollTo({ top: 0 });
  }, [productId]);

  if (!phone) return <div style={{ padding: 30, textAlign: 'center', color: '#9ca3af' }}>Select a phone.</div>;

  const inCart = cart.includes(phone.id);
  const saved = wishlist.includes(phone.id);

  // Left column: hero image, identity, buy actions.
  const left = (
    <div>
      <PhoneImage phone={phone} height={isDesktop ? 340 : 230} />

      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: 12, color: '#6b7280', fontWeight: 600 }}>{phone.brand}</div>
        <h1 className="ms-product-name" style={{ fontSize: isDesktop ? 24 : 20, fontWeight: 800, color: '#111827', margin: '2px 0 4px' }}>
          {phone.name}
        </h1>
        <RatingLine phone={phone} size={14} />
        <div style={{ fontSize: 13, color: '#6b7280', marginTop: 6 }}>{phone.tagline}</div>
        <div className="ms-product-price" style={{ fontSize: isDesktop ? 28 : 24, fontWeight: 900, color: BRAND_DARK, marginTop: 8 }}>
          {price(phone.price)}
        </div>
      </div>

      {/* Highlights pills */}
      <div data-feature="specs" id="feature-specs" style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '12px 0', transition: 'background .3s, box-shadow .3s', borderRadius: 12, padding: 4 }}>
        {phone.highlights.map((h) => (
          <span key={h} style={{ background: '#eef2ff', color: BRAND_DARK, borderRadius: 16, padding: '5px 11px', fontSize: 11.5, fontWeight: 600 }}>
            {h}
          </span>
        ))}
      </div>

      <DeliveryBox phone={phone} />

      {/* Buy actions */}
      <button
        className="ms-add-to-cart"
        data-product-id={phone.id}
        onClick={() => addToCart(phone.id)}
        disabled={inCart}
        style={{
          width: '100%',
          background: inCart ? '#16a34a' : BRAND_COLOR,
          color: 'white',
          border: 'none',
          borderRadius: 12,
          padding: '13px',
          fontWeight: 700,
          fontSize: 14,
          cursor: inCart ? 'default' : 'pointer',
          marginBottom: 8,
        }}
      >
        {inCart ? '✓ In cart' : 'Add to cart'}
      </button>
      <button
        className="ms-wishlist-btn"
        data-product-id={phone.id}
        data-saved={saved}
        onClick={() => toggleWishlist(phone.id)}
        style={{
          width: '100%',
          background: 'white',
          color: saved ? '#e11d48' : '#374151',
          border: `1.5px solid ${saved ? '#fecdd3' : '#e5e7eb'}`,
          borderRadius: 12,
          padding: '11px',
          fontWeight: 700,
          fontSize: 13.5,
          cursor: 'pointer',
        }}
      >
        {saved ? '♥ Saved to wishlist' : '♡ Save to wishlist'}
      </button>
    </div>
  );

  // Right column: spec sections, pros/cons, best-for, reviews, meta.
  const right = (
    <div>
      <SpecRow feature="display" label={FEATURE_LABELS.display}>{phone.display}</SpecRow>
      <SpecRow feature="camera" label={FEATURE_LABELS.camera}>
        {phone.rearCamera}
        <div style={{ color: '#6b7280', marginTop: 3 }}>Front: {phone.frontCamera}</div>
      </SpecRow>
      <SpecRow feature="battery" label={FEATURE_LABELS.battery}>{phone.batteryMah.toLocaleString()} mAh</SpecRow>
      <SpecRow feature="charging" label={FEATURE_LABELS.charging}>{phone.charging}</SpecRow>
      <SpecRow feature="performance" label={FEATURE_LABELS.performance}>
        {phone.processor} · {phone.ramGb.join('/')}GB RAM · {phone.storageGb.join('/')}GB storage
      </SpecRow>
      <SpecRow feature="colors" label={FEATURE_LABELS.colors}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {phone.colors.map((c) => (
            <span key={c} className="ms-color" data-color={c} style={{ background: '#f3f4f6', borderRadius: 14, padding: '4px 10px', fontSize: 12 }}>
              {c}
            </span>
          ))}
        </div>
      </SpecRow>

      {/* Pros / cons */}
      <div className="ms-proscons" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, margin: '10px 0' }}>
        <div style={{ background: '#f0fdf4', border: '1px solid #dcfce7', borderRadius: 12, padding: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#15803d', marginBottom: 6 }}>PROS</div>
          {phone.pros.map((p) => (
            <div key={p} style={{ fontSize: 12, color: '#166534', marginBottom: 3 }}>+ {p}</div>
          ))}
        </div>
        <div style={{ background: '#fef2f2', border: '1px solid #fee2e2', borderRadius: 12, padding: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#b91c1c', marginBottom: 6 }}>CONS</div>
          {phone.cons.map((c) => (
            <div key={c} style={{ fontSize: 12, color: '#991b1b', marginBottom: 3 }}>− {c}</div>
          ))}
        </div>
      </div>

      <div style={{ background: '#eff6ff', border: '1px solid #dbeafe', borderRadius: 12, padding: 12, fontSize: 12.5, color: '#1e40af' }}>
        <strong>Best for:</strong> {phone.bestFor}
      </div>

      <ReviewsSection phone={phone} />

      <div style={{ fontSize: 11, color: '#9ca3af', margin: '12px 2px' }}>
        {phone.os} · {phone.waterResistance} · {phone.weightG}g · {phone.fiveG ? '5G' : '4G'} · Released {phone.releaseYear}
      </div>
    </div>
  );

  return (
    <div className="ms-product" data-product-id={phone.id} style={{ padding: 14 }}>
      {isDesktop ? (
        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 28, alignItems: 'start' }}>
          {left}
          {right}
        </div>
      ) : (
        <>
          {left}
          <div style={{ height: 12 }} />
          {right}
        </>
      )}
    </div>
  );
}

// ── Compare ─────────────────────────────────────────────────────────────────────
function ComparePage() {
  const { compareIds } = useMobileShop();
  const phones = compareIds.map(getPhone).filter(Boolean) as Phone[];
  if (phones.length < 2) return <div style={{ padding: 30, textAlign: 'center', color: '#9ca3af' }}>Pick phones to compare.</div>;

  const rows: [string, (p: Phone) => React.ReactNode][] = [
    ['Price', (p) => price(p.price)],
    ['Rating', (p) => `${p.rating.toFixed(1)} ★ (${p.reviewCount.toLocaleString()})`],
    ['Display', (p) => p.display],
    ['Chip', (p) => p.processor],
    ['Camera', (p) => p.rearCamera],
    ['Battery', (p) => `${p.batteryMah.toLocaleString()} mAh`],
    ['Charging', (p) => p.charging],
    ['Weight', (p) => `${p.weightG}g`],
    ['Water', (p) => p.waterResistance],
  ];

  return (
    <div className="ms-compare" style={{ padding: 14, overflowX: 'auto' }}>
      <SectionTitle>Compare</SectionTitle>
      <table className="ms-compare-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr>
            <th className="ms-compare-gutter" style={{ width: 74 }} />
            {phones.map((p) => (
              <th key={p.id} data-product-id={p.id} style={{ padding: 8, textAlign: 'left', verticalAlign: 'top' }}>
                <PhoneImage phone={p} height={92} />
                <div style={{ fontWeight: 700, marginTop: 6 }}>{p.name}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, get]) => (
            <tr key={label} style={{ borderTop: '1px solid #eef0f3' }}>
              <td style={{ padding: 8, fontWeight: 700, color: '#6b7280' }}>{label}</td>
              {phones.map((p) => (
                <td key={p.id} style={{ padding: 8, color: '#1f2937' }}>{get(p)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── FAQ ──────────────────────────────────────────────────────────────────────────
const FAQ: { topic: string; q: string; a: string }[] = [
  { topic: 'shipping', q: 'How fast is shipping?', a: 'Free 2-day shipping on orders over $50, shipped from US warehouses. Orders placed before 2pm dispatch same day.' },
  { topic: 'returns', q: 'What is the return policy?', a: '30-day free returns. The item must be in original condition with all accessories included.' },
  { topic: 'warranty', q: 'Is there a warranty?', a: 'Every phone includes a 1-year manufacturer warranty. Add the 2-year protection plan for $79 to cover accidental damage.' },
  { topic: 'payment', q: 'What payment options are there?', a: 'Credit and debit cards, PayPal, and 0% APR financing over 12 or 24 months on orders above $500.' },
  { topic: 'trade-in', q: 'Can I trade in my old phone?', a: 'Yes — trade in your old phone for up to $600 of instant credit toward a new one.' },
  { topic: 'price-match', q: 'Do you price match?', a: 'We price-match any authorized retailer within 14 days of purchase.' },
  { topic: 'activation', q: 'Will it work with my carrier?', a: 'All phones are unlocked and work with every major carrier. A free SIM is included.' },
];

function FaqPage() {
  const { faqTopic } = useMobileShop();

  useEffect(() => {
    if (!faqTopic) return;
    const el = document.getElementById(`faq-${faqTopic}`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.style.boxShadow = `0 0 0 2px ${BRAND_COLOR}`;
    el.style.background = '#fffbeb';
    const t = setTimeout(() => {
      el.style.boxShadow = '';
      el.style.background = 'white';
    }, 1800);
    return () => clearTimeout(t);
  }, [faqTopic]);

  return (
    <div className="ms-faq" style={{ padding: 14 }}>
      <SectionTitle>Help &amp; FAQ</SectionTitle>
      {FAQ.map((f) => (
        <div
          key={f.topic}
          className="ms-faq-item"
          data-topic={f.topic}
          id={`faq-${f.topic}`}
          style={{ background: 'white', border: '1px solid #eef0f3', borderRadius: 12, padding: 14, marginBottom: 10, transition: 'background .3s, box-shadow .3s' }}
        >
          <div style={{ fontWeight: 700, fontSize: 13.5, color: '#111827', marginBottom: 5 }}>{f.q}</div>
          <div style={{ fontSize: 13, color: '#4b5563', lineHeight: 1.5 }}>{f.a}</div>
        </div>
      ))}
    </div>
  );
}

// ── App shell (chrome + view switch) ──────────────────────────────────────────
const NAV_ITEMS = [
  { key: 'home', label: 'Home', icon: '🏠' },
  { key: 'search', label: 'Search', icon: '🔍' },
  { key: 'faq', label: 'Help', icon: '💬' },
] as const;

export function MobileShopApp({ presence }: { presence?: ReactNode }) {
  const { view, cart, wishlist, goHome, showSearch, openFaq } = useMobileShop();
  const isDesktop = useIsDesktop();

  const navTo = (key: string) => (key === 'home' ? goHome() : key === 'search' ? showSearch() : openFaq());
  const narrow = view === 'product' || view === 'faq' || view === 'compare';

  return (
    <div className="ms-app" style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f3f4f6' }}>
      {/* Top bar — also the home of the one voice affordance (`presence`). */}
      <header
        className="ms-topbar"
        style={{
          flex: '0 0 auto',
          background: 'white',
          borderBottom: '1px solid #e5e7eb',
          padding: isDesktop ? '14px 24px' : '12px 16px',
        }}
      >
        <div className="ms-topbar-inner" style={{ width: '100%', maxWidth: 1180, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <button className="ms-brand" onClick={goHome} style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer', minWidth: 0 }}>
            <span className="ms-brand-mark" style={{ width: 28, height: 28, borderRadius: 7, background: BRAND_COLOR, color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 15, flex: 'none' }}>V</span>
            <span className="ms-brand-name" style={{ fontWeight: 800, fontSize: 16, color: '#111827', whiteSpace: 'nowrap' }}>Voqal Mobile</span>
          </button>

          {/* Desktop nav lives in the header */}
          {isDesktop && (
            <nav style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {NAV_ITEMS.map((t) => (
                <button
                  key={t.key}
                  className={`ms-nav-${t.key}`}
                  onClick={() => navTo(t.key)}
                  style={{
                    background: view === t.key ? '#eef2ff' : 'none',
                    border: 'none',
                    cursor: 'pointer',
                    borderRadius: 8,
                    padding: '8px 14px',
                    color: view === t.key ? BRAND_DARK : '#4b5563',
                    fontWeight: 600,
                    fontSize: 14,
                  }}
                >
                  {t.label}
                </button>
              ))}
            </nav>
          )}

          <div className="ms-topbar-actions" style={{ display: 'flex', alignItems: 'center', gap: 16, flex: 'none' }}>
            <div className="ms-wishlist" data-wishlist-count={wishlist.length} style={{ position: 'relative', fontSize: 20, color: '#e11d48' }}>
              ♥
              {wishlist.length > 0 && <CountBadge n={wishlist.length} color="#e11d48" />}
            </div>
            <div className="ms-cart" data-cart-count={cart.length} style={{ position: 'relative', fontSize: 22 }}>
              🛒
              {cart.length > 0 && <CountBadge n={cart.length} color={BRAND_COLOR} />}
            </div>
            {presence && <div className="ms-topbar-presence">{presence}</div>}
          </div>
        </div>
      </header>

      {/* Body — single scroll container; pages center via Container */}
      <main className="ms-body" style={{ flex: 1, overflowY: 'auto', minHeight: 0, padding: isDesktop ? '8px 16px 24px' : 0 }}>
        <Container narrow={narrow}>
          {view === 'home' && <HomePage />}
          {view === 'search' && <SearchPage />}
          {view === 'product' && <ProductPage isDesktop={isDesktop} />}
          {view === 'compare' && <ComparePage />}
          {view === 'faq' && <FaqPage />}
        </Container>
      </main>

      {/* Bottom nav — mobile only */}
      {!isDesktop && (
        <nav
          className="ms-bottomnav"
          style={{
            flex: '0 0 auto',
            background: 'white',
            borderTop: '1px solid #e5e7eb',
            display: 'flex',
            justifyContent: 'space-around',
            padding: '8px 0 10px',
          }}
        >
          {NAV_ITEMS.map((t) => (
            <button
              key={t.key}
              className={`ms-nav-${t.key}`}
              onClick={() => navTo(t.key)}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 2,
                color: view === t.key ? BRAND_COLOR : '#9ca3af',
                fontWeight: 600,
                fontSize: 10.5,
              }}
            >
              <span style={{ fontSize: 18 }}>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>
      )}

      <style>{MOBILE_STYLES}</style>
    </div>
  );
}

/**
 * Phone pass (≤640px). The store is mobile-first already, so this is corrective
 * rather than a redesign: tighten the chrome so the top bar (logo + wishlist +
 * cart + the voice control) fits 390px, hold the product grid at two real
 * columns, unstack nothing on desktop, and let the one genuinely wide thing —
 * the spec-compare table — scroll inside its own box instead of pushing the page
 * sideways. Inline styles win over stylesheets, hence the `!important`s.
 */
const MOBILE_STYLES = `
/* The voice control is chrome, not a widget — a hairline separates it from the
   shopper's own controls (wishlist, cart). */
.ms-topbar-presence {
  display: flex;
  align-items: center;
  padding-left: 14px;
  border-left: 1px solid #e5e7eb;
}

@media (max-width: 640px) {
  .ms-topbar { padding: 10px 12px !important; }
  .ms-topbar-inner { gap: 8px; }
  .ms-topbar-actions { gap: 12px !important; }
  .ms-brand { gap: 7px !important; }
  .ms-brand-name { font-size: 14.5px !important; }
  .ms-topbar-presence { padding-left: 10px; }

  .ms-home, .ms-search, .ms-product, .ms-compare, .ms-faq { padding: 12px !important; }

  /* The demo ships no CSS reset, so these "width: 100%" + padding boxes are
     content-box and render 26px wider than their track/column — enough to push
     the whole page sideways on a 390px screen. Correct them where it bites. */
  .ms-product-card, .ms-add-to-cart, .ms-wishlist-btn { box-sizing: border-box; }
  /* Belt and braces: every intentional sideways scroll (featured rail, filter
     rail, compare table) lives in its own container, so the page itself never
     needs one. */
  .ms-body { overflow-x: hidden; }

  .ms-hero { padding: 20px 16px !important; }
  .ms-hero-title { font-size: 20px !important; }

  /* auto-fill would drop to a single 366px column on the narrowest phones —
     pin two, and let the card contents shrink instead. */
  .ms-product-grid { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 10px !important; }
  .ms-featured-card { flex: 0 0 168px !important; }

  /* Nothing under 11px on a phone. */
  .ms-spec-chip, .ms-rating-count, .ms-hist-pct, .ms-bottomnav button { font-size: 11px !important; }

  .ms-proscons { grid-template-columns: 1fr !important; }

  /* Never crush the comparison into unreadable columns: give it a real width
     and let .ms-compare (overflow-x: auto) scroll it. */
  .ms-compare-table { min-width: 540px; }
  .ms-compare-gutter { width: 62px !important; }
}
`;

function CountBadge({ n, color }: { n: number; color: string }) {
  return (
    <span
      style={{
        position: 'absolute',
        top: -6,
        right: -8,
        background: color,
        color: 'white',
        borderRadius: '50%',
        minWidth: 16,
        height: 16,
        fontSize: 10,
        fontWeight: 700,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 3px',
      }}
    >
      {n}
    </span>
  );
}
