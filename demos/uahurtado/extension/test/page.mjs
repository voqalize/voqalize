// The page test: the site adapter (`src/uah-actions.ts`) driven in headless
// Chromium against trimmed copies of the university's own pages
// (`demos/tests/fixtures/uahurtado/`), served at their real URLs by request
// interception, with a stand-in for Bootstrap (`shim.js`). Nothing reaches the
// network: every other request is aborted and recorded.
//
//   pnpm test:page            every case
//   pnpm test:page fees       the cases whose name contains "fees"
//
// Exit 0: all passed. Exit 1: a case failed. Exit 3: no Chromium could be
// launched (the Python wrapper skips on that). Chromium is the one
// playwright-core expects, already installed; this never downloads one.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(here, "../../../tests/fixtures/uahurtado");

const PAGES = {
  "https://admision.uahurtado.cl/": "adm_home.html",
  "https://admision.uahurtado.cl/carreras/psicologia/": "car_psicologia.html",
  "https://admision.uahurtado.cl/carreras/pedagogia-en-ingles/": "car_ped_ingles.html",
  "https://admision.uahurtado.cl/carreras/administracion-publica-100-online/": "car_adm_pub_online.html",
  "https://admision.uahurtado.cl/becas-y-beneficios/": "adm_becas.html",
  "https://admision.uahurtado.cl/gratuidad-universitaria/": "adm_gratuidad.html",
  "https://admision.uahurtado.cl/ven-y-conocenos/": "adm_venyconocenos.html",
  "https://admision.uahurtado.cl/admision-directa/": "adm_directa.html",
  "https://postgrados.uahurtado.cl/programa/magister-intervencion-psicosocial/": "pos_mag_psicosocial.html",
  "https://www.uahurtado.cl/la-universidad/campus/campus-patrimonial/": "www_campus_patrimonial.html",
};
const PSICOLOGIA = "https://admision.uahurtado.cl/carreras/psicologia/";

const bundled = await build({
  entryPoints: [join(here, "page-entry.ts")],
  bundle: true,
  write: false,
  format: "iife",
  target: "chrome120",
  logLevel: "silent",
});
const ADAPTER = bundled.outputFiles[0].text;
const SHIM = readFileSync(join(here, "shim.js"), "utf8");

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  console.log(`SKIP: no Chromium for playwright-core could be launched: ${String(error).split("\n")[0]}`);
  process.exit(3);
}

/** Open `url` (a fixture) with the adapter on it; what left for the network. */
async function open(url) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const outside = [];
  const posts = [];
  await context.route("**/*", (route) => {
    const req = route.request();
    if (req.method() !== "GET") posts.push(req.url());
    const file = req.method() === "GET" ? PAGES[req.url()] : undefined;
    if (file && req.isNavigationRequest()) {
      return route.fulfill({
        status: 200,
        contentType: "text/html; charset=utf-8",
        body: readFileSync(join(FIXTURES, file), "utf8"),
      });
    }
    outside.push(req.url());
    return route.abort();
  });
  const page = await context.newPage();
  const navigations = [];
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("framenavigated", (f) => {
    if (f === page.mainFrame()) navigations.push(f.url());
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ content: SHIM });
  await page.addScriptTag({ content: ADAPTER });
  const run = (command, payload) => page.evaluate(([c, p]) => window.__uah.adapter.run(c, p), [command, payload]);
  const context_ = () => page.evaluate(() => window.__uah.adapter.context());
  const events = (name) => page.evaluate((n) => window.__uah.events.filter(([e]) => e === n).map(([, p]) => p), name);
  const rung = () => page.evaluate(() => document.querySelectorAll("[data-voqalize=highlight]").length);
  const close = () => context.close();
  return { page, run, context: context_, events, rung, outside, posts, navigations, errors, close };
}

const cases = [];
const test = (name, fn) => cases.push({ name, fn });

// ─── A career page ────────────────────────────────────────────────────────

