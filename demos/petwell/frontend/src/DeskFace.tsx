/**
 * Tushar, at the Petwell front desk.
 *
 * He is the `tushar` character from `@voqalize/avatar`, named rather than
 * imported, driven entirely by the `avatar` messages Voqalize already sends on
 * the data channel the call has. There is no video track and nothing to
 * configure: the face only renders. The brain speaks with `omnivoice/gaurav`,
 * the first voice the runtime suggests for him, so the face and the voice are
 * one person.
 *
 * The tile mounts the face only once there is a client — a visitor who never
 * calls never downloads him — and wears {@link DeskPlate} until then. The
 * sentence he is speaking is printed under his face, so the booking still reads
 * with the sound off in a meeting room.
 */

import type { PipecatClient } from '@pipecat-ai/client-js';
import { TranscriptOverlay } from '@pipecat-ai/voice-ui-kit';
import '@pipecat-ai/voice-ui-kit/styles.scoped';
import { Avatar } from '@voqalize/avatar/react';
import type { AmbientPresenceActivity } from '@voqalize/demo-kit';

export const DESK_NAME = 'Tushar';

const STATE: Record<AmbientPresenceActivity, string> = {
  idle: 'Here to help',
  listening: 'Listening',
  thinking: 'Checking',
  speaking: 'Speaking',
};

export function DeskFace({
  client,
  activity,
}: {
  client: PipecatClient | null;
  activity: AmbientPresenceActivity;
}) {
  if (!client) return <DeskPlate />;
  return (
    <figure className={`pw-face is-${activity}`}>
      <div className="pw-face-stage">
        <Avatar client={client} character="tushar" aria-label={`${DESK_NAME}, Petwell front desk`} />
      </div>
      <figcaption className="pw-face-meta">
        <span className="pw-face-name">
          {DESK_NAME} <small>· Front desk</small>
        </span>
        <span className="pw-face-state">{STATE[activity]}</span>
      </figcaption>
      <div className="vkui-root pw-face-captions">
        <TranscriptOverlay participant="remote" size="sm" />
      </div>
      <style>{CSS}</style>
    </figure>
  );
}

/** Before a call: a monogram, not a portrait of a face that is about to move. */
function DeskPlate() {
  return (
    <figure className="pw-face is-offline">
      <div className="pw-face-stage">
        <div className="pw-face-plate">
          <span className="pw-face-mark">T</span>
          <span className="pw-face-hint">Tap the mic to talk to {DESK_NAME}</span>
        </div>
      </div>
      <figcaption className="pw-face-meta">
        <span className="pw-face-name">
          {DESK_NAME} <small>· Front desk</small>
        </span>
        <span className="pw-face-state">Offline</span>
      </figcaption>
      <style>{CSS}</style>
    </figure>
  );
}

const CSS = `
.pw-face { margin: 0; background: #fff; border-radius: 20px; overflow: hidden;
  box-shadow: 0 6px 30px rgba(74,53,150,.10); border: 1.5px solid #e4defa; transition: box-shadow .2s, border-color .2s; }
.pw-face.is-speaking { border-color: #5c42bf; box-shadow: 0 0 0 4px rgba(92,66,191,.18), 0 6px 30px rgba(74,53,150,.12); }
.pw-face.is-listening { border-color: #a78bfa; }
.pw-face-stage { position: relative; aspect-ratio: 4 / 5; background: linear-gradient(180deg, #f4f1ff, #e9e3ff); }
.pw-face-stage > :not(style) { position: absolute; inset: 0; width: 100%; height: 100%; }
.pw-face-plate { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
.pw-face-mark { flex: 0 0 auto; width: 72px; height: 72px; border-radius: 50%; background: #5c42bf; color: #fff;
  display: grid; place-items: center; font-size: 32px; font-weight: 800; }
.pw-face-hint { font-size: 13px; color: #6b6880; text-align: center; padding: 0 16px; }
.pw-face-meta { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 10px 14px 4px; }
.pw-face-name { font-weight: 800; color: #4a3596; font-size: 15px; }
.pw-face-name small { font-weight: 500; color: #6b6880; font-size: 12px; }
.pw-face-state { font-size: 11.5px; font-weight: 700; color: #5c42bf; text-transform: uppercase; letter-spacing: .05em; }
.pw-face.is-offline .pw-face-state { color: #9ca3af; }
.pw-face-captions { display: flex; min-height: 44px; padding: 0 14px 12px; }
.pw-face-captions > :not(style) { max-width: 100%; padding: 0; background: transparent !important; color: #1f1b2e !important;
  font-size: 14px; line-height: 1.4; text-align: left; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden; }
.pw-face-captions * { background: transparent !important; color: inherit !important; }
`;
