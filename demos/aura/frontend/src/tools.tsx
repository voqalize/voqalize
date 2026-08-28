/**
 * Interactive tool surfaces for the Aura L1-support demo — all usable WITHOUT a
 * login, so the agent can do real work top-of-funnel:
 *   - CalculatorPage  : EMI / FD / eligibility (agent fills it, figures recompute live)
 *   - ApplyPage       : start + pre-fill a savings / card / loan application (lead-gen)
 *   - ComparePage     : compare cards / accounts, recommend one
 *   - LocatorPage     : nearby branches / ATMs
 *   - ChecklistPage   : "what documents do I need" checklist
 *   - SendToPhoneToast: "I've sent the steps to your phone" (mock)
 *   - TicketCard      : raised complaint / callback with a reference number
 *   - Spotlight       : general-purpose ring around any [data-aura-spotlight] element
 *
 * Each is driven by the shared store (so the human or the agent can drive), which
 * the voice widget feeds via `ui_command` and reads back via `state_sync`.
 */

import { useEffect, useState, type ReactNode } from 'react';
import { useAura } from './store';
import type { CalcKind, CardControls, Product } from './types';

const PRIMARY = '#4F46E5';
const ACCENT = '#8B5CF6';
const INK = '#1A1620';
const MUTED = '#6E6470';
const BORDER = '#E6E2F2';
const PAPER = '#FFFFFF';

const inr = (n: number): string => `₹${Math.round(n).toLocaleString('en-IN')}`;

function PageShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  const { openHelpCenter } = useAura();
  return (
    <div className="aura-page" style={{ maxWidth: 1000, margin: '0 auto', padding: '28px 24px 60px' }}>
      <button onClick={openHelpCenter} style={{ background: 'none', border: 'none', color: PRIMARY, cursor: 'pointer', fontSize: 13, padding: 0, marginBottom: 8 }}>
        ← Help &amp; Support
      </button>
      <h1 style={{ fontSize: 27, color: INK, fontWeight: 800, margin: '2px 0 2px' }}>{title}</h1>
      {subtitle && <div style={{ fontSize: 15, color: PRIMARY, fontWeight: 600, marginBottom: 18 }}>{subtitle}</div>}
      {children}
    </div>
  );
}

// ── Calculator ────────────────────────────────────────────────────────────────
const CALC_CONFIG: Record<
  CalcKind,
  { title: string; subtitle: string; inputs: [string, string][]; results: [string, string][] }
> = {
  emi: {
    title: 'EMI Calculator',
    subtitle: 'Estimate your monthly loan EMI',
    inputs: [
      ['principal', 'Loan amount (₹)'],
      ['annual_rate', 'Interest rate (% p.a.)'],
      ['tenure_months', 'Tenure (months)'],
    ],
    results: [
      ['emi', 'Monthly EMI'],
      ['total_interest', 'Total interest'],
      ['total_payment', 'Total payable'],
    ],
  },
  fd: {
    title: 'FD Calculator',
    subtitle: 'See your deposit maturity value',
    inputs: [
      ['principal', 'Deposit amount (₹)'],
      ['annual_rate', 'Interest rate (% p.a.)'],
      ['tenure_months', 'Tenure (months)'],
    ],
    results: [
      ['maturity', 'Maturity value'],
      ['interest', 'Interest earned'],
    ],
  },
  eligibility: {
    title: 'Loan Eligibility',
    subtitle: 'See how much you can borrow',
    inputs: [
      ['monthly_income', 'Monthly income (₹)'],
      ['existing_emi', 'Existing EMIs (₹)'],
      ['annual_rate', 'Interest rate (% p.a.)'],
      ['tenure_months', 'Tenure (months)'],
    ],
    results: [
      ['max_loan', 'You may be eligible for'],
      ['max_emi', 'Maximum monthly EMI'],
    ],
  },
};

