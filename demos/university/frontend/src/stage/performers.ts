/**
 * Every Stage move of the site (CONTRACT.md "Stage moves"), registered once on
 * the app-wide `Moves`. Each performer goes to the page it needs, rings its
 * target before it changes anything, refuses with the options the page offers
 * instead of guessing, and returns one short line the agent can repeat. They
 * call the same store actions the page's own controls do.
 */
import { type MoveContext, type Performers, findThing, things } from "@voqalize/stage";
import {
  FACET_NAMES,
  INTAKES,
  PROGRAMS,
  SCHOOLS,
  type Program,
  loose,
  programById,
  resolveFacet,
  resolveOption,
  resolveProgram,
} from "../data/catalogue";
import { PERSONA } from "../data/persona";
import { ALL_FIELDS, STEPS, type FormField, fieldByName, invalid, labelOfField, missingIn, optionsFor, parsePercent, shown, stepOf } from "../data/application";
import { useApplication } from "../state/application";
import { matching, useFinder } from "../state/finder";
import { currentPath, goTo, moves, part, thing, waitFor } from "./host";
import { scene } from "./scene.gen";
import { showWhole } from "./view";

type Spec = typeof scene.spec;

const plural = (n: number) => `${n} programme${n === 1 ? "" : "s"}`;
const card = (id: string) => document.querySelector(`[data-stage-card][data-program="${CSS.escape(id)}"]`);

/** Programme names that look like what was said, for a refusal. */
function closest(said: string): string[] {
  const words = loose(said).split(/[^a-z0-9]+/).filter((w) => w.length > 1);
  const scored = PROGRAMS.map((p) => ({ p, n: words.filter((w) => loose(p.name).includes(w) || p.id.includes(w)).length }))
    .filter((x) => x.n > 0)
    .sort((a, b) => b.n - a.n);
  return scored.slice(0, 6).map((x) => x.p.id);
}

function program(arg: string, said: string | null | undefined, c: MoveContext): Program {
  const p = resolveProgram(said);
  if (!p) c.refuse(arg, `there is no programme "${said ?? ""}" in the catalogue`, closest(said ?? ""));
  return p;
}

async function onFinder(c: MoveContext): Promise<void> {
  if (currentPath() !== "/programs") await goTo("/programs");
  if (!(await waitFor(() => thing("results")))) c.refuse("page", "the programme finder did not open");
}

async function onApply(c: MoveContext): Promise<void> {
  if (currentPath() !== "/apply") await goTo("/apply");
  if (!(await waitFor(() => thing("application")))) c.refuse("page", "the application form did not open");
  if (useApplication.getState().submitted) c.refuse("field", "this application is already submitted; start another one to change it");
}

/** Open a step of the form: ring its header first, then open it. */
async function openStep(n: number, c: MoveContext): Promise<void> {
  if (useApplication.getState().step === n) return;
  const header = thing(`step-${n}`);
  if (header) {
    await c.scrollTo(header);
    await c.ring(header, STEPS[n - 1].title);
  }
  useApplication.getState().setStep(n);
  await new Promise((r) => requestAnimationFrame(() => r(null)));
}

/** A said value, as the id of one of `options` ([id, label]). */
function pickOption(said: string, options: [string, string][]): string | null {
  const s = loose(said);
  if (!s) return null;
  const exact = options.find(([id, label]) => loose(id) === s || loose(label) === s);
  if (exact) return exact[0];
  const starts = options.filter(([, label]) => loose(label).startsWith(s));
  if (starts.length === 1) return starts[0][0];
  const contains = options.filter(([id, label]) => loose(label).includes(s) || loose(id).includes(s));
  return contains.length === 1 ? contains[0][0] : null;
}

