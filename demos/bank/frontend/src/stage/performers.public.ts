/**
 * The public site's moves (CONTRACT.md "Stage moves"): ui.show, nav.open,
 * form.fill / form.step / form.submit, cards.compare, emi.plan, loan.calc and
 * loan.eligibility. Each one navigates first when it must, rings what it is
 * about to change before changing it, writes the same stores a tap does (inside
 * `asAgent`, so the brain hears the change as the agent's), refuses with the
 * options the page offers instead of guessing, and returns one short line.
 */
import { type MoveContext, fold, visible } from "@voqalize/stage";
import { creditCardProduct, inr, loanProduct, products, txnById } from "../data/bank";
import { cardEmi, cardValue, loanEligibility } from "../lib/bankmath";
import { amortise } from "../lib/amortise";
import { emiTxns } from "../pages/public/CardsEmi";
import { LOAN_TYPES, type LoanType, SPEND_KEYS, useAdvisor } from "../state/advisor";
import {
  FIELDS,
  type FormId,
  OA_STEPS,
  choiceLabel,
  choicesOf,
  fieldDef,
  fieldsOf,
  invalid,
  normalise,
  stepOfField,
  useForms,
} from "../state/forms";
import { useSession } from "../state/session";
import { asAgent } from "../voice/events";
import { type AppStage, useMove } from "./host";
import { type Screen, appear, currentPath, navigateTo, screenOf, screenPath, thing } from "./nav";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const SCREENS: Screen[] = [
  "home", "login", "dashboard", "account", "transactions", "insights", "cards_hub", "debit_card", "credit_card", "payments", "bills",
  "deposits", "statements", "offers", "open_account", "cards", "card_detail", "cards_compare", "cards_apply", "cards_emi", "loans", "loan", "loan_apply",
];
const FORM_SCREEN: Record<FormId, Screen> = { open_account: "open_account", card_apply: "cards_apply", loan_apply: "loan_apply" };

const isAppPath = (p: string) => p === "/app" || p.startsWith("/app/");
const here = () => `${currentPath()}${window.location.search}`;

/** The page's own things on screen now, each with its spoken label. */
function visibleThings(): { name: string; label: string; el: HTMLElement }[] {
  return [...document.querySelectorAll<HTMLElement>("[data-stage-thing]")]
    .filter((el) => visible(el))
    .map((el) => ({ name: el.dataset.stageThing ?? "", label: (el.dataset.stageLabel ?? el.textContent ?? "").trim().slice(0, 60), el }))
    .filter((t) => t.name && !t.name.startsWith("screen:"));
}

/** A signed-in screen asked for while signed out: the page shows its sign-in form
 *  there. The agent never signs in (FEEDBACK B7, X9); the customer types and presses. */
const needsSignIn = (path: string) => isAppPath(path) && !useSession.getState().signedIn;

/** The visible nav link that goes to `path`, to ring before navigating. */
function navLinkTo(path: string): HTMLElement | null {
  const want = path.split("?")[0];
  for (const a of document.querySelectorAll<HTMLAnchorElement>("a[href]")) {
    if (!visible(a)) continue;
    const p = new URL(a.href, window.location.href).pathname.replace(BASE, "") || "/";
    if (p === want && a.closest("nav, header, aside, .app-nav, .app-tabs")) return a;
  }
  return null;
}

/** Make sure `screen` (at `path`) is on screen; navigate there when it is not. */
async function ensure(screen: Screen, path: string, c: MoveContext, opts: { exact?: boolean } = {}): Promise<HTMLElement> {
  const onIt = thing(`screen:${screen}`) && (!opts.exact || here() === path);
  if (!onIt) {
    navigateTo(path, screenOf(currentPath()) === screen);
  }
  const root = await appear(() => thing(`screen:${screen}`), 2500);
  if (!root) return c.refuse("screen", `the ${screen.replace(/_/g, " ")} screen did not open`);
  return root;
}

/** Wait for a thing, scroll to it and ring it. */
async function ringThing(name: string, label: string, c: MoveContext, ms = 1200): Promise<HTMLElement | null> {
  const el = await appear(() => thing(name), ms);
  if (!el) return null;
  await c.scrollTo(el);
  await c.ring(el, label);
  return el;
}

const nextFrame = () => new Promise((r) => requestAnimationFrame(() => setTimeout(r, 30)));

