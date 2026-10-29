/**
 * Stage names no pipecat type in its API: it writes out what it uses of the
 * client, so a `PipecatClient` from any copy of the package in the peer range
 * fits as it is. These hold that at type-check time (`pnpm typecheck`), against
 * the copy this package is developed with; a copy of another version fits the
 * same way, since nothing here depends on the class's identity.
 */

import type { PipecatClient, PipecatClientOptions } from "@pipecat-ai/client-js";
import { describe, expect, it } from "vitest";

import type { StageClient } from "../src/attach";
import type { AvatarClient } from "../src/extension/content";
import type { FollowedClient } from "../src/extension/follow";
import type { HolderCallbacks, HolderClient, HolderConfig } from "../src/extension/holder";
import type { RelayedClient } from "../src/extension/relay";

type Fits<A, B> = A extends B ? true : false;

describe("the client Stage takes", () => {
  it("is any PipecatClient, with no cast", () => {
    const stage: Fits<PipecatClient, StageClient> = true;
    const holder: Fits<PipecatClient, HolderClient> = true;
    const relayed: Fits<PipecatClient, RelayedClient> = true;
    // A site's own `makeClient`, typed against its pipecat, is a holder's.
    const make = (_o: HTMLAudioElement, _c: PipecatClientOptions["callbacks"]): PipecatClient => null as never;
    const config: Pick<HolderConfig, "makeClient"> = { makeClient: make };
    // The holder's callbacks are pipecat's callbacks.
    const callbacks: Fits<HolderCallbacks, NonNullable<PipecatClientOptions["callbacks"]>> = true;
    // The face's stand-in passes where the avatar wants a PipecatClient.
    const face = (client: PipecatClient) => client;
    const passes = (standIn: AvatarClient) => face(standIn);
    const isFollowed: Fits<FollowedClient, AvatarClient> = true;
    expect([stage, holder, relayed, config, callbacks, passes, isFollowed].every(Boolean)).toBe(true);
  });
});
