/**
 * The service pages' moves (gifts, orders, returns, kiosk), one performer
 * each. Each goes to its page when it needs to, shows the whole group and
 * rings what it touches before anything changes (X1), refuses with what the
 * page offers instead of guessing, writes the same store a click writes, and
 * returns one short line. None of them presses a final button: Cancel order
 * and Submit return are the shopper's.
 */
import type { MoveContext, Performers } from "@voqalize/stage";
import { type Product, getProduct, index, inr, typeLabel } from "../data/catalog";
import { MATERIALS, PATTERNS } from "../data/gifts";
import { POLICY, RETURN_REASONS, STORE, canCancel, fmtDate, reasonLabel, returnCheck, statusLabel } from "../data/shop";
import { useGifts } from "../state/gifts";
import { KIOSK_GENDERS, type KioskSearch, isEmptySearch, kioskSearch, kioskSummary, useKiosk } from "../state/kiosk";
import { findOrder, ordersNow, returnedSet, useOrdersUi, useReturnForm } from "../state/orders";
import { useStore } from "../state/store";
import { currentPath, el, goTo, part, thing, waitFor } from "./host";
import type { ServiceMoves, Spec } from "./performers";

/** X1: show the target's whole group (`c.scrollTo` is `showWhole`, see host.ts), then ring it. */
async function ringScroll(c: MoveContext, target: Element | null | undefined, label: string): Promise<void> {
  if (!target) return;
  await c.scrollTo(target);
  await c.ring(target, label);
}

const within = (root: Element | null, value: string) => root?.querySelector(`[data-value="${CSS.escape(value)}"]`) ?? root;

/** Match `value` to one of `options`, ignoring case; refuse with the options. */
function oneOf(c: MoveContext, arg: string, value: string, options: string[]): string {
  const hit = options.find((o) => o.toLowerCase() === value.trim().toLowerCase());
  return hit ?? c.refuse(arg, `${value} is not an option`, options);
}

function productOr(c: MoveContext, arg: string, id: string | number): Product {
  const p = getProduct(id);
  return p ?? c.refuse(arg, `there is no product ${id}`);
}

function orderOr(c: MoveContext, id: string) {
  const o = findOrder(id);
  return o ?? c.refuse("order_id", `there is no order ${id}`, ordersNow().map((x) => x.id));
}

const catalogColours = () => Object.keys(index()?.colours ?? {}).filter((x) => x !== "NA");

const onKiosk = (c: MoveContext, arg: string) => {
  if (currentPath() !== "/kiosk") c.refuse(arg, "this move works on the in-store kiosk only (/kiosk)");
};

