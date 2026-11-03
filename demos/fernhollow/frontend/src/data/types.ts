export type RoomId = "living" | "dining" | "bedroom" | "home-office" | "bath" | "kitchen" | "decor";

export interface ProductOption {
  name: string;
  values: string[];
}

export interface Variant {
  id: string;
  title: string;
  options: Record<string, string>;
  price: number;
  compareAtPrice: number | null;
}

export interface Product {
  id: string;
  title: string;
  category: string;
  categorySlug: string;
  room: RoomId;
  collections: string[];
  intro: string;
  highlights: string[];
  priceMin: number;
  priceMax: number;
  onSale: boolean;
  options: ProductOption[];
  variants: Variant[];
  /** `images[].file` from the catalog: `<id>/<n>`. */
  images: string[];
  /** The words the brain's brief and filters use for this product
   *  (backend/data/attributes.json), so the listing can filter by them too. */
  taste: Taste;
}

export interface Taste {
  materials: string[];
  colours: string[];
  styles: string[];
}

export interface Category {
  name: string;
  slug: string;
  room: RoomId;
  count: number;
}

export interface CatalogData {
  store: string;
  rooms: RoomId[];
  categories: Category[];
  products: Product[];
}
