/**
 * The developer-mode example (`sdk/python/examples/stage_shop`) works as it
 * reads: its page, its generated page spec and the script host make its cues
 * on its markup, and keep Stage's rules while they do.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import html from "../../../python/examples/stage_shop/index.html?raw";
import pageSpec from "../../../python/examples/stage_shop/scene.page.json?raw";
import { checkRegistry, conformance } from "../src/conformance";
import type { MoveContext } from "../src/moves";
import type { SceneSpec } from "../src/scene";
import { attach } from "../src/script";

function layOut(): void {
  const body = new DOMParser().parseFromString(html, "text/html").body;
  body.querySelectorAll("script").forEach((s) => s.remove());
  document.body.innerHTML = body.innerHTML;
  for (const el of document.body.querySelectorAll("*")) {
    el.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 100, height: 20, right: 100, bottom: 20, x: 0, y: 0, toJSON() {} }) as DOMRect;
  }
}

const client = { on() {}, off() {}, sendUIEvent() {} };

afterEach(() => {
  document.documentElement.querySelectorAll("[data-voqalize]").forEach((n) => n.remove());
  document.body.innerHTML = "";
});

describe("the stage_shop example", () => {
  it("binds every move, and its cues keep the rules on its own markup", async () => {
    layOut();
    const spec = JSON.parse(pageSpec) as SceneSpec;
    const added: string[] = [];
    const stage = await attach(client, {
      spec,
      theme: { color: "#000", beatMs: 0, dwellMs: 0 },
      performers: {
        // The page's own performer, as index.html writes it.
        "commerce.cart_add": (async ({ path }: { path: string }, c: MoveContext) => {
          const item = document.querySelector(`[data-path="${path}"]`);
          if (!item) return c.refuse("path", `no item ${path} on this page`);
          await c.ring(item.querySelector(".add")!, "Add to cart");
          added.push(path);
          item.setAttribute("data-added", "yes");
          return `added ${path}`;
        }) as never,
      },
    });
    expect(stage.unbound).toEqual([]);
    expect(checkRegistry(stage.scene, stage.moves)).toEqual([]);
    const found = await conformance(stage.scene, stage.moves, [
      { move: "core.show", args: { target: "our sheets" }, setup: layOut },
      { move: "commerce.filter", args: { facet: "Size", value: "King" }, setup: layOut },
      { move: "commerce.cart_add", args: { path: "/p/percale-king" }, setup: layOut },
    ]);
    expect(found).toEqual([]);
    expect(added).toEqual(["/p/percale-king"]);
    stage.detach();
  });

  it("refuses what the page does not have, offering what it does", async () => {
    layOut();
    const stage = await attach(client, { spec: JSON.parse(pageSpec) as SceneSpec, theme: { color: "#000" } });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const result = await stage.moves.run("commerce.filter", { facet: "Size", value: "Twin" }, "x1");
    expect(result).toMatchObject({ outcome: "refused", refused: [{ arg: "value", options: ["Queen", "King"] }] });
    stage.detach();
  });
});
