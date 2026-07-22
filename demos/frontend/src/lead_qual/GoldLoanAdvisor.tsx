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
 */

import { useCallback, useEffect, useState } from 'react';
import {
  PipecatClientProvider,
  usePipecatClientMediaTrack,
} from '@pipecat-ai/client-react';
import { BotAudioOutput, CircularWaveform } from '@pipecat-ai/voice-ui-kit';
import { useVoqalSession } from '@voqalize/client-react';
import { DEMOS } from '../config';

// Tenant + agent + pk + pipeline resolve per-environment from the shared demos
// config (src/config.ts), driven by Vite env vars.
const LEAD = DEMOS.lead_qual;

// ── Language config ───────────────────────────────────────────────────────────
// The demo is Indic multi-language: the STT recognition hint and TTS language are
// keyed off the chosen call language. Everything else in the pipeline (STT model,
// TTS voice/engine) comes from the manifest via `LEAD.pipeline`, so it is never
// hardcoded here.
const LANG_HINT: Record<string, string> = {
  Hindi: 'hi',
  Telugu: 'te',
  Tamil: 'ta',
  Kannada: 'kn',
  Malayalam: 'ml',
  Marathi: 'mr',
  Gujarati: 'gu',
  Bengali: 'bn',
};

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
  const [step, setStep]               = useState<Step>('form');
  const [formErrors, setFormErrors]   = useState<Partial<FormData>>({});
  const [formData, setFormData]       = useState<FormData>({
    name: '', phone: '', state: '', city: '', goldWeight: '', loanAmount: '',
  });
  const [callError, setCallError]     = useState('');
  const [isMuted, setIsMuted]         = useState(false);
  const [callResult, setCallResult]   = useState<CallResult | null>(null);
  const [micPermission, setMicPermission] = useState<MicPermission>('idle');
  const [callDuration, setCallDuration]   = useState(0);
  const [availableMics, setAvailableMics]           = useState<MediaDeviceInfo[]>([]);
  const [selectedMic, setSelectedMic]               = useState<MediaDeviceInfo | null>(null);
  const [availableSpeakers, setAvailableSpeakers]   = useState<MediaDeviceInfo[]>([]);
  const [selectedSpeaker, setSelectedSpeaker]       = useState<MediaDeviceInfo | null>(null);
  const [language, setLanguage]                     = useState<string>('auto');

  // ── Session pipeline + payload (recomputed each render; the hook reads the ──
  //    latest at connect time) ────────────────────────────────────────────────
  const callLanguage = language === 'auto' ? inferredLanguage(formData.state) : language;
  const hint = LANG_HINT[callLanguage] ?? 'hi';

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type`/`action` directly.
  const session = useVoqalSession({
    apiBase: LEAD.apiBase,
    tenantSlug: LEAD.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the call-gate error state.
    publishableKey: LEAD.publishableKey ?? '',
    agentId: LEAD.agentId,
    // STT model + TTS voice/engine come from the manifest (via config); only the
    // language is overridden from the caller's selection.
    pipeline: {
      stt: { ...LEAD.pipeline.stt, language: hint },
      tts: { ...LEAD.pipeline.tts, language: hint },
    },
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
      setIsMuted(false);
    } else if (connectionState === 'error') {
      setCallError(error || 'Could not connect. Please try again.');
      setStep(s => (s === 'connecting' || s === 'call' ? 'call-gate' : s));
    } else if (connectionState === 'disconnected') {
      // Peer left / transport dropped — return to the gate unless we ended cleanly.
      setStep(s => (s === 'call' || s === 'connecting' ? 'call-gate' : s));
    }
  }, [connectionState, error, enableMic]);

  // ── Device enumeration (labels available once mic permission is granted) ────
  const refreshDevices = useCallback(async () => {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const mics = devices.filter(d => d.kind === 'audioinput');
    const speakers = devices.filter(d => d.kind === 'audiooutput');
    setAvailableMics(mics);
    setAvailableSpeakers(speakers);
    setSelectedMic(m => m ?? mics[0] ?? null);
    setSelectedSpeaker(s => s ?? speakers[0] ?? null);
  }, []);

  // Refresh the device list once the call is live too (device ids stabilise).
  useEffect(() => {
    if (connectionState === 'connected') refreshDevices();
  }, [connectionState, refreshDevices]);

  // ── Auto-request mic permission on call-gate ───────────────────────────────
  useEffect(() => {
    if (step !== 'call-gate' || micPermission !== 'idle') return;
    setMicPermission('requesting');
    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      .then(stream => {
        stream.getTracks().forEach(t => t.stop());
        setMicPermission('granted');
        refreshDevices();
      })
      .catch(() => setMicPermission('denied'));
  }, [step, micPermission, refreshDevices]);

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

  const toggleMute = () => {
    setIsMuted(m => {
      const next = !m;
      enableMic(!next);
      return next;
    });
  };

  const hangUp = async () => {
    await disconnect();
    setIsMuted(false);
    setStep('call-gate');
  };

  const updateMic = (deviceId: string) => {
    const mic = availableMics.find(m => m.deviceId === deviceId) ?? null;
    setSelectedMic(mic);
    client?.updateMic(deviceId);
  };

  const updateSpeaker = (deviceId: string) => {
    const spk = availableSpeakers.find(s => s.deviceId === deviceId) ?? null;
    setSelectedSpeaker(spk);
    client?.updateSpeaker(deviceId);
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
    <div className="vkui-root" style={{ minHeight: '100vh', background: '#fdf8ef', color: '#1a1a2e', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}>
      {client && <BotAudioOutput />}

      {/* ── Header ── */}
      <header style={{ background: '#1a2472', padding: '14px 24px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 38, height: 38, background: '#c8960c', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, color: 'white', fontSize: 18 }}>A</div>
        <div>
          <div style={{ color: 'white', fontSize: 20, fontWeight: 700 }}>Auric Gold Finance</div>
          <div style={{ color: '#f0c040', fontSize: 12, fontWeight: 500 }}>Gold Loans</div>
        </div>
      </header>

      {/* ── Hero ── */}
      <div style={{ background: 'linear-gradient(135deg, #1a2472 0%, #111855 100%)', color: 'white', textAlign: 'center', padding: '48px 24px 36px' }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, lineHeight: 1.2 }}>
          Get a Gold Loan in <span style={{ color: '#f0c040' }}>Minutes</span>
        </h1>
        <p style={{ marginTop: 10, color: 'rgba(255,255,255,.75)', fontSize: 15 }}>
          Pledge your gold. Get funds instantly. Safe. Simple. Trusted.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', marginTop: 24 }}>
          {['12%+ p.a.', 'Up to 75% LTV', 'Same-day disbursal', 'Home visit available'].map(t => (
            <span key={t} style={{ background: 'rgba(255,255,255,.1)', border: '1px solid rgba(255,255,255,.2)', borderRadius: 20, padding: '6px 16px', fontSize: 13, fontWeight: 600, color: '#f0c040' }}>{t}</span>
          ))}
        </div>
      </div>

      {/* ── Card ── */}
      <div style={{ maxWidth: 520, margin: '-24px auto 40px', background: 'white', borderRadius: 16, boxShadow: '0 4px 24px rgba(0,0,0,.12)', overflow: 'hidden' }}>
        <div style={{ background: '#c8960c', padding: '14px 24px', fontWeight: 700, fontSize: 15, color: '#1a1600' }}>
          Apply for Gold Loan – Quick Form
        </div>

        <div style={{ padding: 24 }}>
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
            <div style={{ textAlign: 'center', padding: '40px 0' }}>
              <div style={{ width: 200, height: 200, margin: '0 auto' }}>
                <CircularWaveform isThinking size={200} color1="#4a90d9" color2="#c8960c" />
              </div>
              <p style={{ marginTop: 16, color: '#6b7280', fontSize: 14 }}>Connecting to your advisor…</p>
            </div>
          )}

          {step === 'call' && (
            <CallUI
              botStatus={botStatus}
              botStatusLabel={botStatusLabel}
              isMuted={isMuted}
              callDuration={callDuration}
              availableMics={availableMics}
              selectedMic={selectedMic}
              availableSpeakers={availableSpeakers}
              selectedSpeaker={selectedSpeaker}
              onToggleMute={toggleMute}
              onHangUp={hangUp}
              onUpdateMic={updateMic}
              onUpdateSpeaker={updateSpeaker}
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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
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

// ── Active call UI ────────────────────────────────────────────────────────────
function CallUI({
  botStatus, botStatusLabel, isMuted, callDuration,
  availableMics, selectedMic, availableSpeakers, selectedSpeaker,
  onToggleMute, onHangUp, onUpdateMic, onUpdateSpeaker,
}: {
  botStatus: BotStatus;
  botStatusLabel: Record<BotStatus, string>;
  isMuted: boolean;
  callDuration: number;
  availableMics: MediaDeviceInfo[];
  selectedMic: MediaDeviceInfo | null;
  availableSpeakers: MediaDeviceInfo[];
  selectedSpeaker: MediaDeviceInfo | null;
  onToggleMute: () => void;
  onHangUp: () => void;
  onUpdateMic: (id: string) => void;
  onUpdateSpeaker: (id: string) => void;
}) {
  // Media tracks come straight from the live PipecatClient (this component only
  // renders inside the PipecatClientProvider, during an active call).
  const botTrack = usePipecatClientMediaTrack('audio', 'bot');
  const userTrack = usePipecatClientMediaTrack('audio', 'local');

  const fmt = (s: number) => {
    const m = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '20px 0 8px' }}>

      {/* Call timer */}
      <div style={{ fontSize: 13, color: '#9ca3af', fontVariantNumeric: 'tabular-nums', letterSpacing: 1, marginBottom: 20 }}>
        {fmt(callDuration)}
      </div>

      {/* Bot waveform */}
      <div style={{ width: 140, height: 140, position: 'relative', marginBottom: 4 }}>
        <CircularWaveform
          audioTrack={botTrack}
          isThinking={botStatus === 'thinking'}
          size={140}
          color1="#4a90d9"
          color2="#c8960c"
        />
        <div style={{
          position: 'absolute', bottom: -2, left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(26,36,114,.85)', color: 'white', fontSize: 11, fontWeight: 600,
          padding: '3px 10px', borderRadius: 20, whiteSpace: 'nowrap',
        }}>
          Priya — Advisor
        </div>
      </div>

      {/* Status */}
      <div style={{ fontSize: 13, fontWeight: 600, color: '#1a2472', marginTop: 14, marginBottom: 24, height: 20 }}>
        {botStatusLabel[botStatus]}
      </div>

      {/* Three-button meeting control bar */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'flex-start', gap: 32, width: '100%', paddingTop: 8 }}>

        {/* ── Mic — CircularWaveform ring with button inside ── */}
        <MeetingButton label={isMuted ? 'Unmute' : 'Mute'} deviceSelect={
          availableMics.length > 1
            ? <DeviceSelect devices={availableMics} selectedId={selectedMic?.deviceId} onChange={onUpdateMic} />
            : undefined
        }>
          <div style={{ position: 'relative', width: 60, height: 60 }}>
            <CircularWaveform
              audioTrack={isMuted ? null : userTrack}
              size={60}
              color1="#6366f1"
              color2="#a855f7"
              numBars={20}
            />
            <button
              onClick={onToggleMute}
              style={{
                position: 'absolute', top: '50%', left: '50%',
                transform: 'translate(-50%, -50%)',
                width: 42, height: 42, borderRadius: '50%',
                background: isMuted ? '#374151' : 'white',
                border: '1.5px solid #e5e7eb',
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 1px 6px rgba(0,0,0,.12)',
              }}
            >
              {isMuted
                ? <IconMicOff size={17} color="white" />
                : <IconMic size={17} color="#374151" />}
            </button>
          </div>
        </MeetingButton>

        {/* ── End call ── */}
        <MeetingButton label="End">
          <button
            onClick={onHangUp}
            style={{
              width: 52, height: 52, borderRadius: '50%',
              background: '#dc2626', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(220,38,38,.45)',
              marginTop: 4,
            }}
          >
            <IconPhoneOff size={22} color="white" />
          </button>
        </MeetingButton>

        {/* ── Speaker ── */}
        <MeetingButton label="Speaker" deviceSelect={
          availableSpeakers.length > 0
            ? <DeviceSelect devices={availableSpeakers} selectedId={selectedSpeaker?.deviceId} onChange={onUpdateSpeaker} />
            : undefined
        }>
          <div style={{
            width: 42, height: 42, borderRadius: '50%',
            background: 'white', border: '1.5px solid #e5e7eb',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '9px 0 0 9px',
            boxShadow: '0 1px 6px rgba(0,0,0,.12)',
          }}>
            <IconSpeaker size={17} color="#374151" />
          </div>
        </MeetingButton>

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
    <div style={{ maxWidth: 520, margin: '0 auto 40px', background: 'white', borderRadius: 16, boxShadow: '0 4px 24px rgba(0,0,0,.12)', overflow: 'hidden' }}>
      <div style={{ background: qualified ? 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)' : 'linear-gradient(135deg, #6b7280, #4b5563)', color: 'white', padding: '18px 24px', fontWeight: 700, fontSize: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
        {qualified ? '✅' : 'ℹ️'}
        {qualified ? 'Qualification Complete!' : 'Call Ended'}
      </div>

      <div style={{ padding: 24 }}>
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>Your Details</h3>
          <dl style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
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
function IconMic({ size = 22, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 2c-1.66 0-3 1.34-3 3v6c0 1.66 1.34 3 3 3s3-1.34 3-3V5c0-1.66-1.34-3-3-3z" fill={color} />
      <path d="M19 11c0 3.87-3.13 7-7 7s-7-3.13-7-7" stroke={color} strokeWidth="2" strokeLinecap="round" fill="none" />
      <line x1="12" y1="18" x2="12" y2="22" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <line x1="8" y1="22" x2="16" y2="22" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function IconMicOff({ size = 22, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 2c-1.66 0-3 1.34-3 3v6c0 1.66 1.34 3 3 3s3-1.34 3-3V5c0-1.66-1.34-3-3-3z" fill={color} opacity="0.4" />
      <path d="M19 11c0 3.87-3.13 7-7 7s-7-3.13-7-7" stroke={color} strokeWidth="2" strokeLinecap="round" fill="none" />
      <line x1="12" y1="18" x2="12" y2="22" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <line x1="8" y1="22" x2="16" y2="22" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <line x1="3" y1="3" x2="21" y2="21" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

function IconPhoneOff({ size = 26, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color} style={{ transform: 'rotate(135deg)' }}>
      <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.46.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" />
    </svg>
  );
}

function IconSpeaker({ size = 22, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M11 5L6 9H2v6h4l5 4V5z" fill={color} />
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" stroke={color} strokeWidth="2" strokeLinecap="round" fill="none" />
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14" stroke={color} strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

function IconPhoneCall({ size = 24, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color}>
      <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.46.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" />
    </svg>
  );
}

// ── Meeting control helpers ───────────────────────────────────────────────────
function MeetingButton({ children, label, deviceSelect }: {
  children: React.ReactNode;
  label: string;
  deviceSelect?: React.ReactNode;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 60 }}>
      {children}
      <span style={{ fontSize: 11, color: '#6b7280', userSelect: 'none', whiteSpace: 'nowrap' }}>{label}</span>
      {deviceSelect}
    </div>
  );
}

function DeviceSelect({ devices, selectedId, onChange }: {
  devices: MediaDeviceInfo[];
  selectedId?: string;
  onChange: (id: string) => void;
}) {
  if (devices.length <= 1) return null;
  return (
    <select
      value={selectedId ?? ''}
      onChange={e => onChange(e.target.value)}
      style={{
        fontSize: 11, color: '#9ca3af', border: 'none',
        background: 'transparent', maxWidth: 90, cursor: 'pointer',
        textAlign: 'center', outline: 'none',
      }}
    >
      {devices.map(d => (
        <option key={d.deviceId} value={d.deviceId}>
          {d.label?.replace(/\s*\(.*?\)\s*/g, '').trim() || (d.kind === 'audioinput' ? 'Mic' : 'Speaker')}
        </option>
      ))}
    </select>
  );
}
