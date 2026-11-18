/**
 * The live call's pipecat client, for Stage to attach to, and the dock's own
 * "start the call" for buttons elsewhere on the page ("Ask about my cover").
 * The voice dock owns both and puts them here; with no agent configured they
 * stay null and nothing attaches.
 */
import type { StageClient } from "@voqalize/stage";
import { create } from "zustand";

interface VoiceSeam {
  client: StageClient | null;
  begin: (() => void) | null;
}

export const useVoiceClient = create<VoiceSeam>(() => ({ client: null, begin: null }));
export const setVoiceClient = (client: StageClient | null) => useVoiceClient.setState({ client });
export const setVoiceBegin = (begin: (() => void) | null) => useVoiceClient.setState({ begin });
