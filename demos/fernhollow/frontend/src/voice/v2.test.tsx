/**
 * CONTRACT.md v2, the UI half: numbered choices on product cards, and Emily
 * filling checkout field by field. Both rendered for real and driven through
 * the same controller methods the voice adapter calls.
 */
import { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { ProductGrid } from "../components/ProductCard";
import { products, productsInCategory } from "../data/catalog";
import { CheckoutPage } from "../pages/Checkout";
import { useCart } from "../state/cart";
import { placeOrder, useCheckout } from "../state/checkout";
import { useOrders } from "../state/orders";
import { bindRouter, emily, useEmily } from "./controller";
import { setEventSender } from "./events";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

let sent: [string, Record<string, unknown>][] = [];
beforeAll(() => {
  Element.prototype.scrollIntoView = function () {};
  setEventSender((event, payload) => sent.push([event, payload as Record<string, unknown>]));
});
afterEach(() => {
  sent = [];
  document.body.innerHTML = "";
});

function Router() {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => bindRouter((to) => navigate(to), () => location.pathname), [navigate, location.pathname]);
  return null;
}

function mount(path: string, el: React.ReactElement) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  root.render(
    <MemoryRouter initialEntries={[path]}>
      <Router />
      <Routes>
        <Route path="*" element={el} />
      </Routes>
    </MemoryRouter>,
  );
  return root;
}

describe("show_choices", () => {
  it("numbers the cards 1..n, and a click on one is the shopper's choice", async () => {
    const sofas = productsInCategory("sofas").slice(0, 4);
    const root = mount("/category/sofas", <ProductGrid products={sofas} />);
    await sleep(100);
    await emily.show_choices({ product_ids: [sofas[2].id, sofas[0].id], label: "Which one?" });
    await sleep(50);
    const badged = [...document.querySelectorAll(".card.is-choice")].map((c) => c.getAttribute("data-spot"));
    expect(badged.sort()).toEqual([`product:${sofas[0].id}`, `product:${sofas[2].id}`].sort());
    const badge = document.querySelector(`[data-spot="product:${sofas[2].id}"] .choice-badge`);
    expect(badge?.textContent).toBe("1");
    expect(document.querySelector(`[data-spot="product:${sofas[0].id}"] .choice-badge`)?.textContent).toBe("2");
    expect(document.querySelector(`[data-spot="product:${sofas[1].id}"] .choice-badge`)).toBeNull();

    (document.querySelector(`[data-spot="product:${sofas[0].id}"] .card-title a`) as HTMLElement).click();
    await sleep(50);
    expect(sent).toContainEqual(["choice_made", { product_id: sofas[0].id, by: "visitor" }]);
    expect(useEmily.getState().choices).toBeNull();
    expect(document.querySelectorAll(".choice-badge").length).toBe(0);
    root.unmount();
  });

  it("clear_choices removes the badges", async () => {
    const two = products.slice(0, 2);
    const root = mount("/shop", <ProductGrid products={two} />);
    await sleep(50);
    await emily.show_choices({ product_ids: two.map((p) => p.id), label: "" });
    await sleep(30);
    expect(document.querySelectorAll(".choice-badge").length).toBe(2);
    emily.clear_choices();
    await sleep(30);
    expect(document.querySelectorAll(".choice-badge").length).toBe(0);
    root.unmount();
  });
});

describe("checkout_fill", () => {
  it("rings and sets each field, moving to its step, and reports field names only", async () => {
    const p = productsInCategory("desks")[0];
    useCart.setState({ lines: [{ product_id: p.id, variant_id: p.variants[0].id, qty: 1 }] });
    useCheckout.getState().reset();
    const root = mount("/checkout", <CheckoutPage />);
    await sleep(100);

    await emily.checkout_fill({ field: "email", value: "sam.rivera@example.com" });
    await sleep(50);
    expect((document.querySelector('input[name="email"]') as HTMLInputElement).value).toBe("sam.rivera@example.com");
    expect(useCheckout.getState().by.email).toBe("emily");
    expect(document.querySelector('[data-spot="field:email"] .emily-tag')).not.toBeNull();

    await emily.checkout_fill({ field: "first_name", value: "Sam" });
    await sleep(50);
    expect(useCheckout.getState().step).toBe("shipping");
    expect((document.querySelector('input[name="first_name"]') as HTMLInputElement).value).toBe("Sam");

    await emily.checkout_fill({ field: "card_number", value: "4111" });
    expect(document.querySelector('input[name="card_number"]')).toBeNull();

    expect(sent).toContainEqual(["checkout_changed", { field: "email", by: "emily" }]);
    expect(sent).toContainEqual(["checkout_step_reached", { step: "shipping", by: "emily" }]);
    // Never a value on the wire.
    expect(JSON.stringify(sent)).not.toContain("sam.rivera");
    root.unmount();
  });

  it("asks before placing the order, on the Place order button", async () => {
    const p = productsInCategory("desks")[0];
    useCart.setState({ lines: [{ product_id: p.id, variant_id: p.variants[0].id, qty: 1 }] });
    const root = mount("/checkout", <CheckoutPage />);
    await sleep(100);
    await emily.confirm_place_order({ total: p.variants[0].price, label: "" });
    await sleep(50);
    expect(useCheckout.getState().step).toBe("review");
    expect(document.querySelector('[role="alertdialog"]')?.textContent).toContain("Place the order");
    root.unmount();
  });
});

