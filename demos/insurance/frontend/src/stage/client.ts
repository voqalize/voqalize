/**
 * The live call's pipecat client, for Stage to attach to. The voice dock owns
 * it and puts it here; with no agent configured it stays null and nothing
 * attaches. The dock is the only way to start a call (one entry point).
 */
import type { StageClient } from "@voqalize/stage";
import { create } from "zustand";

interface VoiceSeam {
  client: StageClient | null;
}

export const useVoiceClient = create<VoiceSeam>(() => ({ client: null }));
export const setVoiceClient = (client: StageClient | null) => useVoiceClient.setState({ client });
