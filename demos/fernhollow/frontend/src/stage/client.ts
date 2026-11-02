/**
 * The live call's pipecat client, for the parts of the page that attach to it
 * (Stage on the returns form), and the dock's own "start the call", for the
 * returns desk's "Start a return with Mira". The voice dock owns both and puts
 * them here; with no agent configured they stay null and nothing attaches.
 */
import type { StageClient } from "@voqalize/stage";
import { create } from "zustand";

interface VoiceSeam {
  client: StageClient | null;
  /** Start the call, as the dock's own button does. */
  begin: (() => void) | null;
  live: boolean;
}

export const useVoiceClient = create<VoiceSeam>(() => ({ client: null, begin: null, live: false }));
export const setVoiceClient = (client: StageClient | null) => useVoiceClient.setState({ client });
export const setVoiceBegin = (begin: (() => void) | null) => useVoiceClient.setState({ begin });
export const setVoiceLive = (live: boolean) => useVoiceClient.setState({ live });
