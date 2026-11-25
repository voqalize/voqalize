/**
 * The shop's moves (scene.json): the site, the listing, the product page,
 * Find my size, the wishlist, the bag and checkout. Each performer rings what
 * it touches before anything changes (the whole group scrolled into view
 * first, X1), refuses with what the page offers instead of guessing, writes
 * the same store a click writes, and returns one short line.
 */
import type { MoveContext, Performers } from "@voqalize/stage";
import { chartFor } from "../components/SizeChart";
import { useShopUi } from "../components/shopUi";
import {
  FILTER_KEYS,
  type Filters,
  type Product,
  canonical,
  cleanFilters,
  department,
  getProduct,
  index,
  inr,
  isDept,
  loadCatalog,
  routeFor,
  search,
  sizeLabel,
  stockOf,
  summarise,
  typeLabel,
  logicalPath,
} from "../data/catalog";
import { bagTotals, lineKey, POLICY } from "../data/shop";
import { useStore } from "../state/store";
import { DEPT_CHOICES, SORTS } from "../pages/Shop";
import { currentPath, goTo, part, thing, waitFor } from "./host";
import type { ShopMoves, Spec } from "./performers";

const phone = () => window.matchMedia("(max-width: 899px)").matches;

/** X1: show the target's whole group (`c.scrollTo` is `showWhole`, see host.ts), then ring it. */
async function ringScroll(c: MoveContext, el: Element | null | undefined, label: string): Promise<void> {
  if (!el) return;
  await c.scrollTo(el);
  await c.ring(el, label);
}

/** Product ids on screen now, for a refusal's options. */
const onScreen = () => [...new Set([...document.querySelectorAll("[data-stage-thing^='product:']")].map((e) => e.getAttribute("data-stage-thing")!.slice(8)))].slice(0, 12);

async function productOr(c: MoveContext, id: string): Promise<Product> {
  await loadCatalog();
  const p = getProduct(String(id).replace(/\D/g, ""));
  return p ?? c.refuse("product_id", `there is no product ${id}`, onScreen());
}

const inStockSizes = (p: Product) => p.sizes.filter(([, n]) => n > 0).map(([l]) => l);

/** The size the agent named, as the product spells it, in stock; refused otherwise. */
function sizeOr(c: MoveContext, p: Product, said: string | undefined, arg = "size"): string {
  if (p.scale === "one") {
    if (stockOf(p, p.sizes[0][0]) <= 0) c.refuse("product_id", `${p.name} is out of stock`);
    return p.sizes[0][0];
  }
  if (!said) return c.refuse(arg, `${p.name} needs a size`, inStockSizes(p));
  const label = sizeLabel(p, said) ?? c.refuse(arg, `${p.name} has no size ${said}`, inStockSizes(p));
  if (stockOf(p, label) <= 0) c.refuse(arg, `size ${label} of ${p.name} is out of stock`, inStockSizes(p));
  return label;
}

const PAGES = /^\/(shop(\/[a-z]+(\/[a-z0-9-]+)?)?|p\/\d+|compare|wishlist|bag|checkout|orders|returns|gifts|about)?$/;

function normalPath(path: string): string {
  let p = path.trim();
  if (!p.startsWith("/")) p = `/${p}`;
  p = p.replace(/^\/demos\/fashio/, "") || "/";
  const [bare, query = ""] = p.split("?");
  const clean = (bare.replace(/\/$/, "") || "/").toLowerCase();
  return query ? `${clean}?${query}` : clean;
}

