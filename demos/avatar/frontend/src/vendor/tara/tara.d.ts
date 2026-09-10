import type { PipecatClient } from "@pipecat-ai/client-js";

export interface AvatarOptions {
  readonly mount: HTMLElement;
  readonly client: PipecatClient;
  readonly mouthGain?: number;
  readonly gestureGain?: number;
  readonly motionGain?: number;
}

export interface AvatarInstance {
  destroy(): void;
}

export declare function createAvatar(options: AvatarOptions): AvatarInstance;
