/**
 * Every state change the bank makes, behind the confirmation sheet
 * (CONTRACT.md `confirm.ask`). `describeAction` builds the sheet's summary from
 * the customer's own data, or refuses what the bank cannot do (an amount above
 * the balance, a limit above the card's maximum, a spend that is not
 * EMI-eligible); `applyAction` does it once confirmed and returns a reference.
 * The same two functions serve the visitor's taps and the agent's moves.
 */
import type { ArgsOf } from "@voqalize/stage";
import {
  type AccountId,
  accountById,
  billerById,
  brand,
  cardById,
  customer,
  daysFromNow,
  fmtDate,
  inr,
  loanProduct,
  products,
} from "../data/bank";
import { cardEmi, emi, fdQuote, fdRate } from "../lib/bankmath";
import type { scene } from "../stage/scene.gen";
import { type CardId, addTxn, findTxn, moveBalance, useBank } from "../state/bank";
import { emit } from "../voice/events";

export type ConfirmArgs = ArgsOf<typeof scene.spec, "confirm.ask">;
export type ActionKind = ConfirmArgs["kind"];

export interface Described {
  title: string;
  lines: [string, string][];
  confirmLabel: string;
  danger?: boolean;
  /** A line under the summary, in plain words. */
  note?: string;
}

export interface Applied {
  reference: string;
  summary: string;
}

/** What the bank cannot do, with the argument at fault and what it offers instead. */
export class ActionRefusal extends Error {
  constructor(
    readonly arg: string,
    readonly why: string,
    readonly options?: string[],
  ) {
    super(why);
  }
}

const refuse = (arg: string, why: string, options?: string[]): never => {
  throw new ActionRefusal(arg, why, options);
};

export const CONTROL_LABEL: Record<string, string> = {
  international: "International usage",
  online: "Online payments",
  contactless: "Contactless (tap to pay)",
  atm: "ATM withdrawals",
  blocked: "Card block",
  atm_daily: "ATM withdrawal limit",
  pos_daily: "In-store (POS) limit",
  online_daily: "Online payment limit",
};
/** A label in a sentence: lower case, keeping ATM and POS. */
const lc = (k: string) => CONTROL_LABEL[k].toLowerCase().replace("atm", "ATM").replace("pos", "POS");
const SWITCHES = ["international", "online", "contactless", "atm"] as const;
const LIMITS = ["atm_daily", "pos_daily", "online_daily"] as const;

const INITIALS: Record<ActionKind, string> = {
  card_block: "CB",
  card_unblock: "CU",
  card_control: "CC",
  card_limit: "CL",
  bill_pay: "BP",
  transfer: "TR",
  fd_book: "FD",
  emi_convert: "EC",
  offer_accept: "OA",
};
const reference = (kind: ActionKind) => `ANV${INITIALS[kind]}${String(Math.floor(Math.random() * 1e6)).padStart(6, "0")}`;

const cardName = (id: CardId) => {
  const c = cardById(id)!;
  return `${c.name} •••• ${c.last4}`;
};

function needCard(a: ConfirmArgs): CardId {
  if (a.card !== "debit" && a.card !== "credit") refuse("card", "which card: the debit card or the credit card?", ["debit", "credit"]);
  return a.card as CardId;
}

function parseOnOff(v: unknown): boolean {
  const s = String(v ?? "").trim().toLowerCase();
  if (["on", "true", "yes", "enable", "enabled", "allow"].includes(s)) return true;
  if (["off", "false", "no", "disable", "disabled", "block"].includes(s)) return false;
  return refuse("value", "a control is turned on or off", ["on", "off"]);
}

function parseRupees(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(String(v).replace(/[₹,\s]/g, "").replace(/rs\.?/i, ""));
  return Number.isFinite(n) ? n : null;
}

function fromAccount(a: ConfirmArgs): AccountId {
  const f = a.from_account ?? "sb";
  if (f !== "sb" && f !== "ca") refuse("from_account", "pay from savings or current", ["sb", "ca"]);
  return f as AccountId;
}

const accLabel = (id: AccountId) => {
  const acc = accountById(id)!;
  return `${acc.name} •••• ${acc.last4}`;
};

function checkFunds(acc: AccountId, amount: number) {
  const bal = useBank.getState().balances[acc];
  if (amount > bal) refuse("amount", `${inr(amount)} is more than the ${accountById(acc)!.name} balance of ${inr(bal)}`, [`up to ${inr(bal)}`]);
}

