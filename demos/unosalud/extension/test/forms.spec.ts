/**
 * The lead forms on Brevo (`unosalud-actions.ts`), on the saved pages with a
 * stand-in for Brevo's delayed helpers (`fake-brevo.js`): Te llamamos, the
 * urgencias page's form and Convenio Empresas. Filled as the visitor said,
 * the RUT left to the visitor (focused and ringed), ENVIAR ringed and never
 * pressed, and the form's state reported, Brevo's answer included, with only
 * whether a RUT was typed.
 */

import type { Page } from "@playwright/test";

import { events, expect, listen, ORIGIN, perform, test } from "./site-ext";

const submits = (page: Page) => page.evaluate(() => (window as unknown as { __submits: string[] }).__submits);
const value = (page: Page, sel: string) => page.locator(sel).inputValue();
const last = async (page: Page, name: string) => {
  let all: Record<string, unknown>[] = [];
  await expect.poll(async () => (all = await events(page, name)).length).toBeGreaterThan(0);
  return all.at(-1)!;
};
/** Whether the ring is drawn around `sel`. */
const ringedAround = (page: Page, sel: string) =>
  page.evaluate((s) => {
    const t = document.querySelector(s)!.getBoundingClientRect();
    return [...document.querySelectorAll("[data-voqalize=highlight]")].some((el) => {
      const r = el.getBoundingClientRect();
      return Math.abs(r.left + 6 - t.left) < 4 && Math.abs(r.top + 6 - t.top) < 4;
    });
  }, sel);

test.describe("Te llamamos", () => {
  test("filled as said, the comunas loaded from the region, the RUT left to the visitor, the state reported, Brevo's answer heard", async ({ ext }) => {
    const page = await ext.open("/landing/solicitar-diagnostico/");
    await listen(page);
    // LiteSpeed has not run the form's helpers yet.
    expect(await page.evaluate(() => typeof (window as unknown as { cargarComunas?: unknown }).cargarComunas)).toBe("undefined");
    const out = await perform(page, "fill_callback_form", {
      form: "te_llamamos", nombre: "Camila", apellidos: "Rojas Díaz", email: "camila@example.com", phone: "+56 9 8765 4321",
      region: "Región Metropolitana", comuna: "Providencia",
    });
    expect(out).toMatchObject({ event: "command_done", payload: { command: "fill_callback_form" } });
    expect(String(out!.payload.detail)).toContain("the RUT box is focused and ringed");
    expect(await value(page, "#NOMBRE")).toBe("Camila");
    expect(await value(page, "#APELLIDOS")).toBe("Rojas Díaz");
    expect(await value(page, "#EMAIL")).toBe("camila@example.com");
    expect(await value(page, "input[name=SMS]")).toBe("987654321");
    expect(await page.locator("#REGION_2").inputValue()).toBe("7");
    expect(await page.locator("#COMUNA_2").inputValue()).toBe("118");
    expect(await value(page, "#RUT")).toBe("");
    expect(await page.evaluate(() => document.activeElement?.id)).toBe("RUT");
    expect(await ringedAround(page, "#RUT")).toBe(true);
    expect(await last(page, "callback_form_state")).toEqual({
      form: "te_llamamos", filled: ["nombre", "apellidos", "email", "phone", "region", "comuna"], missing: ["rut"], rut_typed: false,
      result: "none", message: "",
    });

    // The visitor types the RUT: reported as typed, its value never.
    await page.locator("#RUT").fill("12345678-5");
    await expect.poll(async () => (await last(page, "callback_form_state")).rut_typed).toBe(true);
    expect(JSON.stringify(await events(page, "callback_form_state"))).not.toContain("12345678");
    // With it there, the next fill rings ENVIAR for the visitor.
    await perform(page, "fill_callback_form", { form: "te_llamamos", nombre: "", apellidos: "", email: "", phone: "", region: "", comuna: "" });
    expect(await ringedAround(page, "#sib-form button[type=submit]")).toBe(true);
    expect(await submits(page)).toEqual([]);
    // The visitor presses ENVIAR; Brevo answers.
    await page.evaluate(() => (window as unknown as { __brevo: { answer(ok: boolean): void } }).__brevo.answer(true));
    await expect.poll(async () => (await last(page, "callback_form_state")).result).toBe("success");
  });

  test("from another page: the form's page loads and is filled there", async ({ ext }) => {
    const page = await ext.open("/");
    const out = await perform(page, "fill_callback_form", { form: "te_llamamos", nombre: "Camila", apellidos: "Rojas", email: "", phone: "", region: "", comuna: "" });
    expect(out).toBeNull();
    await page.waitForURL(`${ORIGIN}/landing/solicitar-diagnostico/`);
    await expect.poll(() => value(page, "#NOMBRE"), { timeout: 15_000 }).toBe("Camila");
    expect(await value(page, "#APELLIDOS")).toBe("Rojas");
  });

  test("a phone that is not a Chilean mobile is refused, nothing typed there", async ({ ext }) => {
    const page = await ext.open("/landing/solicitar-diagnostico/");
    const out = await perform(page, "fill_callback_form", { form: "te_llamamos", nombre: "Ana", apellidos: "", email: "", phone: "2 2345 6789", region: "", comuna: "" });
    expect(String(out!.payload.detail)).toContain("refused");
    expect(await value(page, "input[name=SMS]")).toBe("");
  });
});