export function CalculatorPage() {
  const { calc, recomputeCalc } = useAura();
  if (!calc) return null;
  const cfg = CALC_CONFIG[calc.kind];
  const [primaryKey, primaryLabel] = cfg.results[0];

  return (
    <PageShell title={cfg.title} subtitle={cfg.subtitle}>
      <div className="aura-two-col" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(280px,360px)', gap: 24, alignItems: 'start' }}>
        <div style={{ background: PAPER, border: `1px solid ${BORDER}`, borderRadius: 14, padding: 20 }}>
          {cfg.inputs.map(([key, label]) => (
            <label key={key} style={{ display: 'block', marginBottom: 16 }}>
              <span style={{ display: 'block', fontSize: 13, color: MUTED, fontWeight: 600, marginBottom: 6 }}>{label}</span>
              <input
                type="number"
                value={calc.inputs[key] ?? ''}
                onChange={(e) => recomputeCalc({ ...calc.inputs, [key]: Number(e.target.value) || 0 })}
                style={{ width: '100%', fontSize: 16, fontWeight: 600, color: INK, padding: '10px 12px', border: `1.5px solid ${BORDER}`, borderRadius: 10, outline: 'none' }}
              />
            </label>
          ))}
        </div>

        <div data-aura-spotlight="calc_result" style={{ background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`, color: '#fff', borderRadius: 16, padding: 22, boxShadow: '0 10px 30px rgba(79,70,229,.22)' }}>
          <div style={{ fontSize: 13, opacity: 0.9, fontWeight: 600 }}>{primaryLabel}</div>
          <div style={{ fontSize: 38, fontWeight: 800, margin: '4px 0 14px', lineHeight: 1.1 }}>{inr(calc.result[primaryKey] ?? 0)}</div>
          {cfg.results.slice(1).map(([key, label]) => (
            <div key={key} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderTop: '1px solid rgba(255,255,255,.22)', fontSize: 14 }}>
              <span style={{ opacity: 0.9 }}>{label}</span>
              <span style={{ fontWeight: 700 }}>{inr(calc.result[key] ?? 0)}</span>
            </div>
          ))}
          <div style={{ fontSize: 11, opacity: 0.8, marginTop: 12 }}>Indicative · no login needed</div>
        </div>
      </div>
    </PageShell>
  );
}

// ── Application (lead capture) ──────────────────────────────────────────────────
const PRODUCT_TITLE: Record<Product, { title: string; subtitle: string }> = {
  savings: { title: 'Open a Savings Account', subtitle: 'Start online with Video KYC — no login needed' },
  credit_card: { title: 'Apply for a Credit Card', subtitle: 'Quick online application — no login needed' },
  loan: { title: 'Apply for a Loan', subtitle: 'Quick online application — no login needed' },
};

export function ApplyPage() {
  const { apply, prefillField, submitApplication } = useAura();
  if (!apply) return null;
  const meta = PRODUCT_TITLE[apply.product];

  if (apply.submitted) {
    return (
      <PageShell title={meta.title} subtitle={meta.subtitle}>
        <div style={{ background: '#F0FAF2', border: '1px solid #BFE6C8', borderRadius: 14, padding: 24, maxWidth: 520 }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: '#1B7A38' }}>✓ Application started</div>
          <p style={{ fontSize: 14, color: '#2E5A3A', lineHeight: 1.6 }}>
            We’ve captured your details. An Aura representative will reach out to complete your{' '}
            {apply.product === 'savings' ? 'Video KYC' : 'application'}. No login was needed to begin.
          </p>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell title={meta.title} subtitle={meta.subtitle}>
      <div style={{ background: PAPER, border: `1px solid ${BORDER}`, borderRadius: 14, padding: 20, maxWidth: 560 }}>
        {apply.fields.map((f) => (
          <label key={f.id} data-aura-spotlight={f.id} style={{ display: 'block', marginBottom: 14, borderRadius: 10 }}>
            <span style={{ display: 'block', fontSize: 13, color: MUTED, fontWeight: 600, marginBottom: 6 }}>{f.label}</span>
            <input
              type={f.type}
              value={f.value}
              onChange={(e) => prefillField(f.id, e.target.value)}
              style={{ width: '100%', fontSize: 15, color: INK, padding: '10px 12px', border: `1.5px solid ${f.value ? ACCENT : BORDER}`, borderRadius: 10, outline: 'none', transition: 'border-color .2s' }}
            />
          </label>
        ))}
        <button
          onClick={submitApplication}
          style={{ marginTop: 6, background: PRIMARY, color: '#fff', border: 'none', borderRadius: 10, padding: '12px 22px', fontWeight: 800, fontSize: 15, cursor: 'pointer' }}
        >
          Submit application
        </button>
        <div style={{ fontSize: 11.5, color: MUTED, marginTop: 10 }}>No login needed to start — we’ll never ask for OTP or password here.</div>
      </div>
    </PageShell>
  );
}

// ── Compare ─────────────────────────────────────────────────────────────────────
export function ComparePage() {
  const { compare } = useAura();
  if (!compare) return null;
  return (
    <PageShell title={compare.kind === 'savings' ? 'Compare Savings Accounts' : 'Compare Credit Cards'}>
      <div style={{ overflowX: 'auto' }}>
        <div style={{ display: 'flex', gap: 14, alignItems: 'stretch', minWidth: 'min-content' }}>
          {compare.items.map((it) => {
            const rec = it.id === compare.recommend_id;
            return (
              <div
                key={it.id}
                data-aura-spotlight={rec ? 'recommend' : undefined}
                style={{
                  flex: '1 0 240px',
                  background: PAPER,
                  border: `2px solid ${rec ? ACCENT : BORDER}`,
                  borderRadius: 14,
                  padding: 18,
                  position: 'relative',
                  boxShadow: rec ? '0 10px 28px rgba(139,92,246,.16)' : 'none',
                }}
              >
                {rec && (
                  <span style={{ position: 'absolute', top: -11, left: 16, background: ACCENT, color: '#fff', fontSize: 11, fontWeight: 800, borderRadius: 20, padding: '3px 10px' }}>
                    ★ RECOMMENDED
                  </span>
                )}
                <div style={{ fontSize: 16, fontWeight: 800, color: rec ? PRIMARY : INK, marginBottom: 10, marginTop: 4 }}>{it.name}</div>
                <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {it.features.map((feat, j) => (
                    <li key={j} style={{ fontSize: 13, color: INK, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                      <span style={{ color: ACCENT, fontWeight: 800 }}>•</span>
                      {feat}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
      {compare.recommend_reason && (
        <div style={{ marginTop: 16, background: '#EEF0FE', border: `1px solid ${BORDER}`, borderRadius: 12, padding: '12px 16px', fontSize: 14, color: PRIMARY }}>
          <strong>Why this one:</strong> {compare.recommend_reason}
        </div>
      )}
      <div style={{ marginTop: 12, fontSize: 11.5, color: MUTED }}>
        Indicative comparison — confirm the latest features, fees and eligibility on aurabank.example.
      </div>
    </PageShell>
  );
}

// ── Branch / ATM locator ─────────────────────────────────────────────────────────
export function LocatorPage() {
  const { locator } = useAura();
  if (!locator) return null;
  return (
    <PageShell title="Find a Branch or ATM" subtitle={`Near ${locator.pincode}`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 640 }}>
        {locator.results.map((r, i) => (
          <div key={i} style={{ background: PAPER, border: `1px solid ${BORDER}`, borderRadius: 12, padding: 16, display: 'flex', gap: 14 }}>
            <span style={{ flex: 'none', width: 40, height: 40, borderRadius: 10, background: '#EEF0FE', color: PRIMARY, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>
              {r.kind === 'atm' ? '🏧' : '🏦'}
            </span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: INK }}>
                {r.name} <span style={{ fontSize: 11, fontWeight: 700, color: MUTED, textTransform: 'uppercase' }}>· {r.kind}</span>
              </div>
              <div style={{ fontSize: 13, color: MUTED, marginTop: 3 }}>{r.address}</div>
              <div style={{ fontSize: 12, color: MUTED, marginTop: 4, display: 'flex', gap: 14 }}>
                {r.ifsc && <span>IFSC <strong style={{ color: INK }}>{r.ifsc}</strong></span>}
                {r.hours && <span>{r.hours}</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </PageShell>
  );
}

// ── Document checklist ───────────────────────────────────────────────────────────
export function ChecklistPage() {
  const { checklist } = useAura();
  if (!checklist) return null;
  return (
    <PageShell title={checklist.title} subtitle="What you’ll need">
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 560 }}>
        {checklist.items.map((item, i) => (
          <li key={i} style={{ background: PAPER, border: `1px solid ${BORDER}`, borderRadius: 12, padding: '13px 16px', display: 'flex', gap: 12, alignItems: 'center', fontSize: 14.5, color: INK }}>
            <span style={{ flex: 'none', width: 22, height: 22, borderRadius: 6, background: '#EEF0FE', color: ACCENT, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800 }}>✓</span>
            {item}
          </li>
        ))}
      </ul>
    </PageShell>
  );
}

// ── Send-to-phone toast ──────────────────────────────────────────────────────────
export function SendToPhoneToast() {
  const { sentToPhone, closeSentToPhone } = useAura();
  useEffect(() => {
    if (!sentToPhone) return;
    const t = setTimeout(closeSentToPhone, 6000);
    return () => clearTimeout(t);
  }, [sentToPhone, closeSentToPhone]);
  if (!sentToPhone) return null;
  const masked = sentToPhone.number ? sentToPhone.number.replace(/.(?=.{4})/g, '•') : 'your registered number';
  return (
    <div className="aura-toast" style={{ position: 'fixed', left: 24, bottom: 24, zIndex: 1150, background: '#0F2417', color: '#EAFBEF', borderRadius: 12, padding: '14px 18px', boxShadow: '0 12px 30px rgba(0,0,0,.3)', maxWidth: 320, display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <span style={{ fontSize: 18 }}>{sentToPhone.channel === 'sms' ? '✉️' : '🟢'}</span>
      <div style={{ fontSize: 13.5, lineHeight: 1.5 }}>
        Sent <strong>{sentToPhone.what}</strong> to {masked} via {sentToPhone.channel === 'sms' ? 'SMS' : 'WhatsApp'}.
      </div>
      <button onClick={closeSentToPhone} style={{ background: 'none', border: 'none', color: '#EAFBEF', cursor: 'pointer', fontSize: 14 }}>✕</button>
    </div>
  );
}

// ── Ticket / callback card ───────────────────────────────────────────────────────
export function TicketCard() {
  const { ticket, closeTicket } = useAura();
  if (!ticket) return null;
  // Bottom-*left*: Aria owns the right-hand corner now (AuraDock), and this card
  // appears at exactly the moment she has just raised the request it confirms.
  return (
    <div className="aura-dock" style={{ position: 'fixed', left: 24, bottom: 110, zIndex: 1150, width: 300, background: PAPER, border: `1px solid ${BORDER}`, borderRadius: 14, boxShadow: '0 16px 40px rgba(26,22,32,.22)', overflow: 'hidden' }}>
      <div style={{ background: PRIMARY, color: '#fff', padding: '11px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 800, fontSize: 13.5 }}>Request registered</span>
        <button onClick={closeTicket} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 14 }}>✕</button>
      </div>
      <div style={{ padding: 14 }}>
        <div style={{ fontSize: 12, color: MUTED }}>Reference number</div>
        <div style={{ fontSize: 22, fontWeight: 800, color: PRIMARY, letterSpacing: 1, fontVariantNumeric: 'tabular-nums' }}>{ticket.reference}</div>
        {ticket.topic && <div style={{ fontSize: 13.5, color: INK, marginTop: 8, fontWeight: 600 }}>{ticket.topic}</div>}
        {ticket.summary && <div style={{ fontSize: 13, color: MUTED, marginTop: 4, lineHeight: 1.5 }}>{ticket.summary}</div>}
        <div style={{ fontSize: 11.5, color: MUTED, marginTop: 10 }}>Keep this reference to track your request.</div>
      </div>
    </div>
  );
}

// ── General-purpose spotlight ─────────────────────────────────────────────────────
export function Spotlight() {
  const { spotlightState } = useAura();
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (!spotlightState) {
      setRect(null);
      return;
    }
    let raf = 0;
    let stopped = false;
    let el: HTMLElement | null = null;
    try {
      el = document.querySelector(`[data-aura-spotlight="${CSS.escape(spotlightState.target)}"]`);
    } catch {
      el = null;
    }
    if (!el) {
      setRect(null);
      return;
    }
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    const measure = () => {
      if (stopped || !el) return;
      setRect(el.getBoundingClientRect());
      raf = requestAnimationFrame(measure);
    };
    measure();
    const t = setTimeout(() => {
      stopped = true;
      cancelAnimationFrame(raf);
      setRect(null);
    }, 6500);
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spotlightState?.nonce]);

  if (!rect) return null;
  const pad = 8;
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1140, pointerEvents: 'none' }}>
      <div
        className="aura-step-active"
        style={{
          position: 'fixed',
          left: rect.left - pad,
          top: rect.top - pad,
          width: rect.width + pad * 2,
          height: rect.height + pad * 2,
          border: `3px solid ${ACCENT}`,
          borderRadius: 12,
          boxShadow: '0 0 0 9999px rgba(26,22,32,.32)',
        }}
      />
      {spotlightState?.label && (
        <div style={{ position: 'fixed', left: rect.left, top: Math.max(8, rect.top - 34), background: ACCENT, color: '#fff', fontSize: 12.5, fontWeight: 700, borderRadius: 8, padding: '5px 10px', boxShadow: '0 4px 12px rgba(0,0,0,.25)' }}>
          {spotlightState.label}
        </div>
      )}
    </div>
  );
}

// ── Authenticated account access ──────────────────────────────────────────────
const inrDate = (iso: string): string => {
  if (!iso) return '';
  const d = new Date(iso + 'T00:00:00');
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

// A fake, Aura-branded secure sign-in dialog (mimics an OAuth consent). The agent
// opens it via show_auth_popup() and then carries on talking — nothing waits on
// this sheet, so the customer can authorise it now, in a minute, or never. Only on
// the authorise click does the browser tell the server, which then mints the token.
export function AuthDialog() {
  const { authPrompt, confirmAuth, cancelAuth } = useAura();
  if (!authPrompt) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1300, background: 'rgba(26,22,32,.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ width: 360, maxWidth: '100%', background: PAPER, borderRadius: 16, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.35)' }}>
        <div style={{ background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`, color: '#fff', padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, opacity: 0.9, letterSpacing: 0.3 }}>🔒 AURA SECURE SIGN-IN</div>
          <div style={{ fontSize: 17, fontWeight: 800, marginTop: 4 }}>Authorise account access</div>
        </div>
        <div style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <span style={{ flex: 'none', width: 44, height: 44, borderRadius: '50%', background: '#EEF0FE', color: PRIMARY, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 800 }}>
              {(authPrompt.name || 'A').trim().charAt(0).toUpperCase()}
            </span>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: INK }}>{authPrompt.name}</div>
              {authPrompt.masked_mobile && <div style={{ fontSize: 12.5, color: MUTED }}>Mobile {authPrompt.masked_mobile}</div>}
            </div>
          </div>
          <p style={{ fontSize: 13, color: MUTED, lineHeight: 1.55, margin: '0 0 18px' }}>
            Allow <strong style={{ color: INK }}>Aria, Aura Support</strong> to <strong style={{ color: INK }}>view</strong> your account
            balance and statement for this call. Aria can never move money, and never sees your OTP, PIN or password.
          </p>
          <button
            onClick={confirmAuth}
            style={{ width: '100%', background: PRIMARY, color: '#fff', border: 'none', borderRadius: 10, padding: '13px', fontWeight: 800, fontSize: 15, cursor: 'pointer' }}
          >
            Authorise securely
          </button>
          <button
            onClick={cancelAuth}
            style={{ width: '100%', background: 'none', color: MUTED, border: 'none', padding: '10px', fontWeight: 600, fontSize: 13.5, cursor: 'pointer', marginTop: 4 }}
          >
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}

