/**
 * The Auric Gold Finance gold-loan lead-qualification voice demo.
 *
 * A landing page → enquiry form → verification-call flow. The whole session
 * lifecycle — mint against the control plane, WebRTC transport, mic control,
 * bot-state — is the public SDK's {@link useVoqalSession}; this file is just the
 * marketing chrome, the form, and the call UI. The hosted `lead_qual` brain
 * (advisor "Priya") drives the browser via the standard `ui_command`
 * server-message channel (`interaction.action("call_ended", …)`), which we read
 * through `onServerMessage` to render the results screen.
 *
 * This is exactly the surface an external developer embeds: `useVoqalSession`
 * from `@voqalize/client-react`, driven by a publishable (`pk_`) key.
 *
 * The voice layer is ambient, not a console: the shared {@link AmbientPresence}
 * ring from `@voqalize/client-react` frames the whole page for the session, and
 * the live call carries only a quiet timer + status and two small controls
 * (mute, hang up). The "Start Verification Call" button on the call gate stays —
 * it is the funnel's own CTA (Auric calls you), not a chat launcher.
 */

import { useCallback, useEffect, useState } from 'react';
import { PipecatClientProvider, usePipecatClientMicControl } from '@pipecat-ai/client-react';
import { BotAudioOutput } from '@pipecat-ai/voice-ui-kit';
import { Loader2, Mic, MicOff, PhoneOff } from 'lucide-react';
import {
  AmbientPresence,
  useVoqalSession,
  type AmbientPresencePalette,
} from '@voqalize/client-react';
import { DemoGate } from '@voqalize/demo-kit';
import { config } from './config';

// Tenant + agent + pk + pipeline resolve per-environment from the shared demos
// config (src/config.ts), driven by Vite env vars.
const LEAD = config;

// ── Language config ───────────────────────────────────────────────────────────
// The demo is Indic multi-language, but the page does not map a language to a
// recognizer or a voice — it sends the caller's choice by NAME in the payload and
// the brain resolves both halves (backend/brain.py, `_LANG_BY_NAME`). One owner,
// one mapping.

const INDIAN_STATES = [
  'Andhra Pradesh','Arunachal Pradesh','Assam','Bihar','Chhattisgarh',
  'Delhi','Goa','Gujarat','Haryana','Himachal Pradesh','Jharkhand',
  'Karnataka','Kerala','Madhya Pradesh','Maharashtra','Manipur',
  'Meghalaya','Mizoram','Nagaland','Odisha','Punjab','Rajasthan',
  'Sikkim','Tamil Nadu','Telangana','Tripura','Uttar Pradesh',
  'Uttarakhand','West Bengal',
];

const STATE_LANGUAGE_MAP: Record<string, string> = {
  'Andhra Pradesh': 'Telugu', 'Telangana': 'Telugu',
  'Tamil Nadu': 'Tamil', 'Karnataka': 'Kannada',
  'Kerala': 'Malayalam', 'Maharashtra': 'Marathi', 'Goa': 'Marathi',
  'Gujarat': 'Gujarati', 'West Bengal': 'Bengali',
};

const LANGUAGES = ['Hindi','Telugu','Tamil','Kannada','Malayalam','Marathi','Gujarati','Bengali'];

function inferredLanguage(state: string): string {
  return STATE_LANGUAGE_MAP[state] ?? 'Hindi';
}

// A fictional Auric Gold Finance branch, sent as the enquiry payload's branch so
// a qualified call renders the "nearest branch" card.
const AURIC_BRANCH = {
  name: 'Auric Gold Finance — Ashok Nagar Branch',
  address: 'Plot 27, Ring Road, Ashok Nagar, Hyderabad – 500020',
};

// ── Presence palette ──────────────────────────────────────────────────────────
// Auric's reading of the shared ring. Gold (#c8960c) is the product — it is the
// brand mark, the form header, the metal being pledged — so it carries idle,
// listening and speaking. Thinking shifts to the demo's existing accent blue
// (#4a90d9, the other half of its waveform gradient): the deep navy #1a2472
// would disappear against the navy header and hero the ring runs over, while the
// blue stays legible over navy *and* over the cream #fdf8ef body, and reads as a
// different mode at a glance because it is gold's complement. Offline is the same
// hairline grey the disabled call button uses.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: '#c8960c',
  listening: '#c8960c',
  thinking: '#4a90d9',
  speaking: '#c8960c',
  offline: '#e5e7eb',
};

