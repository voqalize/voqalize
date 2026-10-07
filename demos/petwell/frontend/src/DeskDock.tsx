/**
 * Tushar's dock — the one call surface on the site, bottom right, the way a
 * site's live assistant sits in its corner. It holds everything about the call:
 * the button that starts it, his face while it runs, what he is saying, and the
 * mute and end-call controls.
 *
 * Before a call it is a compact bar — a monogram, one line about who he is, and
 * the call button — so nothing has to squeeze into a tile. While the call runs
 * it opens into a card with the `tushar` character from `@voqalize/avatar`,
 * driven entirely by the `avatar` messages Voqalize sends on the call's data
 * channel; the face downloads only then. On a tablet or phone the card is a
 * slim bar along the bottom of the screen instead.
 *
 * The brain speaks with `omnivoice/gaurav`, the first voice the runtime suggests
 * for him and the one that speaks all ten of his languages, so the face and the
 * voice are one person in every one.
 */

import type { PipecatClient } from '@pipecat-ai/client-js';
import { usePipecatClientMicControl } from '@pipecat-ai/client-react';
import { TranscriptOverlay } from '@pipecat-ai/voice-ui-kit';
import '@pipecat-ai/voice-ui-kit/styles.scoped';
import { Avatar } from '@voqalize/avatar/react';
import type { AmbientPresenceActivity } from '@voqalize/demo-kit';
import { Languages, Loader2, Mic, MicOff, Phone, PhoneOff, RotateCcw } from 'lucide-react';
import { NATIVE_NAME, strings } from './i18n';
import { useSite } from './store';

export const DESK_NAME = 'Tushar';

/** Not live: the call can be started, is starting, or failed to start. */
export function DeskInvite({
  connecting,
  error,
  onStart,
}: {
  connecting: boolean;
  error: string;
  onStart: () => void | Promise<void>;
}) {
  const t = strings(useSite().lang);
  const failed = !!error && !connecting;
  return (
    <div className={`pw-dock-bar${failed ? ' is-error' : ''}`} role="region" aria-label={t.talk}>
      <span className="pw-dock-mark" aria-hidden>
        T
      </span>
      <span className="pw-dock-who">
        <strong>{DESK_NAME}</strong>
        <small title={failed ? error : `${t.deskRole} · ${t.deskLangs}`}>
          {connecting ? (
            t.connecting
          ) : failed ? (
            error
          ) : (
            <>
              {t.deskRole}
              <span className="pw-dock-langs"> · {t.deskLangs}</span>
            </>
          )}
        </small>
      </span>
      <button
        className={`pw-dock-call${connecting ? ' is-connecting' : ''}`}
        onClick={onStart}
        disabled={connecting}
        title={failed ? t.retry : t.talk}
        aria-label={failed ? t.retry : t.talk}
      >
        {connecting ? <Loader2 size={20} className="pw-spin" /> : failed ? <RotateCcw size={19} /> : <Phone size={19} />}
        <span>{failed ? t.retry : t.call}</span>
      </button>
      <style>{CSS}</style>
    </div>
  );
}

/** Live: Tushar's face, what he is saying, and the call's controls. Mounted
 * inside the call's provider, which the mic control needs. */
