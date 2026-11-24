/**
 * The live call's pipecat client, for Stage to attach to. The voice dock owns
 * it and puts it here; with no agent configured it stays null (or, with
 * `?debug=1`, a stand-in that sends nowhere). The dock is the page's one way
 * to start a call: nothing else on the page starts one (X3).
 */
import type { StageClient } from "@voqalize/stage";
import { create } from "zustand";

interface VoiceSeam {
  client: StageClient | null;
}

export const useVoiceClient = create<VoiceSeam>(() => ({ client: null }));
export const setVoiceClient = (client: StageClient | null) => useVoiceClient.setState({ client });
