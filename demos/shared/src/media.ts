/**
 * The demos' local media: `@voqalize/client-transport` in place of pipecat's
 * default media manager, which loads daily's call machine from `c.daily.co`
 * on every call and runs it in the page. With this, nothing in a demo's media
 * path is code we cannot read.
 *
 * `PipecatAppBase` builds its own `SmallWebRTCTransport`, so the manager goes
 * in through `transportOptions` and is wired in `onClient` — the half of the
 * injection the stock transport performs only for its own default (the
 * package's README, "If you build your transport somewhere else").
 *
 * The agent plays on an element the manager owns, so give the base
 * `noAudioOutput` or the kit's `BotAudioOutput` plays her a second time.
 * Owning the element is what gets the call speaker routing and playout
 * recovery: on Android Chrome a page that takes over a live call can attach
 * her track and play nothing until it is re-attached, and the manager does
 * that.
 *
 * ```tsx
 * const media = useVoqalizeMedia();
 * <PipecatAppBase
 *   transportType="smallwebrtc"
 *   transportOptions={media.transportOptions}
 *   onClient={media.onClient}
 *   noAudioOutput
 * />
 * ```
 */

import { RTVIEvent, type PipecatClient } from "@pipecat-ai/client-js";
import type { SmallWebRTCTransportConstructorOptions } from "@pipecat-ai/small-webrtc-transport";
import { VoqalizeMediaManager, attachTrackChangedHandler } from "@voqalize/client-transport";
import { useEffect, useState } from "react";

export interface VoqalizeMedia {
  /** For `PipecatAppBase`'s `transportOptions`. Stable for the component's life. */
  transportOptions: SmallWebRTCTransportConstructorOptions;
  /** For `PipecatAppBase`'s `onClient`; call it first from a demo's own. */
  onClient: (client: PipecatClient) => void;
  manager: VoqalizeMediaManager;
  /**
   * Hand the manager the element she plays on; returns the detach. The hook
   * does this from an effect, so a component that mounts once per call does
   * not leave a guard polling behind it.
   */
  bind: () => () => void;
}

/**
 * One manager and one output element for the component's life. The base
 * rebuilds its client (and transport) when its props change identity; each new
 * transport takes the same manager, and `onClient` re-points it at the new one.
 */
export function useVoqalizeMedia(): VoqalizeMedia {
  const [media] = useState(() => createVoqalizeMedia());
  useEffect(() => media.bind(), [media]);
  return media;
}

export function createVoqalizeMedia(): VoqalizeMedia {
  const manager = new VoqalizeMediaManager();
  const audio = typeof document === "undefined" ? null : document.createElement("audio");
  if (audio) audio.autoplay = true;
  let current: PipecatClient | null = null;

  return {
    manager,
    bind: () => (audio ? manager.bindOutputElement(audio) : () => {}),
    // The package's `VoqalizeMediaManager` implements pipecat's `MediaManager`
    // structurally; the abstract base it would extend is not exported, hence
    // the one cast (`createVoqalizeTransport` makes the same one).
    transportOptions: {
      mediaManager: manager as unknown as SmallWebRTCTransportConstructorOptions["mediaManager"],
    },
    onClient(client) {
      current = client;
      attachTrackChangedHandler(client.transport as never, manager);
      client.on(RTVIEvent.TrackStarted, (track, participant) => {
        if (client !== current || !audio) return;
        if (participant?.local || track.kind !== "audio") return;
        const playing = (audio.srcObject as MediaStream | null)?.getAudioTracks()[0];
        if (playing?.id === track.id) return;
        audio.srcObject = new MediaStream([track]);
        // A refusal is the manager's: it retries on the next tap or key.
        void audio.play().catch(() => {});
      });
      client.on(RTVIEvent.TrackStopped, (track, participant) => {
        if (client !== current || !audio) return;
        if (participant?.local || track.kind !== "audio") return;
        const playing = (audio.srcObject as MediaStream | null)?.getAudioTracks()[0];
        if (playing?.id === track.id) audio.srcObject = null;
      });
    },
  };
}
