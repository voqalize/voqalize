/**
 * The site adapter (`unosalud-actions.ts`) on the saved pages, served with the
 * site's headers: what each page reports (`page_changed`: its kind, the
 * catalogue's places and FAQs on it, its form, and on a clinic's page the
 * clinic's own facts), and the moves (`navigate`, `show_section`,
 * `open_faq`) by the catalogue's keys, with what hides a place revealed as a
 * visitor would reveal it.
 */

import type { Page } from "@playwright/test";

import { expect, perform, test } from "./site-ext";

const context = (page: Page) =>
  page.evaluate(() => (window as unknown as { voqalizeUnosalud: { context(): Record<string, unknown> } }).voqalizeUnosalud.context());
const ring = (page: Page) => page.locator("[data-voqalize=highlight]");
/** The ring's box against `selector`'s: the ring is drawn around it. */
async function ringed(page: Page, selector: string): Promise<boolean> {
  await expect(ring(page).first()).toHaveCSS("opacity", "1");
  return page.evaluate((sel) => {
    const r = document.querySelector("[data-voqalize=highlight]")!.getBoundingClientRect();
    const t = document.querySelector(sel)!.getBoundingClientRect();
    return r.left <= t.left + 1 && r.top <= t.top + 1 && r.right >= t.right - 1 && r.bottom >= t.bottom - 1;
  }, selector);
}
const inView = (page: Page, selector: string) =>
  page.evaluate((sel) => {
    const r = document.querySelector(sel)!.getBoundingClientRect();
    return r.top >= 0 && r.top < window.innerHeight && r.bottom > 0;
  }, selector);

test.describe("what a page reports", () => {
  test("the home: its kind and the catalogue's places on it, with no form", async ({ ext }) => {
    const page = await ext.open("/");
    const c = await context(page);
    expect(c).toMatchObject({ path: "/", kind: "home", form: "none", clinic: null });
    expect(c.anchors).toEqual(expect.arrayContaining(["home_atajos", "home_especialidades", "home_clinicas", "home_testimonios", "home_por_que"]));
  });

  test("a clinic's page: its name, address, hours, references and directions, read from the page", async ({ ext }) => {
    const page = await ext.open("/clinicas/moneda/");
    const c = await context(page);
    expect(c).toMatchObject({ path: "/clinicas/moneda/", kind: "clinic" });
    expect(c.clinic).toEqual({
      name: "Moneda",
      address: "Moneda #953, Santiago, Región Metropolitana",
      hours: "Lunes a viernes: 8:30 a 20:00 hrs.; Sábados: 9:00 a 14:00 hrs.",
      references: "A pasos del Metro Universidad de Chile; A pasos del Metro Plaza de Armas",
      maps_url: "https://www.google.com/maps/dir/?api=1&destination=-33.4418166,-70.65",
    });
    expect(c.anchors).toEqual(expect.arrayContaining(["clinica_hero", "clinica_horario", "clinica_referencias", "clinica_mapa"]));
  });

  test("the FAQ page lists its questions by key; the forms' pages name their form", async ({ ext }) => {
    let page = await ext.open("/preguntas-frecuentes/");
    let c = await context(page);
    expect(c.kind).toBe("faq");
    expect(c.faqs).toEqual(expect.arrayContaining(["faq_pad", "faq_isapre_clinica"]));
    page = await ext.open("/landing/solicitar-diagnostico/");
    expect(await context(page)).toMatchObject({ kind: "callback", form: "callback" });
    page = await ext.open("/urgencias/");
    expect(await context(page)).toMatchObject({ kind: "urgencias", form: "urgencias" });
    page = await ext.open("/landing/convenio-empresa/");
    expect(await context(page)).toMatchObject({ kind: "company", form: "company" });
    page = await ext.open("/agenda-tu-hora/");
    c = await context(page);
    expect(c).toMatchObject({ kind: "booking", form: "booking" });
  });

  test("what the adapter matches on is kept from Chrome's translation", async ({ ext }) => {
    const page = await ext.open("/preguntas-frecuentes/");
    expect(await page.locator("#heading-faq-14421").getAttribute("translate")).toBe("no");
    expect(await page.locator("h1").first().getAttribute("translate")).toBe("no");
    const booking = await ext.open("/agenda-tu-hora/");
    expect(await booking.locator("#motivo").getAttribute("translate")).toBe("no");
    expect(await booking.locator("#datepicker-fecha").getAttribute("translate")).toBe("no");
  });
});