test("the urgencias page's form: name and surname in its one name box, the RUT left to the visitor", async ({ ext }) => {
  const page = await ext.open("/urgencias/");
  await listen(page);
  await perform(page, "fill_callback_form", { form: "urgencias", nombre: "Pedro", apellidos: "Soto", email: "pedro@example.com", phone: "912345678", region: "", comuna: "" });
  expect(await value(page, "#NOMBRE")).toBe("Pedro Soto");
  expect(await value(page, "#RUT")).toBe("");
  expect(await last(page, "callback_form_state")).toMatchObject({ form: "urgencias", missing: ["rut"], rut_typed: false });
  expect(await submits(page)).toEqual([]);
});

test("Convenio Empresas: every field filled, ENVIAR ringed and not pressed", async ({ ext }) => {
  const page = await ext.open("/landing/convenio-empresa/");
  await listen(page);
  const out = await perform(page, "fill_company_form", {
    empresa: "Constructora Andes SpA", nombre: "Rodrigo Fuentes", cargo: "Gerente de Personas", email: "rfuentes@example.com",
    phone: "912345678", region: "Valparaíso", trabajadores: "unos 600 trabajadores", comentarios: "Queremos un convenio para todo el equipo.",
  });
  expect(out).toMatchObject({ event: "command_done", payload: { command: "fill_company_form" } });
  expect(await value(page, "#EMPRESA")).toBe("Constructora Andes SpA");
  expect(await value(page, "#NOMBRE")).toBe("Rodrigo Fuentes");
  expect(await value(page, "#CARGO")).toBe("Gerente de Personas");
  expect(await value(page, "#EMAIL")).toBe("rfuentes@example.com");
  expect(await value(page, "input[name=SMS]")).toBe("912345678");
  expect(await page.locator("#REGION_2").inputValue()).toBe("6");
  expect(await page.locator("#NUMERO_DE_TRABAJADORES").inputValue()).toBe("4");
  expect(await value(page, "#COMENTARIOS")).toBe("Queremos un convenio para todo el equipo.");
  expect(await last(page, "company_form_state")).toEqual({
    filled: ["nombre", "phone", "email", "empresa", "region", "cargo", "trabajadores", "comentarios"], missing: [], result: "none", message: "",
  });
  expect(await ringedAround(page, "#sib-form button[type=submit]")).toBe(true);
  expect(await submits(page)).toEqual([]);
});
