/**
 * `useMove` must survive an effect that runs twice. React's StrictMode does
 * that in development (run, clean up, run), and a change of `stage` does it in
 * production; both used to leave the re-registered performer refusing every
 * move as "that part of the app is not on screen" while the page was mounted.
 */
import { describe, expect, it } from "vitest";

import { Moves } from "../src/moves";
import { type AppStage, type ReactHooks, stageHooks } from "../src/react";
import { defineScene } from "../src/scene";
import { Spotlight } from "../src/spotlight";

const scene = defineScene({
  stage: 1,
  id: "shop",
  moves: [{ id: "core.show", verb: "show", class: "look", args: [{ name: "target" }] }],
});
type S = typeof scene.spec;

/** A React stand-in that records effects so a test can run them the way React does. */
function fakeReact() {
  const effects: { run: () => void | (() => void); cleanup?: void | (() => void) }[] = [];
  const hooks: ReactHooks = {
    useEffect(effect) {
      effects.push({ run: effect });
    },
    useRef<T>(initial: T) {
      return { current: initial };
    },
    useState<T>(initial: T): [T, (v: T) => void] {
      return [initial, () => {}];
    },
  };
  return {
    hooks,
    mount() {
      for (const e of effects) e.cleanup = e.run();
    },
    unmount() {
      for (const e of effects) if (typeof e.cleanup === "function") e.cleanup();
    },
  };
}

function stageFor() {
  const moves = new Moves(new Spotlight({ color: "#000" }));
  return { scene, moves, page: { send() {}, hello() {}, detach() {}, timeline: null }, agent: null } as unknown as AppStage<S>;
}

describe("useMove", () => {
  it("still performs after StrictMode's run, clean up, run", async () => {
    const r = fakeReact();
    const stage = stageFor();
    stageHooks(r.hooks).useMove(stage, "core.show", async ({ target }) => `showed ${target}`);
    r.mount(); // first run
    r.unmount(); // StrictMode's cleanup
    r.mount(); // second run
    const res = await stage.moves.run("core.show", { target: "rail" }, "c1");
    expect(res?.outcome).toBe("applied");
    expect(res?.detail).toBe("showed rail");
  });

  it("refuses once the component has really unmounted", async () => {
    const r = fakeReact();
    const stage = stageFor();
    stageHooks(r.hooks).useMove(stage, "core.show", async () => "showed");
    r.mount();
    r.unmount();
    const res = await stage.moves.run("core.show", { target: "rail" }, "c2");
    expect(res?.outcome).toBe("refused");
    expect(res?.detail).toMatch(/not on screen/);
  });
});
