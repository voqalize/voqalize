/**
 * Sugar Coach demo UI — two screens.
 *
 * Screen 1 (picker): a presenter-facing care console — two patients, three
 * evenings each. Every cell shows exactly what the agent will walk in knowing,
 * so the personalization on the call reads as provably data-driven.
 *
 * Screen 2 (phone): a device frame running the patient's app. The sequence is
 * the demo's signature moment: lock screen → push notification + chime →
 * Join check-in (or snooze) → the evening check-in, with the agent driving
 * the Today screen live (meals logging themselves, meds ticking, the glucose
 * chart zooming to the spike, videos playing in-app). Deliberately not a
 * telephony call screen — the app is nudging the patient into a session.
 *
 * All navigation is React state (via the store) so the live call survives
 * every screen change.
 */

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { COACH_NAME, PATIENTS, PROGRAM_NAME, scenariosFor } from './data';
import { SugarCallSession } from './SugarCoach';
import { useSugar } from './store';
import type { GlucoseDay, Patient, Scenario, TalkMode } from './types';

// ── Palette (evergreen + cream — a consumer health app, not a dashboard) ────
const INK = '#1E2A24';
const INK_SOFT = '#5C6B62';
const CREAM = '#F6F4EE';
const CARD = '#FFFFFF';
const LINE = '#E7E4DA';
const GREEN = '#0E7A5F';
const GREEN_DARK = '#0A5C48';
const GREEN_TINT = '#EAF4F0';
const AMBER = '#C97F1E';
const AMBER_TINT = '#FBF3E6';
const CALL_BG = 'linear-gradient(160deg, #0F2B23 0%, #123A2E 60%, #16463A 100%)';

const FONTS = `
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700;800&display=swap');
`;

const DISPLAY = "'Fraunces', Georgia, serif";
const BODY = "'Inter', system-ui, sans-serif";

/**
 * Responsive scale. The phone-shaped layout already suits a handset, so the
 * mobile pass is a set of custom properties (sizes that are set inline, where a
 * media rule could not reach them) plus a handful of class overrides for the
 * stage. Below 640px the device mock drops its bezel and goes full-bleed — a
 * simulated phone inside a real phone is just a clipped phone — the presenter
 * panel stacks underneath it, and every sub-11px label steps up a notch.
 */
const GLOBAL_CSS = `
${FONTS}
:root {
  --sugar-micro: 10px;
  --sugar-mini: 10.5px;
  --sugar-h1: 40px;
  --sugar-picker-pad: 40px 28px 64px;
  --sugar-stage-pad: 36px 28px;
  --sugar-stage-gap: 44px;
  --sugar-screen-radius: 44px;
}
.sugar-context {
  width: 330px;
  max-width: 90vw;
  max-height: 780px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.sugar-phone {
  width: 378px;
  height: 780px;
  flex: none;
  border-radius: 54px;
  background: #101312;
  padding: 11px;
  box-shadow: 0 30px 80px rgba(15,35,28,.35), inset 0 0 0 2px #2A2E2C;
}
@media (max-width: 640px) {
  :root {
    --sugar-micro: 11px;
    --sugar-mini: 11.5px;
    --sugar-h1: 27px;
    --sugar-picker-pad: 22px 14px 40px;
    --sugar-stage-pad: 0px;
    --sugar-stage-gap: 0px;
    --sugar-screen-radius: 0px;
  }
  .sugar-stage { flex-direction: column; align-items: stretch; }
  /* Full-bleed device: a 6px dark rim is all that is left of the bezel, and it
     doubles as the mat the ambient presence ring paints on. */
  .sugar-phone {
    order: 1;
    width: 100%;
    height: 100dvh;
    border-radius: 0;
    padding: 6px;
    box-sizing: border-box;
    box-shadow: none;
  }
  .sugar-notch { display: none; }
  .sugar-ended { overflow-y: auto; }
  /* Presenter notes stack under the app rather than above it. */
  .sugar-context {
    order: 2;
    width: 100%;
    max-width: none;
    max-height: none;
    overflow-y: visible;
    padding: 20px 16px 32px;
    box-sizing: border-box;
  }
}
@keyframes sugarSlideDown { from { transform: translateY(-120%); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
@keyframes sugarFadeUp { from { transform: translateY(14px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
@keyframes sugarPulse { 0%,100% { transform: scale(1); opacity: .55; } 50% { transform: scale(1.35); opacity: 0; } }
@keyframes sugarBreathe { 0%,100% { box-shadow: 0 0 0 0 rgba(123,217,190,.45); } 50% { box-shadow: 0 0 0 22px rgba(123,217,190,0); } }
@keyframes sugarBlink { 0%,100% { opacity: 1; } 50% { opacity: .45; } }
@keyframes sugarGlow { 0% { box-shadow: 0 0 0 3px rgba(14,122,95,.35); } 100% { box-shadow: 0 0 0 3px rgba(14,122,95,0); } }
.sugar-fresh { animation: sugarFadeUp .5s cubic-bezier(.2,.9,.3,1.2) both; }
.sugar-pulse { animation: sugarBlink 1.6s ease-in-out infinite; }
.sugar-hl { animation: sugarGlow 2.4s ease-out both; border-radius: 18px; }
.sugar-cell:hover { border-color: ${GREEN}; box-shadow: 0 10px 28px rgba(14,60,45,.10); transform: translateY(-2px); }
.sugar-cell { transition: border-color .18s, box-shadow .18s, transform .18s; }
@media (prefers-reduced-motion: reduce) {
  .sugar-fresh, .sugar-pulse, .sugar-hl { animation: none; }
}
`;

// ═════════════════════════════════════════════════════════════════════════════
// Root
// ═════════════════════════════════════════════════════════════════════════════

