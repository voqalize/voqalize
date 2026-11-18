// OWNER: banking-app agent. txn.find, txn.open, insights.show, confirm.ask, confirm.answer.
/**
 * The banking app's Stage performers. Each opens the screen its answer lives on
 * (signing in on the way, as a demo convenience), rings what it touches before
 * changing it, refuses with what the page offers instead of guessing, and
 * returns one short line the agent can repeat. Store writes are wrapped in
 * `asAgent`, so the events they raise say `by: "agent"`.
 */
import type { MoveContext } from "@voqalize/stage";
import { ActionRefusal, type ConfirmArgs, describeAction, resolveBeneficiary } from "../app/actions";
import { answerConfirm, openConfirm, useConfirm } from "../app/ConfirmSheet";
import { spendByCategory, txnMonths } from "../app/spending";
import { type TxnFilter, daysAgo, filterTxns, fmtDate, inr, monthName, products } from "../data/bank";
import { allTxns, filterIsEmpty, findTxn, useBank } from "../state/bank";
import { useSession } from "../state/session";
import { asAgent } from "../voice/events";
import { type AppStage, useMove } from "./host";
import { type Screen, appear, currentPath, navigateTo, screenPath, thing } from "./nav";

const SHORT = { beatMs: 380 };

/** Open `screen` (signing in first when needed) and wait for it to be on the page. */
async function openScreen(screen: Screen, c: MoveContext, id?: string): Promise<HTMLElement> {
  if (!useSession.getState().signedIn) asAgent(() => useSession.getState().signIn());
  const path = screenPath(screen, id);
  if (currentPath().replace(/\/+$/, "") !== path) navigateTo(path);
  const el = await appear(() => thing(`screen:${screen}`), 3000);
  return el ?? c.refuse("screen", `the ${screen.replace("_", " ")} screen did not open`);
}

/** Ring a marked thing if it is on the page (scrolling to it first). */
async function ringThing(name: string, c: MoveContext, label?: string, opts: { beatMs?: number } = {}): Promise<HTMLElement | null> {
  const el = await appear(() => thing(name), 1200);
  if (!el) return null;
  await c.scrollTo(el);
  await c.ring(el, { label: label ?? el.dataset.stageLabel, ...opts });
  return el;
}

const total = (n: number) => inr(Math.round(n * 100) / 100);

function describeResult(rows: ReturnType<typeof filterTxns>): string {
  const out = rows.filter((t) => t.direction === "debit").reduce((a, t) => a + t.amount, 0);
  const inn = rows.filter((t) => t.direction === "credit").reduce((a, t) => a + t.amount, 0);
  const n = `${rows.length} transaction${rows.length === 1 ? "" : "s"}`;
  if (rows.length === 0) return "0 transactions";
  if (out && inn) return `${n}: ${total(out)} out, ${total(inn)} in`;
  return `${n}, total ${total(out || inn)}`;
}

const CARD_SCREEN: Record<string, Screen> = { debit: "debit_card", credit: "credit_card" };

/** Where a confirmation belongs, and what to ring there first. */
function confirmPlace(a: ConfirmArgs): { screen: Screen; ring: string } {
  switch (a.kind) {
    case "card_block":
    case "card_unblock":
      return { screen: CARD_SCREEN[a.card!], ring: `control:${a.card}:blocked` };
    case "card_control":
      return { screen: CARD_SCREEN[a.card!], ring: `control:${a.card}:${a.control}` };
    case "card_limit":
      return { screen: CARD_SCREEN[a.card!], ring: `limit:${a.card}:${a.control}` };
    case "bill_pay":
      return { screen: "bills", ring: `biller:${a.target}` };
    case "transfer":
      return { screen: "payments", ring: `beneficiary:${a.target}` };
    case "fd_book":
      return { screen: "deposits", ring: "fd-form" };
    case "emi_convert":
      return { screen: "credit_card", ring: `emi:${a.target}` };
    case "offer_accept":
      return { screen: "offers", ring: `offer:${a.target}` };
  }
}

