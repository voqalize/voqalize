/**
 * The booking's adapter (`booking-actions.ts`) on the saved /agenda-tu-hora/,
 * with a stand-in for Dentalsoft's own script (`fake-dentalsoft.js`, the real
 * IMask on the phones): the step read off the page, `booking_state` after
 * every change whoever made it, and the moves `open_booking`,
 * `fill_booking_patient`, `booking_pick` and `booking_scan`, step by step, up
 * to the review, where "Confirmar cita" is ringed and never pressed.
 */

import type { Page } from "@playwright/test";

import { events, expect, listen, perform, test } from "./site-ext";

const submits = (page: Page) => page.evaluate(() => (window as unknown as { __submits: string[] }).__submits);
const as = (page: Page, step: string, name = "") =>
  page.evaluate(([s, n]) => (window as unknown as { __ds: { as(s: string, n: string): void } }).__ds.as(s, n), [step, name] as const);
const state = async (page: Page) => {
  let all: Record<string, unknown>[] = [];
  await expect.poll(async () => (all = await events(page, "booking_state")).length).toBeGreaterThan(0);
  return all.at(-1)!;
};
/** The ids of what is ringed now. */
const ringedIds = (page: Page) =>
  page.evaluate(() => [...document.querySelectorAll("[data-voqalize=highlight]")].flatMap((r) => (r.getAttribute("data-ring-for") ?? "").split(" ").filter(Boolean)));

