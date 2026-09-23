/**
 * Rohan, docked in the bottom-right corner of the glass.
 *
 * He is one of `@voqalize/avatar`'s 2.5-D characters — `tushar`, imported from
 * the package like any other face — driven entirely by the `avatar` messages the
 * Voqalize runtime already sends over the data channel the transcript rides.
 * There is no video track and nothing to configure: the rig only renders, the
 * server owns the intent.
 *
 * He is small on purpose. He is helping the customer through the application;
 * he is not the application, and a face at eye height competing with the card
 * shortlist was the wrong hierarchy to teach a viewer in the first five seconds.
 *
 * His module carries three.js and his character binary, so it is loaded on
 * demand and the pre-call gate covers the wait. Until it lands, and before there
 * is a client to embody at all, the dock wears {@link RohanPlate} instead.
 *
 * **Captions are not optional furniture here.** A branch has ambient noise, a
 * kiosk speaker is small, and a customer may be standing beside someone else's
 * conversation — so the sentence Rohan is speaking is printed as he says it and
 * the demo works with the audio off. It runs along a rail *beside* the dock
 * rather than over his face: a 190px tile cannot hold a sentence, and the words
 * matter more than the picture does ({@link RohanCaptions}).
 *
 * The credit line under the tile is the licence's, not ours to style away: the
 * character artwork is CC BY 4.0 and attribution travels with it.
 */

import { useEffect, useState } from 'react';
import type { PipecatClient } from '@pipecat-ai/client-js';
import type { AvatarFactory, AvatarOptions } from '@voqalize/avatar';
import { Avatar } from '@voqalize/avatar/react';
import { TranscriptOverlay } from '@pipecat-ai/voice-ui-kit';
import '@pipecat-ai/voice-ui-kit/styles.scoped';
import type { AmbientPresenceActivity } from '@voqalize/demo-kit';
import { COLOR } from './brand';
import { fontFor, strings, type Language } from './language';

/** Rohan's character module. Resolved once by the bundler. */
const loadRohan = (): Promise<AvatarFactory<AvatarOptions>> =>
  import('@voqalize/avatar/avatars/tushar').then((m) => m.createAvatar);

export interface RohanTileProps {
  /** The live client. `null` in the moment before the host has built one. */
  client: PipecatClient | null;
  /** What the call is doing, from the same events the ambient ring reads. */
  activity: AmbientPresenceActivity;
  language: Language;
}

export function RohanTile({ client, activity, language }: RohanTileProps) {
  const [create, setCreate] = useState<AvatarFactory<AvatarOptions> | null>(null);
  const copy = strings(language);

  useEffect(() => {
    let live = true;
    void loadRohan().then((factory) => {
      if (live) setCreate(() => factory);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    // `vkui-root` is the whole contract with voice-ui-kit's stylesheet: its
    // variables and utilities apply inside this element and nowhere else.
    <div className={`vkui-root kiosk-rohan is-${activity}`}>
      <div className="kiosk-rohan-stage">
        {/* Until his module lands, the band's own ground — a second of it, and
            only behind the gate. The monogram plate is the *pre-call* face and
            is never mounted at the same time as the rig. */}
        {create ? <Avatar create={create} client={client} aria-label={copy.assistant} /> : null}
      </div>
      <RohanStyles />
    </div>
  );
}

/**
 * The band before there is a call — and the ground the rig paints over once
 * there is. A monogram rather than a portrait: a still photograph of a face that
 * is about to start moving is an odd promise to make on a totem, and one more
 * binary to keep in step with the package.
 */
export function RohanPlate({ language }: { language: Language }) {
  const copy = strings(language);
  return (
    <div className="kiosk-rohan-plate" role="img" aria-label={copy.assistant}>
      <span className="kiosk-rohan-mark" style={{ fontFamily: fontFor('en') }}>
        R
      </span>
      <span className="kiosk-rohan-name">{copy.assistant}</span>
      <RohanStyles />
    </div>
  );
}

/**
 * The sentence Rohan is speaking, for the rail beside his dock. Separate from
 * the tile because it outgrew it: the words have to be readable from a metre
 * away and the picture does not.
 */
export function RohanCaptions() {
  return (
    <div className="vkui-root kiosk-rohan-captions">
      <TranscriptOverlay participant="remote" size="sm" />
      <RohanStyles />
    </div>
  );
}

/**
 * The credit the character artwork's licence requires. It sits under the dock,
 * small but present and never behind a disclosure.
 */
export function AvatarCredit() {
  return (
    <p className="kiosk-rohan-credit">
      Avatar by{' '}
      <a href="https://github.com/voqalize/avatar" target="_blank" rel="noopener noreferrer">
        @voqalize/avatar
      </a>{' '}
      — character artwork{' '}
      <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">
        CC BY 4.0
      </a>
    </p>
  );
}

function RohanStyles() {
  return (
    <style>{`
      .kiosk-rohan {
        position: relative;
        width: 100%;
        height: 100%;
      }
      .kiosk-rohan-stage { position: absolute; inset: 0; }
      .kiosk-rohan-stage > * { width: 100%; height: 100%; }

      /* The monogram ground: also what the rig paints over once it lands. */
      .kiosk-rohan-plate {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 10px;
        width: 100%;
        height: 100%;
      }
      .kiosk-rohan-mark {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 52px;
        height: 52px;
        border-radius: 50%;
        background: ${COLOR.amber};
        color: ${COLOR.umber};
        font-size: 26px;
        font-weight: 800;
      }
      .kiosk-rohan-name {
        font-size: 14px;
        font-weight: 700;
        color: rgba(251, 247, 242, 0.86);
      }

      /* The sentence in flight, on its own rail beside the dock. Sized to be
         read standing, which the dock itself is far too small to allow. */
      .kiosk-rohan-captions {
        display: flex;
        width: 100%;
      }
      .kiosk-rohan-captions > * {
        max-width: 100%;
        padding: 9px 15px;
        border-radius: 12px;
        background: rgba(23, 19, 16, 0.82);
        color: ${COLOR.paper};
        font-size: 18px;
        line-height: 1.4;
      }

      .kiosk-rohan-credit {
        margin: 0;
        font-size: 10px;
        line-height: 1.4;
        color: rgba(251, 247, 242, 0.5);
      }
      .kiosk-rohan-credit a { color: inherit; }
    `}</style>
  );
}
