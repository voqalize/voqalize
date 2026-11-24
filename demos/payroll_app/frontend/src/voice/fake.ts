/**
 * A call, faked from the `?debug=1` console: the tile and its states without a
 * client, so the connected look can be seen and screenshotted. Never used
 * outside debug mode.
 */
import { create } from "zustand";

export type CallState = "connecting" | "listening" | "thinking" | "speaking" | "error";

export const useFakeCall = create<{ on: boolean; state: CallState; muted: boolean }>(() => ({
  on: false,
  state: "listening",
  muted: false,
}));

export const FAKE_STATES: CallState[] = ["connecting", "listening", "thinking", "speaking"];
