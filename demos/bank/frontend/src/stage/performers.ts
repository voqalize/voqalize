/** Every move's performer, registered once from the app shell (see host.ts). */
import type { AppStage } from "./host";
import { useAppPerformers } from "./performers.app";
import { usePublicPerformers } from "./performers.public";

export function usePerformers(stage: AppStage): void {
  usePublicPerformers(stage);
  useAppPerformers(stage);
}
