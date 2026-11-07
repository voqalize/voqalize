import { describe, expect, it, vi } from "vitest";
import { InstantStartMediaManager, isIOS } from "../src/session/media.js";

class FakeTrack {
  kind = "audio";
  id = Math.random().toString(36).slice(2);
  enabled = true;
  muted = false;
  readyState: "live" | "ended" = "live";
  contentHint = "";
  private listeners = new Map<string, Set<() => void>>();
  clone(): FakeTrack {
    return new FakeTrack();
  }
  stop() {
    this.readyState = "ended";
  }
  getSettings() {
    return { deviceId: "mic-1", groupId: "g" };
  }
  getConstraints() {
    return {};
  }
  applyConstraints() {
    return Promise.resolve();
  }
  addEventListener(type: string, fn: () => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)?.add(fn);
  }
  removeEventListener(type: string, fn: () => void) {
    this.listeners.get(type)?.delete(fn);
  }
}

/** A browser whose mic prompt is still open until `grant()` or `deny()`. */
function promptOpen() {
  let resolve!: (stream: unknown) => void;
  let reject!: (error: unknown) => void;
  const track = new FakeTrack();
  let denied = false;
  const refusal = () => Object.assign(new Error("denied"), { name: "NotAllowedError" });
  const getUserMedia = vi.fn(() =>
    denied
      ? Promise.reject(refusal())
      : new Promise((res, rej) => {
          resolve = res;
          reject = rej;
        }),
  );
  const mediaDevices = {
    getUserMedia,
    enumerateDevices: () =>
      Promise.resolve([{ kind: "audioinput", deviceId: "mic-1", groupId: "g", label: "Mic" }]),
    addEventListener() {},
    removeEventListener() {},
  };
  return {
    mediaDevices,
    getUserMedia,
    track,
    grant: () => resolve({ getTracks: () => [track], getAudioTracks: () => [track], getVideoTracks: () => [] }),
    deny: () => {
      denied = true;
      reject(refusal());
    },
  };
}

function manager(platform: ReturnType<typeof promptOpen>, instant: boolean) {
  const m = new InstantStartMediaManager({
    mediaDevices: platform.mediaDevices,
    createAudioContext: null,
    publishWatchdogMs: 0,
    visibility: undefined,
    gestures: { addEventListener() {}, removeEventListener() {} },
  });
  m.instant = instant;
  return m;
}

const settled = (p: Promise<unknown>) =>
  Promise.race([p.then(() => "settled"), new Promise((r) => setTimeout(() => r("pending"), 20))]);

describe("InstantStartMediaManager", () => {
  it("connects while the prompt is open in instant mode", async () => {
    const platform = promptOpen();
    const m = manager(platform, true);
    m.setClientOptions({ enableMic: true });
    expect(await settled(m.initialize())).toBe("settled");
    expect(await settled(m.connect())).toBe("settled");
    expect(platform.getUserMedia).toHaveBeenCalledTimes(1);
    expect(await settled(m.pending)).toBe("pending");
  });

  it("waits for the prompt with instant start off, as the stock manager does", async () => {
    const platform = promptOpen();
    const m = manager(platform, false);
    m.setClientOptions({ enableMic: true });
    const init = m.initialize();
    expect(await settled(init)).toBe("pending");
    platform.grant();
    expect(await settled(init)).toBe("settled");
  });

  it("puts the track on the existing sender once granted, with no renegotiation", async () => {
    const platform = promptOpen();
    const m = manager(platform, true);
    const changes: { type: string; track: unknown }[] = [];
    // @internal in the transport (stripped from its types); the transport's own
    // factory subscribes through it to call replaceTrack on the existing sender.
    (m as unknown as { setLocalTrackChangedHandler(h: (e: { type: string; track: unknown }) => void): void })
      .setLocalTrackChangedHandler((e) => {
        changes.push({ type: e.type, track: e.track });
      });
    const started = vi.fn();
    m.setClientOptions({ enableMic: true, callbacks: { onTrackStarted: started } });
    await m.initialize();
    await m.connect();
    expect(changes).toEqual([]);
    platform.grant();
    await m.pending;
    expect(changes.some((c) => c.type === "audio" && c.track !== null)).toBe(true);
    expect(started).toHaveBeenCalled();
  });

  it("reports a refusal through onDeviceError and never rejects the connect", async () => {
    const platform = promptOpen();
    const m = manager(platform, true);
    const onDeviceError = vi.fn();
    m.setClientOptions({ enableMic: true, callbacks: { onDeviceError } });
    await m.initialize();
    await m.connect();
    platform.deny();
    await m.pending;
    expect(onDeviceError).toHaveBeenCalled();
    expect(onDeviceError.mock.calls[0]?.[0]).toMatchObject({ type: "permissions" });
  });

  it("asks once when the client initialises again inside its connect", async () => {
    // The client's connect() calls initDevices() again while the mic is still
    // being asked for. That must not queue a second ask behind the prompt.
    const run = async (initTwice: boolean) => {
      const platform = promptOpen();
      const m = manager(platform, true);
      const onDeviceError = vi.fn();
      m.setClientOptions({ enableMic: true, callbacks: { onDeviceError } });
      await m.initialize();
      if (initTwice) await m.initialize();
      await m.connect();
      const whilePrompting = platform.getUserMedia.mock.calls.length;
      platform.deny();
      await m.pending;
      await new Promise((r) => setTimeout(r, 0));
      return { whilePrompting, total: platform.getUserMedia.mock.calls.length, errors: onDeviceError.mock.calls.length };
    };
    const once = await run(false);
    const twice = await run(true);
    expect(twice.whilePrompting).toBe(1);
    expect(twice).toEqual(once);
  });
});

describe("isIOS", () => {
  it("knows iPhones and iPads, including iPadOS posing as a Mac", () => {
    expect(isIOS({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", maxTouchPoints: 5 })).toBe(true);
    expect(isIOS({ userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", maxTouchPoints: 5 })).toBe(true);
    expect(isIOS({ userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", maxTouchPoints: 0 })).toBe(false);
    expect(isIOS({ userAgent: "Mozilla/5.0 (Linux; Android 15)", maxTouchPoints: 5 })).toBe(false);
    expect(isIOS(undefined)).toBe(false);
  });
});
