/**
 * The facts the page shows, from the same files the brain reads:
 * data/product.json (brand, modules, plans, pricing rules, customers, tax),
 * data/tax_example.json (the worked example) and content/site.json (copy, the
 * lead card's vocabulary, the sales calendar). Nothing here is written twice.
 */
import productJson from "../../../data/product.json";
import taxExampleJson from "../../../data/tax_example.json";
import siteJson from "../../../content/site.json";

export type Product = typeof productJson;
export type Module = Product["modules"][number];
export type Plan = Product["plans"][number];
export type Customer = Product["customers"][number];
export type PlanId = "starter" | "growth" | "scale";

export const PRODUCT = productJson;
export const BRAND = productJson.brand;
export const MODULES: Module[] = productJson.modules;
export const PLANS: Plan[] = productJson.plans;
export const RULES = productJson.pricing_rules;
export const CUSTOMERS: Customer[] = productJson.customers;
export const TAX = productJson.tax;
export const TAX_EXAMPLE = taxExampleJson;
export const SITE = siteJson;
export const CALENDAR = siteJson.calendar;
export const LEAD = siteJson.lead;

export const PLAN_ORDER: PlanId[] = PLANS.map((p) => p.id as PlanId);
export const moduleById = (id: string) => MODULES.find((m) => m.id === id);
export const planById = (id: string) => PLANS.find((p) => p.id === id);
export const painById = (id: string) => LEAD.pains.find((p) => p.id === id);
export const toolLabel = (id: string) => LEAD.current_tools.find((t) => t.id === id)?.label ?? id;
export const moduleDetail = (id: string) => (SITE.module_detail as Record<string, { headline: string; body: string }>)[id];

/** The modules a plan adds beyond the core six (what the calculator's checkboxes are). */
export const EXTRA_MODULES = MODULES.filter((m) => m.min_plan !== "starter");