// The account picker the agent opens via choose_account(). The customer taps ONE;
// that selection (not the LLM) is what the server records for balance/statement.
export function AccountPicker() {
  const { accountPicker, selectAccount, cancelAccount } = useAura();
  if (!accountPicker) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1300, background: 'rgba(26,22,32,.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ width: 400, maxWidth: '100%', background: PAPER, borderRadius: 16, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.35)' }}>
        <div style={{ background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`, color: '#fff', padding: '16px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, opacity: 0.9 }}>🔒 Signed in</div>
          <div style={{ fontSize: 16, fontWeight: 800, marginTop: 3 }}>Choose an account to view</div>
        </div>
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {accountPicker.accounts.map((a) => (
            <button
              key={a.account_id}
              onClick={() => selectAccount(a)}
              style={{ textAlign: 'left', background: PAPER, border: `1.5px solid ${BORDER}`, borderRadius: 12, padding: '14px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14 }}
            >
              <span style={{ flex: 'none', width: 38, height: 38, borderRadius: 10, background: '#EEF0FE', color: PRIMARY, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 17 }}>🏦</span>
              <span style={{ flex: 1 }}>
                <span style={{ display: 'block', fontSize: 15, fontWeight: 700, color: INK }}>{a.nickname || `${a.type} account`}</span>
                <span style={{ display: 'block', fontSize: 12.5, color: MUTED, marginTop: 2 }}>
                  {a.type} · {a.masked_number} · {a.branch}
                </span>
              </span>
              <span style={{ color: ACCENT, fontSize: 20, fontWeight: 800 }}>›</span>
            </button>
          ))}
          <button
            onClick={cancelAccount}
            style={{ background: 'none', color: MUTED, border: 'none', padding: '8px', fontWeight: 600, fontSize: 13.5, cursor: 'pointer', marginTop: 2 }}
          >
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}

// Small session badge so it's visually obvious the customer is authenticated.
export function SessionBadge() {
  const { authSession, selectedAccount } = useAura();
  if (!authSession) return null;
  return (
    <div className="aura-badge" style={{ position: 'fixed', top: 16, right: 24, zIndex: 1150, background: '#0F2417', color: '#EAFBEF', borderRadius: 999, padding: '7px 14px', fontSize: 12.5, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8, boxShadow: '0 6px 18px rgba(0,0,0,.22)' }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#34C759' }} />
      🔒 {authSession.name}
      {selectedAccount && <span style={{ opacity: 0.75, fontWeight: 600 }}>· {selectedAccount.masked_number}</span>}
    </div>
  );
}

// Balance screen (get_account_balance()).
export function BalancePage() {
  const { balance } = useAura();
  if (!balance) return null;
  const a = balance.account;
  return (
    <PageShell title="Account Balance" subtitle={a.nickname || `${a.type} account`}>
      <div data-aura-spotlight="balance" style={{ maxWidth: 460, background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`, color: '#fff', borderRadius: 18, padding: 26, boxShadow: '0 14px 40px rgba(79,70,229,.24)' }}>
        <div style={{ fontSize: 13, opacity: 0.9, fontWeight: 600 }}>Available balance</div>
        <div style={{ fontSize: 44, fontWeight: 800, margin: '6px 0 16px', lineHeight: 1.05 }}>{inr(balance.balance)}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5, borderTop: '1px solid rgba(255,255,255,.22)', paddingTop: 12 }}>
          <span style={{ opacity: 0.9 }}>{a.type} · {a.masked_number}</span>
          <span style={{ opacity: 0.9 }}>{a.branch}</span>
        </div>
        {balance.as_of && <div style={{ fontSize: 11.5, opacity: 0.8, marginTop: 10 }}>🔒 As of {inrDate(balance.as_of)} · secure session</div>}
      </div>
    </PageShell>
  );
}

