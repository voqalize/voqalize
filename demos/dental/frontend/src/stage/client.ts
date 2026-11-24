/**
 * The live call's pipecat client, for Stage to attach to, and whether a call is
 * up (the language toggle asks the brain then). The voice dock owns both and
 * puts them here; with no agent configured they stay empty and nothing attaches.
 */
import type { StageClient } from "@voqalize/stage";
import { create } from "zustand";

interface VoiceSeam {
  client: StageClient | null;
  live: boolean;
}

export const useVoiceClient = create<VoiceSeam>(() => ({ client: null, live: false }));
export const setVoiceClient = (client: StageClient | null) => useVoiceClient.setState({ client });
export const setVoiceLive = (live: boolean) => useVoiceClient.setState({ live });