export function servicePerformers(): Pick<Performers<Spec>, ServiceMoves> {
  return {
    // ─── Gifts ────────────────────────────────────────────────────────────
    "gifts.brief": async (args, c) => {
      const patch: Parameters<ReturnType<typeof useGifts.getState>["setBrief"]>[0] = {};
      const steps: { field: string; value: string; label: string }[] = [];
      if (args.recipient) {
        patch.recipient = oneOf(c, "recipient", args.recipient, STORE.gifts.recipients);
        steps.push({ field: "recipient", value: patch.recipient, label: `For ${patch.recipient}` });
      }
      if (args.occasion) {
        patch.occasion = oneOf(c, "occasion", args.occasion, STORE.gifts.occasions);
        steps.push({ field: "occasion", value: patch.occasion, label: patch.occasion });
      }
      let noLimit: boolean | null = null;
      if (args.budget_max != null) {
        if (args.budget_max < 0) c.refuse("budget_max", "a budget in rupees, or 0 for no limit");
        if (args.budget_max === 0) noLimit = true;
        else patch.budget_max = Math.round(args.budget_max);
        steps.push({ field: "budget", value: String(patch.budget_max ?? 0), label: patch.budget_max ? `Under ${inr(patch.budget_max)}` : "No limit" });
      }
      if (args.size) {
        patch.size = args.size.trim().toUpperCase().replace(/^UK\s*/, "UK ");
        steps.push({ field: "size", value: patch.size, label: `Size ${patch.size}` });
      }
      if (args.colours?.length) {
        patch.colours = args.colours.map((x) => oneOf(c, "colours", x, catalogColours()));
        steps.push({ field: "colours", value: patch.colours[0], label: patch.colours.join(", ") });
      }
      if (args.patterns?.length) {
        patch.patterns = args.patterns.map((x) => oneOf(c, "patterns", x, PATTERNS));
        steps.push({ field: "patterns", value: patch.patterns[0], label: patch.patterns.join(", ") });
      }
      if (args.material) {
        patch.material = oneOf(c, "material", args.material, MATERIALS);
        steps.push({ field: "material", value: patch.material, label: patch.material });
      }
      if (!steps.length) c.refuse("recipient", "say at least one part of the brief", STORE.gifts.recipients);

      await goTo("/gifts");
      for (const s of steps) {
        const field = await waitFor(() => part(`gifts:${s.field}`), 900);
        await c.scrollTo(field ?? document.body);
        if (s.field === "budget" && noLimit) useGifts.getState().setNoLimit(true);
        else useGifts.getState().setBrief({ [s.field === "budget" ? "budget_max" : s.field]: patch[(s.field === "budget" ? "budget_max" : s.field) as keyof typeof patch] });
        await new Promise((r) => requestAnimationFrame(r));
        await c.ring(within(field, s.value) ?? field!, s.label);
      }
      const b = useGifts.getState().brief;
      const told = [b.recipient && `for ${b.recipient}`, b.occasion, b.budget_max ? `under ${inr(b.budget_max)}` : useGifts.getState().noLimit ? "no budget limit" : null, b.size && `size ${b.size}`, b.colours?.join("/"), b.patterns?.join("/"), b.material].filter(Boolean);
      return `brief: ${told.join(", ")}`;
    },

    "gifts.show": async ({ ids, reasons }, c) => {
      const uniq = [...new Set(ids.map((x) => String(x).trim()))];
      if (!uniq.length || uniq.length > 6) c.refuse("ids", "show one to six products");
      const products = uniq.map((id) => productOr(c, "ids", id));
      await goTo("/gifts");
      useGifts.getState().show(
        products.map((p) => p.id),
        products.map((p, i) => (reasons?.[ids.indexOf(String(p.id))] ?? reasons?.[i] ?? "").trim() || typeLabel(p.type)),
      );
      c.done(`${products.length} gift ideas shown: ${products.map((p) => `${p.id} ${p.brand} ${typeLabel(p.type).toLowerCase()} ${inr(p.price)}`).join("; ")}`);
      c.after(async () => {
        const head = await waitFor(() => thing("gifts:results"), 800);
        if (head) await c.scrollTo(head);
        for (const p of products) {
          const card = await waitFor(() => thing(`product:${p.id}`), 600);
          if (!card) continue;
          await c.scrollTo(card);
          await c.ring(card, { label: `${p.brand} · ${inr(p.price)}`, beatMs: 450 });
        }
      });
      return null;
    },

    // ─── Orders ───────────────────────────────────────────────────────────
    "orders.open": async ({ order_id }, c) => {
      const o = orderOr(c, order_id);
      if (currentPath() !== "/orders") await goTo(`/orders?order=${o.id}`);
      const card = await waitFor(() => thing(`order:${o.id}`), 900);
      await ringScroll(c, card, `Order ${o.id}`);
      useOrdersUi.getState().select(o.id);
      const when = o.status === "delivered" && o.delivered ? `delivered ${fmtDate(o.delivered)}` : o.eta && o.status !== "cancelled" ? `expected ${fmtDate(o.eta)}` : "";
      const last = o.events[o.events.length - 1];
      c.done(`${o.id}: ${statusLabel(o.status)}${when ? `, ${when}` : ""}; latest: ${last?.text ?? "none"}${o.courier ? `; ${o.courier.name}, AWB ${o.courier.awb}` : ""}; cancel ${canCancel(o) ? "possible" : "not possible"}`);
      c.after(async () => {
        const detail = await waitFor(() => thing(`order-detail:${o.id}`), 800);
        if (!detail) return;
        const actions = thing(`order-actions:${o.id}`);
        await c.scrollTo(detail);
        await c.ring(actions ?? detail, statusLabel(o.status));
      });
      return null;
    },

    "orders.cancel_open": async ({ order_id }, c) => {
      const o = orderOr(c, order_id);
      if (!canCancel(o)) {
        const open = ordersNow().filter((x) => canCancel(x)).map((x) => x.id);
        c.refuse(
          "order_id",
          o.status === "cancelled"
            ? `${o.id} is already cancelled`
            : `${o.id} is ${statusLabel(o.status).toLowerCase()}: an order can be cancelled only before dispatch (${POLICY.cancel_statuses.map(statusLabel).join(" or ")})`,
          open,
        );
      }
      if (currentPath() !== "/orders" || useOrdersUi.getState().selected !== o.id) {
        if (currentPath() !== "/orders") await goTo(`/orders?order=${o.id}`);
        useOrdersUi.getState().select(o.id);
      }
      const opener = await waitFor(() => el(`[data-cancel-open="${CSS.escape(o.id)}"]`), 900);
      await ringScroll(c, opener, "Cancel order");
      useOrdersUi.getState().openCancel(o.id);
      c.done(`cancel dialog open for ${o.id}; the shopper presses Cancel order to confirm`);
      c.after(async () => {
        const confirm = await waitFor(() => part(`cancel:${o.id}`), 800);
        if (confirm) await c.ring(confirm, "Press to cancel");
      });
      return null;
    },

    // ─── Returns ──────────────────────────────────────────────────────────
    "returns.fill": async ({ order_id, product_id, reason, unused, tags }, c) => {
      const o = orderOr(c, order_id);
      const returned = returnedSet(useStore.getState().returns);
      const eligibleOrders = () => ordersNow().filter((x) => returnCheck(x, null, returned).ok).map((x) => x.id);
      const whole = returnCheck(o, null, returned);
      if (!whole.ok) c.refuse("order_id", whole.why ?? "this order cannot be returned", eligibleOrders());
      const okItems = o.items.filter((i) => returnCheck(o, i.product_id, returned).ok).map((i) => String(i.product_id));
      let pid: number | null = null;
      if (product_id != null && product_id !== "") {
        const item = o.items.find((i) => String(i.product_id) === String(product_id).trim());
        if (!item) c.refuse("product_id", `${o.id} has no product ${product_id}`, okItems);
        const check = returnCheck(o, item!.product_id, returned);
        if (!check.ok) c.refuse("product_id", check.why ?? "this item cannot be returned", okItems);
        pid = item!.product_id;
      }
      if (reason && !RETURN_REASONS.some((r) => r.id === reason)) c.refuse("reason", `${reason} is not a reason`, RETURN_REASONS.map((r) => r.id));

      const f = useReturnForm.getState();
      if (currentPath() !== "/returns" || f.order_id !== o.id || f.reference) {
        await goTo(`/returns?order=${o.id}`);
        if (useReturnForm.getState().reference) useReturnForm.getState().start(o.id);
      }
      await waitFor(() => part("return:submit"), 1200);
      const set = useReturnForm.getState().patch;
      if (pid != null) {
        await ringScroll(c, part(`return:item:${pid}`), getProduct(pid)?.name ?? `Product ${pid}`);
        set({ product_id: pid });
      }
      if (reason) {
        await ringScroll(c, part(`return:reason:${reason}`), reasonLabel(reason));
        set({ reason });
      }
      if (unused != null) {
        await ringScroll(c, part("return:unused"), unused ? "Unused, unwashed, unworn" : "Not confirmed");
        set({ unused });
      }
      if (tags != null) {
        await ringScroll(c, part("return:tags"), tags ? "Tags intact" : "Not confirmed");
        set({ tags });
      }
      const now = useReturnForm.getState();
      const missing = [now.product_id == null && "the item", !now.reason && "the reason", !now.unused && "the unused tick", !now.tags && "the tags tick"].filter(Boolean);
      const left = whole.daysLeft === 0 ? "last day of the window" : `${whole.daysLeft} days left in the window`;
      c.done(
        `${o.id} return form: item ${now.product_id ?? "not chosen"}, reason ${now.reason ? reasonLabel(now.reason) : "not chosen"}, unused ${now.unused ? "yes" : "no"}, tags ${now.tags ? "yes" : "no"}; ${left}; ${missing.length ? `still needs ${missing.join(", ")}` : "ready: the shopper presses Submit return"}`,
      );
      if (!missing.length) {
        c.after(async () => {
          await ringScroll(c, part("return:submit"), "Press Submit return");
        });
      }
      return null;
    },

    // ─── Kiosk ────────────────────────────────────────────────────────────
    "kiosk.search": async (args, c) => {
      onKiosk(c, "query");
      const types = Object.keys(index()?.types ?? {});
      const s: KioskSearch = {};
      if (args.query?.trim()) s.query = args.query.trim();
      if (args.genders?.length) s.genders = args.genders.map((g) => oneOf(c, "genders", g, KIOSK_GENDERS));
      if (args.types?.length) s.types = args.types.map((t) => oneOf(c, "types", t, types));
      if (args.colours?.length) s.colours = args.colours.map((x) => oneOf(c, "colours", x, catalogColours()));
      if (args.sizes?.length) s.sizes = args.sizes.map((x) => x.trim());
      if (args.price_max != null) {
        if (args.price_max <= 0) c.refuse("price_max", "a price in rupees");
        s.price_max = Math.round(args.price_max);
      }
      if (args.usage?.length) s.usage = args.usage;
      if (isEmptySearch(s)) c.refuse("query", "say what to look for");
      const bar = part("kiosk:search");
      await ringScroll(c, bar, args.query?.trim() || kioskSummary(s));
      useKiosk.getState().setSearch(s);
      window.scrollTo({ top: 0, behavior: "smooth" });
      const found = kioskSearch(s);
      c.done(found.length ? `${found.length} results for ${kioskSummary(s)}; first: ${found.slice(0, 3).map((p) => `${p.id} ${p.name} ${inr(p.price)}`).join("; ")}` : `nothing matches ${kioskSummary(s)}`);
      return null;
    },

    "kiosk.show": async ({ product_id }, c) => {
      onKiosk(c, "product_id");
      const p = productOr(c, "product_id", product_id);
      const card = thing(`product:${p.id}`);
      if (card) await ringScroll(c, card, p.name);
      useKiosk.getState().openProduct(p.id);
      window.scrollTo({ top: 0, behavior: "smooth" });
      const sizes = p.sizes.filter(([, n]) => n > 0).map(([l]) => l);
      c.done(`${p.name}, ${inr(p.price)}${p.mrp > p.price ? ` (MRP ${inr(p.mrp)})` : ""}; in stock: ${sizes.join(", ") || "none"}; QR shown`);
      return null;
    },

    "kiosk.qr": async ({ product_id }, c) => {
      onKiosk(c, "product_id");
      const k = useKiosk.getState();
      if (product_id != null && product_id !== "") {
        const p = productOr(c, "product_id", product_id);
        if (k.open !== p.id) k.openProduct(p.id);
        useKiosk.getState().showQr({ kind: "product", id: p.id });
        const qr = await waitFor(() => part("kiosk:qr"), 800);
        await ringScroll(c, qr, "Scan with your phone");
        return `QR for ${p.name} shown; it opens the product page on the shopper's phone`;
      }
      if (!k.shortlist.length) c.refuse("product_id", "the shortlist is empty; name a product", k.open != null ? [String(k.open)] : []);
      k.showQr({ kind: "shortlist" });
      const qr = await waitFor(() => part("kiosk:qr"), 800);
      await ringScroll(c, qr, "Scan to take your shortlist");
      return `shortlist QR shown for ${k.shortlist.length} products`;
    },

    "kiosk.shortlist": async ({ product_id, on }, c) => {
      onKiosk(c, "product_id");
      const p = productOr(c, "product_id", product_id);
      const want = on ?? true;
      const btn = part(`kiosk:shortlist:${p.id}`) ?? thing(`product:${p.id}`);
      if (btn) await ringScroll(c, btn, want ? "Add to shortlist" : "Remove");
      useKiosk.getState().toggleShortlist(p.id, want);
      const n = useKiosk.getState().shortlist.length;
      return want ? `${p.name} on the shortlist; ${n} in all` : `${p.name} taken off; ${n} left`;
    },

    "kiosk.assist": async (_args, c) => {
      onKiosk(c, "assist");
      await ringScroll(c, part("kiosk:assist"), "Call a floor assistant");
      useKiosk.getState().callAssistant(true);
      return `floor assistant called; the banner says one is on the way`;
    },
  };
}