test.describe("the moves", () => {
  test("show_section by key: scrolled under the header and ringed", async ({ ext }) => {
    const page = await ext.open("/");
    const out = await perform(page, "show_section", { anchor: "home_testimonios", text: "" });
    expect(out).toBeNull();
    expect(await inView(page, "#testimonios")).toBe(true);
    expect(await ringed(page, "#testimonios")).toBe(true);
  });

  test("show_section of a place on another page fails, naming the page; a key the catalogue lacks fails", async ({ ext }) => {
    const page = await ext.open("/");
    let out = await perform(page, "show_section", { anchor: "clinica_horario", text: "" });
    expect(out).toMatchObject({ event: "command_failed", payload: { command: "show_section" } });
    expect(String(out!.payload.reason)).toContain("/clinicas/*/");
    out = await perform(page, "show_section", { anchor: "no_such_place", text: "" });
    expect(String(out!.payload.reason)).toContain("no place");
  });

  test("a price pane behind its pill: the pill is pressed, the pane shown and ringed", async ({ ext }) => {
    const page = await ext.open("/especialidades/ortodoncia/");
    expect(await page.locator("#tab1").getAttribute("class")).not.toContain("active");
    await perform(page, "show_section", { anchor: "ortodoncia_precios_ceramicos", text: "" });
    await expect(page.locator("#tab1")).toHaveClass(/active/);
    await expect(page.locator("#tab0")).not.toHaveClass(/active/);
    expect(await ringed(page, "#tab1")).toBe(true);
    // The page did not jump to its top for the pill's href="#".
    expect(await inView(page, "#tab1")).toBe(true);
  });

  test("a clinic in the list that scrolls by itself: the list is scrolled to it", async ({ ext }) => {
    const page = await ext.open("/clinicas/");
    await perform(page, "show_section", { anchor: "clinicas_vitacura", text: "" });
    const sel = '#mapa-list [data-target="1872"]';
    const inList = await page.evaluate((s) => {
      const el = document.querySelector(s)!.getBoundingClientRect();
      const list = document.querySelector("#mapa-list .list")!.getBoundingClientRect();
      return el.top >= list.top - 1 && el.bottom <= list.bottom + 1;
    }, sel);
    expect(inList).toBe(true);
    expect(await ringed(page, sel)).toBe(true);
  });

  test("open_faq by key: the question opens (its answer `.show`) and is ringed", async ({ ext }) => {
    const page = await ext.open("/preguntas-frecuentes/");
    await expect(page.locator("#collapse-faq-14421")).not.toHaveClass(/\bshow\b/);
    const out = await perform(page, "open_faq", { faq: "faq_pad" });
    expect(out).toBeNull();
    await expect(page.locator("#collapse-faq-14421")).toHaveClass(/\bshow\b/);
    expect(await inView(page, "#heading-faq-14421")).toBe(true);
    await expect(ring(page)).toHaveCount(1);
  });

  test("navigate with an anchor: the page loads, and the place is shown on it", async ({ ext }) => {
    const page = await ext.open("/");
    await perform(page, "navigate", { path: "/clinicas/moneda/", anchor: "clinica_horario", text: "", faq: "" });
    await page.waitForURL("https://www.unosalud.cl/clinicas/moneda/");
    await expect(ring(page)).toHaveCount(1, { timeout: 15_000 });
    expect(await ringed(page, "main > header div.shadow-sm div.col-lg-6:nth-of-type(1)")).toBe(true);
  });

  test("navigate refuses the booking (it has its own tab) and another site", async ({ ext }) => {
    const page = await ext.open("/");
    let out = await perform(page, "navigate", { path: "/agenda-tu-hora/", anchor: "", text: "", faq: "" });
    expect(String(out!.payload.reason)).toContain("open_booking");
    out = await perform(page, "navigate", { path: "https://example.com/", anchor: "", text: "", faq: "" });
    expect(String(out!.payload.reason)).toContain("not on");
  });
});
