import { create } from "zustand";
import type { CallState } from "./CallTile";

/**
 * A call, faked for the `?debug=1` console: the tile and its states without a
 * client, so the connected look can be seen and screenshotted.
 */
export const useFakeCall = create<{ on: boolean; state: CallState; heard: string; muted: boolean }>(() => ({
  on: false,
  state: "listening",
  heard: "",
  muted: false,
}));