const registered = (id: string) => customer.registered_billers.find((b) => b.biller_id === id);
const beneficiary = (id: string) => {
  const q = id.trim().toLowerCase();
  return customer.beneficiaries.find((b) => b.id === id || b.name.toLowerCase() === q || b.nickname.toLowerCase() === q);
};
/** A beneficiary id from an id, a name or a nickname ("Mum"). */
export const resolveBeneficiary = (q: string) => beneficiary(q)?.id;
const offerById = (id: string) => customer.offers.find((o) => o.id === id);

/** What is left to pay on a biller (0 once paid here). */
export const billDue = (id: string) => {
  if (useBank.getState().billsPaid[id]) return 0;
  if (id === "anvaya-card") return cardStatementDue();
  return registered(id)?.due ?? 0;
};
export const cardStatementDue = () => (useBank.getState().billsPaid["anvaya-card"] ? 0 : cardById("credit")!.statement!.total_due);

/** The personal-loan offer's default tenure: the product's default, within the offer's maximum. */
export const offerTenureDefault = (max: number) => Math.min(max, loanProduct("personal")?.tenure_default_months ?? 36);

// ─── Describe ──────────────────────────────────────────────────────────────

export function describeAction(a: ConfirmArgs): Described {
  const s = useBank.getState();
  switch (a.kind) {
    case "card_block": {
      const card = needCard(a);
      if (s.cards[card].controls.blocked) refuse("card", `the ${card} card is already blocked`);
      return {
        title: `Block your ${card} card?`,
        lines: [
          ["Card", cardName(card)],
          ["Effect", "Payments, withdrawals and online use stop at once"],
          ["Undo", "Unblock it here at any time"],
        ],
        confirmLabel: "Block card",
        danger: true,
      };
    }
    case "card_unblock": {
      const card = needCard(a);
      if (!s.cards[card].controls.blocked) refuse("card", `the ${card} card is not blocked`);
      return {
        title: `Unblock your ${card} card?`,
        lines: [
          ["Card", cardName(card)],
          ["Effect", "The card works again with its current controls and limits"],
        ],
        confirmLabel: "Unblock card",
      };
    }
    case "card_control": {
      const card = needCard(a);
      const control = a.control as string;
      if (!(SWITCHES as readonly string[]).includes(control)) refuse("control", "a card control is one of these", [...SWITCHES]);
      const on = parseOnOff(a.value);
      const now = s.cards[card].controls[control as (typeof SWITCHES)[number]];
      if (s.cards[card].controls.blocked) refuse("card", `the ${card} card is blocked; unblock it first`, ["card_unblock"]);
      if (now === on) refuse("value", `${lc(control)} is already ${on ? "on" : "off"} on the ${card} card`);
      return {
        title: `Turn ${on ? "on" : "off"} ${lc(control)}?`,
        lines: [
          ["Card", cardName(card)],
          ["Control", CONTROL_LABEL[control]],
          ["Change", `${now ? "On" : "Off"} → ${on ? "On" : "Off"}`],
        ],
        confirmLabel: on ? "Turn on" : "Turn off",
        danger: false,
      };
    }
    case "card_limit": {
      const card = needCard(a);
      const control = a.control as string;
      if (!(LIMITS as readonly string[]).includes(control)) refuse("control", "a card limit is one of these", [...LIMITS]);
      const value = parseRupees(a.value);
      const max = cardById(card)!.limits_max[control];
      if (value == null || value <= 0) refuse("value", "say the new daily limit in rupees", [`up to ${inr(max)}`]);
      if (value! > max) refuse("value", `the most the ${card} card allows for ${lc(control)} is ${inr(max)} a day`, [`up to ${inr(max)}`]);
      const now = s.cards[card].limits[control];
      if (now === value) refuse("value", `the limit is already ${inr(now)}`);
      return {
        title: `Change the ${lc(control)}?`,
        lines: [
          ["Card", cardName(card)],
          ["Current limit", `${inr(now)} a day`],
          ["New limit", `${inr(value!)} a day`],
          ["Maximum allowed", inr(max)],
        ],
        confirmLabel: "Change limit",
      };
    }
    case "bill_pay": {
      const id = a.target ?? "";
      const reg = registered(id) ?? refuse("target", "that biller is not registered", customer.registered_billers.map((b) => b.biller_id));
      const biller = billerById(reg.biller_id)!;
      const due = billDue(id);
      const amount = a.amount ?? due;
      if (!amount || amount <= 0) refuse("amount", `nothing is due on ${biller.name}; say an amount to pay anyway`);
      const from = fromAccount(a);
      checkFunds(from, amount);
      return {
        title: `Pay ${biller.name}?`,
        lines: [
          ["Biller", `${biller.name} (${biller.category})`],
          ["Consumer no.", reg.consumer_masked],
          ["Amount", inr(amount)],
          ...(due ? ([["Due date", fmtDate(daysFromNow(reg.due_days_from_now))]] as [string, string][]) : []),
          ["Pay from", accLabel(from)],
        ],
        confirmLabel: `Pay ${inr(amount)}`,
      };
    }
    case "transfer": {
      const b = beneficiary(a.target ?? "") ?? refuse("target", "that beneficiary is not added", customer.beneficiaries.map((x) => x.id));
      const amount = a.amount ?? refuse("amount", "how much to send?");
      if (amount <= 0) refuse("amount", "the amount must be more than zero");
      if (amount > b.limit) refuse("amount", `the limit for ${b.name} is ${inr(b.limit)} a transfer`, [`up to ${inr(b.limit)}`]);
      const from = fromAccount(a);
      checkFunds(from, amount);
      const mode = b.bank === brand.name ? "Within Anvaya" : amount >= 200000 ? "RTGS" : "IMPS";
      return {
        title: `Send ${inr(amount)} to ${b.name}?`,
        lines: [
          ["To", `${b.name} (${b.nickname})`],
          ["Bank", `${b.bank}, ${b.account_masked}`],
          ["IFSC", b.ifsc],
          ["Amount", inr(amount)],
          ["Mode", mode],
          ["From", accLabel(from)],
        ],
        confirmLabel: `Send ${inr(amount)}`,
      };
    }
    case "fd_book": {
      const amount = a.amount ?? refuse("amount", "how much to put in the deposit?", [`at least ${inr(products.fd.min_amount)}`]);
      if (amount < products.fd.min_amount) refuse("amount", `the smallest deposit is ${inr(products.fd.min_amount)}`, [`at least ${inr(products.fd.min_amount)}`]);
      const months = a.tenure_months ?? refuse("tenure_months", "for how many months?", products.fd.rates.map((r) => r.label));
      if (fdRate(months) == null) refuse("tenure_months", "deposits run from 6 to 120 months", products.fd.rates.map((r) => `${r.label}: ${r.rate}%`));
      const payout = a.payout ?? "cumulative";
      const from = fromAccount(a);
      checkFunds(from, amount);
      const q = fdQuote(amount, months, payout);
      return {
        title: `Book a fixed deposit of ${inr(amount)}?`,
        lines: [
          ["Amount", inr(amount)],
          ["Tenure", `${months} months`],
          ["Rate", `${q.rate}% a year`],
          ["Interest", payout === "cumulative" ? "Added at maturity (compounded quarterly)" : `${inr(q.payout_each)} paid ${payout}`],
          ["Matures on", fmtDate(daysFromNow(Math.round(months * 30.44)))],
          ["Maturity amount", inr(q.maturity)],
          ["From", accLabel(from)],
        ],
        confirmLabel: "Book deposit",
      };
    }
    case "emi_convert": {
      const id = a.target ?? "";
      const t = findTxn(id) ?? refuse("target", `there is no transaction ${id}`);
      const eligible = eligibleEmiTxns().map((x) => x.id);
      if (t.account !== "cc" || !t.emi_eligible) refuse("target", `${t.merchant} (${inr(t.amount)}) is not eligible for EMI`, eligible);
      if (s.emi[t.id]) refuse("target", `${t.merchant} is already on a ${s.emi[t.id].tenure_months}-month EMI`, eligible.filter((x) => !s.emi[x]));
      const tenures = products.emi.tenures.map((x) => String(x.months));
      const months = a.tenure_months ?? refuse("tenure_months", "over how many months?", tenures);
      if (!tenures.includes(String(months))) refuse("tenure_months", "card EMIs run for these months", tenures);
      const r = cardEmi(t.amount, months);
      return {
        title: `Convert ${inr(t.amount)} to EMI?`,
        lines: [
          ["Spend", `${t.merchant}, ${inr(t.amount)}`],
          ["Tenure", `${months} months at ${r.rate}% a year`],
          ["Monthly EMI", inr(r.emi)],
          ["Total interest", inr(r.total_interest)],
          ["Processing fee + GST", `${inr(r.processing_fee)} + ${inr(r.gst_on_fee)}`],
          ["Total cost", inr(r.total_cost)],
        ],
        confirmLabel: "Convert to EMI",
      };
    }
    case "offer_accept": {
      const o = offerById(a.target ?? "") ?? refuse("target", "that offer is not open for you", customer.offers.map((x) => x.id));
      if (s.offers[o.id]) refuse("target", `you have already accepted ${o.title.toLowerCase()}`);
      if (o.kind === "card") {
        const p = products.credit_cards.find((c) => c.id === o.card_id)!;
        return {
          title: `Upgrade to ${p.name}?`,
          lines: [
            ["Card", `${p.name} (${p.network})`],
            ["Replaces", cardName("credit")],
            ["Joining fee", "Waived for you"],
            ["Annual fee", inr(p.annual_fee)],
          ],
          confirmLabel: "Request upgrade",
        };
      }
      const loan = loanProduct("personal")!;
      const amount = a.amount ?? o.amount!;
      if (amount > o.amount!) refuse("amount", `the offer is up to ${inr(o.amount!)}`, [`up to ${inr(o.amount!)}`]);
      if (amount < loan.amount_min) refuse("amount", `the smallest personal loan is ${inr(loan.amount_min)}`);
      const months = a.tenure_months ?? offerTenureDefault(o.tenure_max_months!);
      if (months > o.tenure_max_months! || months < loan.tenure_min_months) refuse("tenure_months", `the tenure is ${loan.tenure_min_months} to ${o.tenure_max_months} months`);
      const m = Math.round(emi(amount, o.rate!, months));
      return {
        title: `Take the pre-approved loan of ${inr(amount)}?`,
        lines: [
          ["Amount", inr(amount)],
          ["Rate", `${o.rate}% a year`],
          ["Tenure", `${months} months`],
          ["Monthly EMI", inr(m)],
          ["Credited to", accLabel("sb")],
          ["Offer valid till", fmtDate(daysFromNow(o.valid_days_from_now ?? 0))],
        ],
        confirmLabel: `Accept ${inr(amount)}`,
      };
    }
  }
  return refuse("kind", "the bank cannot do that from here");
}

