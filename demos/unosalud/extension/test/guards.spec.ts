/**
 * What Javier never does (`guards.ts`), enforced in code:
 *
 *   - the presses he never makes (the booking's Continuar after the RUT,
 *     «Registrarse», «Confirmar cita», the payment link, Brevo's ENVIAR,
 *     Contact Form 7's submit, the captcha) and the fields he never fills
 *     (any RUT, the terms and consent boxes, the captcha's) are refused, with
 *     nothing clicked and nothing typed;
 *   - across whole moves (the booking from the RUT step to the review, the
 *     lead forms), no form's `submit()` or `requestSubmit()` is ever called,
 *     no key event is ever dispatched (so no Enter), the RUT and the terms box
 *     are never touched, and the only submits are the booking's step buttons
 *     he may press.
 */

import type { Page } from "@playwright/test";

import { expect, perform, test } from "./site-ext";

interface Watched {
  submitCalls: string[];
  keys: string[];
  clicks: string[];
}

/** Watch, from the very start of every page: calls to a form's `submit()` and
 *  `requestSubmit()`, keyboard events, and clicks on the guarded controls. */
async function watch(page: Page): Promise<void> {
  await page.context().addInitScript(() => {
    const w = window as unknown as { __watched: Watched };
    w.__watched = { submitCalls: [], keys: [], clicks: [] };
    const submit = HTMLFormElement.prototype.submit;
    HTMLFormElement.prototype.submit = function (this: HTMLFormElement) {
      w.__watched.submitCalls.push(`submit ${this.id}`);
      return submit.call(this);
    };
    const requestSubmit = HTMLFormElement.prototype.requestSubmit;
    HTMLFormElement.prototype.requestSubmit = function (this: HTMLFormElement, s?: HTMLElement | null) {
      w.__watched.submitCalls.push(`requestSubmit ${this.id}`);
      return requestSubmit.call(this, s);
    };
    for (const t of ["keydown", "keypress", "keyup"]) {
      document.addEventListener(t, (e) => w.__watched.keys.push(`${t} ${(e as KeyboardEvent).key}`), true);
    }
    document.addEventListener(
      "click",
      (e) => {
        const el = (e.target as Element | null)?.closest?.("#ingresar-rut, #registro-paciente, #confirma-cita, #btn_link_pago, #conditions, .g-recaptcha, #sib-form button");
        if (el) w.__watched.clicks.push(el.id || el.className);
      },
      true,
    );
  });
}
const watched = (page: Page) => page.evaluate(() => (window as unknown as { __watched: Watched }).__watched);
const submits = (page: Page) => page.evaluate(() => (window as unknown as { __submits: string[] }).__submits);

/** Try a guarded press or fill on the page's adapter: the error's text, or "" if it went through. */
const tryPress = (page: Page, sel: string) =>
  page.evaluate((s) => {
    const g = (window as unknown as { voqalizeUnosalud: { guards: { press(el: HTMLElement): void } } }).voqalizeUnosalud.guards;
    try {
      g.press(document.querySelector<HTMLElement>(s)!);
      return "";
    } catch (e) {
      return String((e as Error).name);
    }
  }, sel);
const tryFill = (page: Page, sel: string) =>
  page.evaluate((s) => {
    const g = (window as unknown as { voqalizeUnosalud: { guards: { fill(el: HTMLInputElement, v: string): void } } }).voqalizeUnosalud.guards;
    try {
      g.fill(document.querySelector<HTMLInputElement>(s)!, "12345678-5");
      return "";
    } catch (e) {
      return String((e as Error).name);
    }
  }, sel);

