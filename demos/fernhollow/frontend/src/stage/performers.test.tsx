/**
 * The returns form's Stage performers, held to Stage's rules on the real form:
 * every declared move has a performer under its class, each reports one
 * result, nothing on the page changes before the spotlight rings it, and a
 * value the form does not offer is refused with the values it does.
 */
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Moves, Spotlight } from "@voqalize/stage";
import { checkRegistry, conformance } from "@voqalize/stage/conformance";
import { ReturnsForm } from "../pages/Returns";
import { useReturns } from "../returns/store";
import { returnsPerformers } from "./performers";
import { scene } from "./scene.gen";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const settle = () => sleep(120);
const CHAIR = "desk-chair-with-aluminum-frame";

let root: ReturnType<typeof createRoot>;

function moves(): Moves {
  const m = new Moves(new Spotlight({ color: "#4b45c6", beatMs: 0, dwellMs: 0 }));
  scene.registerAll(m, returnsPerformers());
  return m;
}

beforeAll(async () => {
  // No smooth scrolling here, and every element has a box to ring.
  Element.prototype.scrollIntoView = function () {};
  const host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  root.render(
    <MemoryRouter initialEntries={["/returns/start?order=FH-20418"]}>
      <Routes>
        <Route path="/returns/start" element={<ReturnsForm />} />
      </Routes>
    </MemoryRouter>,
  );
  await sleep(300);
});

afterAll(() => root.unmount());

describe("returns performers", () => {
  it("registers every declared move under its class", () => {
    expect(checkRegistry(scene, moves())).toEqual([]);
  });

  it("ring before they act, and report once", async () => {
    const m = moves();
    const found = await conformance(scene, m, [
      { move: "returns.fill", args: { field: "order_number", value: "FH-20418" }, setup: settle },
      { move: "returns.open_step", args: { step: 3 }, setup: settle },
      { move: "returns.fill", args: { field: "reason", value: "doesnt_suit_room" }, setup: settle },
      { move: "returns.select_item", args: { product_id: CHAIR, qty: 1 }, setup: settle },
      { move: "returns.fill", args: { field: "resolution", value: "exchange" }, setup: settle },
      { move: "returns.fill", args: { field: `exchange_variant_${CHAIR}`, value: "Walnut" }, setup: settle },
      { move: "returns.fill", args: { field: "collection", value: "pickup" }, setup: settle },
      { move: "returns.fill", args: { field: "pickup_window", value: "saturday" }, setup: settle },
    ]);
    expect(found.filter((f) => f.level === "error")).toEqual([]);
    const s = useReturns.getState();
    expect(s.order_number).toBe("FH-20418");
    expect(s.reason).toBe("doesnt_suit_room");
    expect(s.items[CHAIR]).toBe(1);
    expect(s.exchange[CHAIR]).toBe("Walnut");
    expect(s.pickup_window).toBe("saturday");
    expect(s.by.reason).toBe("emily");
  });

  it("answers with one short line", async () => {
    await settle();
    const r = await moves().run("returns.fill", { field: "reason", value: "doesnt_suit_room" }, "line-1");
    expect(r?.outcome).toBe("applied");
    expect(r?.detail).toBe("reason set to doesn't suit the room");
  });

  it("refuses a value the form does not offer, with the values it does", async () => {
    await settle();
    const r = await moves().run("returns.fill", { field: "reason", value: "too_big" }, "bad-1");
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("doesnt_suit_room");
    expect(useReturns.getState().reason).toBe("doesnt_suit_room");
  });

  it("never fills the email", async () => {
    await settle();
    const r = await moves().run("returns.fill", { field: "email", value: "sam.rivera@example.com" }, "email-1");
    expect(r?.outcome).toBe("refused");
    expect(useReturns.getState().email).toBe("");
  });

  it("refuses a step that does not exist, and an item not in the order", async () => {
    await settle();
    expect((await moves().run("returns.open_step", { step: 9 }, "step-9"))?.outcome).toBe("refused");
    const r = await moves().run("returns.select_item", { product_id: "oatmeal-wool-runner", qty: 1 }, "item-x");
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain(CHAIR);
  });

  it("refuses more than were ordered", async () => {
    await settle();
    const r = await moves().run("returns.select_item", { product_id: CHAIR, qty: 3 }, "qty-3");
    expect(r?.outcome).toBe("refused");
  });
});