// Statement screen (get_statement()).
export function StatementPage() {
  const { statement } = useAura();
  if (!statement) return null;
  const a = statement.account;
  const credits = statement.transactions.filter((t) => t.kind === 'credit').reduce((s, t) => s + t.amount, 0);
  const debits = statement.transactions.filter((t) => t.kind === 'debit').reduce((s, t) => s + t.amount, 0);
  return (
    <PageShell title="Account Statement" subtitle={`${a.nickname || a.type} · ${a.masked_number}`}>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ fontSize: 12.5, color: MUTED }}>
          {inrDate(statement.from_date)} — {inrDate(statement.to_date)}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 16, fontSize: 13 }}>
          <span style={{ color: '#1B7A38', fontWeight: 700 }}>+ {inr(credits)} in</span>
          <span style={{ color: PRIMARY, fontWeight: 700 }}>− {inr(debits)} out</span>
        </div>
      </div>
      <div style={{ background: PAPER, border: `1px solid ${BORDER}`, borderRadius: 14, overflow: 'hidden', maxWidth: 720 }}>
        {statement.transactions.length === 0 && (
          <div style={{ padding: 20, fontSize: 14, color: MUTED }}>No transactions in this period.</div>
        )}
        {statement.transactions.map((t, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 16px', borderTop: i ? `1px solid ${BORDER}` : 'none' }}>
            <span style={{ flex: 'none', width: 34, height: 34, borderRadius: 9, background: t.kind === 'credit' ? '#EAF7EE' : '#EEF0FE', color: t.kind === 'credit' ? '#1B7A38' : PRIMARY, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 800 }}>
              {t.kind === 'credit' ? '↓' : '↑'}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: INK, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.description}</div>
              <div style={{ fontSize: 12, color: MUTED, marginTop: 2 }}>{inrDate(t.date)}</div>
            </div>
            <div style={{ fontSize: 14.5, fontWeight: 800, color: t.kind === 'credit' ? '#1B7A38' : INK, fontVariantNumeric: 'tabular-nums' }}>
              {t.kind === 'credit' ? '+' : '−'}{inr(t.amount)}
            </div>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 11.5, color: MUTED, marginTop: 12 }}>🔒 Secure session · view only. Aria cannot move money.</div>
    </PageShell>
  );
}

