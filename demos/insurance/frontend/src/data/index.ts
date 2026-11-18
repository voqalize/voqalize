/**
 * The demo's data, read at build from demos/insurance/data and content — the
 * same files the brain reads. Files other than products.json and claim_form.json
 * are globbed, so a checkout without them still builds and the page falls back.
 */
import productsJson from "../../../data/products.json";
import claimFormJson from "../../../data/claim_form.json";
import type {
  ClaimForm,
  ClaimsGuide,
  Customer,
  Network,
  PolicyDoc,
  Product,
  ProductContent,
  ProductId,
  ProductsFile,
} from "./types";

export * from "./types";

const productsFile = productsJson as unknown as ProductsFile;
export const RATING_YEAR = productsFile.rating_year;
export const cities = productsFile.cities;
export const ncbByYears = productsFile.ncb.by_years;
export const products: Product[] = productsFile.products;
export const PRODUCT_IDS = products.map((p) => p.id) as ProductId[];
export const productById = (id: string): Product | undefined => products.find((p) => p.id === id);
export const isProductId = (id: string | undefined | null): id is ProductId => !!id && PRODUCT_IDS.includes(id as ProductId);

export const claimForm = claimFormJson as unknown as ClaimForm;

const one = <T>(glob: Record<string, unknown>): T | null => {
  const mod = Object.values(glob)[0] as { default?: T } | T | undefined;
  if (!mod) return null;
  return ((mod as { default?: T }).default ?? mod) as T;
};

const customerGlob = import.meta.glob("../../../data/customer.json", { eager: true });
const networkGlob = import.meta.glob("../../../data/network.json", { eager: true });
const policyGlob = import.meta.glob("../../../data/policies/*.json", { eager: true });
const contentGlob = import.meta.glob("../../../content/products.json", { eager: true });
const guideGlob = import.meta.glob("../../../content/claims_guide.json", { eager: true });

/** The signed-in customer, with a stand-in until data/customer.json exists. */
export const customer: Customer = one<Customer>(customerGlob) ?? {
  id: "CHH-C-000000",
  name: "Rohan Kulkarni",
  first_name: "Rohan",
  dob: "1988-03-14",
  phone: "98220 14521",
  email: "rohan.kulkarni@example.com",
  address: "Baner, Pune 411045",
  city: "pune",
  family: [],
  bank_on_file: {
    account_holder: "Rohan Kulkarni",
    bank_name: "Meridian Bank",
    account_number: "50100417234821",
    masked: "•••• 4821",
    ifsc: "MRDN0000417",
  },
  policies: [],
  past_claims: [],
};

export const network: Network = one<Network>(networkGlob) ?? { garages: [], hospitals: [] };

const allPolicies: PolicyDoc[] = Object.values(policyGlob).map((m) => ((m as { default?: PolicyDoc }).default ?? m) as PolicyDoc);
/** The customer's policies, in customer.json's order (any other file after). */
export const policies: PolicyDoc[] = [
  ...customer.policies.map((id) => allPolicies.find((p) => p.id === id)).filter((p): p is PolicyDoc => !!p),
  ...allPolicies.filter((p) => !customer.policies.includes(p.id)),
];
export const policyById = (id: string | undefined | null): PolicyDoc | undefined => policies.find((p) => p.id === id);

const contentFile = one<unknown>(contentGlob);
export const claimsGuide: ClaimsGuide | null = one<ClaimsGuide>(guideGlob);

/** Product page copy from content/products.json, whatever its outer shape. */
export function productContent(id: ProductId): ProductContent | null {
  const c = contentFile as Record<string, unknown> | unknown[] | null;
  if (!c) return null;
  if (Array.isArray(c)) return (c.find((x) => (x as { id?: string })?.id === id) as ProductContent) ?? null;
  const inner = (c.products ?? c) as Record<string, unknown> | unknown[];
  if (Array.isArray(inner)) return (inner.find((x) => (x as { id?: string })?.id === id) as ProductContent) ?? null;
  return (inner[id] as ProductContent) ?? null;
}

/** Field ids → field, for one product. */
export const fieldOf = (product: Product, id: string) => product.fields.find((f) => f.id === id);
export const addonOf = (product: Product, id: string) => product.addons.find((a) => a.id === id);

/** A select's options, `options_from: cities` resolved. */
export function quoteOptions(f: Product["fields"][number]): { value: string; label: string }[] {
  if (f.options) return f.options;
  if (f.options_from === "cities") return cities.map(({ value, label }) => ({ value, label }));
  return [];
}

export const PRODUCT_SHORT: Record<ProductId, string> = {
  car: "Car",
  bike: "Two-wheeler",
  health: "Health",
  term: "Term life",
  home: "Home",
  travel: "Travel",
};
