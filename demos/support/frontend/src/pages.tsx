/**
 * The Voqal Mobile "Orders & Returns" app UI.
 *
 * Plain state-driven navigation (see store.tsx), so the live voice call is never
 * interrupted. Orders, line items, and the return form carry stable `data-*`
 * hooks (`data-order-id`, `data-item-id`) and semantic class names so the
 * Returns Assistant's screen-driving stays robust.
 *
 * The return form captures a photo of the product, downscales it to fit a single
 * WebRTC data-channel message, shows it to the shopper, and sends it to the
 * agent (`photo_upload`) which verifies the product + box before approving.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { getItem, getOrder, ORDERS, orderTotal, type Item } from './catalog';
import { useOrders, type RefundMethod } from './store';

const BRAND = '#4f46e5';
const BRAND_DARK = '#312e81';
const OK = '#16a34a';
const BAD = '#dc2626';

const REFUND_LABEL: Record<RefundMethod, string> = {
  original_payment: 'Original payment method',
  store_credit: 'Store credit',
};

// ── Responsive helpers ────────────────────────────────────────────────────────
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

function Container({ children }: { children: React.ReactNode }) {
  return <div style={{ width: '100%', maxWidth: 820, margin: '0 auto' }}>{children}</div>;
}

// ── Photo capture: downscale to a single small JPEG data URL ───────────────────
function loadImageFromFile(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('image load failed'));
    };
    img.src = url;
  });
}

function drawScaled(img: HTMLImageElement, maxDim: number): HTMLCanvasElement {
  const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
  const w = Math.max(1, Math.round(img.width * scale));
  const h = Math.max(1, Math.round(img.height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  canvas.getContext('2d')?.drawImage(img, 0, 0, w, h);
  return canvas;
}

// Keep the data URL well under the ~64KB WebRTC data-channel message limit.
async function downscaleToDataUrl(file: File): Promise<string> {
  const img = await loadImageFromFile(file);
  let dim = 512;
  let q = 0.6;
  let url = drawScaled(img, dim).toDataURL('image/jpeg', q);
  for (let i = 0; i < 8 && url.length > 40000; i++) {
    if (q > 0.34) q -= 0.1;
    else dim = Math.round(dim * 0.82);
    url = drawScaled(img, dim).toDataURL('image/jpeg', q);
  }
  return url;
}

// ── Faux product thumbnail — phones get a mini device render; accessories a
// clean accent-tinted tile with their icon. ──────────────────────────────────
function ItemThumb({ item, size = 52 }: { item: Item; size?: number }) {
  if (item.kind === 'phone') {
    const dW = Math.round(size * 0.42);
    const dH = Math.round(size * 0.78);
    return (
      <div
        className="os-item-thumb"
        data-kind="phone"
        style={{
          width: size,
          height: size,
          flex: `0 0 ${size}px`,
          borderRadius: 12,
          background: 'linear-gradient(160deg, #ffffff 0%, #eef2f7 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px solid #eef0f3',
        }}
      >
        <div
          style={{
            width: dW,
            height: dH,
            borderRadius: Math.round(dW * 0.24),
            background: `linear-gradient(155deg, ${item.accent} 0%, #11131a 140%)`,
            padding: 2,
            boxShadow: '0 3px 8px rgba(15,23,42,.2)',
          }}
        >
          <div
            style={{
              width: '100%',
              height: '100%',
              borderRadius: Math.round(dW * 0.18),
              background: 'linear-gradient(160deg, rgba(255,255,255,.16), rgba(0,0,0,.28))',
            }}
          />
        </div>
      </div>
    );
  }
  return (
    <div
      className="os-item-thumb"
      data-kind="accessory"
      style={{
        width: size,
        height: size,
        flex: `0 0 ${size}px`,
        borderRadius: 12,
        background: `${item.accent}14`,
        border: `1px solid ${item.accent}26`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: size * 0.44,
      }}
    >
      {item.icon}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return (
    <span
      style={{
        background: '#ecfdf5',
        color: '#047857',
        borderRadius: 20,
        padding: '3px 10px',
        fontSize: 11,
        fontWeight: 700,
      }}
    >
      {status}
    </span>
  );
}

// ── Orders list ───────────────────────────────────────────────────────────────
function OrdersListPage() {
  const { openOrder } = useOrders();
  const orders = ORDERS;
  return (
    <div className="os-orders" style={{ padding: 14 }}>
      <h1 style={{ fontSize: 19, fontWeight: 800, color: '#111827', margin: '4px 2px 14px' }}>
        Your orders
      </h1>
      {orders.map((order) => (
        <button
          key={order.id}
          className="os-order-card"
          data-order-id={order.id}
          onClick={() => openOrder(order.id)}
          style={{
            display: 'block',
            width: '100%',
            textAlign: 'left',
            background: 'white',
            border: '1px solid #e5e7eb',
            borderRadius: 14,
            padding: 14,
            marginBottom: 12,
            cursor: 'pointer',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: '#111827' }}>Order {order.id}</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>Placed {order.placedOn}</div>
            </div>
            <StatusPill status={order.status} />
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {order.lines.map((l) => {
              const item = getItem(l.itemId);
              return item ? <ItemThumb key={l.itemId} item={item} size={44} /> : null;
            })}
            <div style={{ marginLeft: 'auto', fontWeight: 800, color: BRAND_DARK, fontSize: 15 }}>
              ${orderTotal(order).toLocaleString()}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

// ── Order detail ──────────────────────────────────────────────────────────────
function OrderDetailPage() {
  const { orderId, highlight, startReturn } = useOrders();
  const order = orderId ? getOrder(orderId) : undefined;

  // Highlight: scroll the named line item into view and flash it.
  useEffect(() => {
    if (!highlight || !order || highlight.orderId !== order.id) return;
    const el = document.getElementById(`order-item-${highlight.itemId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.style.background = '#fef9c3';
    el.style.boxShadow = `0 0 0 2px ${BRAND}`;
    const t = setTimeout(() => {
      el.style.background = '';
      el.style.boxShadow = '';
    }, 1800);
    return () => clearTimeout(t);
  }, [highlight, order]);

  useEffect(() => {
    document.querySelector('.os-body')?.scrollTo({ top: 0 });
  }, [orderId]);

  if (!order) return <div style={{ padding: 30, textAlign: 'center', color: '#9ca3af' }}>Select an order.</div>;

  return (
    <div className="os-order" data-order-id={order.id} style={{ padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <h1 style={{ fontSize: 18, fontWeight: 800, color: '#111827' }}>Order {order.id}</h1>
        <StatusPill status={order.status} />
      </div>
      <div style={{ fontSize: 12.5, color: '#6b7280', marginBottom: 14 }}>
        Placed {order.placedOn} · Delivered {order.deliveredOn}
      </div>

      {order.lines.map((l) => {
        const item = getItem(l.itemId);
        if (!item) return null;
        return (
          <div
            key={item.id}
            className="os-order-item"
            data-item-id={item.id}
            id={`order-item-${item.id}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              background: 'white',
              border: '1px solid #eef0f3',
              borderRadius: 12,
              padding: 12,
              marginBottom: 10,
              transition: 'background .3s, box-shadow .3s',
            }}
          >
            <ItemThumb item={item} />
            {/* `min-width` is CSS-side (not inline) so the phone media query can
                raise it and push the Return button onto its own line. */}
            <div className="os-order-item-text" style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 13.5, color: '#111827' }}>{item.name}</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                {item.brand} · ${item.price.toLocaleString()}
              </div>
            </div>
            <button
              className="os-return-btn"
              data-item-id={item.id}
              onClick={() => startReturn(order.id, item.id, '')}
              style={{
                flex: '0 0 auto',
                background: '#eef2ff',
                color: BRAND_DARK,
                border: '1px solid #e0e7ff',
                borderRadius: 10,
                padding: '8px 12px',
                fontWeight: 700,
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              Return item
            </button>
          </div>
        );
      })}

      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 4px', fontWeight: 800, color: '#111827' }}>
        <span>Order total</span>
        <span>${orderTotal(order).toLocaleString()}</span>
      </div>
    </div>
  );
}