/** One ringable control per filter value that changes, in sidebar order. */
function changedControls(before: Filters, after: Filters): { key: keyof Filters; part: string; label: string; value?: string }[] {
  const out: { key: keyof Filters; part: string; label: string; value?: string }[] = [];
  const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  const flips = (key: keyof Filters, prefix: string, label: (v: string) => string) => {
    const a = new Set((before[key] as string[] | undefined) ?? []);
    const b = new Set((after[key] as string[] | undefined) ?? []);
    for (const v of [...new Set([...a, ...b])].filter((x) => a.has(x) !== b.has(x))) out.push({ key, part: `${prefix}:${v}`, label: label(v), value: v });
  };
  for (const key of FILTER_KEYS) {
    if (same(before[key], after[key])) continue;
    switch (key) {
      case "dept":
        out.push({ key, part: `dept:${after.dept ?? "all"}`, label: DEPT_CHOICES.find((d) => d.id === (after.dept ?? "all"))?.label ?? "All" });
        break;
      case "types":
        flips(key, "type", typeLabel);
        break;
      case "brands":
        flips(key, "brand", (v) => v);
        break;
      case "colours":
        flips(key, "colour", (v) => v);
        break;
      case "sizes":
        flips(key, "size", (v) => `Size ${v}`);
        break;
      case "price_min":
      case "price_max":
        if (!out.some((o) => o.part === "price"))
          out.push({ key, part: "price", label: after.price_max != null && after.price_min != null ? `${inr(after.price_min)} to ${inr(after.price_max)}` : after.price_max != null ? `Under ${inr(after.price_max)}` : after.price_min != null ? `${inr(after.price_min)} and up` : "Any price" });
        break;
      case "discount_min":
        out.push({ key, part: "discount", label: after.discount_min ? `${after.discount_min}% off or more` : "Any discount" });
        break;
      case "usage":
        flips(key, "usage", (v) => v);
        break;
      case "seasons":
        flips(key, "season", (v) => v);
        break;
      case "sort":
        out.push({ key, part: "sort", label: SORTS.find((s) => s.id === (after.sort ?? "popular"))?.label ?? "Popular" });
        break;
    }
  }
  return out;
}

const USAGES = ["Casual", "Ethnic", "Formal", "Sports", "Party", "Smart Casual", "Travel"];
const SEASONS = ["Summer", "Fall", "Winter", "Spring"];