export function useAppPerformers(stage: AppStage): void {
  useMove(stage, "txn.find", async (args, c) => {
    const cats = products.spend_categories.map((x) => x.id);
    if (args.category && !cats.includes(args.category)) c.refuse("category", `there is no category "${args.category}"`, cats);
    if (args.from_days_ago != null && args.to_days_ago != null && args.from_days_ago < args.to_days_ago) {
      c.refuse("from_days_ago", "from_days_ago is the older day, so it must be at least to_days_ago");
    }
    await openScreen("transactions", c);
    const store = useBank.getState();
    asAgent(() => {
      store.openTxn(null);
      store.clearFilter();
    });
    await ringThing("txn-filters", c, "Filters", SHORT);

    const steps: [Partial<TxnFilter>, string, boolean][] = [
      [{ account: args.account ?? null }, "filter:account", !!args.account && args.account !== "all"],
      [{ category: args.category ?? null }, "filter:category", !!args.category],
      [{ query: args.query?.trim() || null }, "filter:query", !!args.query?.trim()],
      [{ from_days_ago: args.from_days_ago ?? null, to_days_ago: args.to_days_ago ?? (args.from_days_ago != null ? 0 : null) }, "filter:dates", args.from_days_ago != null || args.to_days_ago != null],
      [{ min_amount: args.min_amount ?? null, max_amount: args.max_amount ?? null }, "filter:amount", args.min_amount != null || args.max_amount != null],
      [{ direction: args.direction ?? null }, "filter:direction", !!args.direction && args.direction !== "any"],
    ];
    for (const [patch, name, used] of steps) {
      if (!used) continue;
      asAgent(() => useBank.getState().setFilter(patch));
      await ringThing(name, c, undefined, SHORT);
    }
    asAgent(() => useBank.getState().setFilter({ label: args.label?.trim() || null }));

    const rows = filterTxns(allTxns(), useBank.getState().filter);
    c.done(describeResult(rows));
    c.after(async () => {
      await ringThing("txn-summary", c, "Results");
    });
    return describeResult(rows);
  });

  useMove(stage, "txn.open", async ({ txn_id }, c) => {
    const id = String(txn_id ?? "").trim().toUpperCase();
    const t = findTxn(id) ?? c.refuse("txn_id", `there is no transaction ${txn_id}`);
    await openScreen("transactions", c);
    const visible = filterTxns(allTxns(), useBank.getState().filter).some((x) => x.id === id);
    if (!visible && !filterIsEmpty(useBank.getState().filter)) asAgent(() => useBank.getState().clearFilter());
    // Older rows sit behind "Show more": press it until the row is on the page.
    for (let i = 0; i < 6 && !thing(`txn:${id}`); i++) {
      const more = await appear(() => thing("txn-more"), 600);
      if (!more) break;
      more.click();
      await appear(() => thing(`txn:${id}`), 300);
    }
    const row = (await appear(() => thing(`txn:${id}`), 1500)) ?? c.refuse("txn_id", `${id} is not in the list`);
    await c.scrollTo(row);
    await c.ring(row, { label: t.merchant });
    asAgent(() => useBank.getState().openTxn(id));
    const where = t.account === "cc" ? "credit card" : t.account === "sb" ? "savings" : "current account";
    const line = `${t.id}: ${t.merchant}, ${inr(t.amount)} ${t.direction} on ${fmtDate(daysAgo(t.days_ago))}, ${where}${t.emi_eligible && t.account === "cc" ? ", EMI eligible" : ""}`;
    c.done(line);
    c.after(async () => {
      await ringThing("txn-detail", c, "Transaction details");
    });
    return line;
  });

  useMove(stage, "insights.show", async ({ month, category }, c) => {
    const months = txnMonths(allTxns());
    const m = String(month ?? "").trim();
    if (!months.includes(m)) c.refuse("month", `there is no data for ${m || "that month"}`, months);
    const data = spendByCategory(m);
    const cat = category ? data.categories.find((x) => x.id === category) : null;
    if (category && !cat) c.refuse("category", `no ${category} spends in ${monthName(m)}`, data.categories.map((x) => x.id));
    await openScreen("insights", c);
    if (useBank.getState().insightsMonth !== m) {
      await ringThing(`month:${m}`, c, monthName(m), SHORT);
      asAgent(() => useBank.getState().setInsightsMonth(m));
    }
    await ringThing("insights-total", c, "Total spent", SHORT);
    const line = `${monthName(m)}: spent ${total(data.total)}${cat ? `; ${cat.name} ${total(cat.amount)}` : ""}`;
    if (cat) {
      c.done(line);
      c.after(async () => {
        await ringThing(`category:${cat.id}`, c, cat.name);
      });
    }
    return line;
  });

  useMove(stage, "confirm.ask", async (raw, c) => {
    let args = { ...raw } as ConfirmArgs;
    if (args.kind === "transfer" && args.target) args = { ...args, target: resolveBeneficiary(args.target) ?? args.target };
    if (args.kind === "emi_convert" && args.target) args = { ...args, target: args.target.trim().toUpperCase() };
    try {
      describeAction(args);
    } catch (err) {
      if (err instanceof ActionRefusal) c.refuse(err.arg, err.why, err.options);
      throw err;
    }
    const place = confirmPlace(args);
    await openScreen(place.screen, c);
    await ringThing(place.ring, c);
    let title = "";
    try {
      title = asAgent(() => openConfirm(args)).title;
    } catch (err) {
      if (err instanceof ActionRefusal) c.refuse(err.arg, err.why, err.options);
      throw err;
    }
    const line = `confirmation shown: ${title}`;
    c.done(line);
    c.after(async () => {
      const sheet = await appear(() => thing("confirm-sheet"), 800);
      if (sheet) await c.ring(sheet, { label: "Confirmation" });
    });
    return line;
  });

  useMove(stage, "confirm.answer", async ({ action_id, yes }, c) => {
    const sheet = useConfirm.getState().sheet;
    if (!sheet) c.refuse("action_id", "no confirmation is on screen");
    if (sheet!.args.action_id !== action_id) c.refuse("action_id", `the sheet on screen is ${sheet!.args.action_id}, not ${action_id}`, [sheet!.args.action_id]);
    if (sheet!.phase !== "open") c.refuse("action_id", `${action_id} is already answered: reference ${sheet!.result?.reference}`);
    const btn = thing(yes ? "confirm-yes" : "confirm-cancel");
    if (btn) await c.ring(btn, { label: yes ? "Confirm" : "Cancel", beatMs: 450 });
    const res = asAgent(() => answerConfirm(!!yes));
    if (!res) c.refuse("action_id", "the sheet closed before it was answered");
    if (res!.outcome === "cancelled") return yes ? res!.summary : "cancelled";
    return `done, reference ${res!.reference}: ${res!.summary}`;
  });
}