describe("order numbers: the page and the brain agree", () => {
  const fill = () => {
    const p = productsInCategory("desks")[0];
    useCart.setState({ lines: [{ product_id: p.id, variant_id: p.variants[0].id, qty: 1 }] });
    useCheckout.getState().reset();
    for (const [f, v] of [
      ["email", "ada@example.com"],
      ["first_name", "Ada"],
      ["last_name", "Lane"],
      ["address1", "1 Fern Way"],
      ["city", "Hollow"],
      ["postcode", "12345"],
    ] as const)
      useCheckout.getState().set(f, v);
    return p;
  };
  const known = () => sent.filter(([e]) => e === "orders_known").map(([, p]) => (p.orders as { number: string }[]).map((o) => o.number));

  it("order_placed uses exactly the brain's number", async () => {
    useOrders.setState({ orders: [] });
    fill();
    await emily.order_placed({ order_number: "FH-77777", total: 1 });
    expect(JSON.parse(sessionStorage.getItem("fh-order") ?? "{}").number).toBe("FH-77777");
    expect(JSON.parse(localStorage.getItem("fernhollow-orders") ?? "[]").map((o: { number: string }) => o.number)).toContain("FH-77777");
    expect(known().at(-1)).toContain("FH-77777");
  });

  it("an order placed by hand reports the page's number at once", () => {
    useOrders.setState({ orders: [] });
    fill();
    const order = placeOrder();
    expect(order).not.toBeNull();
    expect(known().at(-1)?.[0]).toBe(order!.number);
  });

  it("a yes on the confirm prompt carries the number it placed", async () => {
    useOrders.setState({ orders: [] });
    const p = fill();
    const root = mount("/checkout", <CheckoutPage />);
    await sleep(100);
    await emily.confirm_place_order({ total: p.variants[0].price, label: "" });
    await sleep(50);
    (document.querySelector('[role="alertdialog"] .btn-primary') as HTMLElement).click();
    await sleep(50);
    const result = sent.find(([e]) => e === "confirm_result")?.[1];
    const stored = JSON.parse(localStorage.getItem("fernhollow-orders") ?? "[]").at(-1);
    expect(result).toEqual({ confirmed: true, order_number: stored.number, by: "visitor" });
    expect(known().at(-1)?.[0]).toBe(stored.number);
    root.unmount();
  });
});

describe("a yes on Add puts each line in once", () => {
  const line = () => ({ product_id: products[0].id, variant_id: products[0].variants[0].id, qty: 1 });

  it("Emily's prompt, on a call: the brain adds, and the page sends only the yes", async () => {
    useCart.setState({ lines: [] });
    await emily.confirm_add({ lines: [line()], label: "Add it" }, "emily");
    emily.answerConfirm(true);
    expect(useCart.getState().lines).toEqual([]);
    expect(sent.filter(([e]) => e === "confirm_result").map(([, p]) => p.confirmed)).toEqual([true]);
    // The brain's answer is the cart, once.
    emily.cart_updated({ lines: [line()], total: products[0].variants[0].price, saved: 0 });
    expect(useCart.getState().lines.map((l) => l.qty)).toEqual([1]);
  });

  it("the page's own prompt (Add on a whole room) adds on the page", async () => {
    useCart.setState({ lines: [] });
    await emily.confirm_add({ lines: [line()], label: "" }, "visitor");
    emily.answerConfirm(true);
    expect(useCart.getState().lines.map((l) => l.qty)).toEqual([1]);
  });
});