test("career sheet: facts, tabs, weights, fees, audiomalla", async () => {
  const t = await open(PSICOLOGIA);
  const ctx = await t.context();
  assert.equal(ctx.kind, "career");
  assert.equal(ctx.url, PSICOLOGIA);
  const c = ctx.career;
  assert.equal(c.slug, "psicologia");
  assert.equal(c.name, "Psicología");
  const facts = Object.fromEntries(c.facts.map((r) => [r.label, r.value]));
  assert.equal(facts.Sede, "Casa Central");
  assert.equal(facts["Duración"], "10 semestres");
  assert.equal(facts["Régimen"], "Diurno");
  assert.deepEqual(c.tabs.slice(0, 3), ["Malla Curricular", "Descripción de la Carrera", "Requisitos y Aranceles"]);
  assert.equal(c.tabs.length, 7);
  assert.equal(c.weights.length, 7);
  assert.deepEqual(c.weights[0], { label: "NEM", value: "10%" });
  assert.equal(c.weights.find((r) => /^Historia/.test(r.label)).value, "10% ó 10%");
  assert.equal(c.weights.at(-1).value, "570");
  assert.ok(!c.weights.some((r) => r.label === "Criterio"), "the header row is not a weight");
  assert.match(c.fees_text, /Año 2027/);
  assert.match(c.fees_text, /\$277\.456/);
  assert.match(c.fees_text, /\$7\.167\.421/);
  assert.equal(c.requirements_text, "");
  assert.equal(c.has_audiomalla, true);
  assert.match(c.audiomalla_label, /Andrea Jaramillo/);
  assert.match(c.malla_pdf, /\.pdf$/);
  // The panes are hidden, but their headings are reachable; the toggles are the tabs.
  assert.ok(ctx.toggles.includes("Requisitos y Aranceles"));
  assert.ok(ctx.headings.includes("Aranceles"));
  assert.ok(ctx.headings.includes("Datos Académicos"));
  assert.ok(ctx.headings.includes("Audiomalla"));
  assert.deepEqual(ctx.form.fields, ["nombre", "apellido", "rut", "email", "fono", "consulta", "carrera"]);
  assert.equal(ctx.form.career, "Psicología");
  assert.equal(ctx.translated, false);
  await t.close();
});

test("a show cue on a tab label clicks the tab and shows its pane", async () => {
  const t = await open(PSICOLOGIA);
  const r = await t.run("show_section", { heading: "Requisitos y Aranceles", text: null });
  assert.equal(r.ok, true, r.error);
  const state = await t.page.evaluate(() => ({
    pane: document.getElementById("requisitos_carrera").className,
    malla: document.getElementById("malla").className,
    tab: document.getElementById("requisitos_carrera-tab").className,
    shown: document.getElementById("requisitos_carrera").getBoundingClientRect().height > 0,
  }));
  assert.match(state.pane, /\bactive\b/);
  assert.match(state.pane, /\bshow\b/);
  assert.doesNotMatch(state.malla, /\bactive\b/);
  assert.match(state.tab, /\bactive\b/);
  assert.ok(state.shown);
  assert.equal(await t.rung(), 1);
  await t.close();
});

test("a show cue on a heading inside a closed tab opens the tab first", async () => {
  const t = await open(PSICOLOGIA);
  const r = await t.run("show_section", { heading: "Experiencia de aprendizaje", text: null });
  assert.equal(r.ok, true, r.error);
  assert.match(await t.page.getAttribute("#descripcion_carrera", "class"), /\bactive\b/);
  const bad = await t.run("show_section", { heading: "Horarios de buses", text: null });
  assert.equal(bad.ok, false);
  assert.match(bad.error, /no heading or tab "Horarios de buses".*it has: .*Requisitos y Aranceles/);
  await t.close();
});

