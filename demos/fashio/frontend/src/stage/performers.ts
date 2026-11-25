/**
 * Every move in scene.json, one performer each, registered once for the
 * page's life. The shop's moves (site, listing, product, fit, wishlist, bag,
 * checkout) are in `performers.shop.ts`; the service pages' (gifts, orders,
 * returns, kiosk) in `performers.service.ts`. Each performer rings what it
 * touches before anything changes, refuses with what the page offers instead
 * of guessing, writes the same store a click does, and returns one short line.
 */
import type { Performers } from "@voqalize/stage";
import { moves } from "./host";
import { scene } from "./scene.gen";
import { shopPerformers } from "./performers.shop";
import { servicePerformers } from "./performers.service";

export type Spec = typeof scene.spec;
export type ShopMoves = "site.go" | "shop.filter" | "shop.show" | "compare.show" | "product.size" | "size_chart.open" | "fit.fill" | "fit.recommend" | "wishlist.set" | "bag.add" | "bag.gift" | "checkout.focus";
export type ServiceMoves = Exclude<keyof Performers<Spec>, ShopMoves>;

const all: Performers<Spec> = { ...shopPerformers(), ...servicePerformers() };
scene.registerAll(moves, all);
