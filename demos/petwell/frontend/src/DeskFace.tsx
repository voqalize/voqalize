/**
 * Tushar, at the Petwell front desk — a small video-call tile docked over the
 * website, the way a site's live assistant sits in its corner.
 *
 * He is the `tushar` character from `@voqalize/avatar`, named rather than
 * imported, driven entirely by the `avatar` messages Voqalize already sends on
 * the data channel the call has. The brain speaks with `omnivoice/gaurav`, the
 * first voice the runtime suggests for him — and the voice that speaks all ten
 * of his languages — so the face and the voice are one person in every one.
 *
 * The tile mounts the face only once there is a live client — a visitor who
 * never calls never downloads him — and wears a monogram plate until then. The
 * sentence he is speaking is printed under his face, so the site still reads
 * with the sound off.
 */

import type { PipecatClient } from '@pipecat-ai/client-js';
import { TranscriptOverlay } from '@pipecat-ai/voice-ui-kit';
import '@pipecat-ai/voice-ui-kit/styles.scoped';
import { Avatar } from '@voqalize/avatar/react';
import type { AmbientPresenceActivity } from '@voqalize/demo-kit';
import { strings } from './i18n';
import { useSite } from './store';

export const DESK_NAME = 'Tushar';

export function DeskFace({
  client,
  activity,
}: {
  client: PipecatClient | null;
  activity: AmbientPresenceActivity;
}) {
  const t = strings(useSite().lang);
  const live = client !== null;
  return (
    <figure className={`pw-face is-${live ? activity : 'offline'}`}>
      <div className="pw-face-stage">
        {live ? (
          <Avatar client={client} character="tushar" aria-label={`${DESK_NAME}, Petwell front desk`} />
        ) : (
          <div className="pw-face-plate">
            <span className="pw-face-mark">T</span>
            <span className="pw-face-hint">{t.deskHint}</span>
          </div>
        )}
      </div>
      <figcaption className="pw-face-meta">
        <span className="pw-face-name">
          {DESK_NAME} <small>· {t.deskRole}</small>
        </span>
        <span className="pw-face-state">{live ? t.deskState[activity] : t.deskOffline}</span>
      </figcaption>
      {live ? (
        <div className="vkui-root pw-face-captions">
          <TranscriptOverlay participant="remote" size="sm" />
        </div>
      ) : (
        <p className="pw-face-speaks">{t.speaks}</p>
      )}
      <style>{CSS}</style>
    </figure>
  );
}

const CSS = `
.pw-face { margin: 0; background: #fff; border-radius: 20px; overflow: hidden;
  box-shadow: 0 14px 40px rgba(31,27,46,.22); border: 1.5px solid #e4defa; transition: box-shadow .2s, border-color .2s; }
.pw-face.is-speaking { border-color: #5c42bf; box-shadow: 0 0 0 4px rgba(92,66,191,.2), 0 14px 40px rgba(31,27,46,.22); }
.pw-face.is-listening { border-color: #a78bfa; }
.pw-face-stage { position: relative; aspect-ratio: 1 / 1; background: linear-gradient(180deg, #f4f1ff, #e9e3ff); }
.pw-face-stage > :not(style) { position: absolute; inset: 0; width: 100%; height: 100%; }
.pw-face-plate { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; }
.pw-face-mark { flex: 0 0 auto; width: 64px; height: 64px; border-radius: 50%; background: #5c42bf; color: #fff;
  display: grid; place-items: center; font-size: 28px; font-weight: 800; }
.pw-face-hint { font-size: 12.5px; color: #6b6880; text-align: center; padding: 0 14px; }
.pw-face-meta { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; padding: 9px 12px 2px; }
.pw-face-name { font-weight: 800; color: #4a3596; font-size: 14px; white-space: nowrap; }
.pw-face-name small { font-weight: 500; color: #6b6880; font-size: 11.5px; }
.pw-face-state { font-size: 10.5px; font-weight: 700; color: #5c42bf; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }
.pw-face.is-offline .pw-face-state { color: #9ca3af; }
.pw-face-speaks { margin: 0; padding: 2px 12px 11px; font-size: 11.5px; color: #6b6880; line-height: 1.4; }
.pw-face-captions { display: flex; min-height: 40px; padding: 0 12px 10px; }
.pw-face-captions > :not(style) { max-width: 100%; padding: 0; background: transparent !important; color: #1f1b2e !important;
  font-size: 13px; line-height: 1.4; text-align: left; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden; }
.pw-face-captions * { background: transparent !important; color: inherit !important; }
@media (max-width: 640px) {
  .pw-face { border-radius: 16px; }
  .pw-face-meta { padding: 5px 8px; }
  .pw-face-name small, .pw-face-state, .pw-face-captions, .pw-face-hint, .pw-face-speaks { display: none; }
  .pw-face-mark { width: 44px; height: 44px; font-size: 20px; }
  .pw-face-name { font-size: 12px; }
}
`;
