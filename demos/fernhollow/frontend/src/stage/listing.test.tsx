/**
 * Emily filters the page you are on (CONTRACT.md v5): the listing moves on the
 * real Dining page. Each rings the rail's own control and presses it as a
 * click would, so the checkbox, the URL and the grid change in place and
 * nothing navigates; an option the page does not offer is refused with the
 * ones it does.
 */
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Moves, Spotlight } from "@voqalize/stage";
import { checkRegistry, conformance } from "@voqalize/stage/conformance";
import { RoomPage } from "../pages/Listing";
import { setEventSender } from "../voice/events";
import { useAppStage } from "./host";
import { scene } from "./scene.gen";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
Element.prototype.scrollIntoView = function () {};
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

const moves = new Moves(new Spotlight({ color: "#4b45c6", beatMs: 0, dwellMs: 0 }));
const seen: { path: string; search: string }[] = [];
const sent: [string, Record<string, unknown>][] = [];

function Probe() {
  const l = useLocation();
  seen.push({ path: l.pathname, search: l.search });
  return null;
}

let root: ReturnType<typeof createRoot>;
async function mount(entry = "/room/dining") {
  root?.unmount();
  document.body.innerHTML = "";
  const host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  root.render(
    <MemoryRouter initialEntries={[entry]}>
      <Probe />
      <Routes>
        <Route path="/room/:room" element={<RoomPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await sleep(250);
}

const run = async (move: string, args: unknown) => {
  await sleep(80);
  return moves.run(move, args, `${move}-${Math.random().toString(36).slice(2, 7)}`);
};
const count = () => Number(document.querySelector(".listing-count")?.textContent?.match(/\d+/)?.[0]);
const box = (facet: string, value: string) =>
  document.querySelector(`.rail-filters [data-stage-part="${facet}:${value}"] input`) as HTMLInputElement | null;

beforeAll(() => {
  // The shell's Stage, as useStage builds it, with no call underneath.
  useAppStage.setState({
    stage: { scene, moves, page: { send() {}, hello() {}, detach() {} }, agent: null } as never,
  });
  setEventSender((event, payload) => sent.push([event, payload as Record<string, unknown>]));
});
afterAll(() => root?.unmount());

describe("listing moves", () => {
  it("every listing move has a performer on a listing page", async () => {
    await mount();
    expect(checkRegistry(scene, moves).filter((f) => f.move.startsWith("listing."))).toEqual([]);
  });

  it("ring before they act, and report once", async () => {
    await mount();
    const settle = () => sleep(80);
    const found = await conformance(scene, moves, [
      { move: "listing.filter", args: { facet: "Material", value: "Ceramic" }, setup: settle },
      { move: "listing.unfilter", args: { facet: "Material", value: "Ceramic" }, setup: settle },
      { move: "listing.filter", args: { facet: "Finish", value: "walnut" }, setup: settle },
      { move: "listing.price", args: { max: 500 }, setup: settle },
      { move: "listing.sort", args: { by: "price low to high" }, setup: settle },
      { move: "listing.clear_filters", args: {}, setup: settle },
    ]);
    expect(found.filter((f) => f.level === "error")).toEqual([]);
  });
});

describe("on the Dining page", () => {
  it("listing.filter{Material, Ceramic} ticks the real checkbox, updates the URL and the grid, and does not navigate", async () => {
    await mount();
    const all = count();
    expect(box("Material", "Ceramic")?.checked).toBe(false);
    const r = await run("listing.filter", { facet: "material", value: "ceramic" });
    await sleep(80);
    expect(r?.outcome).toBe("applied");
    expect(box("Material", "Ceramic")?.checked).toBe(true);
    const last = seen[seen.length - 1];
    expect(last.path).toBe("/room/dining");
    expect(decodeURIComponent(last.search)).toContain("opt=Material:Ceramic");
    expect(count()).toBeLessThan(all);
    expect(r?.detail).toBe(`Material: Ceramic on — ${count()} pieces`);
    expect(new Set(seen.map((s) => s.path))).toEqual(new Set(["/room/dining"]));
  });

  it("refuses an option the page does not offer, with the ones it does", async () => {
    await mount();
    const r = await run("listing.filter", { facet: "Material", value: "Velvet" });
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("Ceramic");
    const f = await run("listing.filter", { facet: "Colour", value: "Blue" });
    expect(f?.outcome).toBe("refused");
    expect(JSON.stringify(f)).toContain("Finish");
    expect(box("Material", "Ceramic")?.checked).toBe(false);
  });

  it("refuses to untick what is not on", async () => {
    await mount();
    expect((await run("listing.unfilter", { facet: "Material", value: "Ceramic" }))?.outcome).toBe("refused");
  });

  it("sends listing_viewed with the rail's own labels, on arrival and after a change", async () => {
    sent.length = 0;
    await mount();
    await sleep(300);
    const arrival = sent.filter(([e]) => e === "listing_viewed").at(-1)?.[1];
    expect(arrival).toMatchObject({ page: "/room/dining", title: "Dining", active: {}, sort: "Featured" });
    expect((arrival?.facets as Record<string, string[]>).Material).toContain("Ceramic");
    await run("listing.filter", { facet: "Material", value: "Ceramic" });
    await sleep(350);
    const after = sent.filter(([e]) => e === "listing_viewed").at(-1)?.[1];
    expect(after?.active).toEqual({ Material: ["Ceramic"] });
    expect(after?.count).toBe(count());
    expect(after?.by).toBe("emily");
  });
});
