/**
 * Tess, at the top of the glass.
 *
 * She wears one of `@voqalize/avatar`'s 2.5-D characters — `tess`, imported from
 * the package like any other face — driven entirely by the `avatar` messages the
 * Voqalize runtime already sends over the data channel the transcript rides.
 * There is no video track and nothing to configure: the rig only renders, the
 * server owns the intent.
 *
 * She holds the top of the screen because the kiosk is driven by voice first.
 * The customer talks to a face, and the answers they could tap instead sit in
 * the tray below her, where a hand reaches — never over her.
 *
 * Her module carries three.js and her character binary, so it is loaded on
 * demand and the pre-call gate covers the wait. Until it lands, and before there
 * is a client to embody at all, the tile wears {@link TessPlate} instead.
 *
 * **Captions are not optional furniture here.** A branch has ambient noise, a
 * kiosk speaker is small, and a customer may be standing beside someone else's
 * conversation — so the sentence Tess is speaking is printed under her face as
 * she says it, one or two lines, and the demo works with the audio off.
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

/** Tess's face, the `tess` character. Resolved once by the bundler. */
const loadTess = (): Promise<AvatarFactory<AvatarOptions>> =>
  import('@voqalize/avatar/avatars/tess').then((m) => m.createAvatar);

export interface TessTileProps {
  /** The live client. `null` in the moment before the host has built one. */
  client: PipecatClient | null;
  /** What the call is doing, from the same events the ambient ring reads. */
  activity: AmbientPresenceActivity;
  language: Language;
}

export function TessTile({ client, activity, language }: TessTileProps) {
  const [create, setCreate] = useState<AvatarFactory<AvatarOptions> | null>(null);
  const copy = strings(language);

  useEffect(() => {
    let live = true;
    void loadTess().then((factory) => {
      if (live) setCreate(() => factory);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    // `vkui-root` is the whole contract with voice-ui-kit's stylesheet: its
    // variables and utilities apply inside this element and nowhere else. The
    // styles stay outside it — that stylesheet displays a `<style>` it contains.
    <>
      <div className={`vkui-root kiosk-tess is-${activity}`}>
        <div className="kiosk-tess-stage">
          {create ? <Avatar create={create} client={client} aria-label={copy.assistant} /> : null}
        </div>
      </div>
      <TessStyles />
    </>
  );
}

/**
 * The tile before there is a call. A monogram rather than a portrait: a still
 * photograph of a face that is about to start moving is an odd promise to make
 * on a totem, and one more binary to keep in step with the package.
 */
export function TessPlate({ language }: { language: Language }) {
  const copy = strings(language);
  return (
    <div className="kiosk-tess is-offline" role="img" aria-label={copy.assistant}>
      <div className="kiosk-tess-plate">
        <span className="kiosk-tess-mark" style={{ fontFamily: fontFor('en') }}>
          T
        </span>
        <span className="kiosk-tess-name">{copy.assistant}</span>
      </div>
      <TessStyles />
    </div>
  );
}

/** The sentence Tess is speaking, under her face. */
export function TessCaptions() {
  return (
    <>
      <div className="vkui-root kiosk-tess-captions">
        <TranscriptOverlay participant="remote" size="sm" />
      </div>
      <TessStyles />
    </>
  );
}

function TessStyles() {
  return (
    <style>{`
      /* No tile of her own: she stands on the glass's own light, not in a frame. */
      .kiosk-tess {
        position: relative;
        width: 100%;
        height: 100%;
      }
      .kiosk-tess-stage { position: absolute; inset: 0; }
      .kiosk-tess-stage > :not(style) { width: 100%; height: 100%; }

      .kiosk-tess-plate {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 12px;
        height: 100%;
      }
      .kiosk-tess-mark {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 64px;
        height: 64px;
        border-radius: 50%;
        background: ${COLOR.accent};
        color: ${COLOR.brandDeep};
        font-size: 30px;
        font-weight: 700;
      }
      .kiosk-tess-name { font-size: 16px; font-weight: 600; color: ${COLOR.brand}; }

      .kiosk-tess-captions { display: flex; width: 100%; }
      .kiosk-tess-captions > :not(style) {
        max-width: 100%;
        padding: 0;
        background: transparent !important;
        color: ${COLOR.muted} !important;
        font-size: 16px;
        line-height: 1.45;
        text-align: left;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }
      .kiosk-tess-captions * { background: transparent !important; color: inherit !important; }

    `}</style>
  );
}
