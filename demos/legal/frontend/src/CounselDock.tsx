/**
 * The counsel dock — Tanya at the foot of the left rail, and every control for
 * the call directly under her.
 *
 * **Why the bottom left.** The right of this screen is already spoken for: the
 * task tray hangs from the top right and the obligations pill sits in the
 * bottom-right corner with its drawer behind it. Those are the *secondary*
 * things — work the assistant kicked off, and a ledger the lawyer opens when
 * they want it. Putting the assistant herself in the same column would have her
 * competing with her own output for the same corner, and it is the output that
 * is supposed to be glanceable. The left column is the orientation column —
 * matter, sections, data room — and the presenter belongs at the foot of it,
 * under the outline she is walking the lawyer through.
 *
 * The controls moved with her, and that is the point rather than a consequence.
 * They used to live in the top bar, on the argument that this should read as the
 * product's own chrome instead of a bolted-on chat widget. That argument was
 * about the *shape* of a bottom-right bubble, not about the corner — and it cost
 * something: the mute button was at the opposite end of the screen from the face
 * it muted, so the one control a lawyer reaches for in a hurry was the furthest
 * thing from where they were looking. Under the picture is where a decade of
 * video calls has taught everyone to find it.
 *
 * **The face is Tanya**, from `@voqalize/avatar` — the same 2.5-D character the
 * homepage agent wears, and she is here because the voice moved first: Docket
 * now speaks with `kokoro/ava`, which is Tanya's voice on voqalize.com. One
 * face, one checkpoint, wherever she turns up. Her module carries three.js and
 * her character binary, so it is imported on demand and the pre-call notice
 * covers the download.
 *
 * She takes one prop that matters — the live `PipecatClient` — and drives
 * herself off the `avatar` messages the runtime already sends down the same data
 * channel the transcript rides. No video track, no second stream, nothing to
 * configure. Before the client exists she renders nothing at all, which is why
 * the stage has a ground of its own to show.
 */

import { useEffect, useState } from 'react';
import type { PipecatClient } from '@pipecat-ai/client-js';
import { usePipecatClient, usePipecatClientMicControl } from '@pipecat-ai/client-react';
import type { AvatarFactory, AvatarOptions } from '@voqalize/avatar';
import { Avatar } from '@voqalize/avatar/react';
import { Loader2, Mic, MicOff, PhoneOff } from 'lucide-react';
import type { AmbientPresenceActivity } from '@voqalize/demo-kit';

/** Where the call is. The dock renders one of these three faces of itself. */
export type DockStatus = 'idle' | 'connecting' | 'live' | 'error';

const ACTIVITY_LABEL: Record<AmbientPresenceActivity, string> = {
  idle: 'Live',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
};

/** Tanya's module. Resolved once and cached by the bundler. */
const loadTanya = (): Promise<AvatarFactory<AvatarOptions>> =>
  import('@voqalize/avatar/avatars/tanya').then((m) => m.createAvatar);

export interface CounselDockProps {
  status: DockStatus;
  activity: AmbientPresenceActivity;
  /** Connection trouble, already in the words the visitor should read. */
  error: string;
  onBegin: () => void;
  onEnd: () => void;
}

export function CounselDock({ status, activity, error, onBegin, onEnd }: CounselDockProps) {
  const client = usePipecatClient();
  const live = status === 'live';

  return (
    <aside className={`desk-counsel is-${status}`} aria-label="Counsel">
      <div className="desk-counsel-stage">
        <Face client={client ?? null} />
        {live ? (
          <span className="desk-counsel-chip">
            <span className={`desk-counsel-dot is-${activity}`} aria-hidden />
            {ACTIVITY_LABEL[activity]}
          </span>
        ) : null}
        <span className="desk-counsel-plate">Tanya &middot; Counsel</span>
      </div>
      <div className="desk-counsel-bar">
        {live ? <LiveControls activity={activity} onEnd={onEnd} /> : <BeginControl status={status} error={error} onBegin={onBegin} />}
      </div>
      <DockStyles />
    </aside>
  );
}

/**
 * Tanya, once her module has arrived. The import starts when the dock mounts —
 * which is while the visitor is still reading the notice — so the face is here
 * by the time there is a call for her to embody. Until then the stage shows its
 * own ground, which is what it shows behind her anyway.
 */
function Face({ client }: { client: PipecatClient | null }) {
  const [create, setCreate] = useState<AvatarFactory<AvatarOptions> | null>(null);
  useEffect(() => {
    let live = true;
    void loadTanya().then((factory) => {
      if (live) setCreate(() => factory);
    });
    return () => {
      live = false;
    };
  }, []);
  if (!create) return <div className="desk-counsel-face" role="img" aria-label="Tanya" />;
  return <Avatar className="desk-counsel-face" create={create} client={client} aria-label="Tanya" />;
}

/** Before the call, and after it ends: one affordance, and what went wrong. */
function BeginControl({ status, error, onBegin }: { status: DockStatus; error: string; onBegin: () => void }) {
  return (
    <div className="desk-presence">
      {status === 'connecting' ? (
        <button className="desk-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={17} className="desk-spin" />
        </button>
      ) : (
        <button className="desk-presence-btn" onClick={onBegin} title="Begin Review">
          <Mic size={17} />
        </button>
      )}
      <span className="desk-presence-label">
        {status === 'connecting' ? 'Connecting…' : status === 'error' ? error || 'Connection issue' : 'Begin Review'}
      </span>
    </div>
  );
}

/** During it: the mic stays open, so the prominent control is the mute, with a
 *  small secondary one to end. */