export function shopPerformers(): Pick<Performers<Spec>, ShopMoves> {
  return {
    "site.go": async ({ path }, c) => {
      await loadCatalog();
      const raw = normalPath(path);
      // /p/?id=<id> (the URL) and /p/<id> (the logical path) are the same page.
      const asked = logicalPath(raw.split("?")[0], raw.split("?")[1] ?? "");
      const p = asked.startsWith("/p/") ? asked : raw;
      const bare = p.split("?")[0];
      if (bare === "/kiosk") c.refuse("path", "the kiosk is the in-store screen, not a page to send a shopper to", ["/", "/shop", "/gifts", "/orders"]);
      if (!PAGES.test(bare)) c.refuse("path", `the store has no page ${path}`, ["/", "/shop", "/shop/women", "/wishlist", "/bag", "/checkout", "/orders", "/returns", "/gifts", "/about"]);
      const product = /^\/p\/(\d+)$/.exec(bare)?.[1];
      const prod = product ? getProduct(product) : undefined;
      if (product && !prod) c.refuse("path", `there is no product ${product}`, onScreen().map((id) => `/p/${id}`));
      const shop = /^\/shop(?:\/([a-z]+))?(?:\/([a-z0-9-]+))?$/.exec(bare);
      if (shop?.[1] && !isDept(shop[1])) c.refuse("path", `there is no department ${shop[1]}`, (index()?.departments ?? []).map((d) => `/shop/${d.id}`));
      if (shop?.[2] && !index()?.types[shop[2]]) c.refuse("path", `there is no category ${shop[2]}`, department(shop[1])?.sections.flatMap((s) => s.types).map((t) => `/shop/${shop[1]}/${t}`));
      if (bare === "/compare") {
        const ids = (new URLSearchParams(p.split("?")[1] ?? "").get("ids") ?? "").split(",").filter(Boolean);
        if (ids.some((id) => !getProduct(id))) c.refuse("path", `no product ${ids.find((id) => !getProduct(id))}`);
        if (ids.length) useStore.getState().setCompare(ids.map(Number));
      }
      // Ring what leads there: the product's card, the header link or icon, or the logo.
      const via = (product && thing(`product:${product}`)) || thing(`nav:${bare}`) || (shop?.[1] && thing(`nav:/shop/${shop[1]}`)) || thing("nav:/");
      if (via && currentPath() !== bare) {
        await c.scrollTo(via);
        await c.ring(via, prod ? prod.name : bare === "/" ? "Home" : bare.slice(1).replace(/\//g, " / "));
      }
      // A shop route opened by the agent is the same as by hand: its department and category, nothing else.
      if (shop) useStore.getState().setFilters({ dept: shop[1] as Filters["dept"], types: shop[2] ? [shop[2]] : undefined, query: new URLSearchParams(p.split("?")[1] ?? "").get("q") ?? undefined });
      await goTo(p);
      window.scrollTo({ top: 0, behavior: "smooth" });
      if (prod) return `on ${prod.name}, ${inr(prod.price)}`;
      if (shop) {
        const f = useStore.getState().filters;
        return `on the listing: ${summarise(f)}, ${search(f).length} products`;
      }
      return `on ${bare === "/" ? "the home page" : bare.slice(1)}`;
    },

    "shop.filter": async (args, c) => {
      await loadCatalog();
      const ix = index()!;
      const fix = (kind: "brands" | "colours" | "types", xs: string[] | undefined) =>
        xs?.map((x) => {
          const hit = canonical(kind, String(x));
          if (hit) return hit;
          const options = kind === "types" ? Object.keys(ix.types) : kind === "colours" ? Object.keys(ix.colours) : ix.brands.filter((b) => b.toLowerCase().includes(String(x).toLowerCase().slice(0, 3))).slice(0, 12);
          return c.refuse(kind, `the catalogue has no ${kind === "types" ? "category" : kind.slice(0, -1)} ${x}`, options);
        });
      const pick = (arg: string, xs: string[] | undefined, allowed: string[]) =>
        xs?.map((x) => allowed.find((a) => a.toLowerCase() === String(x).toLowerCase()) ?? c.refuse(arg, `${x} is not an option`, allowed));
      const sizes = args.sizes?.map((s) => {
        const raw = String(s).trim().toUpperCase();
        const label = /^\d+$/.test(raw) && Number(raw) < 20 ? `UK ${raw}` : raw.replace(/^UK\s*/, "UK ").replace(/^ONE ?SIZE$/, "Onesize");
        const known = ix.products.some((p) => p.sizes.some(([l]) => l.toUpperCase() === label.toUpperCase()));
        return known ? ix.products.flatMap((p) => p.sizes.map(([l]) => l)).find((l) => l.toUpperCase() === label.toUpperCase())! : c.refuse("sizes", `no product comes in size ${s}`, ["XS", "S", "M", "L", "XL", "XXL", "28", "30", "32", "34", "UK 6", "UK 7", "UK 8", "UK 9"]);
      });
      if (args.price_min != null && args.price_max != null && args.price_min > args.price_max) c.refuse("price_min", "the lowest price is above the highest");
      const want = cleanFilters({
        dept: args.dept as Filters["dept"],
        types: fix("types", args.types ?? undefined),
        brands: fix("brands", args.brands ?? undefined),
        colours: fix("colours", args.colours ?? undefined),
        sizes,
        price_min: args.price_min ?? undefined,
        price_max: args.price_max ?? undefined,
        discount_min: args.discount_min ?? undefined,
        usage: pick("usage", args.usage ?? undefined, USAGES),
        seasons: pick("seasons", args.seasons ?? undefined, SEASONS),
        query: args.query?.trim() || undefined,
        sort: args.sort as Filters["sort"],
      });

      const before = useStore.getState().filters;
      const target = routeFor(want);
      if (!currentPath().startsWith("/shop")) {
        // The route's own part first, so the listing opens on it; each control is still rung there.
        useStore.getState().setFilters({ dept: want.dept, types: want.dept && want.types?.length === 1 ? want.types : undefined, query: want.query });
        await goTo(target);
      }
      const sheet = phone();
      if (sheet) {
        useStore.getState().setFiltersOpen(true);
        await waitFor(() => part("dept:all"), 800);
      }
      const controls = changedControls(before, want);
      if (controls.some((x) => x.key === "brands")) useShopUi.setState({ allBrands: true, brandQuery: "" });
      for (const control of controls) {
        const el = await waitFor(() => part(control.part), 900);
        await ringScroll(c, el, control.label);
        const now = useStore.getState().filters;
        if (control.value !== undefined) {
          const xs = ((now[control.key] as string[] | undefined) ?? []).slice();
          const at = xs.indexOf(control.value);
          if (at >= 0) xs.splice(at, 1);
          else xs.push(control.value);
          useStore.getState().patchFilters({ [control.key]: xs });
        } else if (control.part === "price") {
          useStore.getState().patchFilters({ price_min: want.price_min, price_max: want.price_max });
        } else if (control.key === "dept") {
          useStore.getState().patchFilters({ dept: want.dept });
        } else {
          useStore.getState().patchFilters({ [control.key]: want[control.key] });
        }
      }
      useStore.getState().setFilters(want);
      useShopUi.setState({ allBrands: false });
      if (sheet) useStore.getState().setFiltersOpen(false);
      const results = search(want);
      c.done(
        results.length
          ? `${results.length} products: ${summarise(want)}; first ${results
              .slice(0, 3)
              .map((p) => `${p.id} ${p.name} ${inr(p.price)}`)
              .join("; ")}`
          : `no products match ${summarise(want)}`,
      );
      c.after(async () => {
        const head = await waitFor(() => thing("results"), 600);
        await ringScroll(c, head, `${results.length} products`);
      });
      return null;
    },

    "shop.show": async ({ product_id }, c) => {
      const p = await productOr(c, product_id);
      const card = thing(`product:${p.id}`);
      if (!card) return c.refuse("product_id", `${p.id} is not on screen`, onScreen());
      await c.scrollTo(card);
      await c.ring(card, `${p.brand}, ${inr(p.price)}`);
      return `${p.name}, ${inr(p.price)}${p.mrp > p.price ? ` (MRP ${inr(p.mrp)})` : ""}; in stock: ${inStockSizes(p).join(", ") || "none"}`;
    },

    "compare.show": async ({ ids }, c) => {
      await loadCatalog();
      const unique = [...new Set(ids.map((x) => String(x).replace(/\D/g, "")))];
      if (unique.length < 2 || unique.length > 4) c.refuse("ids", "compare two to four products", onScreen());
      const products = unique.map((id) => getProduct(id) ?? c.refuse("ids", `there is no product ${id}`, onScreen()));
      const cards = products.map((p) => thing(`product:${p.id}`)).filter((x): x is Element => !!x);
      if (cards.length) {
        await c.scrollTo(cards[0]);
        await c.ring(cards, { label: "Compare", separate: true });
      }
      useStore.getState().setCompare(products.map((p) => p.id));
      await goTo(`/compare?ids=${products.map((p) => p.id).join(",")}`);
      c.done(`comparing ${products.map((p) => `${p.name} at ${inr(p.price)}`).join(" and ")}`);
      c.after(async () => {
        const rows = await waitFor(() => {
          const r = [...document.querySelectorAll("[data-stage-part^='row:']")];
          return r.length ? r : null;
        }, 900);
        for (const row of (rows ?? []).filter((r) => /Price|Discount|Sizes|Fit|Fabric/.test(r.getAttribute("data-stage-part") ?? "")).slice(0, 5)) {
          await c.scrollTo(row);
          await c.ring(row, { label: row.getAttribute("data-stage-label") ?? undefined, beatMs: 350 });
        }
      });
      return null;
    },

    "product.size": async ({ product_id, size }, c) => {
      const p = await productOr(c, product_id);
      if (p.scale === "one") c.refuse("size", `${p.name} comes in one size`);
      const label = sizeOr(c, p, size);
      await goTo(`/p/${p.id}`);
      const btn = await waitFor(() => part(`size:${label}`), 1200);
      await ringScroll(c, btn, `Size ${label}`);
      useStore.getState().pickSize(p.id, label);
      const n = stockOf(p, label);
      return `size ${label} of ${p.name} selected${n <= 3 ? `; only ${n} left` : ""}`;
    },

    "size_chart.open": async ({ product_id, size }, c) => {
      const p = await productOr(c, product_id);
      const chart = chartFor(p) ?? c.refuse("product_id", p.scale === "one" ? `${p.name} comes in one size` : `there is no size chart for ${typeLabel(p.type)}`);
      await goTo(`/p/${p.id}`);
      const link = await waitFor(() => part("size-chart"), 1200);
      await ringScroll(c, link, "Size chart");
      const row = size ? sizeLabel(p, size) ?? chart.rows.find((r) => r[0].toUpperCase() === size.trim().toUpperCase())?.[0] : undefined;
      if (size && !row) c.refuse("size", `the chart has no row ${size}`, chart.rows.map((r) => r[0]));
      useStore.getState().openSizeChart(p.id, row);
      const values = row ? chart.rows.find((r) => r[0] === row) : undefined;
      c.done(values ? `${chart.title} open; ${row}: ${chart.columns.slice(1).map((col, i) => `${col} ${values[i + 1]}`).join(", ")} (${chart.unit})` : `${chart.title} open`);
      // The next ring replaces the Size chart link's, which would otherwise stay
      // up over the drawer: the row asked about, or the whole table.
      c.after(async () => {
        const el = await waitFor(() => part(row ? `chart-row:${row}` : "size-chart:table"), 800);
        await ringScroll(c, el, row ?? chart.title);
      });
      return null;
    },

    "fit.fill": async ({ product_id, height_cm, usual_size, fit }, c) => {
      const p = await productOr(c, product_id);
      if (p.scale === "one") c.refuse("product_id", `${p.name} comes in one size`);
      if (height_cm != null && (height_cm < 90 || height_cm > 230)) c.refuse("height_cm", "a height in centimetres, 90 to 230");
      await goTo(`/p/${p.id}`);
      useStore.getState().openSizeChart(null);
      useStore.getState().setFit(p.id, { open: true });
      const panel = await waitFor(() => thing("fit"), 1200);
      await ringScroll(c, panel, "Find my size");
      const steps: [string, Parameters<ReturnType<typeof useStore.getState>["setFit"]>[1], string][] = [];
      if (height_cm != null) steps.push(["fit:height", { height_cm }, `${height_cm} cm`]);
      if (usual_size) steps.push(["fit:usual", { usual_size: usual_size.trim().toUpperCase().replace(/^UK\s*/, "UK ") }, `Usually ${usual_size}`]);
      if (fit) steps.push(["fit:fit", { fit }, fit[0].toUpperCase() + fit.slice(1)]);
      for (const [name, patch, label] of steps) {
        await ringScroll(c, await waitFor(() => part(name), 600), label);
        useStore.getState().setFit(p.id, { ...patch, pick: undefined });
      }
      const now = useStore.getState().fit[p.id];
      return `Find my size for ${p.name}: height ${now?.height_cm ?? "not given"}, usual size ${now?.usual_size ?? "not given"}, fit ${now?.fit ?? "not given"}`;
    },

    "fit.recommend": async ({ product_id, size, reason, wanted }, c) => {
      const p = await productOr(c, product_id);
      if (p.scale === "one") c.refuse("product_id", `${p.name} comes in one size`);
      const label = sizeOr(c, p, size);
      const want = wanted ? sizeLabel(p, wanted) : undefined;
      await goTo(`/p/${p.id}`);
      useStore.getState().openSizeChart(null);
      useStore.getState().setFit(p.id, { open: true, pick: { size: label, reason: reason.trim(), wanted: want && want !== label ? want : undefined } });
      const card = await waitFor(() => part("fit:pick"), 1200);
      await ringScroll(c, card, `Size ${label}`);
      const btn = part(`size:${label}`);
      if (btn) await ringScroll(c, btn, `Size ${label}`);
      useStore.getState().pickSize(p.id, label);
      return `recommended and selected size ${label} of ${p.name}${want && want !== label ? ` (${want} is out of stock)` : ""}`;
    },

    "wishlist.set": async ({ product_id, on }, c) => {
      const p = await productOr(c, product_id);
      const want = on ?? true;
      const heart = part(`wishlist:${p.id}`) ?? thing("nav:/wishlist");
      await ringScroll(c, heart, want ? "Save to wishlist" : "Remove from wishlist");
      useStore.getState().toggleWishlist(p.id, want);
      const n = useStore.getState().wishlist.length;
      return want ? `${p.name} saved; ${n} on the wishlist` : `${p.name} taken off the wishlist; ${n} left`;
    },

    "bag.add": async ({ product_id, size, qty }, c) => {
      const p = await productOr(c, product_id);
      const label = sizeOr(c, p, p.scale === "one" ? undefined : size);
      const n = Math.max(1, Math.min(5, Math.round(Number(qty) || 1)));
      const stock = stockOf(p, label);
      if (n > stock) c.refuse("qty", `only ${stock} left in size ${label}`, Array.from({ length: Math.min(stock, 5) }, (_, i) => String(i + 1)));
      if (currentPath() === `/p/${p.id}`) {
        if (p.scale !== "one") {
          await ringScroll(c, part(`size:${label}`), `Size ${label}`);
          useStore.getState().pickSize(p.id, label);
        }
        await ringScroll(c, part("add-to-bag"), "Add to bag");
      } else {
        const card = thing(`product:${p.id}`);
        if (card) await ringScroll(c, card, `${p.brand}, size ${label}`);
      }
      useStore.getState().addToBag(p.id, label, n);
      const t = bagTotals(useStore.getState().bag);
      c.done(`added ${n} × ${p.name}, size ${label}; the bag has ${t.count} ${t.count === 1 ? "item" : "items"}, total ${inr(t.total)}${t.delivery ? `, ${inr(POLICY.delivery.free_over - t.subtotal)} short of free delivery` : ""}`);
      c.after(async () => {
        const icon = thing("nav:/bag");
        if (icon) await c.ring(icon, `${t.count} in bag`);
      });
      return null;
    },

    "bag.gift": async ({ product_id, size, on, note }, c) => {
      const p = await productOr(c, product_id);
      const bag = useStore.getState().bag;
      const label = p.scale === "one" ? p.sizes[0][0] : sizeLabel(p, size) ?? size;
      const line = bag.find((l) => lineKey(l.product_id, l.size) === lineKey(p.id, label));
      if (!line) c.refuse("product_id", `${p.name} in size ${size} is not in the bag`, bag.map((l) => `${l.product_id}|${l.size}`));
      const text = note?.trim();
      if (text && text.length > POLICY.gift_wrap.note_max) c.refuse("note", `a note is at most ${POLICY.gift_wrap.note_max} characters; this one is ${text.length}`);
      const want = on ?? true;
      await goTo("/bag");
      const box = await waitFor(() => part(`gift:${p.id}|${label}`), 1200);
      await ringScroll(c, box, want ? `Gift wrap, ${inr(POLICY.gift_wrap.price)}` : "No gift wrap");
      useStore.getState().setGift(p.id, label, want, want ? text ?? undefined : "");
      const t = bagTotals(useStore.getState().bag);
      return want ? `${p.name} gift wrapped${text ? ` with the note "${text}"` : ""}; total now ${inr(t.total)}` : `gift wrap taken off ${p.name}; total now ${inr(t.total)}`;
    },

    "checkout.focus": async ({ field }, c) => {
      await loadCatalog();
      if (!useStore.getState().bag.length) c.refuse("field", "the bag is empty, so there is no checkout yet", ["/bag", "/shop"]);
      await goTo("/checkout");
      const box = await waitFor(() => part(`checkout:${field}`), 1200);
      const label = { contact: "Your name and mobile", address: "Delivery address", payment: "Payment", place: "Place order" }[field];
      await ringScroll(c, box, label);
      if (field !== "place") box?.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
      const t = bagTotals(useStore.getState().bag);
      return field === "place" ? `Place order is ready for the shopper to press; total ${inr(t.total)}` : `${label} shown; the shopper fills it in`;
    },
  };
}