// ── Diagnostics checklist ─────────────────────────────────────────────────────
function DiagnosticsPage() {
  const { diag, openOrder } = useOrders();
  const item = diag ? getItem(diag.itemId) : undefined;

  useEffect(() => {
    document.querySelector('.os-body')?.scrollTo({ top: 0 });
  }, [diag?.itemId]);

  // Keep the step being discussed in view.
  useEffect(() => {
    if (!diag || diag.complete) return;
    document.getElementById(`diag-step-${diag.currentIndex}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [diag?.currentIndex, diag?.complete]);

  if (!diag || !item) return <div style={{ padding: 30, textAlign: 'center', color: '#9ca3af' }}>No diagnostics in progress.</div>;

  return (
    <div className="os-diagnostics" data-item-id={item.id} style={{ padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
        <ItemThumb item={item} size={44} />
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 800, color: '#111827' }}>Troubleshooting</h1>
          <div style={{ fontSize: 12.5, color: '#6b7280' }}>{item.name}</div>
        </div>
      </div>
      <div style={{ fontSize: 12.5, color: '#6b7280', margin: '4px 2px 14px' }}>
        Let's check a few things before starting a return.
      </div>

      {diag.steps.map((st, i) => {
        const isCurrent = !diag.complete && i === diag.currentIndex;
        const done = st.result !== 'pending';
        const icon = st.result === 'ok' ? '✓' : st.result === 'issue' ? '!' : isCurrent ? '…' : String(i + 1);
        const iconBg = st.result === 'ok' ? OK : st.result === 'issue' ? '#d97706' : isCurrent ? BRAND : '#e5e7eb';
        const iconColor = done || isCurrent ? 'white' : '#9ca3af';
        return (
          <div
            key={i}
            className={`os-diag-step${isCurrent ? ' os-diag-current' : ''}`}
            data-index={i}
            data-result={st.result}
            id={`diag-step-${i}`}
            style={{
              display: 'flex',
              gap: 12,
              alignItems: 'flex-start',
              background: isCurrent ? '#eef2ff' : 'white',
              border: `1px solid ${isCurrent ? BRAND : '#eef0f3'}`,
              borderRadius: 12,
              padding: 12,
              marginBottom: 10,
              transition: 'background .3s, border-color .3s',
              animation: isCurrent ? 'os-pulse 1.4s ease-in-out infinite' : undefined,
            }}
          >
            <span style={{ flex: '0 0 24px', width: 24, height: 24, borderRadius: '50%', background: iconBg, color: iconColor, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13 }}>
              {icon}
            </span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: done || isCurrent ? '#111827' : '#6b7280' }}>{st.label}</div>
              {st.summary && (
                <div style={{ fontSize: 12.5, color: st.result === 'issue' ? '#b45309' : '#15803d', marginTop: 3, lineHeight: 1.4 }}>
                  {st.summary}
                </div>
              )}
              {isCurrent && !st.summary && <div style={{ fontSize: 12, color: BRAND, marginTop: 3 }}>Now checking…</div>}
            </div>
          </div>
        );
      })}

      {diag.complete && diag.resolved && (
        <div className="os-diag-resolved" style={{ background: '#f0fdf4', border: '1px solid #dcfce7', borderRadius: 12, padding: 14, marginTop: 6 }}>
          <div style={{ fontWeight: 800, color: '#166534', fontSize: 14 }}>✓ Looks like it's working again!</div>
          <div style={{ fontSize: 12.5, color: '#166534', marginTop: 4 }}>No return needed — glad we sorted it out.</div>
          <button
            onClick={() => openOrder(diag.orderId)}
            style={{ marginTop: 12, background: OK, color: 'white', border: 'none', borderRadius: 10, padding: '9px 16px', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}
          >
            Back to order
          </button>
        </div>
      )}
    </div>
  );
}

// ── Return flow ───────────────────────────────────────────────────────────────
function FieldRow({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '9px 0', borderTop: '1px solid #f1f3f5' }}>
      <span style={{ fontSize: 12.5, color: '#6b7280', fontWeight: 600 }}>{label}</span>
      <span style={{ fontSize: 12.5, color: muted ? '#9ca3af' : '#111827', fontWeight: 600, textAlign: 'right', maxWidth: '62%' }}>
        {value}
      </span>
    </div>
  );
}

function PhotoSection({ item }: { item: Item }) {
  const { ret, setPhoto, agentSend } = useOrders();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);

  if (!ret) return null;
  const { photoDataUrl, photoPending, photoCheck, photoRequested } = ret;

  const onPick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-picking the same file
    if (!file) return;
    setBusy(true);
    try {
      const dataUrl = await downscaleToDataUrl(file);
      setPhoto(dataUrl);
      agentSend?.('photo_upload', { item_id: ret.itemId, image: dataUrl });
    } catch {
      /* ignore — shopper can retry */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: BRAND, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 8 }}>
        Photo of the product &amp; box
      </div>

      <input
        ref={inputRef}
        className="os-photo-input"
        type="file"
        accept="image/*"
        capture="environment"
        onChange={onPick}
        style={{ display: 'none' }}
      />

      {photoDataUrl && (
        <img
          src={photoDataUrl}
          alt="Return product"
          className="os-photo-preview"
          style={{ width: '100%', maxHeight: 240, objectFit: 'cover', borderRadius: 12, border: '1px solid #e5e7eb', marginBottom: 10 }}
        />
      )}

      {/* Verification status */}
      {photoPending && (
        <div className="os-photo-check" data-passed="pending" style={{ ...checkBox('#eff6ff', '#1e40af'), marginBottom: 10 }}>
          ⏳ Checking the photo with the Returns Assistant…
        </div>
      )}
      {photoCheck && (
        <div
          className="os-photo-check"
          data-passed={String(photoCheck.passed)}
          style={{ ...checkBox(photoCheck.passed ? '#f0fdf4' : '#fef2f2', photoCheck.passed ? '#166534' : '#991b1b'), marginBottom: 10 }}
        >
          <div style={{ fontWeight: 700 }}>
            {photoCheck.passed ? '✓ Photo verified' : '✕ Photo needs another try'}
          </div>
          <div style={{ fontSize: 12, marginTop: 3, display: 'flex', gap: 12 }}>
            <span>{photoCheck.matches ? '✓ Product matches' : '✕ Product unclear'}</span>
            <span>{photoCheck.boxPresent ? '✓ Box present' : '✕ Box missing'}</span>
          </div>
          {photoCheck.note && <div style={{ fontSize: 12, marginTop: 4, opacity: 0.85 }}>{photoCheck.note}</div>}
        </div>
      )}

      <button
        className="os-photo-btn"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        style={{
          width: '100%',
          background: photoDataUrl ? 'white' : BRAND,
          color: photoDataUrl ? BRAND_DARK : 'white',
          border: photoDataUrl ? `1.5px solid ${BRAND}` : 'none',
          borderRadius: 12,
          padding: '12px',
          fontWeight: 700,
          fontSize: 13.5,
          cursor: busy ? 'default' : 'pointer',
          animation: photoRequested && !photoDataUrl ? 'os-pulse 1.2s ease-in-out infinite' : undefined,
        }}
      >
        {busy ? 'Processing…' : photoDataUrl ? `📷 Retake photo of the ${item.kind}` : '📷 Take / upload a photo'}
      </button>
    </div>
  );
}

function checkBox(bg: string, color: string): React.CSSProperties {
  return { background: bg, color, border: `1px solid ${color}22`, borderRadius: 12, padding: '10px 12px', fontSize: 13 };
}

function ReturnPage() {
  const { ret, orderId, agentSend, submitReturn, openOrder } = useOrders();
  const item = ret ? getItem(ret.itemId) : undefined;

  useEffect(() => {
    document.querySelector('.os-body')?.scrollTo({ top: 0 });
  }, [ret?.itemId]);

  if (!ret || !item) return <div style={{ padding: 30, textAlign: 'center', color: '#9ca3af' }}>No return in progress.</div>;

  const { form, photoCheck, submitted, rma } = ret;
  const canSubmit = !!form && !!photoCheck?.passed && !submitted;

  const onSubmit = () => {
    const id = submitReturn();
    agentSend?.('return_submitted', { order_id: ret.orderId, item_id: ret.itemId, rma: id });
  };

  if (submitted) {
    return (
      <div className="os-return-success" style={{ padding: 22, textAlign: 'center' }}>
        <div style={{ fontSize: 46 }}>✅</div>
        <h1 style={{ fontSize: 20, fontWeight: 800, color: '#111827', margin: '8px 0 4px' }}>Return submitted</h1>
        <div style={{ fontSize: 13.5, color: '#4b5563', lineHeight: 1.5, maxWidth: 380, margin: '0 auto' }}>
          We've created return <strong>{rma}</strong> for your {item.name}. A prepaid shipping label is on its way to
          your email — your refund is issued once the carrier scans the package.
        </div>
        <button
          onClick={() => orderId && openOrder(orderId)}
          style={{ marginTop: 18, background: BRAND, color: 'white', border: 'none', borderRadius: 10, padding: '10px 18px', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}
        >
          Back to order
        </button>
      </div>
    );
  }

  return (
    <div className="os-return" data-item-id={item.id} style={{ padding: 14 }}>
      <h1 style={{ fontSize: 18, fontWeight: 800, color: '#111827', marginBottom: 12 }}>Return item</h1>

      {/* Item being returned */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: 'white', border: '1px solid #eef0f3', borderRadius: 12, padding: 12, marginBottom: 14 }}>
        <ItemThumb item={item} />
        <div>
          <div style={{ fontWeight: 700, fontSize: 13.5, color: '#111827' }}>{item.name}</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
            {item.brand} · ${item.price.toLocaleString()} · Order {ret.orderId}
          </div>
        </div>
      </div>

      {/* Return form — filled by the agent */}
      <div className="os-return-form" style={{ background: 'white', border: '1px solid #eef0f3', borderRadius: 12, padding: '4px 14px 12px' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: BRAND, textTransform: 'uppercase', letterSpacing: 0.6, padding: '12px 0 2px' }}>
          Return details
        </div>
        {form ? (
          <>
            <FieldRow label="Reason" value={form.reason || ret.reason || '—'} />
            <FieldRow label="Condition" value={form.condition} />
            <FieldRow label="Refund to" value={REFUND_LABEL[form.refundMethod]} />
            {form.notes && <FieldRow label="Notes" value={form.notes} />}
          </>
        ) : (
          <FieldRow
            label="Reason"
            value={ret.reason ? ret.reason : 'The Returns Assistant will fill this in…'}
            muted={!ret.reason}
          />
        )}
      </div>

      {/* Photo capture + verification */}
      <PhotoSection item={item} />

      {/* Submit */}
      <button
        className="os-submit-return"
        data-ready={String(canSubmit)}
        onClick={onSubmit}
        disabled={!canSubmit}
        style={{
          width: '100%',
          marginTop: 16,
          background: canSubmit ? OK : '#e5e7eb',
          color: canSubmit ? 'white' : '#9ca3af',
          border: 'none',
          borderRadius: 12,
          padding: '13px',
          fontWeight: 800,
          fontSize: 14,
          cursor: canSubmit ? 'pointer' : 'not-allowed',
        }}
      >
        Confirm &amp; submit return
      </button>
      {!canSubmit && (
        <div style={{ fontSize: 11.5, color: '#9ca3af', textAlign: 'center', marginTop: 8 }}>
          {!photoCheck?.passed ? 'Add a verified photo of the product and its box to continue.' : 'Review the details above, then submit.'}
        </div>
      )}
    </div>
  );
}

// ── App shell ─────────────────────────────────────────────────────────────────
export function OrdersApp({ presence }: { presence?: ReactNode }) {
  const { view, openOrders, orderId, openOrder } = useOrders();
  // Still worth a JS branch: only the shell's own padding differs, and the value
  // is consumed as an inline style. Everything else responsive lives in the
  // `@media` block at the bottom of this file.
  const isDesktop = useIsDesktop();

  const showBack = view !== 'orders';
  const onBack = () => {
    if ((view === 'return' || view === 'diagnostics') && orderId) openOrder(orderId);
    else openOrders();
  };

  return (
    <div className="os-app" style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f3f4f6' }}>
      <header
        className="os-topbar"
        style={{ flex: '0 0 auto', background: 'white', borderBottom: '1px solid #e5e7eb', padding: isDesktop ? '14px 24px' : '12px 16px' }}
      >
        <div className="os-topbar-row" style={{ width: '100%', maxWidth: 820, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          {showBack && (
            <button
              className="os-back"
              onClick={onBack}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: '#4b5563', lineHeight: 1 }}
              title="Back"
            >
              ‹
            </button>
          )}
          <button className="os-brand" onClick={openOrders} style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer', minWidth: 0 }}>
            <span style={{ flex: '0 0 auto', width: 28, height: 28, borderRadius: 7, background: BRAND, color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 15 }}>V</span>
            <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1, alignItems: 'flex-start', minWidth: 0 }}>
              <span className="os-brand-name" style={{ fontWeight: 800, fontSize: 15, color: '#111827' }}>Voqal Mobile</span>
              <span className="os-brand-sub" style={{ fontSize: 11, color: '#6b7280' }}>Orders &amp; Returns</span>
            </span>
          </button>
          {/* The voice layer's one control, mounted as part of the store's chrome. */}
          {presence && <div className="os-topbar-presence">{presence}</div>}
        </div>
      </header>

      <main className="os-body" style={{ flex: 1, overflowY: 'auto', minHeight: 0, padding: isDesktop ? '8px 16px 28px' : 0 }}>
        <Container>
          {view === 'orders' && <OrdersListPage />}
          {view === 'order' && <OrderDetailPage />}
          {view === 'diagnostics' && <DiagnosticsPage />}
          {view === 'return' && <ReturnPage />}
        </Container>
      </main>

      <style>{`
        @keyframes os-pulse { 0%,100% { box-shadow: 0 0 0 0 ${BRAND}66; } 50% { box-shadow: 0 0 0 8px ${BRAND}00; } }

        /* The top bar carries the brand *and* the presence control. The control
           never shrinks; the wordmark truncates first, so the row can't push the
           page into a horizontal scroll on a narrow phone. */
        .os-topbar-presence { flex: 0 0 auto; margin-left: auto; padding-left: 8px; }
        .os-brand { min-width: 0; overflow: hidden; }
        .os-order-item-text { min-width: 0; }
        .os-brand-name, .os-brand-sub {
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 100%;
        }

        /* ── Phone (390×844 target) ───────────────────────────────────────── */
        @media (max-width: 640px) {
          .os-topbar-row { gap: 8px; }
          .os-brand-sub { display: none; }
          .os-back { padding: 4px 6px; margin-left: -6px; font-size: 22px; }

          .os-orders, .os-order, .os-diagnostics, .os-return { padding: 12px !important; }
          .os-return-success { padding: 18px 14px !important; }

          /* Order detail: keep the product name readable — the "Return item"
             button drops to its own line instead of squeezing the title. */
          .os-order-item { flex-wrap: wrap; }
          .os-order-item-text { min-width: 60%; }
          .os-order-item .os-return-btn { margin-left: auto; }

          /* Photo preview shouldn't eat the whole fold on a phone. */
          .os-photo-preview { max-height: 200px !important; }
        }
      `}</style>
    </div>
  );
}