test.describe("the booking", () => {
  test("open_booking on the RUT step rings the RUT for the visitor, types nothing, and the state says only whether a RUT was typed", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    await listen(page);
    expect((await state(page)).step).toBe("getPAC");
    const out = await perform(page, "open_booking", { promo: "" });
    expect(out).toMatchObject({ event: "command_done", payload: { command: "open_booking" } });
    expect(String(out!.payload.detail)).toContain("the visitor types the RUT");
    await expect.poll(() => ringedIds(page)).toContain("rut");
    expect(await page.locator("#rut").inputValue()).toBe("");
    expect(await page.evaluate(() => document.activeElement?.id)).toBe("rut");
    // The visitor types it: the state says so, and never carries it.
    await page.locator("#rut").fill("12.345.678-5");
    await page.locator("#rut").dispatchEvent("change");
    await expect.poll(async () => (await state(page)).rut_entered).toBe(true);
    const all = JSON.stringify(await events(page, "booking_state"));
    expect(all).not.toContain("12.345.678");
    expect(all).not.toContain("12345678");
  });

  test("open_booking with a promotion's code loads the booking again with it, before the visitor starts", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    const out = await perform(page, "open_booking", { promo: "Convenio_Fonasa" });
    expect(out).toBeNull();
    await page.waitForURL("https://www.unosalud.cl/agenda-tu-hora/?promo=Convenio_Fonasa");
  });

  test("a step not on screen fails with the step that is", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    const out = await perform(page, "booking_pick", { motivo: 15, region: "", comuna: "", sucursal: "", date: "", time: "" });
    expect(out).toMatchObject({ event: "command_failed" });
    expect(String(out!.payload.reason)).toContain("on getPAC");
  });

  test("a new patient: the details are filled as dictated (the phone through the mask) and «Registrarse» is ringed, not pressed", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    await as(page, "setPAC");
    const out = await perform(page, "fill_booking_patient", {
      nombre: "María", paterno: "González", materno: "Pérez", birth_date: "1990-03-15", email: "maria@example.com", phone: "+56 9 1234 5678",
      confirm_existing: false,
    });
    expect(out).toMatchObject({ event: "command_done" });
    expect(String(out!.payload.detail)).toContain("«Registrarse» is ringed");
    expect(await page.locator("#nombre").inputValue()).toBe("María");
    expect(await page.locator("#paterno").inputValue()).toBe("González");
    expect(await page.locator("#materno").inputValue()).toBe("Pérez");
    expect(await page.locator("#fecnac").inputValue()).toBe("15-03-1990");
    expect(await page.locator("#new_emailpac").inputValue()).toBe("maria@example.com");
    // IMask's own formatting, from the digits typed into it.
    expect(await page.locator("#new_fono").inputValue()).toBe("+569 1234 5678");
    await expect.poll(() => ringedIds(page)).toContain("registro-paciente");
    expect(await submits(page)).toEqual([]);
  });

  test("a phone that is not a Chilean mobile is refused, and nothing is typed there", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    await as(page, "setPAC");
    const out = await perform(page, "fill_booking_patient", { nombre: "", paterno: "", materno: "", birth_date: "", email: "", phone: "22 345 678", confirm_existing: false });
    expect(out).toMatchObject({ event: "command_failed" });
    expect(String(out!.payload.reason)).toContain("Chilean mobile");
    expect(await page.locator("#new_fono").inputValue()).toBe("");
  });

  test("an existing patient: the greeting's name in the state, a new phone through the mask, and «Continuar» pressed on confirm", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    await listen(page);
    await as(page, "setEF", "Javiera");
    await expect.poll(async () => (await state(page)).patient_first_name).toBe("Javiera");
    const out = await perform(page, "fill_booking_patient", { nombre: "", paterno: "", materno: "", birth_date: "", email: "", phone: "987654321", confirm_existing: true });
    expect(out).toMatchObject({ event: "command_done" });
    expect(await page.locator("#fono").inputValue()).toBe("+569 8765 4321");
    expect(await submits(page)).toEqual(["actualiza-datos"]);
    await expect.poll(async () => (await state(page)).step).toBe("getMRes");
  });

  test("booking_pick from the motivo to the review: each step taken and reported, the hour pressed, and «Confirmar cita» ringed for the visitor", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    await listen(page);
    await as(page, "getMRes");
    const out = await perform(page, "booking_pick", { motivo: 15, region: "", comuna: "", sucursal: "Manuel Montt", date: "2026-10-28", time: "10:30" });
    expect(out).toMatchObject({ event: "command_done", payload: { command: "booking_pick" } });
    expect(String(out!.payload.detail)).toContain("«Confirmar cita» is ringed");
    await expect.poll(async () => (await state(page)).step).toBe("getDC");
    const s = await state(page);
    expect(s).toMatchObject({ step: "getDC", motivo: 15, date: "2026-10-28", booked: false });
    expect(String(s.sucursal)).toContain("MANUEL MONTT");
    expect(s.summary).toMatchObject({ fecha: "28-10-2026", hora: "10:30", odontologo: "Dra. Ana Pérez" });
    await expect.poll(() => ringedIds(page)).toContain("confirma-cita");
    // The step buttons he may press, and the hour's own move to the review:
    // never «Confirmar cita».
    expect(await submits(page)).toEqual(["selecciona-motivo", "continue_getSuc", "continue_getHor"]);
    // Every step was reported on the way.
    const steps = (await events(page, "booking_state")).map((e) => e.step);
    expect(steps).toEqual(expect.arrayContaining(["getMRes", "getSuc", "getHor", "getDC"]));
  });

  test("a day with no hours says so; a day that cannot be booked fails with the open days", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    await listen(page);
    await as(page, "getHor");
    let out = await perform(page, "booking_pick", { motivo: 0, region: "", comuna: "", sucursal: "", date: "2026-10-30", time: "" });
    expect(out).toMatchObject({ event: "command_done" });
    expect(String(out!.payload.detail)).toContain("no hours that day");
    await expect.poll(async () => (await state(page)).no_slots).toBe(true);
    out = await perform(page, "booking_pick", { motivo: 0, region: "", comuna: "", sucursal: "", date: "2026-11-01", time: "" });
    expect(out).toMatchObject({ event: "command_failed" });
    expect(String(out!.payload.reason)).toContain("cannot be booked");
  });

  test("booking_scan reads successive open days (past a month's end, skipping closed days) and leaves the first with hours picked", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    await listen(page);
    await as(page, "getHor");
    const out = await perform(page, "booking_scan", { from_date: "2026-10-29", days: 4 });
    expect(out).toMatchObject({ event: "command_done", payload: { command: "booking_scan" } });
    await expect.poll(async () => ((await state(page)).days as unknown[]).length).toBe(4);
    const s = await state(page);
    // 29, 30, 31 Oct, then 2 Nov (1 Nov is a Sunday, closed); a day divisible by 3 has none.
    expect(s.days).toEqual([
      { date: "2026-10-29", times: ["09:00", "10:30", "16:15"] },
      { date: "2026-10-30", times: [] },
      { date: "2026-10-31", times: ["09:00", "10:30", "16:15"] },
      { date: "2026-11-02", times: ["09:00", "10:30", "16:15"] },
    ]);
    expect(s).toMatchObject({ step: "getHor", date: "2026-10-29", slots: ["09:00", "10:30", "16:15"] });
  });

  test("the visitor's own changes are reported too", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    await listen(page);
    await as(page, "getSuc");
    await page.locator("#region").selectOption("13");
    await page.locator("#comuna").selectOption({ index: 1 });
    await expect.poll(async () => (await state(page)).comuna).not.toBe("");
    expect((await state(page)).region).toContain("METROPOLITANA");
  });
});