export function usePublicPerformers(stage: AppStage): void {
  // ── ui.show ──────────────────────────────────────────────────────────────
  useMove(stage, "ui.show", async ({ thing: said }, c) => {
    const want = fold(String(said ?? "").trim());
    const all = visibleThings();
    if (!want) c.refuse("thing", "say what to show", [...new Set(all.map((t) => t.label))].slice(0, 30));
    const hit =
      all.find((t) => fold(t.name) === want) ??
      all.find((t) => fold(t.label) === want) ??
      all.find((t) => fold(t.label).startsWith(want)) ??
      all.find((t) => fold(t.label).includes(want));
    if (!hit) return c.refuse("thing", `nothing on this screen is called "${said}"`, [...new Set(all.map((t) => t.label).filter(Boolean))].slice(0, 30));
    await c.reveal(hit.el);
    await c.scrollTo(hit.el);
    await c.ring(hit.el, hit.label);
    return `showed ${hit.label}`;
  });

  // ── nav.open ─────────────────────────────────────────────────────────────
  useMove(stage, "nav.open", async ({ screen, id }, c) => {
    const s = screen as Screen;
    if (!SCREENS.includes(s)) c.refuse("screen", `there is no screen ${screen}`, SCREENS);
    if (s === "account" && id && !["sb", "ca"].includes(id)) c.refuse("id", "the accounts are sb (savings) and ca (current)", ["sb", "ca"]);
    if ((s === "card_detail" || s === "cards_apply") && id && !creditCardProduct(id))
      c.refuse("id", `there is no card ${id}`, products.credit_cards.map((x) => x.id));
    if ((s === "loan" || s === "loan_apply") && id && !loanProduct(id)) c.refuse("id", `there is no loan ${id}`, LOAN_TYPES);
    // The sign-in screen remembers where she was, to go back there once she signs in.
    const back = currentPath();
    const path = s === "login" && back !== "/" && back !== "/login" && !isAppPath(back) ? `/login?from=${encodeURIComponent(back)}` : screenPath(s, id ?? null);
    if (here() === path && thing(`screen:${s}`)) {
      const root = thing(`screen:${s}`)!;
      await c.scrollTo(root);
      return `${s.replace(/_/g, " ")} is already open`;
    }
    const link = navLinkTo(path);
    if (link) {
      await c.scrollTo(link);
      await c.ring(link, link.textContent?.trim() || s);
    }
    const locked = needsSignIn(path);
    navigateTo(path);
    if (locked || s === "login") {
      const form = await appear(() => thing("sign-in-form"), 3000);
      if (!form) return c.refuse("screen", "the sign-in screen did not open");
      await c.ring(form, { label: "Sign in" });
      return locked
        ? `the sign-in screen is showing in place of ${s.replace(/_/g, " ")}: she is signed out, and only she signs in, by typing her mobile number and PIN`
        : "the sign-in screen is open: she types her mobile number and PIN and presses Sign in herself";
    }
    const root = await appear(() => thing(`screen:${s}`), 3000);
    if (!root) return c.refuse("screen", `the ${s.replace(/_/g, " ")} screen did not open`);
    return `opened ${s.replace(/_/g, " ")}`;
  });

  // ── form.fill ────────────────────────────────────────────────────────────
  useMove(stage, "form.fill", async ({ form, field, value }, c) => {
    const f = form as FormId;
    if (!FIELDS[f]) c.refuse("form", `there is no form ${form}`, ["open_account", "card_apply", "loan_apply"]);
    const name = String(field ?? "").trim();
    const values = useForms.getState().values[f];
    const all = FIELDS[f].map((d) => d.name);
    if (!all.includes(name)) c.refuse("field", `the ${f.replace("_", " ")} form has no field "${name}"`, fieldsOf(f, values));
    if (f === "loan_apply" && !fieldsOf(f, values).includes(name)) {
      const need = { property_value: "home", gold_grams: "gold", car_price: "car" }[name] ?? "";
      c.refuse("field", `${name} is only asked for a ${need} loan; this application is for a ${values.loan_type || "loan not chosen yet"}`, fieldsOf(f, values));
    }
    const v = normalise(f, name, String(value ?? ""));
    if (!v) c.refuse("value", `say a value for ${fieldDef(f, name)?.label ?? name}`);
    const choices = choicesOf(f, name);
    if (choices && !choices.includes(v)) c.refuse("value", `${fieldDef(f, name)?.label ?? name} is one of ${choices.map((x) => choiceLabel(name, x)).join(", ")}`, choices);
    const why = invalid(f, name, v, values);
    if (why) c.refuse("value", why);

    const path = f === "open_account" ? "/open-account" : f === "card_apply" ? "/cards/apply" : "/loans/apply";
    await ensure(FORM_SCREEN[f], path, c);
    if (useForms.getState().submitted[f]) asAgent(() => useForms.getState().reset(f));

    if (f === "open_account") {
      const step = stepOfField(name);
      if (useForms.getState().step[f] !== step) {
        const stepEl = thing(`step-${step}`);
        if (stepEl) {
          await c.scrollTo(stepEl);
          await c.ring(stepEl, OA_STEPS[step - 1].title);
        }
        asAgent(() => useForms.getState().setStep(f, step));
      }
    }
    const label = fieldDef(f, name)?.label ?? name;
    const box = await appear(() => thing(`field:${f}:${name}`), 1500);
    if (!box) return c.refuse("field", `${label} is not on screen`);
    const target = choices ? (box.querySelector(`[data-stage-part="${CSS.escape(`${name}:${v}`)}"]`) ?? box) : box;
    await c.scrollTo(box);
    await c.ring(target, choices ? `${label}: ${choiceLabel(name, v)}` : label);
    asAgent(() => useForms.getState().setField(f, name, v));
    return `set ${name}`;
  });

  // ── form.step ────────────────────────────────────────────────────────────
  useMove(stage, "form.step", async ({ form, step }, c) => {
    const f = form as FormId;
    if (!FIELDS[f]) c.refuse("form", `there is no form ${form}`, ["open_account", "card_apply", "loan_apply"]);
    const n = Number(step);
    const max = f === "open_account" ? OA_STEPS.length : 1;
    if (!Number.isInteger(n) || n < 1 || n > max)
      c.refuse("step", f === "open_account" ? "account opening has six steps" : "this form is one page, step 1", Array.from({ length: max }, (_, i) => String(i + 1)));
    const path = f === "open_account" ? "/open-account" : f === "card_apply" ? "/cards/apply" : "/loans/apply";
    await ensure(FORM_SCREEN[f], path, c);
    if (f !== "open_account") return "the form is on screen";
    const el = thing(`step-${n}`);
    if (el) {
      await c.scrollTo(el);
      await c.ring(el, OA_STEPS[n - 1].title);
    }
    asAgent(() => useForms.getState().setStep(f, n));
    const missing = n > 1 ? useForms.getState().missing(f, n - 1) : [];
    return `on step ${n}, ${OA_STEPS[n - 1].title.toLowerCase()}${missing.length ? `; step ${n - 1} still needs ${missing.join(", ")}` : ""}`;
  });

  // ── form.submit ──────────────────────────────────────────────────────────
  useMove(stage, "form.submit", async ({ form }, c) => {
    const f = form as FormId;
    if (!FIELDS[f]) c.refuse("form", `there is no form ${form}`, ["open_account", "card_apply", "loan_apply"]);
    const done = useForms.getState().submitted[f];
    if (done) return `already submitted, reference ${done.reference}`;
    const missing = useForms.getState().missing(f);
    if (missing.length) c.refuse("form", `still missing ${missing.join(", ")}`, missing);
    const path = f === "open_account" ? "/open-account" : f === "card_apply" ? "/cards/apply" : "/loans/apply";
    await ensure(FORM_SCREEN[f], path, c);
    if (f === "open_account" && useForms.getState().step[f] !== 6) {
      const el = thing("step-6");
      if (el) await c.ring(el, OA_STEPS[5].title);
      asAgent(() => useForms.getState().setStep(f, 6));
    }
    const button = await appear(() => thing(`submit:${f}`), 1500);
    if (!button) return c.refuse("form", "the Submit button is not on screen");
    await c.scrollTo(button);
    await c.ring(button, button.dataset.stageLabel ?? "Submit");
    const r = asAgent(() => useForms.getState().submit(f));
    if ("missing" in r) return c.refuse("form", `still missing ${r.missing.join(", ")}`, r.missing);
    c.after(async () => {
      const conf = await appear(() => thing(f === "loan_apply" ? "lead-card" : "confirmation"), 1500);
      if (conf) {
        await c.scrollTo(conf);
        await c.ring(conf, f === "loan_apply" ? "Lead card" : "Application received");
      }
    });
    if (r.lead) {
      return `submitted, lead ${r.reference}: ${r.lead.product}, ${inr(r.lead.amount)}, EMI ${inr(r.lead.emi)}, ${r.lead.within ? "within" : "above"} the eligible ${inr(r.lead.eligibility.max_amount)}; status qualified`;
    }
    return `submitted, reference ${r.reference}`;
  });

  // ── cards.compare ────────────────────────────────────────────────────────
  useMove(stage, "cards.compare", async (args, c) => {
    const ids = (Array.isArray(args.card_ids) ? args.card_ids : String(args.card_ids ?? "").split(/[,\s]+/)).map((x) => String(x).trim()).filter(Boolean);
    const known = products.credit_cards.map((x) => x.id);
    const bad = ids.filter((id) => !known.includes(id));
    if (bad.length) c.refuse("card_ids", `no card ${bad.join(", ")}`, known);
    const unique = [...new Set(ids)];
    if (unique.length < 2 || unique.length > 5) c.refuse("card_ids", "compare two to five cards", known);
    const patch: Record<string, number> = {};
    for (const k of SPEND_KEYS) {
      const v = (args as Record<string, unknown>)[k];
      if (v == null) continue;
      const n = Number(v);
      if (!Number.isFinite(n) || n < 0) c.refuse(k, `${k} is a monthly amount in rupees`);
      patch[k] = Math.round(n);
    }
    await ensure("cards_compare", "/cards/compare", c);
    const line = thing("compare:profile");
    if (line && Object.keys(patch).length) {
      await c.scrollTo(line);
      await c.ring(line, "Spend profile");
    }
    asAgent(() => {
      if (Object.keys(patch).length) useAdvisor.getState().setProfile(patch);
      useAdvisor.getState().setCompare(unique);
    });
    await nextFrame();
    const profile = useAdvisor.getState().profile;
    const vals = unique.map((id) => cardValue(creditCardProduct(id)!, profile));
    const best = vals.reduce((b, v) => (v.net_yearly > b.net_yearly ? v : b), vals[0]);
    const detail = `comparing ${unique.map((id) => creditCardProduct(id)!.name.replace("Global ", "")).join(", ")}; best for this spend: ${creditCardProduct(best.card_id)!.name} at ${inr(best.net_yearly)} a year`;
    c.done(detail);
    for (const id of unique) {
      const el = thing(`compare:${id}`);
      if (el) await c.ring(el, creditCardProduct(id)!.name);
    }
    return detail;
  });

  // ── emi.plan ─────────────────────────────────────────────────────────────
  useMove(stage, "emi.plan", async ({ txn_id, amount, tenure_months }, c) => {
    const tenures = products.emi.tenures.map((t) => t.months);
    const n = Number(tenure_months);
    if (!tenures.includes(n)) c.refuse("tenure_months", `the tenures are ${tenures.join(", ")} months`, tenures.map(String));
    let path = "/cards/emi";
    let principal: number;
    if (txn_id) {
      const t = txnById(String(txn_id));
      if (!t || t.account !== "cc" || t.direction !== "debit" || !t.emi_eligible) {
        return c.refuse("txn_id", t ? `${t.merchant} (${t.id}) cannot be converted to EMI` : `there is no transaction ${txn_id}`, emiTxns().map((x) => `${x.id} ${x.merchant} ${inr(x.amount)}`));
      }
      principal = t.amount;
      if (!useSession.getState().signedIn) return c.refuse("txn_id", "she is not signed in: her own card spends show once she signs in herself");
      path = `/cards/emi?txn=${t.id}`;
    } else if (amount != null) {
      principal = Math.round(Number(amount));
      if (!Number.isFinite(principal) || principal < products.emi.min_amount)
        c.refuse("amount", `the smallest spend that converts to EMI is ${inr(products.emi.min_amount)}`);
    } else {
      return c.refuse("txn_id", "say which card spend, or an amount");
    }
    if (here() !== path) navigateTo(path, screenOf(currentPath()) === "cards_emi");
    await appear(() => thing("screen:cards_emi"), 2500);
    if (!txn_id) asAgent(() => useAdvisor.getState().setEmi({ txn: null, amount: principal }));
    const row = await appear(() => thing(`emi:${n}`), 1500);
    if (!row) return c.refuse("tenure_months", "the EMI table is not on screen");
    await c.scrollTo(row);
    await c.ring(row, `${n} months`);
    asAgent(() => useAdvisor.getState().setEmi({ tenure: n }));
    const r = cardEmi(principal, n);
    return `EMI ${inr(r.emi)} a month for ${n} months at ${r.rate}%; interest ${inr(r.total_interest)}, fee ${inr(r.processing_fee)} plus ${inr(r.gst_on_fee)} GST, total cost ${inr(r.total_cost)}`;
  });

  // ── loan.calc ────────────────────────────────────────────────────────────
  useMove(stage, "loan.calc", async ({ loan_type, amount, tenure_months, rate }, c) => {
    const t = loan_type as LoanType;
    const loan = loanProduct(t) ?? c.refuse("loan_type", `there is no ${loan_type} loan`, LOAN_TYPES);
    const p = Math.round(Number(amount));
    if (!(p >= loan.amount_min && p <= loan.amount_max)) c.refuse("amount", `a ${loan.short.toLowerCase()} is ${inr(loan.amount_min)} to ${inr(loan.amount_max)}`);
    const n = Math.round(Number(tenure_months));
    if (!(n >= loan.tenure_min_months && n <= loan.tenure_max_months)) c.refuse("tenure_months", `a ${loan.short.toLowerCase()} runs ${loan.tenure_min_months} to ${loan.tenure_max_months} months`);
    const r = rate == null ? loan.rate_typical : Number(rate);
    if (!(r >= loan.rate_min && r <= loan.rate_max)) c.refuse("rate", `the ${loan.short.toLowerCase()} rate is ${loan.rate_min}% to ${loan.rate_max}%`);
    await ensure("loan", `/loans/${t}`, c, { exact: true });
    const calc = await appear(() => thing("loan:calculator"), 1500);
    if (calc) {
      await c.scrollTo(calc);
      await c.ring(calc, "EMI calculator");
    }
    asAgent(() => useAdvisor.getState().setCalc(t, { amount: p, tenure: n, rate: r }));
    await nextFrame();
    const a = amortise(p, r, n);
    const detail = `EMI ${inr(a.emi)}`;
    c.done(detail);
    await ringThing("loan:emi", "EMI", c);
    await ringThing("loan:working", "The working", c);
    return detail;
  });

  // ── loan.eligibility ─────────────────────────────────────────────────────
  useMove(stage, "loan.eligibility", async ({ loan_type, monthly_income, existing_emis, tenure_months, gold_grams }, c) => {
    const t = loan_type as LoanType;
    const loan = loanProduct(t) ?? c.refuse("loan_type", `there is no ${loan_type} loan`, LOAN_TYPES);
    const patch: Record<string, number> = {};
    if (t === "gold") {
      const g = Number(gold_grams);
      if (!(g > 0)) c.refuse("gold_grams", "a gold loan goes by the gold: say how many grams");
      patch.gold_grams = g;
    } else {
      const inc = Number(monthly_income);
      if (!(inc > 0)) c.refuse("monthly_income", "say the monthly take-home income");
      patch.monthly_income = inc;
      if (existing_emis != null) {
        const e = Number(existing_emis);
        if (!(e >= 0)) c.refuse("existing_emis", "existing EMIs are a monthly amount in rupees");
        patch.existing_emis = e;
      }
      if (tenure_months != null) {
        const n = Math.round(Number(tenure_months));
        if (!(n >= loan.tenure_min_months && n <= loan.tenure_max_months))
          c.refuse("tenure_months", `a ${loan.short.toLowerCase()} runs ${loan.tenure_min_months} to ${loan.tenure_max_months} months`);
        patch.tenure_months = n;
      }
    }
    await ensure("loan", `/loans/${t}`, c, { exact: true });
    const panel = await appear(() => thing("loan:eligibility-check"), 1500);
    if (panel) {
      await c.scrollTo(panel);
      await c.ring(panel, "Eligibility check");
    }
    asAgent(() => useAdvisor.getState().setElig(t, patch, true));
    await nextFrame();
    const el = loanEligibility(loan, useAdvisor.getState().elig[t]);
    const detail = `up to ${inr(el.max_amount)}${el.max_emi != null ? `, with an EMI of up to ${inr(el.max_emi)}` : ""}`;
    c.done(detail);
    await ringThing("loan:eligibility", "Eligibility", c);
    return detail;
  });
}
