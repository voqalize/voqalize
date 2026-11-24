/**
 * The live call's client, for Stage to attach to. The voice dock fills it in;
 * with no agent configured it stays null and Stage never attaches.
 */
import type { StageClient } from "@voqalize/stage";
import { create } from "zustand";

interface VoiceSeam {
  client: StageClient | null;
}
export const useVoiceClient = create<VoiceSeam>(() => ({ client: null }));
export const setVoiceClient = (client: StageClient | null) => useVoiceClient.setState({ client });