export function SugarApp() {
  const { phase } = useSugar();
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        overflow: 'auto',
        background: CREAM,
        color: INK,
        fontFamily: BODY,
      }}
    >
      <style>{GLOBAL_CSS}</style>
      {phase === 'picker' ? <PickerScreen /> : <PhoneStage />}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Screen 1 — the care console (scenario picker)
// ═════════════════════════════════════════════════════════════════════════════

function PickerScreen() {
  const { language, setLanguage } = useSugar();
  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: 'var(--sugar-picker-pad)' }}>
      <header style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 10 }}>
        <div>
          <div style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 'var(--sugar-h1)', letterSpacing: '-0.01em', color: GREEN_DARK }}>
            {PROGRAM_NAME}
            <span style={{ fontFamily: BODY, fontWeight: 600, fontSize: 13, color: INK_SOFT, marginLeft: 12, letterSpacing: '.08em', textTransform: 'uppercase' }}>
              Care console
            </span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: 14.5, color: INK_SOFT, maxWidth: 620, lineHeight: 1.5 }}>
            Every evening, the app nudges the patient into a two-minute voice check-in. Pick a
            patient and a day — the card is everything {COACH_NAME} walks in knowing.
          </p>
        </div>
        <LanguageToggle language={language} setLanguage={setLanguage} />
      </header>

      {/* `min(440px, 100%)` keeps the two-up console on desktop and collapses to a
          single column on a handset instead of forcing a 440px track. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(440px, 100%), 1fr))', gap: 28, marginTop: 26 }}>
        {PATIENTS.map((p) => (
          <PatientColumn key={p.id} patient={p} />
        ))}
      </div>
    </div>
  );
}

function LanguageToggle({ language, setLanguage }: { language: string; setLanguage: (l: 'English' | 'Hindi') => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ fontSize: 12, fontWeight: 600, color: INK_SOFT, letterSpacing: '.05em', textTransform: 'uppercase' }}>Call language</span>
      <div style={{ display: 'flex', background: '#EBE8DF', borderRadius: 12, padding: 3 }}>
        {(['English', 'Hindi'] as const).map((l) => (
          <button
            key={l}
            onClick={() => setLanguage(l)}
            style={{
              border: 'none',
              borderRadius: 9,
              padding: '7px 16px',
              fontSize: 13,
              fontWeight: 700,
              fontFamily: BODY,
              cursor: 'pointer',
              background: language === l ? CARD : 'transparent',
              color: language === l ? GREEN_DARK : INK_SOFT,
              boxShadow: language === l ? '0 2px 8px rgba(20,40,30,.12)' : 'none',
            }}
          >
            {l === 'Hindi' ? 'हिन्दी' : l}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Presenter control (Screen 1): flip how much the coach leads before Join. */
const PACE: { mode: TalkMode; label: string; blurb: string }[] = [
  { mode: 'quiet', label: 'Quiet', blurb: 'She listens — you narrate the day, she logs it silently.' },
  { mode: 'guided', label: 'Guided', blurb: 'She leads — one gentle question at a time.' },
];

function PaceToggle() {
  const { talkMode, setTalkMode } = useSugar();
  const active = PACE.find((p) => p.mode === talkMode) ?? PACE[0];
  return (
    <div style={{ background: CARD, border: `1px solid ${LINE}`, borderRadius: 16, padding: '12px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: INK_SOFT }}>
          Coach pace
        </span>
        <div style={{ display: 'flex', background: '#EBE8DF', borderRadius: 11, padding: 3 }}>
          {PACE.map((p) => (
            <button
              key={p.mode}
              onClick={() => setTalkMode(p.mode)}
              style={{
                border: 'none',
                borderRadius: 8,
                padding: '6px 13px',
                fontSize: 12.5,
                fontWeight: 700,
                fontFamily: BODY,
                cursor: 'pointer',
                background: talkMode === p.mode ? CARD : 'transparent',
                color: talkMode === p.mode ? GREEN_DARK : INK_SOFT,
                boxShadow: talkMode === p.mode ? '0 2px 8px rgba(20,40,30,.12)' : 'none',
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div style={{ marginTop: 8, fontSize: 12, color: INK_SOFT, lineHeight: 1.45 }}>{active.blurb}</div>
    </div>
  );
}

function PatientColumn({ patient }: { patient: Patient }) {
  const { startScenario } = useSugar();
  const scenarios = scenariosFor(patient.id);
  return (
    <section>
      <div
        style={{
          background: CARD,
          border: `1px solid ${LINE}`,
          borderRadius: 20,
          padding: '18px 20px',
          display: 'flex',
          gap: 14,
          alignItems: 'center',
        }}
      >
        <Avatar patient={patient} size={52} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 21 }}>{patient.name}</div>
          <div style={{ fontSize: 12.5, color: INK_SOFT, marginTop: 2 }}>
            {patient.age} · {patient.city} · {patient.occupation}
          </div>
          <div style={{ fontSize: 12.5, color: INK_SOFT, marginTop: 2 }}>
            {patient.condition_line} · <span style={{ color: GREEN_DARK, fontWeight: 600 }}>{patient.program_line}</span>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
        {scenarios.map((s) => (
          <button
            key={s.id}
            className="sugar-cell"
            onClick={() => startScenario(s.id)}
            style={{
              textAlign: 'left',
              background: CARD,
              border: `1px solid ${LINE}`,
              borderRadius: 18,
              padding: '16px 18px',
              cursor: 'pointer',
              fontFamily: BODY,
              color: INK,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: INK_SOFT }}>
                {s.day_label}
              </span>
              <span style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 17 }}>{s.title}</span>
              <span
                style={{
                  marginLeft: 'auto',
                  fontSize: 11,
                  fontWeight: 700,
                  color: GREEN_DARK,
                  background: GREEN_TINT,
                  borderRadius: 999,
                  padding: '3px 10px',
                }}
              >
                {s.chip}
              </span>
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 3 }}>
              {s.context_bullets.map((b, i) => (
                <li key={i} style={{ fontSize: 12.5, color: INK_SOFT, lineHeight: 1.45, display: 'flex', gap: 7 }}>
                  <span aria-hidden style={{ color: GREEN, flex: 'none' }}>·</span>
                  {b}
                </li>
              ))}
            </ul>
            <div style={{ marginTop: 10, fontSize: 12.5, fontWeight: 700, color: GREEN_DARK }}>
              Send the evening nudge →
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function Avatar({ patient, size, ring }: { patient: Patient; size: number; ring?: boolean }) {
  const initials = patient.name.split(' ').map((w) => w[0]).join('');
  return (
    <div
      className={ring ? undefined : undefined}
      style={{
        width: size,
        height: size,
        flex: 'none',
        borderRadius: '50%',
        background: `hsl(${patient.hue} 38% 90%)`,
        color: `hsl(${patient.hue} 45% 30%)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontWeight: 800,
        fontSize: size * 0.36,
        letterSpacing: '.02em',
      }}
    >
      {initials}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Screen 2 — the phone stage
// ═════════════════════════════════════════════════════════════════════════════

function PhoneStage() {
  const { scenario, patient, backToPicker, phase } = useSugar();
  if (!scenario || !patient) return null;
  return (
    <div
      className="sugar-stage"
      style={{
        minHeight: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--sugar-stage-gap)',
        padding: 'var(--sugar-stage-pad)',
        flexWrap: 'wrap',
      }}
    >
      <ContextPanel scenario={scenario} patient={patient} onBack={backToPicker} showBack={phase !== 'call'} />
      <PhoneFrame scenario={scenario} patient={patient} />
    </div>
  );
}

/** Audience-facing panel: exactly what the agent walks in with. */
function ContextPanel({
  scenario,
  patient,
  onBack,
  showBack,
}: {
  scenario: Scenario;
  patient: Patient;
  onBack: () => void;
  showBack: boolean;
}) {
  return (
    <aside className="sugar-context">
      {showBack && (
        <button
          onClick={onBack}
          style={{ alignSelf: 'flex-start', background: 'none', border: 'none', color: INK_SOFT, fontSize: 13, fontWeight: 600, cursor: 'pointer', padding: 0, fontFamily: BODY }}
        >
          ← All scenarios
        </button>
      )}
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.1em', textTransform: 'uppercase', color: INK_SOFT }}>
          {scenario.day_label} · {scenario.chip}
        </div>
        <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 26, color: GREEN_DARK, marginTop: 2 }}>{scenario.title}</div>
      </div>

      {showBack && <PaceToggle />}

      <PanelCard title={`What ${COACH_NAME} walks in knowing`}>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {scenario.context_bullets.map((b, i) => (
            <li key={i} style={{ fontSize: 12.5, color: INK, lineHeight: 1.5, display: 'flex', gap: 8 }}>
              <span aria-hidden style={{ color: GREEN, flex: 'none' }}>—</span>
              {b}
            </li>
          ))}
        </ul>
        <div style={{ marginTop: 10, fontSize: 11.5, color: INK_SOFT, lineHeight: 1.5 }}>
          Care plan by {patient.doctor} · full context (plan, logs, glucose, prior calls) rides the
          session payload — nothing on this call is scripted.
        </div>
      </PanelCard>

      {scenario.prior_calls.length > 0 && (
        <PanelCard title="Previous calls">
          {scenario.prior_calls.map((c, i) => (
            <div key={i} style={{ marginBottom: i < scenario.prior_calls.length - 1 ? 10 : 0 }}>
              <div style={{ fontSize: 11.5, fontWeight: 700, color: INK_SOFT }}>{c.day}</div>
              <div style={{ fontSize: 12.5, lineHeight: 1.5, marginTop: 2 }}>{c.summary}</div>
              {c.commitment && (
                <div style={{ fontSize: 12, color: AMBER, fontWeight: 600, marginTop: 3 }}>
                  Committed: {c.commitment}
                </div>
              )}
            </div>
          ))}
        </PanelCard>
      )}

      <PanelCard title="Things to try on the call" tint>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {scenario.try_hints.map((h, i) => (
            <li key={i} style={{ fontSize: 12.5, lineHeight: 1.5, display: 'flex', gap: 8 }}>
              <span aria-hidden style={{ color: AMBER, flex: 'none', fontWeight: 800 }}>{i + 1}</span>
              {h}
            </li>
          ))}
        </ul>
      </PanelCard>
    </aside>
  );
}

function PanelCard({ title, children, tint }: { title: string; children: ReactNode; tint?: boolean }) {
  return (
    <div style={{ background: tint ? AMBER_TINT : CARD, border: `1px solid ${tint ? '#EFDDBE' : LINE}`, borderRadius: 16, padding: '14px 16px' }}>
      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: tint ? AMBER : INK_SOFT, marginBottom: 8 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

// ── The device ───────────────────────────────────────────────────────────────

function PhoneFrame({ scenario, patient }: { scenario: Scenario; patient: Patient }) {
  const { phase } = useSugar();
  return (
    <div className="sugar-phone">
      <div
        style={{
          position: 'relative',
          width: '100%',
          height: '100%',
          borderRadius: 'var(--sugar-screen-radius)',
          overflow: 'hidden',
          background: phase === 'incoming' ? CALL_BG : '#FAFAF7',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* punch-hole camera — dropped on a real handset (.sugar-notch) */}
        <div className="sugar-notch" aria-hidden style={{ position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)', width: 84, height: 24, borderRadius: 14, background: '#0B0D0C', zIndex: 40 }} />
        {phase === 'incoming' && <IncomingSequence scenario={scenario} />}
        {phase === 'call' && <AppScreen scenario={scenario} patient={patient} />}
        {phase === 'ended' && <EndedScreen scenario={scenario} patient={patient} />}
      </div>
    </div>
  );
}

function StatusBar({ clock, dark }: { clock: string; dark?: boolean }) {
  const c = dark ? 'rgba(255,255,255,.92)' : INK;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 26px 6px', fontSize: 13, fontWeight: 700, color: c, zIndex: 30 }}>
      <span>{clock}</span>
      <span style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 'var(--sugar-mini)', fontWeight: 600 }}>
        5G
        <span aria-hidden style={{ display: 'inline-block', width: 22, height: 11, border: `1.5px solid ${c}`, borderRadius: 3.5, position: 'relative' }}>
          <span style={{ position: 'absolute', inset: 1.5, right: '30%', background: c, borderRadius: 1.5 }} />
        </span>
      </span>
    </div>
  );
}

// ── The signature moment: push notification + chime → Join / Snooze ─────────
// Deliberately NOT a telephony call screen — this is the app nudging the
// patient into a session, like a meeting or workout reminder.

/** Two soft ascending tones — a notification chime, not a ringtone. Plays on
 * arrival, then a quiet reminder every few seconds while the invite waits. */
function useChime(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    let alive = true;
    const chime = (gainPeak: number) => {
      if (!alive) return;
      [659.25, 880].forEach((f, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.value = f;
        const t = ctx.currentTime + i * 0.16;
        gain.gain.setValueAtTime(0, t);
        gain.gain.linearRampToValueAtTime(gainPeak, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.8);
        osc.connect(gain).connect(ctx.destination);
        osc.start(t);
        osc.stop(t + 0.85);
      });
    };
    chime(0.05);
    const iv = window.setInterval(() => chime(0.028), 5200);
    return () => {
      alive = false;
      window.clearInterval(iv);
      ctx.close().catch(() => {});
    };
  }, [active]);
}

function IncomingSequence({ scenario }: { scenario: Scenario }) {
  const { acceptCall, declineCall } = useSugar();
  const [stage, setStage] = useState<'lock' | 'invite' | 'snoozed'>('lock');
  useChime(stage === 'invite');

  useEffect(() => {
    const t = window.setTimeout(() => setStage('invite'), 1300);
    return () => window.clearTimeout(t);
  }, []);

  const snooze = () => {
    setStage('snoozed');
    window.setTimeout(declineCall, 1500);
  };

  return (
    <div style={{ position: 'relative', flex: 1, display: 'flex', flexDirection: 'column', color: '#fff' }}>
      <StatusBar clock={scenario.app.clock_label} dark />
      <div style={{ textAlign: 'center', marginTop: 84 }}>
        <div style={{ fontSize: 64, fontWeight: 300, letterSpacing: '-0.02em', fontFamily: BODY }}>
          {scenario.app.clock_label.replace(/ (AM|PM)$/, '')}
        </div>
        <div style={{ fontSize: 14.5, opacity: 0.75, marginTop: 2 }}>{scenario.app.date_label}</div>
      </div>

      {stage !== 'lock' && (
        <div
          style={{
            margin: '38px 14px 0',
            background: 'rgba(255,255,255,.15)',
            backdropFilter: 'blur(16px)',
            borderRadius: 22,
            padding: '14px 15px 13px',
            animation: 'sugarSlideDown .55s cubic-bezier(.2,.9,.3,1.1) both',
          }}
        >
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <CoachMark size={40} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontSize: 12.5, fontWeight: 800 }}>
                  {PROGRAM_NAME} · {COACH_NAME}
                </span>
                <span style={{ fontSize: 11, opacity: 0.7 }}>now</span>
              </div>
              {stage === 'snoozed' ? (
                <div style={{ fontSize: 13, lineHeight: 1.4, opacity: 0.95, marginTop: 2 }}>
                  Snoozed — I'll nudge you again at 7:15.
                </div>
              ) : (
                <div style={{ fontSize: 13, lineHeight: 1.4, opacity: 0.95, marginTop: 2 }}>
                  {scenario.nudge}
                </div>
              )}
            </div>
          </div>
          {stage === 'invite' && (
            <div style={{ display: 'flex', gap: 9, marginTop: 12 }}>
              <button
                onClick={acceptCall}
                style={{
                  flex: 1.4,
                  border: 'none',
                  borderRadius: 13,
                  padding: '11px 0',
                  background: '#2FA875',
                  color: '#fff',
                  fontSize: 13.5,
                  fontWeight: 800,
                  fontFamily: BODY,
                  cursor: 'pointer',
                  animation: 'sugarBreathe 2s ease-out infinite',
                }}
              >
                Join check-in
              </button>
              <button
                onClick={snooze}
                style={{
                  flex: 1,
                  border: 'none',
                  borderRadius: 13,
                  padding: '11px 0',
                  background: 'rgba(255,255,255,.16)',
                  color: '#fff',
                  fontSize: 13.5,
                  fontWeight: 700,
                  fontFamily: BODY,
                  cursor: 'pointer',
                }}
              >
                Snooze
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** The Sugar app mark — a droplet in a soft ring. */
function CoachMark({ size }: { size: number }) {
  return (
    <div
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: 'radial-gradient(circle at 32% 28%, #2FA875 0%, #0E7A5F 70%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flex: 'none',
      }}
    >
      <svg width={size * 0.44} height={size * 0.44} viewBox="0 0 24 24" fill="none">
        <path d="M12 3 C12 3 6 10.2 6 14.4 C6 17.9 8.7 20.5 12 20.5 C15.3 20.5 18 17.9 18 14.4 C18 10.2 12 3 12 3 Z" fill="#fff" opacity=".95" />
      </svg>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// The app's Today screen (live call)
// ═════════════════════════════════════════════════════════════════════════════

function AppScreen({ scenario, patient }: { scenario: Scenario; patient: Patient }) {
  const { highlightSection, videoOpen, summary } = useSugar();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!highlightSection) return;
    const el = scrollRef.current?.querySelector(`[data-sec="${highlightSection}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [highlightSection]);

  return (
    <div style={{ position: 'relative', flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <StatusBar clock={scenario.app.clock_label} />
      <div style={{ padding: '8px 12px 4px' }}>
        <SugarCallSession />
      </div>
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '8px 12px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Greeting scenario={scenario} patient={patient} />
        <FlagBanner doctor={patient.doctor} />
        <Section k="glucose" title="Glucose" highlight={highlightSection}>
          <GlucoseCard />
        </Section>
        <Section k="meals" title="Food" highlight={highlightSection}>
          <MealsCard />
        </Section>
        <Section k="activity" title="Activity" highlight={highlightSection}>
          <ActivityCard goal={patient.plan.exercise} />
        </Section>
        <Section k="meds" title="Medications" highlight={highlightSection}>
          <MedsCard />
        </Section>
        <Section k="summary" title="Tomorrow" highlight={highlightSection}>
          <CommitmentCard />
        </Section>
        <Section k="plan" title={`Care plan · ${patient.doctor}`} highlight={highlightSection}>
          <PlanCard patient={patient} />
        </Section>
      </div>
      {videoOpen && <VideoOverlay />}
      {summary && !videoOpen && <SummarySheet />}
    </div>
  );
}

function Greeting({ scenario, patient }: { scenario: Scenario; patient: Patient }) {
  const { meals } = useSugar();
  const kcal = meals.reduce((s, m) => s + m.total_calories, 0);
  return (
    <div style={{ padding: '6px 6px 2px', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
      <div>
        <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 22, color: INK }}>
          Good evening, {patient.first_name}
        </div>
        <div style={{ fontSize: 11.5, color: INK_SOFT, marginTop: 1 }}>{scenario.app.date_label}</div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: GREEN_DARK }}>{kcal > 0 ? `${kcal.toLocaleString('en-IN')} kcal` : '—'}</div>
        <div style={{ fontSize: 'var(--sugar-mini)', color: INK_SOFT }}>
          {scenario.app.streak_days > 0 ? `logged today · ${scenario.app.streak_days}-day streak` : 'logged today'}
        </div>
      </div>
    </div>
  );
}

function Section({ k, title, highlight, children }: { k: string; title: string; highlight: string | null; children: ReactNode }) {
  return (
    <section data-sec={k} className={highlight === k ? 'sugar-hl' : undefined}>
      <div style={{ fontSize: 'var(--sugar-mini)', fontWeight: 800, letterSpacing: '.09em', textTransform: 'uppercase', color: INK_SOFT, margin: '2px 6px 5px' }}>
        {title}
      </div>
      {children}
    </section>
  );
}

function Card({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{ background: CARD, border: `1px solid ${LINE}`, borderRadius: 18, padding: '12px 14px', ...style }}>
      {children}
    </div>
  );
}

// ── Glucose ─────────────────────────────────────────────────────────────────

function GlucoseCard() {
  const { glucose, glucoseFocus, sensorOrder } = useSugar();
  if (!glucose) return null;
  if (glucose.status === 'expired') {
    return (
      <Card>
        <div style={{ height: 96, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, borderRadius: 12, background: '#F3F2ED', border: `1px dashed ${LINE}` }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: INK_SOFT }}>Sensor expired {glucose.expired_since}</div>
          <div style={{ fontSize: 11.5, color: INK_SOFT }}>No readings for 3 days</div>
        </div>
        {sensorOrder !== 'none' && <SensorRenewalCard />}
      </Card>
    );
  }
  return (
    <Card>
      <GlucoseChart glucose={glucose} focusLabel={glucoseFocus?.time_label} focusNote={glucoseFocus?.note} />
      {sensorOrder !== 'none' && <SensorRenewalCard />}
    </Card>
  );
}

/**
 * Single-series CGM line: thin 2px stroke, recessive grid, a shaded 70–180
 * target band, and one direct-labeled event marker (no legend — the section
 * title names the series).
 */
function GlucoseChart({ glucose, focusLabel, focusNote }: { glucose: GlucoseDay; focusLabel?: string; focusNote?: string }) {
  const W = 316;
  const H = 118;
  const X0 = 8;
  const X1 = W - 8;
  const [vMin, vMax] = [60, 240];
  const x = (h: number) => X0 + ((h - 6) / 14) * (X1 - X0);
  const y = (v: number) => 10 + (1 - (v - vMin) / (vMax - vMin)) * (H - 32);
  const pts = glucose.points;
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.h).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');

  // The focused event: match by time label (the brain zooms before it asks).
  const focused = focusLabel
    ? glucose.events.find((e) => e.time_label.toLowerCase().includes(focusLabel.toLowerCase().replace(/around |about /g, '').trim())) ?? glucose.events[0]
    : undefined;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', display: 'block' }} role="img" aria-label="Glucose readings through the day">
        {/* target band 70–180 */}
        <rect x={X0} y={y(180)} width={X1 - X0} height={y(70) - y(180)} rx={6} fill="rgba(14,122,95,.07)" />
        <text x={X0 + 4} y={y(180) + 10} fontSize={8} fill={INK_SOFT}>180</text>
        <text x={X0 + 4} y={y(70) - 3} fontSize={8} fill={INK_SOFT}>70</text>
        {/* recessive hour ticks */}
        {[6, 10, 14, 18].map((h) => (
          <g key={h}>
            <line x1={x(h)} y1={12} x2={x(h)} y2={H - 20} stroke={LINE} strokeWidth={0.6} />
            <text x={x(h)} y={H - 8} fontSize={8} fill={INK_SOFT} textAnchor="middle">
              {h === 12 ? '12 PM' : h > 12 ? `${h - 12} PM` : `${h} AM`}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke={GREEN} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {/* event markers */}
        {glucose.events.map((e, i) => {
          const isFocus = focused && e.time_label === focused.time_label;
          return (
            <g key={i}>
              {isFocus && (
                <>
                  <line x1={x(e.h)} y1={12} x2={x(e.h)} y2={H - 20} stroke={AMBER} strokeWidth={1} strokeDasharray="3 3" />
                  <circle cx={x(e.h)} cy={y(e.v)} r={9} fill="none" stroke={AMBER} strokeWidth={1.6} className="sugar-pulse" />
                </>
              )}
              <circle cx={x(e.h)} cy={y(e.v)} r={4} fill={isFocus ? AMBER : GREEN_DARK} stroke="#fff" strokeWidth={1.6} />
              <text
                x={Math.min(x(e.h), X1 - 44)}
                y={Math.max(y(e.v) - 10, 10)}
                fontSize={9}
                fontWeight={700}
                fill={isFocus ? AMBER : INK_SOFT}
              >
                {e.v} · {e.time_label}
              </text>
            </g>
          );
        })}
      </svg>
      {focused && (
        <div className="sugar-fresh" style={{ marginTop: 6, fontSize: 11.5, fontWeight: 600, color: AMBER, background: AMBER_TINT, borderRadius: 10, padding: '6px 10px' }}>
          {focusNote || focused.note} — {focused.time_label}
        </div>
      )}
    </div>
  );
}

function SensorRenewalCard() {
  const { sensorOrder, tapSensorOrder } = useSugar();
  if (sensorOrder === 'ordered') {
    return (
      <div className="sugar-fresh" style={{ marginTop: 10, display: 'flex', gap: 10, alignItems: 'center', background: GREEN_TINT, borderRadius: 14, padding: '11px 13px' }}>
        <span aria-hidden style={{ color: GREEN_DARK, fontWeight: 800, fontSize: 16 }}>✓</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: GREEN_DARK }}>Replacement sensor ordered</div>
          <div style={{ fontSize: 11.5, color: INK_SOFT }}>Arrives tomorrow · billed to your plan</div>
        </div>
      </div>
    );
  }
  return (
    <div className="sugar-fresh" style={{ marginTop: 10, background: '#FDFCF8', border: `1px solid ${LINE}`, borderRadius: 14, padding: '11px 13px', display: 'flex', gap: 12, alignItems: 'center' }}>
      <div aria-hidden style={{ width: 40, height: 40, borderRadius: 12, background: GREEN_TINT, display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
        <span style={{ width: 18, height: 18, borderRadius: '50%', border: `3px solid ${GREEN}`, display: 'inline-block' }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>14-day glucose sensor</div>
        <div style={{ fontSize: 11.5, color: INK_SOFT }}>₹3,999 · ships tomorrow</div>
      </div>
      <button
        onClick={tapSensorOrder}
        style={{ border: 'none', background: GREEN, color: '#fff', borderRadius: 10, padding: '8px 13px', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: BODY }}
      >
        Order
      </button>
    </div>
  );
}

// ── Food / activity / meds ──────────────────────────────────────────────────

const MEAL_LABEL: Record<string, string> = {
  breakfast: 'Breakfast',
  lunch: 'Lunch',
  snack: 'Snack',
  dinner: 'Dinner',
  other: 'Meal',
};

function MealsCard() {
  const { meals } = useSugar();
  return (
    <Card>
      {meals.length === 0 && <Empty label="Nothing logged yet — tell the coach what you ate" />}
      {meals.map((m, i) => (
        <div
          key={m.id}
          className={m.fresh ? 'sugar-fresh' : undefined}
          style={{ padding: '8px 2px', borderTop: i > 0 ? `1px solid ${LINE}` : 'none' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ fontSize: 13, fontWeight: 800 }}>
              {MEAL_LABEL[m.meal_type] ?? m.meal_type}
              <span style={{ fontWeight: 600, color: INK_SOFT, fontSize: 11.5, marginLeft: 7 }}>{m.time_label}</span>
            </span>
            <span style={{ fontSize: 12.5, fontWeight: 800, color: GREEN_DARK }}>{m.total_calories} kcal</span>
          </div>
          <div style={{ marginTop: 3, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {m.items.map((it, j) => (
              <div key={j} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: INK_SOFT }}>
                <span>
                  {it.name} <span style={{ opacity: 0.75 }}>× {it.quantity}</span>
                </span>
                <span>{it.calories}</span>
              </div>
            ))}
          </div>
          {m.note && <div style={{ fontSize: 11, color: INK_SOFT, marginTop: 3, fontStyle: 'italic' }}>{m.note}</div>}
        </div>
      ))}
    </Card>
  );
}

function ActivityCard({ goal }: { goal: string }) {
  const { activities } = useSugar();
  return (
    <Card>
      {activities.length === 0 && <Empty label="No activity yet today" />}
      {activities.map((a, i) => (
        <div
          key={a.id}
          className={a.fresh ? 'sugar-fresh' : undefined}
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '7px 2px', borderTop: i > 0 ? `1px solid ${LINE}` : 'none' }}
        >
          <span style={{ fontSize: 13, fontWeight: 700 }}>
            {a.kind}
            <span style={{ fontWeight: 600, color: INK_SOFT, fontSize: 11.5, marginLeft: 7 }}>{a.time_label}</span>
          </span>
          <span style={{ fontSize: 12.5, fontWeight: 800, color: GREEN_DARK }}>{a.duration_min} min</span>
        </div>
      ))}
      <div style={{ marginTop: 8, fontSize: 11, color: INK_SOFT, borderTop: `1px dashed ${LINE}`, paddingTop: 7 }}>
        Plan: {goal}
      </div>
    </Card>
  );
}

function MedsCard() {
  const { meds } = useSugar();
  return (
    <Card>
      {meds.map((m, i) => (
        <div key={m.name + i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 2px', borderTop: i > 0 ? `1px solid ${LINE}` : 'none' }}>
          <MedTick status={m.status} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 700 }}>{m.name}</div>
            <div style={{ fontSize: 11, color: INK_SOFT }}>{m.timing}</div>
          </div>
          <span style={{ fontSize: 11, fontWeight: 700, color: m.status === 'taken' ? GREEN_DARK : m.status === 'missed' ? AMBER : INK_SOFT }}>
            {m.status === 'pending' ? '' : m.status}
            {m.time_label && m.status === 'taken' ? ` · ${m.time_label}` : ''}
          </span>
        </div>
      ))}
    </Card>
  );
}

function MedTick({ status }: { status: string }) {
  const done = status === 'taken';
  const missed = status === 'missed' || status === 'skipped';
  return (
    <span
      aria-hidden
      style={{
        width: 20,
        height: 20,
        flex: 'none',
        borderRadius: 7,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 12,
        fontWeight: 800,
        color: '#fff',
        background: done ? GREEN : missed ? AMBER : 'transparent',
        border: done || missed ? 'none' : `2px solid ${LINE}`,
      }}
    >
      {done ? '✓' : missed ? '–' : ''}
    </span>
  );
}

function Empty({ label }: { label: string }) {
  return <div style={{ fontSize: 12, color: INK_SOFT, padding: '6px 2px' }}>{label}</div>;
}

// ── Commitment / plan / flags ───────────────────────────────────────────────

function CommitmentCard() {
  const { commitment } = useSugar();
  if (!commitment) {
    return (
      <Card>
        <Empty label="Your commitment for tomorrow lands here at the end of the call" />
      </Card>
    );
  }
  return (
    <Card style={{ borderLeft: `4px solid ${AMBER}`, background: AMBER_TINT }}>
      <div className="sugar-fresh">
        <div style={{ fontSize: 13.5, fontWeight: 700, lineHeight: 1.4 }}>{commitment.text}</div>
        {commitment.when && <div style={{ fontSize: 11.5, color: INK_SOFT, marginTop: 3 }}>{commitment.when}</div>}
      </div>
    </Card>
  );
}

function PlanCard({ patient }: { patient: Patient }) {
  return (
    <Card>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        <PlanRow k="Diet">
          {patient.plan.diet.map((d, i) => (
            <div key={i} style={{ fontSize: 12, lineHeight: 1.45 }}>· {d}</div>
          ))}
        </PlanRow>
        <PlanRow k="Exercise">
          <div style={{ fontSize: 12, lineHeight: 1.45 }}>{patient.plan.exercise}</div>
        </PlanRow>
        <PlanRow k="Medication">
          {patient.plan.medications.map((m, i) => (
            <div key={i} style={{ fontSize: 12, lineHeight: 1.45 }}>
              {m.name} — {m.timing}
            </div>
          ))}
        </PlanRow>
        <PlanRow k="Monitoring">
          <div style={{ fontSize: 12, lineHeight: 1.45 }}>{patient.plan.monitoring}</div>
        </PlanRow>
      </div>
    </Card>
  );
}

function PlanRow({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 'var(--sugar-micro)', fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: INK_SOFT, marginBottom: 2 }}>{k}</div>
      {children}
    </div>
  );
}

function FlagBanner({ doctor }: { doctor: string }) {
  const { flags } = useSugar();
  if (flags.length === 0) return null;
  return (
    <div className="sugar-fresh" style={{ background: AMBER_TINT, border: '1px solid #EFDDBE', borderRadius: 14, padding: '10px 13px' }}>
      {flags.map((f, i) => (
        <div key={i} style={{ display: 'flex', gap: 9, alignItems: 'flex-start', marginTop: i > 0 ? 6 : 0 }}>
          <span aria-hidden style={{ color: AMBER, fontWeight: 800, fontSize: 13, flex: 'none' }}>⚑</span>
          <div>
            <div style={{ fontSize: 12.5, fontWeight: 700, color: '#8A5A12' }}>
              Flagged for {doctor} — {f.topic}
            </div>
            {f.detail && <div style={{ fontSize: 11.5, color: INK_SOFT, marginTop: 1 }}>{f.detail}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Video overlay (agent-driven YouTube, with sound) ────────────────────────

let ytReady: Promise<void> | null = null;
function loadYT(): Promise<void> {
  if (ytReady) return ytReady;
  ytReady = new Promise<void>((resolve) => {
    const w = window as unknown as { YT?: { Player?: unknown }; onYouTubeIframeAPIReady?: () => void };
    if (w.YT && w.YT.Player) {
      resolve();
      return;
    }
    const prev = w.onYouTubeIframeAPIReady;
    w.onYouTubeIframeAPIReady = () => {
      prev?.();
      resolve();
    };
    const tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(tag);
  });
  return ytReady;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function VideoOverlay() {
  const { videoCmd, videoTitle, closeVideo } = useSugar();
  const playerRef = useRef<any>(null);
  const readyRef = useRef(false);
  const lastNonce = useRef(0);
  const pendingRef = useRef<typeof videoCmd>(null);

  const applyCmd = (cmd: NonNullable<typeof videoCmd>) => {
    const p = playerRef.current;
    if (!p) return;
    try {
      // Unlike a muted explainer clip, this video is FOR the patient — sound on.
      p.unMute?.();
      if (cmd.action === 'play' && cmd.youtubeId) p.loadVideoById({ videoId: cmd.youtubeId, startSeconds: cmd.startSec ?? 0 });
      else if (cmd.action === 'pause') p.pauseVideo();
      else if (cmd.action === 'resume') p.playVideo();
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    let cancelled = false;
    loadYT().then(() => {
      if (cancelled) return;
      const YT = (window as any).YT;
      playerRef.current = new YT.Player('sugar-yt-player', {
        playerVars: { rel: 0, modestbranding: 1, playsinline: 1, controls: 1 },
        events: {
          onReady: () => {
            readyRef.current = true;
            if (pendingRef.current) {
              applyCmd(pendingRef.current);
              pendingRef.current = null;
            }
          },
        },
      });
    });
    return () => {
      cancelled = true;
      try {
        playerRef.current?.destroy();
      } catch {
        /* ignore */
      }
      playerRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!videoCmd || videoCmd.nonce === lastNonce.current) return;
    lastNonce.current = videoCmd.nonce;
    if (!readyRef.current) {
      pendingRef.current = videoCmd;
      return;
    }
    applyCmd(videoCmd);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoCmd]);

  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 60, background: 'rgba(12,20,17,.88)', backdropFilter: 'blur(6px)', display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: 14, animation: 'sugarFadeUp .35s ease both' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#fff', padding: '0 4px 10px' }}>
        <div style={{ fontSize: 13.5, fontWeight: 700 }}>{videoTitle}</div>
        <button onClick={closeVideo} style={{ background: 'rgba(255,255,255,.16)', border: 'none', color: '#fff', borderRadius: 9, width: 27, height: 27, cursor: 'pointer', fontSize: 13 }} aria-label="Close video">
          ✕
        </button>
      </div>
      <div style={{ background: '#000', borderRadius: 16, overflow: 'hidden', aspectRatio: '16 / 9' }}>
        <div id="sugar-yt-player" style={{ width: '100%', height: '100%' }} />
      </div>
      <div style={{ color: 'rgba(255,255,255,.75)', fontSize: 11.5, textAlign: 'center', marginTop: 10 }}>
        The coach is still on the line — just talk to pause.
      </div>
    </div>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ── Summary sheet (end of call) ─────────────────────────────────────────────

function SummarySheet() {
  const { summary, commitment } = useSugar();
  if (!summary) return null;
  return (
    <div style={{ position: 'absolute', left: 10, right: 10, bottom: 12, zIndex: 50, background: CARD, borderRadius: 20, boxShadow: '0 18px 50px rgba(15,35,28,.35)', border: `1px solid ${LINE}`, padding: '15px 17px', animation: 'sugarFadeUp .45s cubic-bezier(.2,.9,.3,1.1) both' }}>
      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.09em', textTransform: 'uppercase', color: GREEN_DARK, marginBottom: 8 }}>
        Today, in the book
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {summary.lines.map((l, i) => (
          <div key={i} style={{ fontSize: 12.5, lineHeight: 1.45, display: 'flex', gap: 8 }}>
            <span aria-hidden style={{ color: GREEN, flex: 'none', fontWeight: 800 }}>✓</span>
            {l}
          </div>
        ))}
        {summary.flagged && (
          <div style={{ fontSize: 12.5, lineHeight: 1.45, display: 'flex', gap: 8 }}>
            <span aria-hidden style={{ color: AMBER, flex: 'none', fontWeight: 800 }}>⚑</span>
            {summary.flagged}
          </div>
        )}
      </div>
      {commitment && (
        <div style={{ marginTop: 9, paddingTop: 9, borderTop: `1px dashed ${LINE}`, fontSize: 12.5 }}>
          <span style={{ fontWeight: 800, color: AMBER }}>Tomorrow: </span>
          {commitment.text}
        </div>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Ended screen
// ═════════════════════════════════════════════════════════════════════════════

function EndedScreen({ scenario, patient }: { scenario: Scenario; patient: Patient }) {
  const { summary, commitment, flags, sensorOrder, backToPicker } = useSugar();
  return (
    <div className="sugar-ended" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', color: '#fff', background: CALL_BG, padding: '0 24px 30px' }}>
      <StatusBar clock={scenario.app.clock_label} dark />
      <div style={{ textAlign: 'center', marginTop: 40 }}>
        <CoachMark size={72} />
        <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 24, marginTop: 14 }}>Check-in complete</div>
        <div style={{ fontSize: 12.5, opacity: 0.7, marginTop: 3 }}>
          Next check-in — tomorrow, 7:00 PM
        </div>
      </div>

      <div style={{ marginTop: 26, background: 'rgba(255,255,255,.10)', borderRadius: 18, padding: '14px 16px', backdropFilter: 'blur(8px)' }}>
        <div style={{ fontSize: 'var(--sugar-mini)', fontWeight: 800, letterSpacing: '.09em', textTransform: 'uppercase', opacity: 0.7, marginBottom: 8 }}>
          Today, in the book
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {(summary?.lines ?? ['Check-in complete — logs updated by voice']).map((l, i) => (
            <div key={i} style={{ fontSize: 12.5, lineHeight: 1.45, display: 'flex', gap: 8 }}>
              <span aria-hidden style={{ color: '#7BD9BE', flex: 'none', fontWeight: 800 }}>✓</span>
              {l}
            </div>
          ))}
          {flags.map((f, i) => (
            <div key={`f${i}`} style={{ fontSize: 12.5, lineHeight: 1.45, display: 'flex', gap: 8 }}>
              <span aria-hidden style={{ color: '#F2C063', flex: 'none', fontWeight: 800 }}>⚑</span>
              Sent to {patient.doctor}: {f.topic}
            </div>
          ))}
          {sensorOrder === 'ordered' && (
            <div style={{ fontSize: 12.5, lineHeight: 1.45, display: 'flex', gap: 8 }}>
              <span aria-hidden style={{ color: '#7BD9BE', flex: 'none', fontWeight: 800 }}>✓</span>
              Replacement sensor ordered — arrives tomorrow
            </div>
          )}
        </div>
        {commitment && (
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,.15)', fontSize: 12.5 }}>
            <span style={{ fontWeight: 800, color: '#F2C063' }}>Tomorrow: </span>
            {commitment.text}
          </div>
        )}
      </div>

      <button
        onClick={backToPicker}
        style={{ marginTop: 'auto', alignSelf: 'center', background: 'rgba(255,255,255,.14)', border: '1px solid rgba(255,255,255,.25)', color: '#fff', borderRadius: 14, padding: '11px 22px', fontSize: 13.5, fontWeight: 700, cursor: 'pointer', fontFamily: BODY }}
      >
        Back to scenarios
      </button>
    </div>
  );
}