test.describe("the guards", () => {
  test("on the booking: the presses and fields that are the visitor's are refused, and nothing happens", async ({ ext }) => {
    const page = await ext.ctx.newPage();
    await watch(page);
    await page.goto("https://www.unosalud.cl/agenda-tu-hora/", { waitUntil: "domcontentloaded" });
    await page.locator("[data-voqalize=widget] .invite").waitFor();
    // Every step's controls exist in the page, shown or not.
    await page.evaluate(() => {
      document.getElementById("container_link_pago")!.classList.remove("d-none");
    });
    for (const sel of ["#ingresar-rut", "#registro-paciente", "#confirma-cita", "#btn_link_pago", ".g-recaptcha"]) {
      expect(await tryPress(page, sel), sel).toBe("GuardError");
    }
    for (const sel of ["#rut", "#conditions", "#recaptchaResponse", "#g-recaptcha-response"]) {
      expect(await tryFill(page, sel), sel).toBe("GuardError");
    }
    // The step buttons he may press, and plain fields, go through.
    expect(await tryFill(page, "#nombre")).toBe("");
    const w = await watched(page);
    expect(w.clicks).toEqual([]);
    expect(await page.locator("#rut").inputValue()).toBe("");
    expect(await page.locator("#conditions").isChecked()).toBe(false);
    expect(await submits(page)).toEqual([]);
  });

  test("on the lead forms: ENVIAR, the RUT and Contact Form 7's submit are refused", async ({ ext }) => {
    let page = await ext.open("/landing/solicitar-diagnostico/");
    expect(await tryPress(page, "#sib-form button[type=submit]")).toBe("GuardError");
    expect(await tryFill(page, "#RUT")).toBe("GuardError");
    expect(await page.locator("#RUT").inputValue()).toBe("");
    page = await ext.open("/contactanos/convenios/");
    expect(await tryPress(page, "form.wpcf7-form [type=submit]")).toBe("GuardError");
  });

  test("across the whole booking and the forms: no submit() call, no key event, the RUT and terms untouched, only the step buttons he may press", async ({ ext }) => {
    const page = await ext.ctx.newPage();
    await watch(page);
    await page.goto("https://www.unosalud.cl/agenda-tu-hora/", { waitUntil: "domcontentloaded" });
    await page.locator("[data-voqalize=widget] .invite").waitFor();
    await perform(page, "open_booking", { promo: "" });
    // The visitor clears the RUT step themselves; then a new patient.
    await page.evaluate(() => (window as unknown as { __ds: { as(s: string): void } }).__ds.as("setPAC"));
    await perform(page, "fill_booking_patient", {
      nombre: "María", paterno: "González", materno: "Pérez", birth_date: "1990-03-15", email: "maria@example.com", phone: "912345678", confirm_existing: true,
    });
    // «Registrarse» is the visitor's: it was ringed, not pressed. They press it.
    expect(await submits(page)).toEqual([]);
    await page.locator("#registro-paciente").click();
    await expect.poll(() => page.evaluate(() => (document.getElementById("step") as HTMLInputElement).value)).toBe("getMRes");
    await perform(page, "booking_pick", { motivo: 22, region: "", comuna: "", sucursal: "Manuel Montt", date: "2026-10-28", time: "09:00" });
    await perform(page, "booking_scan", { from_date: "", days: 2 }).catch(() => null);
    const w = await watched(page);
    expect(w.submitCalls).toEqual([]);
    expect(w.keys).toEqual([]);
    // Only the visitor's own press of «Registrarse», and none of the others.
    expect(w.clicks).toEqual(["registro-paciente"]);
    expect(await submits(page)).toEqual(["registro-paciente", "selecciona-motivo", "continue_getSuc", "continue_getHor"]);
    expect(await page.locator("#rut").inputValue()).toBe("");
    expect(await page.locator("#conditions").isChecked()).toBe(false);

    const form = await ext.ctx.newPage();
    await watch(form);
    await form.goto("https://www.unosalud.cl/landing/solicitar-diagnostico/", { waitUntil: "domcontentloaded" });
    await form.locator("[data-voqalize=widget] .invite").waitFor();
    await perform(form, "fill_callback_form", { form: "te_llamamos", nombre: "Ana", apellidos: "Soto", email: "ana@example.com", phone: "912345678", region: "RM", comuna: "Santiago" });
    const f = await watched(form);
    expect(f.submitCalls).toEqual([]);
    expect(f.keys).toEqual([]);
    expect(f.clicks).toEqual([]);
    expect(await submits(form)).toEqual([]);
  });
});
