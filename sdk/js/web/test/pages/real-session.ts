/**
 * The package's own `WidgetSession` with the network and the browser's media
 * replaced: a client that connects at once, a mic track that is an
 * `EventTarget`, a permission status and a device list the test moves. So
 * the mic pill is driven by the same track, permission and device events a
 * real call gives, through the real session and mic controller.
 *
 * Loaded only by the scenarios that use it, so the other pages never pull in
 * the session.
 */

import type { ClientLike, WidgetSession } from "../../src/session/adapter.js";

class FakeTrack extends EventTarget {
  kind = "audio";
  muted = false;
  readyState: MediaStreamTrackState = "live";
  constructor(readonly deviceId: string) {
    super();
  }
  getSettings() {
    return { deviceId: this.deviceId };
  }
  fire(type: "mute" | "unmute" | "ended") {
    if (type === "mute") this.muted = true;
    if (type === "unmute") this.muted = false;
    if (type === "ended") this.readyState = "ended";
    this.dispatchEvent(new Event(type));
  }
}

class FakePermission extends EventTarget {
  state: PermissionState = "granted";
  onchange = null;
  name = "microphone";
  set(state: PermissionState) {
    this.state = state;
    this.dispatchEvent(new Event("change"));
  }
}

class FakeDevices extends EventTarget {
  list = [
    { kind: "audioinput", deviceId: "default", label: "MacBook Pro Microphone", groupId: "" },
    { kind: "audioinput", deviceId: "usb", label: "Jabra Evolve2 65", groupId: "" },
  ];
  enumerateDevices() {
    return Promise.resolve(this.list as unknown as MediaDeviceInfo[]);
  }
  unplug(id: string) {
    this.list = this.list.filter((d) => d.deviceId !== id);
    this.dispatchEvent(new Event("devicechange"));
  }
}

/** The handles a test moves, as `window.__vql`. */
export interface RealSessionControls {
  muteTrack(): void;
  unmuteTrack(): void;
  endTrack(): void;
  unplug(): void;
  revoke(): void;
  grant(): void;
  wire(): unknown[];
}

export async function realSession(): Promise<{ session: WidgetSession; controls: RealSessionControls }> {
  const { WidgetSession } = await import("../../src/session/adapter.js");
  const permission = new FakePermission();
  const devices = new FakeDevices();
  const sent: unknown[] = [];
  let track = new FakeTrack("usb");
  let callbacks: Record<string, ((...args: unknown[]) => void) | undefined> = {};
  const startTrack = () => {
    track = new FakeTrack("usb");
    callbacks.onTrackStarted?.(track, { id: "local", name: "", local: true });
  };
  const client: ClientLike = {
    initDevices: () => Promise.resolve(),
    connect: () => {
      queueMicrotask(() => {
        callbacks.onBotReady?.({});
        startTrack();
      });
      return Promise.resolve({});
    },
    disconnect: () => Promise.resolve(),
    enableMic: (on) => {
      // The client turns the mic back on after a grant: a new track starts.
      if (on && permission.state === "granted" && track.readyState === "ended") startTrack();
    },
    sendClientMessage: (type, data) => {
      if (type === "mic_state") sent.push(data);
    },
    updateMic: () => {},
    updateSpeaker: () => {},
  };
  const session = new WidgetSession({
    createClient: (args) => {
      callbacks = args.callbacks as typeof callbacks;
      return client;
    },
    createMediaManager: () => ({ instant: true, bindOutputElement: () => () => {} }),
    isIOS: false,
    canPickSpeaker: true,
    permissions: { query: () => Promise.resolve(permission as unknown as PermissionStatus) },
    mediaDevices: devices as unknown as Pick<MediaDevices, "addEventListener" | "removeEventListener" | "enumerateDevices">,
  });
  const controls: RealSessionControls = {
    muteTrack: () => track.fire("mute"),
    unmuteTrack: () => track.fire("unmute"),
    endTrack: () => track.fire("ended"),
    unplug: () => devices.unplug("usb"),
    revoke: () => {
      permission.set("denied");
      // Chrome stops the track when the permission goes.
      track.fire("ended");
    },
    grant: () => permission.set("granted"),
    wire: () => sent,
  };
  return { session, controls };
}