/** The value a fill will set, checked against the form; refuses otherwise. */
function valueFor(f: FormField, said: string, values: Record<string, string>, c: MoveContext): { value: string; label: string } {
  const v = said.trim();
  if (!v) c.refuse("value", `say what to put in ${f.label.toLowerCase()}`);
  switch (f.type) {
    case "text": {
      const bad = invalid(f, v);
      if (bad) c.refuse("value", bad);
      return { value: v, label: f.private ? "" : v };
    }
    case "percent": {
      const n = parsePercent(v);
      if (n === null) c.refuse("value", `${f.label} takes a number from 0 to 100, like 92.4`);
      return { value: String(n), label: `${n}%` };
    }
    case "program": {
      const p = program("value", v, c);
      return { value: p.id, label: p.name };
    }
    case "intake": {
      const p = programById(values.program);
      if (!p) c.refuse("value", "choose the programme first: the intake comes with it");
      const intake = INTAKES[p.intake];
      const s = loose(v);
      if (loose(intake.label) === s || p.intake === v || loose(intake.label).includes(s) || s.includes(loose(intake.label))) {
        return { value: intake.label, label: intake.label };
      }
      return c.refuse("value", `${p.name} starts in ${intake.label}`, [intake.label]);
    }
    default: {
      const options = optionsFor(f, values);
      if (f.name === "room_type" && values.hostel !== "yes") c.refuse("field", "set hostel to yes first: room preference is only for a hostel room", ["hostel"]);
      const id = pickOption(v, options);
      if (!id) {
        const p = programById(values.program);
        const why =
          f.name === "campus" && p
            ? `${p.name} is taught at ${options.map(([, l]) => l).join(", ")}`
            : f.name === "scholarship" && p
              ? `${p.name} offers ${options.length > 1 ? options.slice(0, -1).map(([, l]) => l).join(", ") : "no scholarship"}`
              : `${f.label} has no option "${v}"`;
        c.refuse("value", why, options.map(([oid]) => oid));
      }
      return { value: id, label: options.find(([oid]) => oid === id)?.[1] ?? id };
    }
  }
}

const PAGES: Record<string, string> = {
  home: "/",
  programs: "/programs",
  programmes: "/programs",
  admissions: "/admissions",
  scholarships: "/scholarships",
  "campus-life": "/campus-life",
  apply: "/apply",
  schools: "/schools",
};