// ── Types ─────────────────────────────────────────────────────────────────────
type Step = 'form' | 'call-gate' | 'connecting' | 'call' | 'ended';
type BotStatus = 'connecting' | 'ready' | 'thinking' | 'speaking' | 'listening';
type MicPermission = 'idle' | 'requesting' | 'granted' | 'denied';

interface FormData {
  name: string; phone: string; state: string; city: string;
  goldWeight: string; loanAmount: string;
}
interface CallResult {
  outcome: string;
  lead: Record<string, unknown>;
  branch?: { name?: string; address?: string } | null;
}

export function GoldLoanAdvisor() {
  // ── State ──────────────────────────────────────────────────────────────────
  const [joined, setJoined]           = useState(false);
  const [step, setStep]               = useState<Step>('form');
  const [formErrors, setFormErrors]   = useState<Partial<FormData>>({});
  const [formData, setFormData]       = useState<FormData>({
    name: '', phone: '', state: '', city: '', goldWeight: '', loanAmount: '',
  });
  const [callError, setCallError]     = useState('');
  const [callResult, setCallResult]   = useState<CallResult | null>(null);
  const [micPermission, setMicPermission] = useState<MicPermission>('idle');
  const [callDuration, setCallDuration]   = useState(0);
  const [language, setLanguage]           = useState<string>('auto');

  // ── Session payload (recomputed each render; the hook reads the latest at ──
  //    connect time) ──────────────────────────────────────────────────────────
  const callLanguage = language === 'auto' ? inferredLanguage(formData.state) : language;

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type`/`action` directly.
  const session = useVoqalSession({
    apiBase: LEAD.apiBase,
    tenantSlug: LEAD.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the call-gate error state.
    publishableKey: LEAD.publishableKey ?? '',
    agentId: LEAD.agentId,
    // No pipeline override. The caller's language selection rides the payload
    // below and the brain applies it with one configure_language call at session
    // start — the brain is the only thing that sees this caller, and one call
    // keeps the recognizer and the TTS voice from drifting apart.
    payload: {
      name: formData.name,
      phone: formData.phone,
      state: formData.state,
      city: formData.city,
      gold_weight: formData.goldWeight || undefined,
      loan_amount: formData.loanAmount || undefined,
      language: callLanguage,
      branch_name: AURIC_BRANCH.name,
      branch_address: AURIC_BRANCH.address,
    },
    onServerMessage: useCallback((msg: Record<string, unknown>) => {
      // The hosted brain drives the browser via the standard ui_command channel
      // (interaction.action("call_ended", …)); every demo page reads this shape.
      if (msg.type === 'ui_command' && msg.action === 'call_ended') {
        setCallResult({
          outcome: (msg.outcome as string) ?? 'other',
          lead: (msg.lead as Record<string, unknown>) ?? {},
          branch: (msg.branch as { name?: string; address?: string } | null) ?? null,
        });
        setStep('ended');
      }
    }, []),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic } = session;

  // ── Cleanup on unmount ──────────────────────────────────────────────────────
  useEffect(() => () => { disconnect().catch(() => {}); }, [disconnect]);

  // ── Connection-state → step transitions ─────────────────────────────────────
  useEffect(() => {
    if (connectionState === 'connected') {
      setStep(s => (s === 'connecting' ? 'call' : s));
      enableMic(true);
    } else if (connectionState === 'error') {
      setCallError(error || 'Could not connect. Please try again.');
      setStep(s => (s === 'connecting' || s === 'call' ? 'call-gate' : s));
    } else if (connectionState === 'disconnected') {
      // Peer left / transport dropped — return to the gate unless we ended cleanly.
      setStep(s => (s === 'call' || s === 'connecting' ? 'call-gate' : s));
    }
  }, [connectionState, error, enableMic]);

  // ── Auto-request mic permission on call-gate ───────────────────────────────
  useEffect(() => {
    if (step !== 'call-gate' || micPermission !== 'idle') return;
    setMicPermission('requesting');
    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      .then(stream => {
        stream.getTracks().forEach(t => t.stop());
        setMicPermission('granted');
      })
      .catch(() => setMicPermission('denied'));
  }, [step, micPermission]);

  // Reset permission if user goes back to form
  useEffect(() => {
    if (step === 'form') setMicPermission('idle');
  }, [step]);

  // ── Call duration timer ────────────────────────────────────────────────────
  useEffect(() => {
    if (step !== 'call') return;
    setCallDuration(0);
    const id = setInterval(() => setCallDuration(d => d + 1), 1000);
    return () => clearInterval(id);
  }, [step]);

  // ── Form ───────────────────────────────────────────────────────────────────
  const handleField = (field: keyof FormData) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    setFormData(f => ({ ...f, [field]: e.target.value }));
    setFormErrors(e2 => ({ ...e2, [field]: undefined }));
  };

  const submitForm = () => {
    const errors: Partial<FormData> = {};
    if (!formData.name.trim())                          errors.name  = 'Please enter your full name';
    if (!/^\d{10}$/.test(formData.phone))               errors.phone = 'Enter a valid 10-digit number';
    if (!formData.state)                                errors.state = 'Please select your state';
    if (!formData.city.trim())                          errors.city  = 'Please enter your city';
    if (Object.keys(errors).length) { setFormErrors(errors); return; }
    setStep('call-gate');
  };

  // ── Connection ─────────────────────────────────────────────────────────────
  const startCall = async () => {
    setCallError('');
    setStep('connecting');
    await connect();
  };

  const hangUp = async () => {
    await disconnect();
    setStep('call-gate');
  };

  // ── Bot status (derived from the hook's connection + bot state) ─────────────
  const botStatus: BotStatus =
    connectionState !== 'connected' ? 'connecting'
    : botState === 'thinking' ? 'thinking'
    : botState === 'speaking' ? 'speaking'
    : botState === 'listening' ? 'listening'
    : 'ready';

  const botStatusLabel: Record<BotStatus, string> = {
    connecting: 'Connecting…',
    ready:      'Priya is ready',
    thinking:   'Thinking…',
    speaking:   'Priya is speaking',
    listening:  'Listening…',
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  const content = (
    <div style={{ minHeight: '100vh', background: '#fdf8ef', color: '#1a1a2e', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}>
      <style>{PAGE_CSS}</style>
      {client && <BotAudioOutput />}

      {/* Root-level: the funnel starts with an enquiry form and only reaches its
          own call-gate step afterwards, so joining here uncovers the page — the
          microphone opens at that step, inside the demo's own flow. */}
      <DemoGate
        open={!joined}
        title="Auric Gold Finance"
        blurb="Fill in a gold-loan enquiry, then take the verification call — the advisor confirms your details out loud and the eligibility result lands on screen."
        accent={PRESENCE.listening}
        joinLabel="Start the demo"
        onJoin={() => setJoined(true)}
      />

      {/* The voice layer as a property of the whole page — the ring frames every
          step of the funnel, not just the call screen. */}
      <AmbientPresence botState={botState} connectionState={connectionState} palette={PRESENCE} />

      {/* ── Header ── */}
      <header className="lq-header" style={{ background: '#1a2472', padding: '14px 24px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 38, height: 38, background: '#c8960c', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, color: 'white', fontSize: 18, flex: 'none' }}>A</div>
        <div>
          <div style={{ color: 'white', fontSize: 20, fontWeight: 700 }}>Auric Gold Finance</div>
          <div style={{ color: '#f0c040', fontSize: 12, fontWeight: 500 }}>Gold Loans</div>
        </div>
      </header>

      {/* ── Hero ── */}
      <div className="lq-hero" style={{ background: 'linear-gradient(135deg, #1a2472 0%, #111855 100%)', color: 'white', textAlign: 'center', padding: '48px 24px 36px' }}>
        <h1 className="lq-hero-title" style={{ fontSize: 30, fontWeight: 800, lineHeight: 1.2 }}>
          Get a Gold Loan in <span style={{ color: '#f0c040' }}>Minutes</span>
        </h1>
        <p className="lq-hero-sub" style={{ marginTop: 10, color: 'rgba(255,255,255,.75)', fontSize: 15 }}>
          Pledge your gold. Get funds instantly. Safe. Simple. Trusted.
        </p>
        <div className="lq-pills" style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', marginTop: 24 }}>
          {['12%+ p.a.', 'Up to 75% LTV', 'Same-day disbursal', 'Home visit available'].map(t => (
            <span key={t} style={{ background: 'rgba(255,255,255,.1)', border: '1px solid rgba(255,255,255,.2)', borderRadius: 20, padding: '6px 16px', fontSize: 13, fontWeight: 600, color: '#f0c040' }}>{t}</span>
          ))}
        </div>
      </div>

      {/* ── Card ── */}
      <div className="lq-card" style={{ maxWidth: 520, margin: '-24px auto 40px', background: 'white', borderRadius: 16, boxShadow: '0 4px 24px rgba(0,0,0,.12)', overflow: 'hidden' }}>
        <div className="lq-card-head" style={{ background: '#c8960c', padding: '14px 24px', fontWeight: 700, fontSize: 15, color: '#1a1600' }}>
          Apply for Gold Loan – Quick Form
        </div>

        <div className="lq-card-body" style={{ padding: 24 }}>
          {step === 'form' && (
            <FormSection
              formData={formData}
              errors={formErrors}
              onChange={handleField}
              onSubmit={submitForm}
            />
          )}

          {step === 'call-gate' && (
            <CallGateSection
              name={formData.name}
              error={callError}
              micPermission={micPermission}
              language={language}
              state={formData.state}
              onLanguageChange={setLanguage}
              onStart={startCall}
            />
          )}

          {step === 'connecting' && (
            <div style={{ textAlign: 'center', padding: '32px 0' }}>
              <Loader2 className="lq-spin" size={26} color="#c8960c" />
              <p style={{ marginTop: 14, color: '#6b7280', fontSize: 14 }}>Connecting to your advisor…</p>
            </div>
          )}

          {step === 'call' && (
            <CallUI
              botStatus={botStatus}
              botStatusLabel={botStatusLabel}
              callDuration={callDuration}
              onHangUp={hangUp}
            />
          )}
        </div>
      </div>

      {step === 'ended' && callResult && (
        <ResultsSection result={callResult} phone={formData.phone} />
      )}
    </div>
  );

  return client ? <PipecatClientProvider client={client}>{content}</PipecatClientProvider> : content;
}

// ── Form section ──────────────────────────────────────────────────────────────
function FormSection({ formData, errors, onChange, onSubmit }: {
  formData: FormData;
  errors: Partial<FormData>;
  onChange: (f: keyof FormData) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void;
  onSubmit: () => void;
}) {
  return (
    <div>
      <Field label="Full Name *" error={errors.name}>
        <input style={inputStyle} type="text" placeholder="e.g. Ramesh Kumar" value={formData.name} onChange={onChange('name')} autoComplete="name" />
      </Field>

      <Field label="Mobile Number *" error={errors.phone}>
        <input style={inputStyle} type="tel" placeholder="10-digit mobile number" maxLength={10} inputMode="numeric" value={formData.phone} onChange={onChange('phone')} />
      </Field>

      <div className="lq-grid2" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="State *" error={errors.state}>
          <select style={inputStyle} value={formData.state} onChange={onChange('state')}>
            <option value="">Select state</option>
            {INDIAN_STATES.map(s => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="City *" error={errors.city}>
          <input style={inputStyle} type="text" placeholder="Your city" value={formData.city} onChange={onChange('city')} />
        </Field>
      </div>

      <div className="lq-grid2" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Gold Weight (grams)" note="Approximate is fine">
          <input style={inputStyle} type="number" placeholder="e.g. 50" min={1} value={formData.goldWeight} onChange={onChange('goldWeight')} />
        </Field>
        <Field label="Loan Amount (₹)" note="Approximate amount needed">
          <input style={inputStyle} type="number" placeholder="e.g. 200000" min={10000} step={1000} value={formData.loanAmount} onChange={onChange('loanAmount')} />
        </Field>
      </div>

      <button
        style={{ width: '100%', padding: '14px', background: '#1a2472', color: 'white', border: 'none', borderRadius: 10, fontSize: 16, fontWeight: 700, cursor: 'pointer', marginTop: 8 }}
        onClick={onSubmit}
      >
        Check Eligibility &amp; Apply
      </button>
    </div>
  );
}

// ── Call gate ─────────────────────────────────────────────────────────────────
function CallGateSection({ name: _name, error, micPermission, language, state, onLanguageChange, onStart }: {
  name: string;
  error: string;
  micPermission: MicPermission;
  language: string;
  state: string;
  onLanguageChange: (lang: string) => void;
  onStart: () => void;
}) {
  const canStart = micPermission === 'granted';
  const autoLabel = inferredLanguage(state);

  return (
    <div style={{ textAlign: 'center', padding: '12px 0 4px' }}>
      <style>{`
        @keyframes floatUp {
          0%, 100% { opacity: 0.2; transform: translateY(5px); }
          50%       { opacity: 1;   transform: translateY(-3px); }
        }
      `}</style>

      {/* ── Mic permission states ── */}
      {micPermission === 'requesting' && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 10, marginBottom: 12 }}>
            {[0, 200, 400].map(delay => (
              <svg key={delay} width="18" height="22" viewBox="0 0 18 22"
                style={{ animation: `floatUp 1.3s ease-in-out ${delay}ms infinite` }}
              >
                <path d="M9 0L0 10h5.5v12h7V10H18L9 0z" fill="#1a2472" />
              </svg>
            ))}
          </div>
          <div style={{ background: '#eff6ff', border: '1.5px solid #93c5fd', borderRadius: 10, padding: '12px 16px' }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: '#1e40af', marginBottom: 3 }}>Allow Microphone Access</div>
            <div style={{ fontSize: 13, color: '#3730a3' }}>Click <strong>"Allow"</strong> in the browser popup above</div>
          </div>
        </div>
      )}

      {micPermission === 'denied' && (
        <div style={{ background: '#fff7ed', border: '1.5px solid #fed7aa', borderRadius: 10, padding: '12px 16px', marginBottom: 24 }}>
          <div style={{ fontSize: 13, color: '#9a3412' }}>
            ⚠️ Microphone blocked — click the lock icon in your address bar to allow, then reload.
          </div>
        </div>
      )}

      {/* Brief context when mic is ready */}
      {micPermission === 'granted' && (
        <div style={{ marginBottom: 20, textAlign: 'center' }}>
          <p style={{ fontSize: 14, color: '#374151', lineHeight: 1.6, margin: 0 }}>
            Thanks for submitting your details. A short verification call will confirm your eligibility — takes about 2 minutes.
          </p>
        </div>
      )}

      {/* ── Language selector ── */}
      <div style={{ marginBottom: 20, textAlign: 'left' }}>
        <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#6b7280', marginBottom: 6 }}>
          Call language
        </label>
        <select
          value={language}
          onChange={e => onLanguageChange(e.target.value)}
          style={{ ...inputStyle, color: '#1a1a2e' }}
        >
          <option value="auto">Auto ({autoLabel})</option>
          {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>

      {/* ── Call button ── */}
      <button
        disabled={!canStart}
        onClick={onStart}
        style={{
          width: '100%', padding: '15px 24px',
          background: canStart ? '#16a34a' : '#e5e7eb',
          color: canStart ? 'white' : '#9ca3af',
          border: 'none', borderRadius: 12,
          cursor: canStart ? 'pointer' : 'default',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
          fontSize: 16, fontWeight: 700,
          boxShadow: canStart ? '0 4px 14px rgba(22,163,74,.35)' : 'none',
          transition: 'background .2s, box-shadow .2s, transform .1s',
        }}
        onMouseEnter={e => { if (canStart) e.currentTarget.style.transform = 'translateY(-1px)'; }}
        onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; }}
        onMouseDown={e => { if (canStart) e.currentTarget.style.transform = 'translateY(1px)'; }}
        onMouseUp={e => { if (canStart) e.currentTarget.style.transform = 'translateY(-1px)'; }}
      >
        <IconPhoneCall size={20} color={canStart ? 'white' : '#9ca3af'} />
        Start Verification Call
      </button>
      <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 10 }}>
        Required to complete your application · ~2 min
      </div>

      {error && (
        <div style={{ marginTop: 16, padding: '10px 14px', background: '#fee2e2', borderRadius: 8, color: '#dc2626', fontSize: 13 }}>
          {error}
        </div>
      )}
    </div>
  );
}

// ── Active call ───────────────────────────────────────────────────────────────
// No console: the ring around the page carries the agent's state. All that is
// left here is what a phone call legitimately shows — who is on the line, how
// long it has run, and two controls: mute and hang up.
function CallUI({ botStatus, botStatusLabel, callDuration, onHangUp }: {
  botStatus: BotStatus;
  botStatusLabel: Record<BotStatus, string>;
  callDuration: number;
  onHangUp: () => void;
}) {
  // The mic lives on the live PipecatClient (this component only renders inside
  // the PipecatClientProvider, during an active call).
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();

  const fmt = (s: number) => {
    const m = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
  };

  return (
    <div style={{ padding: '14px 0 6px' }}>
      <p style={{ margin: 0, fontSize: 14, color: '#374151', lineHeight: 1.6, textAlign: 'center' }}>
        Priya is on the line to verify your details. Just speak naturally — the glow
        around the page shows when she is listening.
      </p>

      <div
        className="lq-call-bar"
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 14, marginTop: 22,
        }}
      >
        {/* Status + timer — small and quiet, not a console readout. */}
        <div style={{ textAlign: 'right', lineHeight: 1.35 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#1a2472' }}>
            {isMicEnabled ? botStatusLabel[botStatus] : 'Muted'}
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af', fontVariantNumeric: 'tabular-nums', letterSpacing: 1 }}>
            {fmt(callDuration)}
          </div>
        </div>

        {/* Mute toggle — the one prominent affordance while live. */}
        <button
          onClick={() => enableMic(!isMicEnabled)}
          title={isMicEnabled ? 'Mute' : 'Unmute'}
          aria-label={isMicEnabled ? 'Mute' : 'Unmute'}
          style={{
            width: 46, height: 46, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: isMicEnabled ? '#c8960c' : 'white',
            border: `1.5px solid ${isMicEnabled ? '#c8960c' : '#d1d5db'}`,
            color: isMicEnabled ? 'white' : '#6b7280',
            boxShadow: isMicEnabled ? '0 0 0 4px rgba(200,150,12,.16)' : 'none',
            cursor: 'pointer', flex: 'none',
            transition: 'background .15s, box-shadow .15s, border-color .15s',
          }}
        >
          {isMicEnabled ? <Mic size={18} /> : <MicOff size={18} />}
        </button>

        {/* End — deliberately secondary. */}
        <button
          onClick={onHangUp}
          title="End call"
          aria-label="End call"
          style={{
            width: 34, height: 34, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'transparent', border: 'none', color: '#9ca3af',
            cursor: 'pointer', flex: 'none',
          }}
        >
          <PhoneOff size={16} />
        </button>
      </div>
    </div>
  );
}


// ── Results section ───────────────────────────────────────────────────────────
function ResultsSection({ result, phone }: { result: CallResult; phone: string }) {
  const qualified = result.outcome === 'qualified';
  const lead = result.lead as Record<string, unknown>;
  const branch = result.branch;

  const fmt = (v: unknown) => {
    if (!v) return '—';
    return String(v).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  const fields = [
    ['Name',        lead.name],
    ['Phone',       lead.phone],
    ['Gold form',   fmt(lead.gold_form)],
    ['Weight',      lead.gold_weight_grams ? `${lead.gold_weight_grams} g` : null],
    ['Loan amount', lead.loan_amount_inr ? `₹${Number(lead.loan_amount_inr).toLocaleString('en-IN')}` : null],
    ['Purpose',     fmt(lead.loan_purpose)],
    ['Timeline',    fmt(lead.timeline)],
    ['Next step',   fmt(lead.preferred_next_step)],
  ].filter(([, v]) => v && v !== '—') as [string, string][];

  return (
    <div className="lq-card lq-card-flat" style={{ maxWidth: 520, margin: '0 auto 40px', background: 'white', borderRadius: 16, boxShadow: '0 4px 24px rgba(0,0,0,.12)', overflow: 'hidden' }}>
      <div className="lq-card-head" style={{ background: qualified ? 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)' : 'linear-gradient(135deg, #6b7280, #4b5563)', color: 'white', padding: '18px 24px', fontWeight: 700, fontSize: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
        {qualified ? '✅' : 'ℹ️'}
        {qualified ? 'Qualification Complete!' : 'Call Ended'}
      </div>

      <div className="lq-card-body" style={{ padding: 24 }}>
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>Your Details</h3>
          <dl className="lq-dl" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
            {fields.map(([k, v]) => (
              <div key={k} style={{ display: 'flex', flexDirection: 'column' }}>
                <dt style={{ fontSize: 11, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>{k}</dt>
                <dd style={{ fontSize: 14, fontWeight: 600, color: '#1a1a2e', marginTop: 2 }}>{v}</dd>
              </div>
            ))}
          </dl>
        </div>

        {qualified && branch?.name && (
          <>
            <div style={{ height: 1, background: '#e5e7eb', margin: '16px 0' }} />
            <div>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>Nearest Auric Gold Finance Branch</h3>
              <div style={{ background: '#f8f9ff', border: '1px solid #e0e4ff', borderRadius: 10, padding: '14px 16px' }}>
                <div style={{ fontWeight: 700, fontSize: 15, color: '#1a2472' }}>{branch.name}</div>
                {branch.address && <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>{branch.address}</div>}
                <a
                  href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(branch.address ?? branch.name ?? '')}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 10, background: '#1a2472', color: 'white', padding: '7px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, textDecoration: 'none' }}
                >
                  📍 Open in Google Maps
                </a>
              </div>
              <p style={{ fontSize: 13, color: '#6b7280', textAlign: 'center', marginTop: 12 }}>
                We will also call you at <strong>{phone}</strong> within 2 hours.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function Field({ label, error, note, children }: {
  label: string; error?: string; note?: string; children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#6b7280', marginBottom: 5 }}>{label}</label>
      {children}
      {note  && <div style={{ fontSize: 11.5, color: '#9ca3af', marginTop: 3 }}>{note}</div>}
      {error && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 3 }}>{error}</div>}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '11px 13px',
  border: '1.5px solid #d1d5db', borderRadius: 10,
  fontSize: 15, outline: 'none', boxSizing: 'border-box',
};

// ── SVG icons ─────────────────────────────────────────────────────────────────
function IconPhoneCall({ size = 24, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color}>
      <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.46.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" />
    </svg>
  );
}

// ── Page CSS ──────────────────────────────────────────────────────────────────
// The page is styled inline (CSS-in-JS) throughout; this block carries the two
// things inline styles cannot express — the connecting spinner's keyframes and
// the phone breakpoint. Mobile rules need `!important` because they override
// inline `style` props. Desktop (>640px) is untouched.
const PAGE_CSS = `
  body { margin: 0; }

  .lq-spin { animation: lq-spin 0.9s linear infinite; }
  @keyframes lq-spin { to { transform: rotate(360deg); } }

  /* The dd default indent would push every result value off its column. */
  .lq-dl dd { margin-inline-start: 0; }

  @media (max-width: 640px) {
    .lq-header { padding: 12px 16px !important; }

    .lq-hero { padding: 30px 18px 26px !important; }
    .lq-hero-title { font-size: 25px !important; }
    .lq-hero-sub { font-size: 14px !important; }
    .lq-pills { gap: 8px !important; margin-top: 18px !important; }

    /* Fluid card with real side gutters instead of a 520px block flush to the
       viewport edge. */
    .lq-card { margin: -20px 14px 30px !important; border-radius: 14px !important; }
    .lq-card-flat { margin-top: 0 !important; }
    .lq-card-head { padding: 13px 18px !important; }
    .lq-card-body { padding: 18px !important; }

    /* Paired fields and result values are too narrow to share a row at 390px. */
    .lq-grid2 { grid-template-columns: 1fr !important; }
    .lq-dl { grid-template-columns: 1fr !important; }

    .lq-call-bar { gap: 12px !important; }
  }
`;