// ── Credit-card controls + forex cross-sell ────────────────────────────────────

// The credit-card picker the agent opens via choose_credit_card(). The customer
// taps ONE; that selection (not the LLM) is what the server records.
export function CardPicker() {
  const { cardPicker, selectCard, cancelCard } = useAura();
  if (!cardPicker) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1300, background: 'rgba(26,22,32,.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ width: 420, maxWidth: '100%', background: PAPER, borderRadius: 16, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.35)' }}>
        <div style={{ background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`, color: '#fff', padding: '16px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, opacity: 0.9 }}>🔒 Signed in</div>
          <div style={{ fontSize: 16, fontWeight: 800, marginTop: 3 }}>Choose a card to manage</div>
        </div>
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {cardPicker.cards.map((c) => (
            <button
              key={c.card_id}
              onClick={() => selectCard(c)}
              style={{ textAlign: 'left', background: PAPER, border: `1.5px solid ${BORDER}`, borderRadius: 12, padding: '14px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14 }}
            >
              <span style={{ flex: 'none', width: 46, height: 30, borderRadius: 6, background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 15 }}>💳</span>
              <span style={{ flex: 1 }}>
                <span style={{ display: 'block', fontSize: 15, fontWeight: 700, color: INK }}>{c.product}</span>
                <span style={{ display: 'block', fontSize: 12.5, color: MUTED, marginTop: 2 }}>
                  {c.network}{c.variant ? ` ${c.variant}` : ''} · {c.masked_number}
                </span>
              </span>
              <span style={{ color: ACCENT, fontSize: 20, fontWeight: 800 }}>›</span>
            </button>
          ))}
          <button
            onClick={cancelCard}
            style={{ background: 'none', color: MUTED, border: 'none', padding: '8px', fontWeight: 600, fontSize: 13.5, cursor: 'pointer', marginTop: 2 }}
          >
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}

// A toggle switch (usage on/off) — the customer flips these themselves.
function Toggle({ on, onChange, label, sub, spot }: { on: boolean; onChange: (v: boolean) => void; label: string; sub?: string; spot?: string }) {
  return (
    <div data-aura-spotlight={spot} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', background: PAPER, border: `1px solid ${on ? ACCENT : BORDER}`, borderRadius: 12, transition: 'border-color .15s' }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14.5, fontWeight: 700, color: INK }}>{label}</div>
        {sub && <div style={{ fontSize: 12.5, color: MUTED, marginTop: 2 }}>{sub}</div>}
      </div>
      <button
        onClick={() => onChange(!on)}
        aria-pressed={on}
        aria-label={label}
        style={{ position: 'relative', width: 46, height: 27, borderRadius: 999, border: 'none', cursor: 'pointer', background: on ? ACCENT : '#CBC9DD', transition: 'background .15s', flex: 'none' }}
      >
        <span style={{ position: 'absolute', top: 3, left: on ? 22 : 3, width: 21, height: 21, borderRadius: '50%', background: '#fff', transition: 'left .15s', boxShadow: '0 1px 3px rgba(0,0,0,.25)' }} />
      </button>
    </div>
  );
}

function LimitRow({ label, value, onChange, disabled }: { label: string; value: number; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <label style={{ display: 'block', padding: '12px 16px', background: PAPER, border: `1px solid ${BORDER}`, borderRadius: 12, opacity: disabled ? 0.45 : 1 }}>
      <span style={{ display: 'block', fontSize: 12.5, color: MUTED, fontWeight: 600, marginBottom: 6 }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: MUTED, fontWeight: 700 }}>₹</span>
        <input
          type="number"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          style={{ flex: 1, fontSize: 15, fontWeight: 600, color: INK, padding: '9px 11px', border: `1.5px solid ${BORDER}`, borderRadius: 10, outline: 'none' }}
        />
      </div>
    </label>
  );
}

// The card usage & limits form (show_card_controls()). The customer adjusts the
// toggles and limits, then taps Update — Aria only opens it and points at it.
export function CardControlsPage() {
  const { cardControls, saveCardControls } = useAura();
  const [c, setC] = useState<CardControls | null>(cardControls?.controls ?? null);
  // Re-seed the local form when a different card's controls open.
  useEffect(() => {
    setC(cardControls?.controls ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cardControls?.card.card_id]);
  if (!cardControls || !c) return null;
  const info = cardControls.card;
  const set = (patch: Partial<CardControls>) => setC({ ...c, ...patch });

  return (
    <PageShell title="Card Controls & Limits" subtitle={`${info.product} · ${info.masked_number}`}>
      <div data-aura-spotlight="card" style={{ maxWidth: 340, background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`, color: '#fff', borderRadius: 16, padding: 20, boxShadow: '0 12px 32px rgba(79,70,229,.24)', marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12.5, fontWeight: 700, opacity: 0.9 }}>{info.network}{info.variant ? ` ${info.variant}` : ''}</span>
          <span style={{ fontSize: 12.5, fontWeight: 700, opacity: 0.9 }}>AURA</span>
        </div>
        <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: 1.5, margin: '18px 0 6px', fontVariantNumeric: 'tabular-nums' }}>{info.masked_number}</div>
        <div style={{ fontSize: 13, opacity: 0.9 }}>{info.product}</div>
        <div style={{ fontSize: 11.5, opacity: 0.8, marginTop: 8 }}>Credit limit {inr(cardControls.credit_limit)}</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 12, maxWidth: 760 }}>
        <Toggle spot="international" on={c.international_enabled} onChange={(v) => set({ international_enabled: v })} label="International usage" sub="Use this card abroad and on overseas sites" />
        <Toggle on={c.domestic_enabled} onChange={(v) => set({ domestic_enabled: v })} label="Domestic usage" sub="Use this card within India" />
        <Toggle on={c.contactless_enabled} onChange={(v) => set({ contactless_enabled: v })} label="Tap to pay (contactless)" sub="Wave to pay at the terminal" />
        <Toggle on={c.online_enabled} onChange={(v) => set({ online_enabled: v })} label="Online transactions" sub="E-commerce and in-app payments" />
        <LimitRow label="Domestic spend limit (per month)" value={c.domestic_limit} onChange={(v) => set({ domestic_limit: v })} disabled={!c.domestic_enabled} />
        <LimitRow label="International spend limit (per month)" value={c.international_limit} onChange={(v) => set({ international_limit: v })} disabled={!c.international_enabled} />
        <LimitRow label="ATM cash withdrawal limit" value={c.atm_cash_limit} onChange={(v) => set({ atm_cash_limit: v })} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 18 }}>
        <button
          onClick={() => saveCardControls(c)}
          style={{ background: PRIMARY, color: '#fff', border: 'none', borderRadius: 10, padding: '12px 22px', fontWeight: 800, fontSize: 15, cursor: 'pointer' }}
        >
          Update controls
        </button>
        {cardControls.saved && (
          <span style={{ fontSize: 13.5, fontWeight: 700, color: '#1B7A38' }}>✓ Controls updated</span>
        )}
      </div>
      <div style={{ fontSize: 11.5, color: MUTED, marginTop: 10 }}>🔒 Secure session · you set and save these yourself. Aria only opens the controls.</div>
    </PageShell>
  );
}

