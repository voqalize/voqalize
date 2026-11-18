/**
 * The live call's pipecat client, for Stage to attach to, and the dock's own
 * "start the call", for buttons elsewhere on the page ("Ask Arjun"). The voice
 * dock owns both and puts them here; with no agent configured they stay null.
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