test("show_admission: fees read with year 2027 and the Psicología figures", async () => {
  const t = await open(PSICOLOGIA);
  await t.page.evaluate(() => {
    window.__uah.rec.rest.carrera = { psicologia: { fees_text: "Año 2027\nMatrícula $277.456" } };
  });
  const r = await t.run("show_admission", { url: PSICOLOGIA, slug: "psicologia", focus: "fees" });
  assert.equal(r.ok, true, r.error);
  assert.equal(r.event.event, "admission_read");
  const p = r.event.payload;
  assert.equal(p.slug, "psicologia");
  assert.equal(p.url, PSICOLOGIA);
  assert.equal(p.year, "2027");
  assert.equal(p.matricula, "$277.456");
  assert.equal(p.arancel, "$7.167.421");
  assert.equal(p.titulacion_uf, "11");
  assert.equal(p.weights.length, 7);
  assert.equal(p.api_fees_text, "Año 2027\nMatrícula $277.456");
  assert.match(await t.page.getAttribute("#requisitos_carrera", "class"), /\bactive\b/);
  assert.equal(await t.rung(), 1);
  await t.close();
});

test("fees come from the visible text, not data-sheets-value (Pedagogía en Inglés)", async () => {
  const url = "https://admision.uahurtado.cl/carreras/pedagogia-en-ingles/";
  const t = await open(url);
  // The fixture keeps the stale attribute the page carries beside the figure.
  assert.match(await t.page.content(), /data-sheets-value="[^"]*\$158\.000/);
  const ctx = await t.context();
  assert.match(ctx.career.fees_text, /\$218\.567/);
  assert.doesNotMatch(ctx.career.fees_text, /158\.000/);
  assert.doesNotMatch(ctx.career.fees_text, /Admisión Directa/, "the column's next block is not fees");
  // No REST record: the read still answers, with the api field empty.
  const r = await t.run("show_admission", { url, slug: "pedagogia-en-ingles", focus: "requirements" });
  assert.equal(r.ok, true, r.error);
  const p = r.event.payload;
  assert.equal(p.matricula, "$218.567");
  assert.equal(p.arancel, "$4.678.245");
  assert.equal(p.titulacion_uf, "8");
  assert.equal(p.api_fees_text, "");
  assert.equal(p.weights.find((w) => w.label === "Ranking").value, "35%");
  await t.close();
});

test("an online career's requirements are a list, not weights", async () => {
  const t = await open("https://admision.uahurtado.cl/carreras/administracion-publica-100-online/");
  const c = (await t.context()).career;
  assert.deepEqual(c.weights, []);
  assert.match(c.requirements_text, /Técnicos de Nivel Superior/);
  assert.match(c.fees_text, /\$311\.559/);
  assert.equal(c.has_audiomalla, false);
  assert.equal(c.tabs.length, 4);
  await t.close();
});

test("show_admission on a career not in front keeps the move and loads the page", async () => {
  const t = await open(PSICOLOGIA);
  const other = "https://admision.uahurtado.cl/carreras/pedagogia-en-ingles/";
  const r = await t.run("show_admission", { url: other, slug: "pedagogia-en-ingles", focus: "fees" });
  assert.deepEqual(r, { ok: true, moved: true });
  const rec = await t.page.evaluate(() => ({ pend: window.__uah.rec.pend, loads: window.__uah.rec.loads }));
  assert.equal(rec.loads[0], other);
  assert.equal(rec.pend[0].command, "show_admission");
  assert.equal(rec.pend[0].payload.slug, "pedagogia-en-ingles");
  await t.close();
});

test("play_audiomalla: a refused play rings the player and fails in words", async () => {
  const t = await open(PSICOLOGIA);
  await t.page.evaluate(() => {
    HTMLMediaElement.prototype.play = () => Promise.reject(new DOMException("no gesture", "NotAllowedError"));
  });
  const r = await t.run("play_audiomalla", { url: PSICOLOGIA });
  assert.equal(r.ok, false);
  assert.match(r.error, /did not let the audiomalla start \(no gesture\).*rung for the visitor to press/);
  assert.equal(await t.rung(), 1);
  assert.deepEqual(await t.page.evaluate(() => window.__uah.rec.mic), []);
  await t.close();
});