export function DeskLive({
  client,
  activity,
  onEnd,
  live,
}: {
  client: PipecatClient;
  activity: AmbientPresenceActivity;
  onEnd: () => void;
  /** False while the call connects: mounted, hidden, the face warming up. */
  live: boolean;
}) {
  const site = useSite();
  const t = strings(site.lang);
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const state = isMicEnabled ? t.deskState[activity] : t.muted;
  return (
    <figure
      className={`pw-dock-live is-${activity}${isMicEnabled ? '' : ' is-muted'}${live ? '' : ' is-pending'}`}
      aria-label={DESK_NAME}
      aria-hidden={!live}
    >
      <div className="pw-dock-stage">
        <Avatar client={client} character="tushar" aria-label={`${DESK_NAME}, Petwell front desk`} />
        <span className="pw-dock-pill">
          <i />
          {state}
        </span>
      </div>
      <div className="pw-dock-body">
        <figcaption className="pw-dock-head">
          <span className="pw-dock-who">
            <strong>{DESK_NAME}</strong>
            <small className="pw-dock-state-inline">{state}</small>
          </span>
          <span className="pw-dock-lang" title={t.speaks}>
            <Languages size={13} />
            {NATIVE_NAME[site.voiceLanguage] ?? site.voiceLanguage}
          </span>
        </figcaption>
        <div className="vkui-root pw-dock-captions">
          <TranscriptOverlay participant="remote" size="sm" />
        </div>
        <div className="pw-dock-controls">
          <button
            className={`pw-dock-btn${isMicEnabled ? '' : ' is-off'}`}
            onClick={() => enableMic(!isMicEnabled)}
            title={isMicEnabled ? t.mute : t.unmute}
            aria-label={isMicEnabled ? t.mute : t.unmute}
            aria-pressed={!isMicEnabled}
          >
            {isMicEnabled ? <Mic size={18} /> : <MicOff size={18} />}
            <span>{isMicEnabled ? t.mute : t.unmute}</span>
          </button>
          <button className="pw-dock-btn is-end" onClick={onEnd} title={t.endCall} aria-label={t.endCall}>
            <PhoneOff size={18} />
            <span>{t.endCall}</span>
          </button>
        </div>
      </div>
      <style>{CSS}</style>
    </figure>
  );
}

