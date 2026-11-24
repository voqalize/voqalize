/**
 * The site's Stage performers on the real pages, held to Stage's rules: every
 * declared move has a performer under its class, each reports one result,
 * nothing changes before the spotlight rings it, and each agent's main flow
 * can be made by moves alone, ending where a click would.
 */
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { Moves, Spotlight } from "@voqalize/stage";
import { checkRegistry, conformance } from "@voqalize/stage/conformance";
import { BookDemo } from "../pages/BookDemo";
import { Home } from "../pages/Home";
import { Pricing } from "../pages/Pricing";
import { businessDays, slotsOn, todayIst } from "../lib/calendar";
import { actions, useSite } from "../state/store";
import { StageHost } from "./host";
import { performers } from "./performers";
import { scene } from "./scene.gen";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
Element.prototype.scrollIntoView = function () {};
window.scrollTo = (() => undefined) as typeof window.scrollTo;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
let root: ReturnType<typeof createRoot> | null = null;

function fresh(): Moves {
  const m = new Moves(new Spotlight({ color: "#e8a33d", beatMs: 0, dwellMs: 0 }));
  scene.registerAll(m, performers());
  return m;
}

async function open(path: string) {
  root?.unmount();
  document.body.innerHTML = "";
  actions.reset();
  const host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  root.render(
    <MemoryRouter initialEntries={[path]}>
      <StageHost />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/book-demo" element={<BookDemo />} />
      </Routes>
    </MemoryRouter>,
  );
  await sleep(250);
}

const run = (m: Moves, move: string, args: unknown) => m.run(move, args, `${move}-${Math.random().toString(36).slice(2, 7)}`);

afterAll(() => root?.unmount());

describe("registry", () => {
  it("has a performer for every declared move, under its class", () => {
    expect(checkRegistry(scene, fresh()).filter((f) => f.level === "error")).toEqual([]);
  });
});

describe("sales rep on /", () => {
  beforeEach(() => open("/"));

  it("fills the lead card field by field and marks modules, ringing first", async () => {
    const findings = await conformance(scene, fresh(), [
      { move: "lead.fill", args: { field: "company", value: "Banyan & Bay Foods" } },
      { move: "lead.fill", args: { field: "headcount", value: "56" } },
      { move: "lead.fill", args: { field: "pains", items: ["tax_proofs"] } },
      { move: "modules.highlight", args: { ids: ["tax", "declarations"] } },
      { move: "modules.show", args: { id: "declarations" } },
    ]);
    expect(findings.filter((f) => f.level === "error")).toEqual([]);
    const s = useSite.getState();
    expect(s.lead.company).toBe("Banyan & Bay Foods");
    expect(s.lead.headcount).toBe(56);
    expect(s.matched).toEqual(["tax", "declarations"]);
  });

  it("refuses a pain the card does not list, with the ones it does", async () => {
    const r = await run(fresh(), "lead.fill", { field: "pains", items: ["morale"] });
    expect(r?.outcome).toBe("refused");
    expect(r?.refused?.[0]?.options).toContain("tax_proofs");
  });
});

describe("pricing on /pricing", () => {
  beforeEach(() => open("/pricing"));

  it("sets the calculator and shows the shared rule's numbers", async () => {
    const m = fresh();
    const r = await run(m, "pricing.set", { headcount: 56, modules: ["reimbursements"], billing: "monthly", filing: false });
    expect(r?.outcome).toBe("applied");
    expect(r?.detail).toContain("₹6,664");
    await sleep(100);
    expect(document.querySelector('[data-stage-part="line:base"]')?.textContent).toContain("6,664");
    const line = await run(m, "pricing.line", { item: "gst" });
    expect(line?.outcome).toBe("applied");
  });
});

describe("booker on /book-demo", () => {
  beforeEach(() => open("/book-demo"));

  it("picks a free slot, fills the form and confirms with a reference", async () => {
    const day = businessDays(todayIst()).find((d) => slotsOn(d).some((s) => !s.taken))!;
    const slot = slotsOn(day).find((s) => !s.taken)!;
    const m = fresh();
    expect((await run(m, "calendar.show", { day }))?.outcome).toBe("applied");
    await sleep(50);
    expect((await run(m, "booking.pick", { slot_id: slot.id }))?.outcome).toBe("applied");
    const early = await run(m, "booking.confirm", {});
    expect(early?.outcome).toBe("refused");
    for (const [field, value] of [["name", "Meghna Rao"], ["company", "Banyan & Bay Foods"], ["email", "meghna@banyanbay.example"]]) {
      await sleep(30);
      expect((await run(m, "booking.fill", { field, value }))?.outcome).toBe("applied");
    }
    const done = await run(m, "booking.confirm", {});
    expect(done?.outcome).toBe("applied");
    expect(useSite.getState().booking.status).toBe("confirmed");
    expect(done?.detail).toMatch(/TKD-\d{4}-\d{4}-[A-Z]{2}/);
  });

  it("refuses a taken slot", async () => {
    const taken = businessDays(todayIst()).flatMap(slotsOn).find((s) => s.taken)!;
    const r = await run(fresh(), "booking.pick", { slot_id: taken.id });
    expect(r?.outcome).toBe("refused");
  });
});