function LiveControls({ activity, onEnd }: { activity: AmbientPresenceActivity; onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  return (
    <div className="desk-presence">
      <button
        className={`desk-presence-btn is-live glow-${activity} ${isMicEnabled ? '' : 'is-muted'}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? 'Mute' : 'Unmute'}
      >
        {isMicEnabled ? <Mic size={17} /> : <MicOff size={17} />}
      </button>
      <span className="desk-presence-label">{isMicEnabled ? 'Mic open' : 'Muted'}</span>
      <button className="desk-presence-end" onClick={onEnd} title="End Review">
        <PhoneOff size={14} />
      </button>
    </div>
  );
}

function DockStyles() {
  return (
    <style>{`
      /* Pinned to the bottom-left corner, the width of the rail it continues, and
         above the ambient ring (z 90/91) so its glow washes the page edge rather
         than the presenter's face. */
      .desk-counsel {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 220px;
        z-index: 95;
        display: flex;
        flex-direction: column;
        background: #FAFAF9;
        border-right: 1px solid #E4E1DB;
        border-top: 1px solid #E4E1DB;
        font-family: 'Inter', system-ui, sans-serif;
      }

      /* The picture. A neutral warm ground rather than an oxblood wash: it reads
         as a call tile instead of a panel of the brand. */
      .desk-counsel-stage {
        position: relative;
        flex: none;
        height: 132px;
        overflow: hidden;
        background: linear-gradient(168deg, #F4F2EE 0%, #E9E5DE 100%);
      }
      .desk-counsel-face { width: 100%; height: 100%; display: block; }
      .desk-counsel-chip {
        position: absolute;
        top: 8px;
        left: 8px;
        display: flex;
        align-items: center;
        gap: 5px;
        padding: 3px 8px;
        border-radius: 999px;
        background: rgba(15, 14, 13, 0.6);
        backdrop-filter: blur(6px);
        color: #FAFAF9;
        font-size: 10.5px;
        font-weight: 650;
        letter-spacing: 0.01em;
      }
      .desk-counsel-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #9A3324;
        flex: none;
        transition: background 0.2s ease;
      }
      .desk-counsel-dot.is-thinking { background: #B9862E; }
      .desk-counsel-dot.is-speaking { background: #C2452F; }
      .desk-counsel-plate {
        position: absolute;
        left: 8px;
        bottom: 8px;
        padding: 2px 8px;
        border-radius: 7px;
        background: rgba(15, 14, 13, 0.52);
        backdrop-filter: blur(6px);
        color: #FAFAF9;
        font-size: 10.5px;
        font-weight: 600;
      }

      /* The control row, directly under the picture. */
      .desk-counsel-bar {
        flex: none;
        height: 50px;
        display: flex;
        align-items: center;
        padding: 0 12px;
        border-top: 1px solid #EDEBE6;
      }

      .desk-presence {
        display: flex;
        align-items: center;
        gap: 10px;
        width: 100%;
      }
      .desk-presence-label {
        font-size: 12px;
        font-weight: 600;
        color: #706D66;
        letter-spacing: 0.01em;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .desk-presence-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 38px;
        height: 38px;
        border-radius: 50%;
        border: 1.5px solid #9A3324;
        background: #9A3324;
        color: #FAFAF9;
        cursor: pointer;
        transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
        flex: none;
      }
      .desk-presence-btn:hover { transform: scale(1.05); }
      .desk-presence-btn:active { transform: scale(0.97); }
      .desk-presence-btn.is-connecting {
        background: transparent;
        color: #9A3324;
        cursor: default;
      }
      .desk-presence-btn.is-connecting:hover { transform: none; }
      .desk-presence-btn.is-live {
        box-shadow: 0 0 0 4px rgba(154, 51, 36, 0.14);
      }
      .desk-presence-btn.is-live.glow-thinking { box-shadow: 0 0 0 4px rgba(154, 51, 36, 0.22); }
      .desk-presence-btn.is-live.glow-speaking { box-shadow: 0 0 0 5px rgba(154, 51, 36, 0.3); }
      .desk-presence-btn.is-muted {
        background: #FAFAF9;
        border-color: #CCCAC6;
        color: #706D66;
        box-shadow: none;
      }
      .desk-presence-end {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 26px;
        height: 26px;
        border-radius: 50%;
        border: none;
        background: transparent;
        color: #AFA9A0;
        cursor: pointer;
        transition: color 0.15s ease, background 0.15s ease;
        flex: none;
        margin-left: auto;
      }
      .desk-presence-end:hover { color: #9A3324; background: #F2F1F0; }
      .desk-spin { animation: legal-spin 0.9s linear infinite; }
      @keyframes legal-spin { to { transform: rotate(360deg); } }

      /* On a phone the rail is a horizontal clause strip, so there is no column
         to sit at the foot of. The dock detaches into the corner itself and
         shrinks to the two things that have to be reachable — the face, and the
         control. The obligations pill keeps the opposite corner. */
      @media (max-width: 720px) {
        .desk-counsel {
          left: 10px;
          bottom: 10px;
          width: auto;
          flex-direction: row;
          align-items: center;
          gap: 8px;
          padding: 8px;
          border: 1px solid #E4E1DB;
          border-radius: 14px;
          box-shadow: 0 10px 28px rgba(15, 14, 13, 0.16);
        }
        .desk-counsel-stage {
          width: 52px;
          height: 52px;
          border-radius: 50%;
          flex: none;
        }
        .desk-counsel-chip,
        .desk-counsel-plate { display: none; }
        .desk-counsel-bar {
          height: auto;
          padding: 0 4px 0 0;
          border-top: none;
        }
        .desk-presence-label { display: none; }
      }
    `}</style>
  );
}