const CSS = `
.pw-dock-bar, .pw-dock-live { font-family: inherit; color: #1f1b2e; background: #fff; border: 1.5px solid #e4defa;
  box-shadow: 0 14px 40px rgba(31,27,46,.22); }
.pw-dock-bar { display: flex; align-items: center; gap: 12px; padding: 10px 10px 10px 12px; border-radius: 999px; }
.pw-dock-bar.is-error { border-color: #fda29b; }
.pw-dock-mark { flex: 0 0 auto; width: 44px; height: 44px; border-radius: 50%; background: #5c42bf; color: #fff;
  display: grid; place-items: center; font-weight: 800; font-size: 19px; }
.pw-dock-who { display: flex; flex-direction: column; min-width: 0; flex: 1; line-height: 1.25; }
.pw-dock-who strong { font-size: 15px; color: #4a3596; }
.pw-dock-who small { font-size: 12px; color: #6b6880; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pw-dock-bar .pw-dock-who { flex: 0 1 auto; padding-right: 4px; }
@media (max-width: 480px) { .pw-dock-langs { display: none; } }
.pw-dock-bar.is-error .pw-dock-who small { color: #d92d20; }
.pw-dock-call { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 7px; height: 44px; padding: 0 18px 0 15px;
  border: 0; border-radius: 999px; background: #5c42bf; color: #fff !important; font-weight: 700; font-size: 14px;
  cursor: pointer; box-shadow: 0 0 0 0 rgba(92,66,191,.45); animation: pw-dock-ring 2.4s ease-out infinite; }
.pw-dock-call:hover { background: #4a3596; }
.pw-dock-call.is-connecting { animation: none; background: #a99ae0; cursor: default; }
@keyframes pw-dock-ring { 0% { box-shadow: 0 0 0 0 rgba(92,66,191,.45); } 70%, 100% { box-shadow: 0 0 0 12px rgba(92,66,191,0); } }
.pw-spin { animation: pw-spin .9s linear infinite; }
@keyframes pw-spin { to { transform: rotate(360deg); } }

.pw-dock-live { margin: 0; border-radius: 22px; overflow: hidden; transition: border-color .2s, box-shadow .2s; }
/* Mounted before the call is live so the face warms up out of sight. */
.pw-dock-live.is-pending { position: absolute; right: 0; bottom: 0; visibility: hidden; pointer-events: none; }
.pw-dock-live.is-speaking { border-color: #5c42bf; box-shadow: 0 0 0 4px rgba(92,66,191,.2), 0 14px 40px rgba(31,27,46,.22); }
.pw-dock-live.is-listening { border-color: #a78bfa; }
.pw-dock-stage { position: relative; aspect-ratio: 1 / 1; background: linear-gradient(180deg, #f4f1ff, #e9e3ff); }
.pw-dock-stage > :not(style):not(.pw-dock-pill) { position: absolute; inset: 0; width: 100%; height: 100%; }
.pw-dock-pill { position: absolute; left: 10px; top: 10px; z-index: 2; display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 999px; background: rgba(255,255,255,.92); font-size: 11.5px; font-weight: 700; color: #4a3596;
  box-shadow: 0 2px 8px rgba(31,27,46,.12); }
.pw-dock-pill i { width: 7px; height: 7px; border-radius: 50%; background: #12b76a; }
.pw-dock-live.is-speaking .pw-dock-pill i { background: #5c42bf; animation: pw-dock-blink 1s ease-in-out infinite; }
.pw-dock-live.is-listening .pw-dock-pill i { background: #a78bfa; }
.pw-dock-live.is-thinking .pw-dock-pill i { background: #f79009; }
.pw-dock-live.is-muted .pw-dock-pill i { background: #9ca3af; }
@keyframes pw-dock-blink { 50% { opacity: .35; } }
.pw-dock-body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 8px; }
.pw-dock-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.pw-dock-state-inline { display: none; }
.pw-dock-lang { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 999px;
  background: #f4f1ff; color: #5c42bf; font-size: 12px; font-weight: 700; }
.pw-dock-captions { display: flex; min-height: 38px; }
.pw-dock-captions > :not(style) { max-width: 100%; padding: 0; background: transparent !important; color: #1f1b2e !important;
  font-size: 13px; line-height: 1.45; text-align: left; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden; }
.pw-dock-captions * { background: transparent !important; color: inherit !important; }
.pw-dock-controls { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.pw-dock-btn { display: inline-flex; align-items: center; justify-content: center; gap: 7px; height: 40px; border-radius: 12px;
  border: 1.5px solid #e4defa; background: #fff; color: #4a3596 !important; font-weight: 700; font-size: 13.5px; cursor: pointer; }
.pw-dock-btn:hover { background: #f4f1ff; }
.pw-dock-btn.is-off { background: #fff4e5; border-color: #fedf89; color: #b54708 !important; }
.pw-dock-btn.is-end { background: #d92d20; border-color: #d92d20; color: #fff !important; }
.pw-dock-btn.is-end:hover { background: #b42318; }

/* Tablet and phone: the live card becomes a slim bar along the bottom —
   thumbnail, name and state, and the two controls as round buttons — so it never
   covers the booking drawer or the page. */
@media (max-width: 1000px) {
  .pw-dock-bar { border-radius: 18px; padding: 8px 8px 8px 10px; gap: 10px; }
  .pw-dock-mark { width: 40px; height: 40px; font-size: 17px; }
  .pw-dock-call { height: 42px; padding: 0 16px 0 13px; }
  .pw-dock-live { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 18px; }
  .pw-dock-stage { flex: 0 0 auto; width: 60px; border-radius: 14px; overflow: hidden; }
  .pw-dock-pill, .pw-dock-captions, .pw-dock-btn span { display: none; }
  .pw-dock-body { flex: 1; min-width: 0; padding: 0; flex-direction: row; align-items: center; gap: 8px; }
  .pw-dock-head { flex: 1; min-width: 0; flex-direction: column; align-items: flex-start; gap: 2px; }
  .pw-dock-state-inline { display: block; }
  .pw-dock-lang { padding: 1px 7px; font-size: 11px; }
  .pw-dock-head .pw-dock-lang { display: none; }
  .pw-dock-controls { display: flex; gap: 6px; }
  .pw-dock-btn { width: 42px; height: 42px; padding: 0; border-radius: 50%; }
}
@media (prefers-reduced-motion: reduce) {
  .pw-dock-call, .pw-spin, .pw-dock-live .pw-dock-pill i { animation: none; }
}
`;