// The Aura Multi-Currency Forex Card cross-sell + one-tap lead capture
// (show_forex_card()). Shown as the travel next-step after international limits.
const FOREX_BENEFITS: [string, string][] = [
  ['Zero foreign-exchange markup', 'Load 16+ currencies and lock today’s rate — skip the ~3.5% markup on every overseas swipe.'],
  ['Complimentary airport lounge access', 'Relax before your flight at domestic and international lounges.'],
  ['24×7 emergency assistance abroad', 'Global help and emergency cash if the card is lost while travelling.'],
  ['Widely accepted, chip-and-PIN secure', 'Works at millions of merchants and ATMs worldwide.'],
];

export function ForexCardPage() {
  const { forex, submitForexLead, authSession } = useAura();
  if (!forex) return null;
  return (
    <PageShell title="Aura Multi-Currency Forex Card" subtitle="Travel-ready — zero markup, lounge access">
      <div className="aura-two-col" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(280px,360px)', gap: 24, alignItems: 'start' }}>
        <div>
          <div style={{ maxWidth: 360, background: 'linear-gradient(135deg,#16142E 0%, #3730A3 55%, #8B5CF6 100%)', color: '#fff', borderRadius: 16, padding: 22, boxShadow: '0 14px 40px rgba(79,70,229,.28)', marginBottom: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 12.5, fontWeight: 800, letterSpacing: 1, opacity: 0.95 }}>AURA · MULTI-CURRENCY</span>
              <span style={{ fontSize: 12.5, opacity: 0.9 }}>🌐</span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: 1.5, margin: '22px 0 6px', fontVariantNumeric: 'tabular-nums' }}>XXXX XXXX XXXX ••••</div>
            <div style={{ fontSize: 12.5, opacity: 0.9 }}>Forex Card · 16+ currencies</div>
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {FOREX_BENEFITS.map(([title, sub], i) => (
              <li key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <span style={{ flex: 'none', width: 24, height: 24, borderRadius: 7, background: '#EEF0FE', color: ACCENT, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13 }}>✓</span>
                <span>
                  <span style={{ display: 'block', fontSize: 14.5, fontWeight: 700, color: INK }}>{title}</span>
                  <span style={{ display: 'block', fontSize: 13, color: MUTED, marginTop: 2, lineHeight: 1.5 }}>{sub}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div data-aura-spotlight="forex_request" className="aura-sticky-rail" style={{ background: PAPER, border: `1.5px solid ${BORDER}`, borderRadius: 16, padding: 22, position: 'sticky', top: 96 }}>
          {forex.submitted ? (
            <div>
              <div style={{ fontSize: 18, fontWeight: 800, color: '#1B7A38' }}>✓ Request received</div>
              <p style={{ fontSize: 13.5, color: '#2E5A3A', lineHeight: 1.6, marginTop: 8 }}>
                We’ve captured your interest in the Aura Forex Card. A relationship manager will reach out on your registered mobile to complete it before your trip.
              </p>
              {forex.reference && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 12, color: MUTED }}>Reference</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: PRIMARY, letterSpacing: 1, fontVariantNumeric: 'tabular-nums' }}>{forex.reference}</div>
                </div>
              )}
            </div>
          ) : (
            <div>
              <div style={{ fontSize: 16, fontWeight: 800, color: INK }}>Get travel-ready</div>
              <p style={{ fontSize: 13, color: MUTED, lineHeight: 1.55, margin: '6px 0 16px' }}>
                {authSession?.name ? `${authSession.name}, we` : 'We'}’ll set up your Aura Forex Card and reach out on your registered mobile — no markup, ready before you fly.
              </p>
              <button
                onClick={submitForexLead}
                style={{ width: '100%', background: PRIMARY, color: '#fff', border: 'none', borderRadius: 10, padding: '13px', fontWeight: 800, fontSize: 15, cursor: 'pointer' }}
              >
                Request this Forex Card
              </button>
              <div style={{ fontSize: 11.5, color: MUTED, marginTop: 10 }}>Indicative offer · no OTP or password needed to register interest.</div>
            </div>
          )}
        </div>
      </div>
    </PageShell>
  );
}