/** Credit card spends that can be turned into EMIs (and are not yet). */
export function eligibleEmiTxns() {
  const s = useBank.getState();
  return [...s.extraTxns, ...customer.transactions].filter((t) => t.account === "cc" && t.emi_eligible && t.amount >= products.emi.min_amount && !s.emi[t.id]);
}

// ─── Apply ─────────────────────────────────────────────────────────────────

function setCard(card: CardId, patch: Partial<{ controls: Partial<Record<string, boolean>>; limits: Partial<Record<string, number>> }>) {
  const s = useBank.getState();
  const cur = s.cards[card];
  useBank.setState({
    cards: {
      ...s.cards,
      [card]: {
        controls: { ...cur.controls, ...(patch.controls ?? {}) },
        limits: { ...cur.limits, ...(patch.limits ?? {}) },
      },
    },
  });
}

/** Do it (after a confirmation). Validates again: the state may have moved on. */
export function applyAction(a: ConfirmArgs): Applied {
  describeAction(a);
  const ref = reference(a.kind);
  const visitor = a.action_id.startsWith("V");
  switch (a.kind) {
    case "card_block":
    case "card_unblock": {
      const card = a.card as CardId;
      const blocked = a.kind === "card_block";
      setCard(card, { controls: { blocked } });
      if (visitor) emit("card_control_changed", { card, control: "blocked", value: blocked ? "on" : "off" });
      return { reference: ref, summary: `${card} card ${blocked ? "blocked" : "unblocked"}` };
    }
    case "card_control": {
      const card = a.card as CardId;
      const on = parseOnOff(a.value);
      setCard(card, { controls: { [a.control as string]: on } });
      if (visitor) emit("card_control_changed", { card, control: a.control as string, value: on ? "on" : "off" });
      return { reference: ref, summary: `${lc(a.control as string)} turned ${on ? "on" : "off"} on the ${card} card` };
    }
    case "card_limit": {
      const card = a.card as CardId;
      const value = parseRupees(a.value)!;
      setCard(card, { limits: { [a.control as string]: value } });
      if (visitor) emit("card_control_changed", { card, control: a.control as string, value: String(value) });
      return { reference: ref, summary: `${lc(a.control as string)} on the ${card} card set to ${inr(value)} a day` };
    }
    case "bill_pay": {
      const id = a.target!;
      const biller = billerById(id)!;
      const amount = a.amount ?? billDue(id);
      const from = fromAccount(a);
      const bal = moveBalance(from, -amount);
      const s = useBank.getState();
      if (id === "anvaya-card") {
        addTxn({ account: from, description: "BILLPAY ANVAYA CREDIT CARD 3094", merchant: "Anvaya Spark credit card bill", category: "transfers", amount, direction: "debit", mode: "Bill pay", balance_after: bal, note: `Reference ${ref}` });
        addTxn({ account: "cc", description: "PAYMENT RECEIVED THANK YOU", merchant: "Payment received from savings", category: "transfers", amount, direction: "credit", mode: "Bill pay" });
        useBank.setState({ cc: { outstanding: Math.max(0, s.cc.outstanding - amount), available: s.cc.available + amount } });
      } else {
        addTxn({ account: from, description: `BILLPAY ${biller.name.toUpperCase()}`, merchant: biller.name, category: "bills", amount, direction: "debit", mode: "Bill pay", balance_after: bal, note: `Reference ${ref}` });
      }
      useBank.setState({ billsPaid: { ...useBank.getState().billsPaid, [id]: { amount, reference: ref } } });
      return { reference: ref, summary: `${inr(amount)} paid to ${biller.name} from ${accountById(from)!.name}` };
    }
    case "transfer": {
      const b = beneficiary(a.target!)!;
      const amount = a.amount!;
      const from = fromAccount(a);
      const bal = moveBalance(from, -amount);
      const mode = b.bank === brand.name ? "Transfer" : amount >= 200000 ? "RTGS" : "IMPS";
      addTxn({ account: from, description: `${mode.toUpperCase()} DR ${b.name.toUpperCase()}`, merchant: b.name, category: "transfers", amount, direction: "debit", mode, balance_after: bal, note: `Reference ${ref}` });
      const s = useBank.getState();
      useBank.setState({ transfers: [{ reference: ref, beneficiary: b.id, amount, from }, ...s.transfers] });
      return { reference: ref, summary: `${inr(amount)} sent to ${b.name} ${mode === "Transfer" ? "within Anvaya" : `by ${mode}`}` };
    }
    case "fd_book": {
      const amount = a.amount!;
      const months = a.tenure_months!;
      const payout = a.payout ?? "cumulative";
      const from = fromAccount(a);
      const q = fdQuote(amount, months, payout);
      const bal = moveBalance(from, -amount);
      addTxn({ account: from, description: `FD BOOKED ${months}M ${q.rate}%`, merchant: `Fixed deposit, ${months} months`, category: "investments", amount, direction: "debit", mode: "Transfer", balance_after: bal, note: `Reference ${ref}` });
      const s = useBank.getState();
      const id = `fd-${s.deposits.length + 1}`;
      useBank.setState({
        deposits: [
          { id, kind: "fd", amount, rate: q.rate, tenure_months: months, opened_days_ago: 0, matures_days_from_now: Math.round(months * 30.44), payout, maturity_amount: q.maturity, reference: ref },
          ...s.deposits,
        ],
      });
      return { reference: ref, summary: `fixed deposit of ${inr(amount)} for ${months} months at ${q.rate}%, maturing at ${inr(q.maturity)}` };
    }
    case "emi_convert": {
      const t = findTxn(a.target!)!;
      const r = cardEmi(t.amount, a.tenure_months!);
      const s = useBank.getState();
      useBank.setState({ emi: { ...s.emi, [t.id]: { txn_id: t.id, tenure_months: r.months, rate: r.rate, emi: r.emi, total_cost: r.total_cost, reference: ref } } });
      return { reference: ref, summary: `${t.merchant} (${inr(t.amount)}) converted to ${r.months} EMIs of ${inr(r.emi)}` };
    }
    case "offer_accept": {
      const o = offerById(a.target!)!;
      const s = useBank.getState();
      if (o.kind === "card") {
        useBank.setState({ offers: { ...s.offers, [o.id]: { reference: ref } } });
        return { reference: ref, summary: `upgrade to ${products.credit_cards.find((c) => c.id === o.card_id)!.name} requested` };
      }
      const amount = a.amount ?? o.amount!;
      const months = a.tenure_months ?? offerTenureDefault(o.tenure_max_months!);
      const m = Math.round(emi(amount, o.rate!, months));
      const bal = moveBalance("sb", amount);
      addTxn({ account: "sb", description: "PERSONAL LOAN DISBURSAL", merchant: "Anvaya personal loan credited", category: "income", amount, direction: "credit", mode: "Transfer", balance_after: bal, note: `${months} months at ${o.rate}%, EMI ${inr(m)}. Reference ${ref}` });
      useBank.setState({ offers: { ...useBank.getState().offers, [o.id]: { reference: ref, amount, tenure_months: months, emi: m } } });
      return { reference: ref, summary: `${inr(amount)} credited to savings; ${months} EMIs of ${inr(m)}` };
    }
  }
  return refuse("kind", "the bank cannot do that from here");
}
