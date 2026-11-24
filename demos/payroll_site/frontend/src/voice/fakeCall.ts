/**
 * A call, faked for the `?debug=1` console: the live look (the face tile and
 * its controls) without a connection, so it can be seen and screenshotted.
 * Shown over the dock whether or not this build carries an agent; a real call
 * always wins over it.
 */
import { create } from "zustand";
import type { CallState } from "./CallTile";

export const useFakeCall = create<{ state: CallState; muted: boolean }>(() => ({ state: "idle", muted: false }));

export const endFakeCall = () => useFakeCall.setState({ state: "idle", muted: false });
