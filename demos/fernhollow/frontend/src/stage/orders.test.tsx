/**
 * The events the brain hears from the orders page and the return form
 * (src/stage/orders.ts): sent from the shell, with values, and with the hand
 * that made each change — the agent's move, or the shopper's tap.
 */
import { createRoot } from "react-dom/client";
import { afterAll, describe, expect, it } from "vitest";
import { Moves, Spotlight } from "@voqalize/stage";
import { useAccount, useOrderView } from "../orders/tracking";
import { useReturns } from "../returns/store";
import { useOrderMoves } from "./orders";
import { scene } from "./scene.gen";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

const sent: { name: string; by: string; data: Record<string, unknown>; call_ref?: string }[] = [];
const stage = {
  scene,
  moves: new Moves(new Spotlight({ color: "#000", beatMs: 0, dwellMs: 0 })),
  page: { send: (e: (typeof sent)[number]) => sent.push(e) },
  agent: { callRef: "call-1", until: Number.POSITIVE_INFINITY },
} as never;

function Shell() {
  useOrderMoves(stage);
  return null;
}

const host = document.createElement("div");
document.body.appendChild(host);
const root = createRoot(host);
afterAll(() => root.unmount());

describe("orders and returns events", () => {
  it("carry values and the hand that made the change", async () => {
    root.render(<Shell />);
    await sleep(50);
    useOrderView.getState().setOpen("FH-31207", "visitor");
    await sleep(20);
    useAccount.getState().move("FH-31207", "d3-evening", "emily");
    await sleep(20);
    useAccount.getState().requestEarlier("FH-31188");
    await sleep(20);
    useReturns.getState().start("FH-20418", "emily");
    await sleep(20);
    useReturns.getState().setItem("desk-chair-with-aluminum-frame", 1);
    await sleep(20);
    useReturns.getState().setStep(2, "emily");
    await sleep(20);
    useReturns.getState().setChoice("reason", "doesnt_suit_room", "emily");
    await sleep(20);
    useAccount.getState().cancel("FH-31207");
    await sleep(20);

    expect(sent.map((e) => [e.name, e.by, e.data])).toEqual([
      ["orders.opened", "visitor", { order_number: "FH-31207", status: "packed" }],
      ["orders.delivery_changed", "agent", { order_number: "FH-31207", slot: "d3-evening" }],
      ["orders.earlier_requested", "visitor", { order_number: "FH-31188" }],
      ["orders.return_started", "agent", { order_number: "FH-20418", step: 1, filled: [] }],
      [
        "returns.field_filled",
        "visitor",
        { order_number: "FH-20418", field: "qty_desk-chair-with-aluminum-frame", value: "1", filled: ["items", "qty_desk-chair-with-aluminum-frame"] },
      ],
      ["returns.step_reached", "agent", { order_number: "FH-20418", step: 2, filled: ["items", "qty_desk-chair-with-aluminum-frame"] }],
      [
        "returns.field_filled",
        "agent",
        { order_number: "FH-20418", field: "reason", value: "doesnt_suit_room", filled: ["items", "qty_desk-chair-with-aluminum-frame", "reason"] },
      ],
      ["orders.cancelled", "visitor", { order_number: "FH-31207", status: "cancelled" }],
    ]);
    expect(sent.find((e) => e.by === "agent")?.call_ref).toBe("call-1");
  });
});