test("play_audiomalla: the mic is held while it plays and given back when it stops", async () => {
  const t = await open(PSICOLOGIA);
  // The mp3 is not served here: playing is the element's events, as Chrome fires them.
  await t.page.evaluate(() => {
    let paused = true;
    Object.defineProperty(HTMLMediaElement.prototype, "paused", { get: () => paused, configurable: true });
    HTMLMediaElement.prototype.play = function () {
      paused = false;
      this.dispatchEvent(new Event("play"));
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function () {
      paused = true;
      this.dispatchEvent(new Event("pause"));
    };
  });
  // Start on another tab: the Malla Curricular tab is opened for the player.
  await t.run("show_section", { heading: "Requisitos y Aranceles", text: null });
  const r = await t.run("play_audiomalla", { url: PSICOLOGIA });
  assert.equal(r.ok, true, r.error);
  assert.match(r.detail, /audiomalla is playing \(Andrea Jaramillo, directora de carrera\)/);
  assert.match(await t.page.getAttribute("#malla", "class"), /\bactive\b/);
  assert.deepEqual(await t.page.evaluate(() => window.__uah.rec.mic), [true]);
  await t.page.evaluate(() => document.querySelector("#malla audio").pause());
  await t.page.waitForTimeout(150);
  assert.deepEqual(await t.page.evaluate(() => window.__uah.rec.mic), [true, false]);
  assert.deepEqual(await t.events("audiomalla_ended"), [{ finished: false }]);
  await t.close();
});

// ─── The lead form ────────────────────────────────────────────────────────

test("fill_lead_form fills the dictated fields, never the RUT, never submits", async () => {
  const t = await open(PSICOLOGIA);
  await t.page.evaluate(() => {
    window.__submits = 0;
    document.getElementById("admisionForm").addEventListener("submit", () => window.__submits++);
  });
  const r = await t.run("fill_lead_form", {
    nombre: "Ana", apellido: "Pérez", email: "ana@example.com", fono: "+56 9 1234 5678",
    consulta: "Consulta por arancel 2027", carrera: null, via: null, focus_rut: false,
  });
  assert.equal(r.ok, true, r.error);
  assert.match(r.detail, /filled nombre, apellido, email, fono, consulta/);
  assert.match(r.detail, /still empty: rut/);
  const v = await t.page.evaluate(() => {
    const f = document.getElementById("admisionForm");
    const get = (n) => f.querySelector(`[name="${n}"]`).value;
    return {
      nombre: get("entry.230062511"), apellido: get("entry.721330585"), rut: get("entry.289307241"),
      email: get("entry.1559668481"), fono: get("entry.916683147"), consulta: get("entry.699238472"),
      carrera: get("entry.229701830"), both: get("entry.2138016348"), submits: window.__submits,
    };
  });
  assert.equal(v.nombre, "Ana");
  assert.equal(v.apellido, "Pérez");
  assert.equal(v.email, "ana@example.com");
  assert.equal(v.fono, "+56 9 1234 5678");
  assert.equal(v.consulta, "Consulta por arancel 2027");
  assert.equal(v.rut, "", "the RUT is the visitor's to type");
  assert.equal(v.carrera, "Psicología");
  assert.equal(v.both, "Ana Pérez", "the form's own onchange composed nombre_y_apellido");
  assert.equal(v.submits, 0);
  const [state] = await t.events("lead_form_state");
  assert.deepEqual(state.missing, ["rut"]);
  assert.equal(state.ready, false);
  assert.equal(state.career, "Psicología");
  // "Enviar" is rung for the visitor (and the RUT with it), never pressed.
  assert.equal(await t.rung(), 2);
  await t.page.waitForTimeout(300);
  assert.deepEqual(t.navigations, [PSICOLOGIA]);
  assert.deepEqual(t.posts, []);
  await t.close();
});

test("focus_rut rings and focuses the RUT field, empty", async () => {
  const t = await open(PSICOLOGIA);
  const r = await t.run("fill_lead_form", {
    nombre: null, apellido: null, email: null, fono: null, consulta: null, carrera: null, via: null, focus_rut: true,
  });
  assert.equal(r.ok, true, r.error);
  const f = await t.page.evaluate(() => ({ name: document.activeElement?.getAttribute("name"), value: document.activeElement?.value }));
  assert.deepEqual(f, { name: "entry.289307241", value: "" });
  await t.close();
});

test("the visitor's press of Enviar is never stopped by the extension", async () => {
  const t = await open(PSICOLOGIA);
  await t.page.evaluate(() => {
    window.__submits = 0;
    document.getElementById("admisionForm").addEventListener("submit", (e) => {
      window.__submits++;
      e.preventDefault(); // stands in for the post; a cancelled press is not reported
    });
  });
  await t.page.click("form#admisionForm button[type=submit]");
  await t.page.waitForTimeout(300);
  assert.equal(await t.page.evaluate(() => window.__submits), 1, "the press was not stopped");
  assert.deepEqual(await t.events("lead_submitted"), []);
  await t.close();
});

test("a press the site lets through goes to the university and is reported once", async () => {
  const t = await open(PSICOLOGIA);
  await t.page.evaluate(() => {
    // Post into a frame, so the page (and what it recorded) stays.
    const sink = document.createElement("iframe");
    sink.name = "sink";
    document.body.append(sink);
    document.getElementById("admisionForm").target = "sink";
  });
  await t.page.click("form#admisionForm button[type=submit]");
  await t.page.waitForTimeout(500);
  assert.equal(t.posts.length, 1, "the form was posted");
  assert.deepEqual(await t.events("lead_submitted"), [{}]);
  await t.close();
});

test("the home form picks the career from its select by text", async () => {
  const t = await open("https://admision.uahurtado.cl/");
  const ctx = await t.context();
  assert.equal(ctx.kind, "home");
  assert.ok(ctx.form.career_options.includes("Psicología"));
  assert.ok(!ctx.form.career_options.some((o) => /seleccione/i.test(o)));
  assert.ok(!ctx.form.fields.includes("apellido"), "the home form has no apellido");
  const r = await t.run("fill_lead_form", {
    nombre: "Ana", apellido: "Pérez", email: null, fono: null, consulta: null, carrera: "psicologia", via: null, focus_rut: false,
  });
  assert.equal(r.ok, true, r.error);
  assert.match(r.detail, /carrera \(Psicología\)/);
  assert.match(r.detail, /this form has no apellido field/);
  assert.equal(await t.page.inputValue("form#admisionForm [name='entry.229701830']"), "Psicología");
  await t.close();
});

test("the admisión directa form picks the vía by text", async () => {
  const t = await open("https://admision.uahurtado.cl/admision-directa/");
  const ctx = await t.context();
  assert.ok(ctx.form.via_options.includes("Deportistas destacadas/os"));
  assert.ok(!ctx.form.via_options.includes("Vía de Admisión"));
  const r = await t.run("fill_lead_form", {
    nombre: null, apellido: null, email: null, fono: null, consulta: null, carrera: null, via: "deportistas destacados", focus_rut: false,
  });
  assert.equal(r.ok, true, r.error);
  assert.match(r.detail, /via \(Deportistas destacadas\/os\)/);
  await t.close();
});

// ─── The Carreras mega-menu ───────────────────────────────────────────────

test("open_career_menu opens the menu and rings the faculty's group", async () => {
  const t = await open(PSICOLOGIA);
  const r = await t.run("open_career_menu", { faculty: "ingenieria", url: "https://admision.uahurtado.cl/" });
  assert.equal(r.ok, true, r.error);
  assert.match(r.detail, /the Carreras menu is open at Facultad de Ingeniería/);
  assert.match(r.detail, /Ingeniería Civil Industrial/);
  assert.match(r.detail, /Ingeniería Civil en Informática/);
  assert.doesNotMatch(r.detail, /Psicología/);
  assert.match(await t.page.getAttribute("#collapseCarreras", "class"), /\bshow\b/);
  assert.equal(await t.rung(), 1);
  const none = await t.run("open_career_menu", { faculty: "Medicina", url: "https://admision.uahurtado.cl/" });
  assert.equal(none.ok, false);
  assert.match(none.error, /no group for "Medicina".*Facultad de Derecho/);
  await t.close();
});

test("open_career_menu off admision loads admision first", async () => {
  const t = await open("https://www.uahurtado.cl/la-universidad/campus/campus-patrimonial/");
  const r = await t.run("open_career_menu", { faculty: "Educación", url: "https://admision.uahurtado.cl/" });
  assert.deepEqual(r, { ok: true, moved: true });
  const rec = await t.page.evaluate(() => window.__uah.rec);
  assert.deepEqual(rec.loads, ["https://admision.uahurtado.cl/"]);
  assert.deepEqual(rec.pend[0], { command: "open_career_menu", payload: { faculty: "Educación", url: "https://admision.uahurtado.cl/" } });
  await t.close();
});

// ─── Becas, gratuidad ─────────────────────────────────────────────────────

test("becas: a beca inside a hidden pill opens that pill; a pill label switches", async () => {
  const t = await open("https://admision.uahurtado.cl/becas-y-beneficios/");
  const ctx = await t.context();
  assert.ok(ctx.toggles.includes("BECAS DE ARANCEL"));
  assert.ok(ctx.headings.includes("Beca Alberto Hurtado"));
  let r = await t.run("show_section", { heading: "Beca Alberto Hurtado", text: null });
  assert.equal(r.ok, true, r.error);
  let active = await t.page.evaluate(() => [...document.querySelectorAll("#v-pills-tab .nav-link.active")].map((b) => b.id));
  assert.deepEqual(active, ["v-pills-tres-tab"]);
  assert.match(await t.page.getAttribute("#v-pills-tres", "class"), /\bactive\b/);
  assert.doesNotMatch(await t.page.getAttribute("#v-pills-uno", "class"), /\bactive\b/);
  r = await t.run("show_section", { heading: "Descuentos de arancel", text: null });
  assert.equal(r.ok, true, r.error);
  active = await t.page.evaluate(() => [...document.querySelectorAll("#v-pills-tab .nav-link.active")].map((b) => b.id));
  assert.deepEqual(active, ["v-pills-cuatro-tab"]);
  await t.close();
});

test("gratuidad: open_faq expands the matching accordion and rings it", async () => {
  const t = await open("https://admision.uahurtado.cl/gratuidad-universitaria/");
  const ctx = await t.context();
  assert.ok(ctx.faqs.includes("¿PUEDO OPTAR A LA GRATUIDAD SI YA CURSÉ UNA CARRERA?"));
  assert.ok(ctx.faqs.some((q) => /^¿Qué estudiantes pueden acceder/.test(q)), "a question heading is an FAQ too");
  assert.ok(!ctx.toggles.some((l) => l.endsWith("?")), "accordion questions are not toggles");
  const r = await t.run("open_faq", { question: "¿Puedo optar a la gratuidad si ya cursé una carrera?" });
  assert.equal(r.ok, true, r.error);
  assert.match(await t.page.getAttribute("#collapseThree", "class"), /\bshow\b/);
  assert.equal(await t.rung(), 1);
  const bad = await t.run("open_faq", { question: "¿Hay estacionamiento?" });
  assert.equal(bad.ok, false);
  assert.match(bad.error, /no FAQ "¿Hay estacionamiento\?".*it has: /);
  await t.close();
});

// ─── Visits ───────────────────────────────────────────────────────────────

test("ven y conócenos: cards marked REALIZADO are done; sign-ups rung, never followed", async () => {
  const t = await open("https://admision.uahurtado.cl/ven-y-conocenos/");
  const ctx = await t.context();
  assert.ok(ctx.visits.length >= 8);
  const primavera = ctx.visits.find((v) => v.title === "TALLERES DE PRIMAVERA");
  assert.equal(primavera.done, false);
  assert.equal(primavera.open, true);
  assert.equal(primavera.signup_label, "Inscribirse aquí");
  assert.match(primavera.signup_url, /^https:\/\/share\.hsforms\.com\//);
  const virtual = ctx.visits.filter((v) => v.title === "UAH VIRTUAL");
  assert.ok(virtual.length === 2 && virtual.every((v) => v.done && !v.open));
  assert.equal(virtual[0].signup_label, "Inscripciones cerradas");
  const done = await t.run("show_signup", { title: "UAH Virtual" });
  assert.equal(done.ok, false);
  assert.match(done.error, /marked REALIZADO/);
  let popups = 0;
  t.page.on("popup", () => popups++);
  const ok = await t.run("show_signup", { title: "Talleres de Primavera" });
  assert.equal(ok.ok, true, ok.error);
  assert.match(ok.detail, /Inscribirse aquí.*rung.*share\.hsforms\.com/);
  assert.equal(await t.rung(), 1);
  await t.page.waitForTimeout(300);
  assert.equal(popups, 0, "the sign-up link was not clicked");
  assert.deepEqual(t.navigations, ["https://admision.uahurtado.cl/ven-y-conocenos/"]);
  const none = await t.run("show_signup", { title: "Feria de invierno 2030" });
  assert.match(none.error, /no visit "Feria de invierno 2030".*TALLERES DE PRIMAVERA/);
  await t.close();
});

// ─── A postgraduate programme ─────────────────────────────────────────────

test("show_program opens Requisitos y Valores and reads it with the record", async () => {
  const url = "https://postgrados.uahurtado.cl/programa/magister-intervencion-psicosocial/";
  const t = await open(url);
  const ctx = await t.context();
  assert.equal(ctx.kind, "program");
  assert.equal(ctx.program.slug, "magister-intervencion-psicosocial");
  assert.ok(ctx.program.accordion.includes("Requisitos y Valores"));
  assert.ok(ctx.toggles.includes("Requisitos y Valores"));
  const post = Object.fromEntries(ctx.program.sidebar.map((r) => [r.label, r.value]));
  assert.match(post.Postulaciones, /Postulación desde: 01 octubre 2026; Postulación hasta: 31 marzo 2027/);
  assert.match(post.Inicio, /02 abril 2027/);
  assert.deepEqual(ctx.form.fields, ["nombre", "apellido", "rut", "email", "fono", "carrera"]);
  await t.page.evaluate(() => {
    window.__uah.rec.rest.programa = {
      "magister-intervencion-psicosocial": {
        postulacion_desde: "20261001", postulacion_hasta: "20270331", inicio_programa: "20270402", requisitos_text: "Arancel Total",
      },
    };
  });
  const r = await t.run("show_program", { url, slug: "magister-intervencion-psicosocial" });
  assert.equal(r.ok, true, r.error);
  assert.equal(r.event.event, "program_read");
  const p = r.event.payload;
  assert.match(p.requisitos_text, /Arancel Total: \$ 5\.250\.000/);
  assert.match(p.requisitos_text, /antes del 30\/10\/2026/);
  assert.equal(p.postulacion_desde, "20261001");
  assert.equal(p.inicio_programa, "20270402");
  assert.ok(p.sidebar.some((row) => row.label === "Postulaciones"));
  assert.match(await t.page.getAttribute("#collapseRequisitos", "class"), /\bshow\b/);
  assert.equal(await t.rung(), 1);
  await t.close();
});

// ─── Campus ───────────────────────────────────────────────────────────────

test("campus: UBICACIÓN and the map are headings a cue can show", async () => {
  const t = await open("https://www.uahurtado.cl/la-universidad/campus/campus-patrimonial/");
  const ctx = await t.context();
  assert.equal(ctx.kind, "page");
  assert.ok(ctx.headings.includes("UBICACIÓN"));
  assert.ok(ctx.headings.includes("Mapa"));
  assert.ok(ctx.headings.includes("Video"));
  const r = await t.run("show_section", { heading: "Mapa", text: null });
  assert.equal(r.ok, true, r.error);
  assert.equal(await t.rung(), 1);
  const inView = await t.page.evaluate(() => {
    const f = [...document.querySelectorAll("iframe")].find((i) => /maps/.test(i.getAttribute("data-src")));
    const box = f.getBoundingClientRect();
    return box.top >= 0 && box.top < innerHeight;
  });
  assert.ok(inView, "the map is scrolled into view");
  const u = await t.run("show_section", { heading: "Ubicación", text: null });
  assert.equal(u.ok, true, u.error);
  await t.close();
});

test("navigate: another page keeps its section for the next page; this page re-reports", async () => {
  const t = await open(PSICOLOGIA);
  const away = await t.run("navigate", {
    url: "https://www.uahurtado.cl/la-universidad/campus/campus-patrimonial/", heading: "UBICACIÓN", text: null, faq: null,
  });
  assert.deepEqual(away, { ok: true, moved: true });
  const rec = await t.page.evaluate(() => window.__uah.rec);
  assert.equal(rec.pend[0].command, "navigate");
  assert.equal(rec.pend[0].payload.heading, "UBICACIÓN");
  const before = (await t.events("page_changed")).length;
  const same = await t.run("navigate", { url: PSICOLOGIA, heading: "Requisitos y Aranceles", text: null, faq: null });
  assert.equal(same.ok, true, same.error);
  assert.equal((await t.events("page_changed")).length, before + 1);
  const off = await t.run("navigate", { url: "https://www.google.com/", heading: null, text: null, faq: null });
  assert.equal(off.ok, false);
  assert.match(off.error, /not on admision\., postgrados\. or www\.uahurtado\.cl/);
  await t.close();
});

// ─── The service worker's copy of a record ────────────────────────────────

const { htmlText } = await import(
  `data:text/javascript;base64,${Buffer.from(
    (await build({ entryPoints: [join(here, "../src/text.ts")], bundle: true, write: false, format: "esm", logLevel: "silent" }))
      .outputFiles[0].text,
  ).toString("base64")}`
);

test("the worker reads acf.aranceles_carrera's HTML as the page's lines", async () => {
  // As the REST API serves Psicología's record: raw ACF, CRLF, nbsp, stale attributes.
  const html =
    '<strong>Año 2027</strong>\r\n\r\nMatrícula\u00a0<span data-sheets-value="{&quot;2&quot;:&quot;$267.162&quot;}">$277.456\r\n</span>' +
    'Arancel anual\u00a0<span data-sheets-value="{">$7.167.421\r\n</span>Titulación 11 UF.\r\n\r\n&nbsp;';
  assert.equal(htmlText(html), "Año 2027\nMatrícula $277.456\nArancel anual $7.167.421\nTitulación 11 UF.");
  assert.equal(htmlText("<ul><li>Uno</li><li>Dos &amp; tres</li></ul>"), "- Uno\n- Dos & tres");
});

// ─── Run ──────────────────────────────────────────────────────────────────

const only = process.argv[2];
let failed = 0;
let ran = 0;
const started = Date.now();
for (const c of cases) {
  if (only && !c.name.includes(only)) continue;
  const t0 = Date.now();
  ran++;
  try {
    await c.fn();
    console.log(`ok   ${c.name} (${Date.now() - t0} ms)`);
  } catch (error) {
    failed++;
    console.log(`FAIL ${c.name}\n     ${String(error?.stack ?? error).split("\n").slice(0, 6).join("\n     ")}`);
  }
}
await browser.close();
console.log(`${failed ? "FAILED" : "passed"}: ${ran - failed}/${ran} in ${Date.now() - started} ms`);
process.exit(failed ? 1 : 0);
