/**
 * The live call's client, for Stage to attach to, plus the dock's own "start
 * the call". The voice dock fills both in; with no agent configured they stay
 * null and Stage never attaches.
 */
import type { StageClient } from "@voqalize/stage";
import { create } from "zustand";

interface VoiceSeam {
  client: StageClient | null;
  begin: (() => void) | null;
  live: boolean;
}
export const useVoiceClient = create<VoiceSeam>(() => ({ client: null, begin: null, live: false }));
export const setVoiceClient = (client: StageClient | null) => useVoiceClient.setState({ client });
export const setVoiceBegin = (begin: (() => void) | null) => useVoiceClient.setState({ begin });
export const setVoiceLive = (live: boolean) => useVoiceClient.setState({ live });
