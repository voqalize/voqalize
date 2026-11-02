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
import { CategoryPage, RoomPage } from "../pages/Listing";
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
        <Route path="/category/:slug" element={<CategoryPage />} />
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
      { move: "listing.range", args: { facet: "Price", min: 100 }, setup: settle },
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

  it("sends listing_viewed with each facet by kind, on arrival and after a change", async () => {
    sent.length = 0;
    await mount();
    await sleep(300);
    const arrival = sent.filter(([e]) => e === "listing_viewed").at(-1)?.[1] as any;
    expect(arrival).toMatchObject({ page: "/room/dining", title: "Dining", sort: { value: "Featured" } });
    const material = arrival.facets.find((x: any) => x.name === "Material");
    expect(material).toMatchObject({ kind: "options", multi: true });
    expect(material.values).toContain("Ceramic");
    expect(material.active).toBeUndefined();
    await run("listing.filter", { facet: "Material", value: "Ceramic" });
    await sleep(350);
    const after = sent.filter(([e]) => e === "listing_viewed").at(-1)?.[1] as any;
    expect(after.facets.find((x: any) => x.name === "Material").active).toEqual(["Ceramic"]);
    expect(after.count).toBe(count());
    expect(after.by).toBe("emily");
  });
});

const lastViewed = () => sent.filter(([e]) => e === "listing_viewed").at(-1)?.[1] as any;
const partsIn = (facet: string) =>
  [...document.querySelectorAll(`.rail-filters [data-stage-part^="${facet}:"]`)].map((el) => el.getAttribute("data-stage-part")!.slice(facet.length + 1));

describe.each(["dining-chairs", "sofas", "rugs", "table-lamps"])("the rail on /category/%s, by kind", (slug) => {
  it("listing_viewed describes every facet of the rail, by kind, with its exact labels", async () => {
    sent.length = 0;
    await mount(`/category/${slug}`);
    await sleep(320);
    const v = lastViewed();
    expect(v.page).toBe(`/category/${slug}`);
    expect(v.count).toBe(count());
    expect(v.sort.options).toContain("Price, low to high");
    const groups = [...document.querySelectorAll(".rail-filters .filter-title")].map((el) => el.textContent).filter((t) => t !== "Search within");
    const toggles = [...document.querySelectorAll(".rail-filters .toggle")].map((el) => el.textContent?.replace(/\d+$/, "").trim());
    expect(v.facets.map((x: any) => x.name)).toEqual(expect.arrayContaining([...groups, ...toggles]));
    for (const x of v.facets) {
      if (x.kind === "options") expect(partsIn(x.name)).toEqual(x.values);
      if (x.kind === "bands") {
        expect(partsIn(x.name)).toEqual(x.bands.map((b: any) => b.label));
        for (const b of x.bands) expect(b.min != null || b.max != null).toBe(true);
      }
      if (x.kind === "toggle") expect(partsIn(x.name)).toEqual([x.name]);
    }
    expect(v.facets.find((x: any) => x.name === "Price").kind).toBe("bands");
  });

  it("a bands facet and an options facet both apply through moves, as clicks would", async () => {
    await mount(`/category/${slug}`);
    await sleep(320);
    const v = lastViewed();
    const price = v.facets.find((x: any) => x.kind === "bands");
    const band = price.bands[0];
    const r1 = await run("listing.filter", { facet: price.name, value: band.label });
    await sleep(320);
    expect(r1?.outcome).toBe("applied");
    expect(document.querySelector(`.rail-filters [data-stage-part="${price.name}:${band.label}"]`)?.getAttribute("aria-pressed")).toBe("true");
    expect(r1?.detail).toBe(`${price.name}: ${band.label} on — ${count()} ${count() === 1 ? "piece" : "pieces"}`);
    expect(lastViewed().facets.find((x: any) => x.name === price.name).active).toEqual([band.label]);

    const opt = lastViewed().facets.find((x: any) => x.kind === "options" && x.name !== "Category" && x.values.length > 1);
    const value = opt.values[0];
    const r2 = await run("listing.filter", { facet: opt.name.toLowerCase(), value: value.toLowerCase() });
    await sleep(320);
    expect(r2?.outcome).toBe("applied");
    expect(box(opt.name, value)?.checked).toBe(true);
    const after = lastViewed();
    expect(after.count).toBe(count());
    expect(r2?.detail).toBe(`${opt.name}: ${value} on — ${count()} ${count() === 1 ? "piece" : "pieces"}`);
    expect(after.facets.find((x: any) => x.name === opt.name).active).toEqual([value]);
    expect(seen.at(-1)?.path).toBe(`/category/${slug}`);
  });
});

describe("listing.range on a bands facet", () => {
  const chips = () =>
    [...document.querySelectorAll('.rail-filters [data-stage-part^="Price:"]')].map((el) => ({
      label: el.getAttribute("data-stage-part")!.slice("Price:".length),
      pressed: el.getAttribute("aria-pressed") === "true",
    }));

  it("max equal to a band's top presses that band (and listing.price is the same move)", async () => {
    await mount("/category/dining-chairs");
    await sleep(320);
    const under = lastViewed().facets.find((x: any) => x.name === "Price").bands[0];
    const r = await run("listing.range", { facet: "Price", max: under.max });
    await sleep(320);
    expect(r?.outcome).toBe("applied");
    expect(chips()[0].pressed).toBe(true);
    expect(seen.at(-1)?.search).toContain(`max=${under.max}`);
    await mount("/category/dining-chairs");
    const again = await run("listing.price", { max: under.max });
    expect(again?.detail).toBe(r?.detail);
  });

  it("a span across two bands takes both in", async () => {
    await mount("/category/dining-chairs");
    await sleep(320);
    const [, middle] = lastViewed().facets.find((x: any) => x.name === "Price").bands;
    const r = await run("listing.range", { facet: "Price", max: middle.max - 10 });
    await sleep(320);
    expect(r?.outcome).toBe("applied");
    expect(r?.detail).toContain(" and ");
    expect(seen.at(-1)?.search).toContain(`max=${middle.max - 10}`);
  });

  it("refuses a span no band reaches, with the band labels", async () => {
    await mount("/category/dining-chairs");
    const r = await run("listing.range", { facet: "Price", min: 1_000_000 });
    expect(r?.outcome).toBe("refused");
    for (const c of chips()) expect(JSON.stringify(r)).toContain(c.label);
  });

  it("refuses a facet that is not a range, naming the ones that are", async () => {
    await mount("/category/dining-chairs");
    const r = await run("listing.range", { facet: "Finish", max: 3 });
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("Price");
  });
});

describe("the count the brain hears", () => {
  it("after Finish: Walnut it is the grid's own count, and no filter_changed is sent", async () => {
    await mount("/category/dining-chairs");
    await sleep(320);
    sent.length = 0;
    const r = await run("listing.filter", { facet: "Finish", value: "Walnut" });
    await sleep(350);
    const shown = count();
    expect(shown).toBeGreaterThan(0);
    expect(r?.detail).toBe(`Finish: Walnut on — ${shown} pieces`);
    const viewed = sent.filter(([e]) => e === "listing_viewed");
    expect(viewed.length).toBeGreaterThan(0);
    for (const [, p] of viewed) expect(p.count).toBe(shown);
    expect(sent.filter(([e]) => e === "filter_changed")).toEqual([]);
  });
});