export function performers(): Performers<Spec> {
  return {
    "catalogue.filter": async ({ facet, value }, c: MoveContext) => {
      const f = resolveFacet(facet) ?? c.refuse("facet", `the finder has no "${facet}" filter`, FACET_NAMES);
      const opt = resolveOption(f, value) ?? c.refuse("value", `${f.name} has no option "${value}"`, f.options.map((o) => o.label));
      await onFinder(c);
      const before = useFinder.getState();
      if (before.filters[f.name].includes(opt.id)) {
        return `${f.name}: ${opt.label} is already ticked, ${plural(matching(before.filters).length)}`;
      }
      const opened = useFinder.getState().panelOpen;
      useFinder.getState().setPanel(true);
      const box = (await waitFor(() => part(`${f.name}:${opt.label}`))) ?? c.refuse("value", "that filter is not on screen");
      await c.scrollTo(box);
      await c.ring(box, `${f.name}: ${opt.label}`);
      useFinder.getState().setOption(f.name, opt.id, true);
      const line = `${f.name}: ${opt.label} ticked, ${plural(matching(useFinder.getState().filters).length)}`;
      c.done(line);
      // On a phone the panel covers the list: let the tick be seen, then show the list.
      if (!opened) {
        await c.beat(700);
        useFinder.getState().setPanel(false);
      }
      return line;
    },

    "catalogue.clear": async ({ facet }, c: MoveContext) => {
      const f = facet ? (resolveFacet(facet) ?? c.refuse("facet", `the finder has no "${facet}" filter`, FACET_NAMES)) : null;
      await onFinder(c);
      const s = useFinder.getState();
      const on = f ? s.filters[f.name].length : FACET_NAMES.reduce((n, k) => n + s.filters[k].length, 0);
      if (!on) return f ? `nothing is ticked under ${f.name}` : "no filters are ticked";
      s.setPanel(true);
      const target = (f ? thing(`facet-${f.name}`) : null) ?? thing("chips") ?? thing("filters");
      if (target) {
        await c.scrollTo(target);
        await c.ring(target, f ? `${f.name} filter` : "All filters");
      }
      useFinder.getState().clear(f?.name);
      const n = matching(useFinder.getState().filters).length;
      c.after(async () => {
        await c.beat(500);
        useFinder.getState().setPanel(false);
      });
      return f ? `${f.name} filter cleared, ${plural(n)}` : `all filters cleared, ${plural(n)}`;
    },

    "catalogue.pick": async ({ first, second, third }, c: MoveContext) => {
      const said = [["first", first], ["second", second], ["third", third]].filter((x): x is [string, string] => !!x[1]);
      const picks: Program[] = [];
      for (const [arg, v] of said) {
        const p = program(arg, v, c);
        if (!picks.includes(p)) picks.push(p);
      }
      await onFinder(c);
      useFinder.getState().setPanel(false);
      const header = thing("results");
      if (header) {
        await c.scrollTo(header);
        await c.ring(header, `${PERSONA.name}'s picks`);
      }
      useFinder.getState().setPicks([]);
      for (const [i, p] of picks.entries()) {
        const visible = card(p.id);
        if (visible) {
          await c.scrollTo(visible);
          await c.ring(visible, `Pick ${i + 1}: ${p.name}`);
          useFinder.getState().addPick(p.id);
        } else {
          // Hidden by the filters: it comes in pinned on top, then is ringed.
          useFinder.getState().addPick(p.id);
          const pinned = await waitFor(() => card(p.id));
          if (pinned) {
            await c.scrollTo(pinned);
            await c.ring(pinned, `Pick ${i + 1}: ${p.name}`);
          }
        }
      }
      c.after(async () => {
        const tray = thing("shortlist");
        if (tray) {
          await c.scrollTo(tray);
          await c.ring(tray, "Shortlist");
        }
      });
      return `picked ${picks.map((p) => p.name).join(", ")}`;
    },

    "catalogue.compare": async ({ first, second, third }, c: MoveContext) => {
      const said = [["first", first], ["second", second], ["third", third]].filter((x): x is [string, string] => !!x[1]);
      const ps: Program[] = [];
      for (const [arg, v] of said) {
        const p = program(arg, v, c);
        if (!ps.includes(p)) ps.push(p);
      }
      if (ps.length < 2) c.refuse("second", "a comparison needs two different programmes");
      await onFinder(c);
      useFinder.getState().setPanel(false);
      const shown = ps.map((p) => card(p.id)).filter((x): x is Element => !!x);
      const anchor = shown.length ? shown : [thing("results")].filter((x): x is Element => !!x);
      if (anchor.length) {
        // X1: every card being compared in view together, not just the first.
        await (anchor.length > 1 ? showWhole(anchor) : c.scrollTo(anchor[0]));
        await c.ring(anchor, "Compare");
      }
      useFinder.getState().openCompare(ps.map((p) => p.id));
      const panel = await waitFor(() => thing("comparison"));
      const line = `comparing ${ps.map((p) => p.name).join(" and ")} side by side`;
      c.done(line);
      if (panel) {
        await c.scrollTo(panel);
        await c.ring(panel, "Comparison");
      }
      return line;
    },

    "site.open": async ({ program: said }, c: MoveContext) => {
      const p = program("program", said, c);
      const link = document.querySelector(`[data-program-link="${CSS.escape(p.id)}"]`);
      if (link && link.getBoundingClientRect().height > 0) {
        await c.scrollTo(link);
        await c.ring(link, p.name);
      }
      useFinder.getState().closeCompare();
      await goTo(`/programs/${p.id}`);
      const title = await waitFor(() => (currentPath() === `/programs/${p.id}` ? thing("title") : null));
      if (!title) c.refuse("program", "the programme page did not open");
      window.scrollTo({ top: 0 });
      c.after(async () => {
        await c.scrollTo(title);
        await c.ring(title, p.name);
      });
      return `opened ${p.name}`;
    },

    "site.go": async ({ page }, c: MoveContext) => {
      const key = loose(page).replace(/^\//, "").replace(/\s+/g, "-");
      let path = PAGES[key];
      let label = key.replace(/-/g, " ");
      if (!path && key.startsWith("schools/")) {
        const id = key.slice("schools/".length);
        const s = SCHOOLS.find((x) => x.id === id || loose(x.short) === id.replace(/-/g, " "));
        if (!s) c.refuse("page", `there is no school "${id}"`, SCHOOLS.map((x) => `schools/${x.id}`));
        path = `/schools/${s.id}`;
        label = s.name;
      }
      if (!path) c.refuse("page", `the site has no "${page}" page`, [...Object.keys(PAGES).filter((k) => k !== "programmes"), "schools/<school id>"]);
      const nav = document.querySelector(`[data-nav="${CSS.escape(path)}"]`);
      if (nav && nav.getBoundingClientRect().height > 0) {
        await c.scrollTo(nav);
        await c.ring(nav, label);
      }
      useFinder.getState().closeCompare();
      await goTo(path);
      window.scrollTo({ top: 0 });
      return path === "/" ? "opened the home page" : `opened the ${label} page`;
    },

    "site.show": async ({ target }, c: MoveContext) => {
      const el = findThing(target);
      if (!el) {
        const names = [...new Set(things().map((t) => t.name))].filter((n) => !n.startsWith("faq-"));
        c.refuse("target", `this page has no section "${target}"`, names);
      }
      await c.reveal(el);
      if (el instanceof HTMLDetailsElement) el.open = true;
      if (el.getAttribute("data-stage-thing") === "faqs") el.querySelector("details")?.setAttribute("open", "");
      await c.scrollTo(el);
      const label = el.getAttribute("data-stage-label") ?? target;
      await c.ring(el, label);
      return `showing ${label.toLowerCase()}`;
    },

    "apply.fill": async ({ field, value }, c: MoveContext) => {
      const f = fieldByName(field.trim().toLowerCase()) ?? c.refuse("field", `the application has no field "${field}"`, ALL_FIELDS.map((x) => x.name));
      await onApply(c);
      const values = useApplication.getState().values;
      const { value: v, label } = valueFor(f, String(value ?? ""), values, c);
      const step = stepOf(f.name) ?? 1;
      await openStep(step, c);
      if (!shown(f, useApplication.getState().values)) c.refuse("field", `${f.label} is not asked for with these answers`);
      const target =
        f.type === "choice" || f.type === "intake" || f.type === "scholarship" || f.type === "document"
          ? await waitFor(() => part(`${f.name}:${v}`) ?? document.querySelector(`[data-field="${CSS.escape(f.name)}"]`))
          : await waitFor(() => document.querySelector(`[name="${CSS.escape(f.name)}"]`));
      if (!target) c.refuse("field", `${f.label} is not on screen`);
      await c.scrollTo(target);
      await c.ring(target, f.label);
      const before = useApplication.getState().values;
      useApplication.getState().set(f.name, v);
      const after = useApplication.getState().values;
      const name = f.label.replace(/\s*\(%\)$/, "").toLowerCase();
      if (f.private) return `${name} filled`;
      if (f.type === "percent") return `${name} set to ${label}`;
      if (f.type === "document") return `${name}: ${v === "uploaded" ? "uploaded" : "to upload later"}`;
      if (f.name === "program") {
        const cleared = ["campus", "intake", "scholarship"].filter((k) => before[k] && !after[k]);
        return `programme set to ${label}${cleared.length ? `; ${cleared.join(" and ")} cleared, the new programme does not offer the old choice` : ""}`;
      }
      return `${name}: ${label}`;
    },

    "apply.step": async ({ step }, c: MoveContext) => {
      const n = Number(step);
      if (!Number.isInteger(n) || n < 1 || n > STEPS.length) c.refuse("step", `the application has ${STEPS.length} steps`, STEPS.map((s) => String(s.step)));
      await onApply(c);
      const header = thing(`step-${n}`) ?? c.refuse("step", "that step is not on screen");
      await c.scrollTo(header);
      await c.ring(header, STEPS[n - 1].title);
      useApplication.getState().setStep(n);
      return `step ${n}, ${STEPS[n - 1].title.toLowerCase()}, is open`;
    },

    "apply.next": async (_args, c: MoveContext) => {
      await onApply(c);
      const s = useApplication.getState();
      if (s.step >= STEPS.length) c.refuse("step", "this is the last step: the applicant presses Pay and submit themselves");
      const missing = missingIn(s.step, s.values);
      if (missing.length) {
        c.refuse("step", `still empty on step ${s.step}: ${missing.map((m) => labelOfField(m).replace(/\s*\(%\)$/, "").toLowerCase()).join(", ")}`, missing);
      }
      const btn = thing("continue");
      if (btn) {
        await c.scrollTo(btn);
        await c.ring(btn, "Continue");
      }
      useApplication.getState().next();
      const now = useApplication.getState().step;
      return `on to step ${now}, ${STEPS[now - 1].title.toLowerCase()}`;
    },
  };
}

let registered = false;
/** Register every performer on the app-wide `Moves`, once. */
export function registerPerformers(): void {
  if (registered) return;
  registered = true;
  scene.registerAll(moves, performers());
}
