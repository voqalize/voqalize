/**
 * Mobile-phone catalog — browser mirror of the canonical Python catalog at
 * `demos/shopping/backend/catalog.py`.
 *
 * The voice agent reasons over the Python copy and drives the UI by pushing
 * product `id`s in `ui-command` RTVI events. This file resolves those ids for
 * rendering, so the `id` values here MUST stay in sync with the Python catalog.
 */

import type { ApplyFilters, Sort } from './actions.gen';

export interface Phone {
  id: string;
  brand: string;
  name: string;
  price: number; // USD
  category: Category;
  tagline: string;
  colors: string[];
  display: string;
  processor: string;
  ramGb: number[];
  storageGb: number[];
  rearCamera: string;
  frontCamera: string;
  batteryMah: number;
  charging: string;
  os: string;
  weightG: number;
  waterResistance: string;
  fiveG: boolean;
  rating: number; // average customer rating out of 5
  reviewCount: number;
  releaseYear: number;
  highlights: string[];
  pros: string[];
  cons: string[];
  bestFor: string;
}

export const CATALOG: Phone[] = [
  {
    id: 'galaxy-s24-ultra',
    brand: 'Samsung',
    name: 'Galaxy S24 Ultra',
    price: 1299,
    category: 'flagship',
    tagline: 'The everything phone, with a built-in S Pen and AI everywhere.',
    colors: ['Titanium Black', 'Titanium Gray', 'Titanium Violet', 'Titanium Yellow'],
    display: '6.8" QHD+ Dynamic AMOLED 2X, 120Hz, 2600 nits',
    processor: 'Snapdragon 8 Gen 3 for Galaxy',
    ramGb: [12],
    storageGb: [256, 512, 1024],
    rearCamera: '200MP main + 50MP 5x periscope + 10MP 3x tele + 12MP ultrawide',
    frontCamera: '12MP',
    batteryMah: 5000,
    charging: '45W wired, 15W wireless',
    os: 'Android 14, One UI 6.1 — 7 years of updates',
    weightG: 232,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.8,
    reviewCount: 4210,
    releaseYear: 2024,
    highlights: ['Built-in S Pen', '200MP camera', '5x optical zoom', 'Titanium frame', 'Galaxy AI'],
    pros: ['Best-in-class zoom camera', 'S Pen productivity', '7 years of OS updates', 'Huge bright display'],
    cons: ['Expensive', 'Large and heavy', 'Slower charging than rivals'],
    bestFor: 'Power users who want the biggest camera reach and stylus productivity.',
  },
  {
    id: 'iphone-15-pro-max',
    brand: 'Apple',
    name: 'iPhone 15 Pro Max',
    price: 1199,
    category: 'flagship',
    tagline: 'The biggest iPhone, with a 5x zoom and titanium build.',
    colors: ['Natural Titanium', 'Blue Titanium', 'White Titanium', 'Black Titanium'],
    display: '6.7" Super Retina XDR OLED, 120Hz ProMotion, 2000 nits',
    processor: 'Apple A17 Pro',
    ramGb: [8],
    storageGb: [256, 512, 1024],
    rearCamera: '48MP main + 12MP 5x periscope tele + 12MP ultrawide',
    frontCamera: '12MP TrueDepth',
    batteryMah: 4441,
    charging: '20W wired, 15W MagSafe, USB-C',
    os: 'iOS 17',
    weightG: 221,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.8,
    reviewCount: 3120,
    releaseYear: 2023,
    highlights: ['Titanium design', 'A17 Pro chip', '5x optical zoom', 'Action button', 'USB-C'],
    pros: ['Best big-screen iPhone', '5x periscope zoom', 'Excellent video recording', 'Long software support'],
    cons: ['Heavy', 'Expensive', 'Slow wired charging'],
    bestFor: 'iOS users who want the biggest screen and longest camera zoom.',
  },
  {
    id: 'iphone-15-pro',
    brand: 'Apple',
    name: 'iPhone 15 Pro',
    price: 999,
    category: 'flagship',
    tagline: 'Titanium, the A17 Pro chip, and a customizable Action button.',
    colors: ['Natural Titanium', 'Blue Titanium', 'White Titanium', 'Black Titanium'],
    display: '6.1" Super Retina XDR OLED, 120Hz ProMotion, 2000 nits',
    processor: 'Apple A17 Pro',
    ramGb: [8],
    storageGb: [128, 256, 512, 1024],
    rearCamera: '48MP main + 12MP 3x tele + 12MP ultrawide',
    frontCamera: '12MP TrueDepth',
    batteryMah: 3274,
    charging: '20W wired, 15W MagSafe, USB-C',
    os: 'iOS 17',
    weightG: 187,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.8,
    reviewCount: 5300,
    releaseYear: 2023,
    highlights: ['Titanium design', 'A17 Pro chip', 'Action button', 'USB-C', 'Console-grade gaming'],
    pros: ['Top-tier performance', 'Excellent video recording', 'Compact and light', 'Long software support'],
    cons: ['Only 3x zoom', 'Pricey storage upgrades', 'Slow wired charging'],
    bestFor: 'iOS users who want a compact flagship with the best video and gaming.',
  },
  {
    id: 'pixel-8-pro',
    brand: 'Google',
    name: 'Pixel 8 Pro',
    price: 999,
    category: 'flagship',
    tagline: 'The smartest camera phone, powered by Google AI.',
    colors: ['Obsidian', 'Porcelain', 'Bay'],
    display: '6.7" LTPO OLED, 120Hz, 2400 nits',
    processor: 'Google Tensor G3',
    ramGb: [12],
    storageGb: [128, 256, 512],
    rearCamera: '50MP main + 48MP 5x tele + 48MP ultrawide',
    frontCamera: '10.5MP',
    batteryMah: 5050,
    charging: '30W wired, 23W wireless',
    os: 'Android 14 — 7 years of updates',
    weightG: 213,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.6,
    reviewCount: 2150,
    releaseYear: 2023,
    highlights: ['Best-in-class AI photo editing', 'Magic Editor', 'Temperature sensor', '7 years of updates'],
    pros: ['Unmatched computational photography', 'Clean software', 'Helpful AI features', 'Long update window'],
    cons: ['Tensor runs warm', 'Average charging speed', 'Big footprint'],
    bestFor: 'Photographers who want the best point-and-shoot results and AI editing.',
  },
  {
    id: 'asus-rog-8-pro',
    brand: 'Asus',
    name: 'ROG Phone 8 Pro',
    price: 1099,
    category: 'flagship',
    tagline: 'A gaming powerhouse with a 165Hz screen and huge battery.',
    colors: ['Phantom Black'],
    display: '6.78" LTPO AMOLED, 165Hz, 2500 nits',
    processor: 'Snapdragon 8 Gen 3',
    ramGb: [16, 24],
    storageGb: [512, 1024],
    rearCamera: '50MP main + 32MP 3x tele + 13MP ultrawide',
    frontCamera: '32MP',
    batteryMah: 5500,
    charging: '65W wired, 15W wireless',
    os: 'Android 14 — 2 years of updates',
    weightG: 225,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.7,
    reviewCount: 760,
    releaseYear: 2024,
    highlights: ['165Hz gaming display', '5500mAh battery', 'AirTrigger shoulder buttons', 'Active cooling'],
    pros: ['Best-in-class gaming', 'Huge battery life', 'Ultra-smooth 165Hz display', 'Loud stereo speakers'],
    cons: ['Bulky and heavy', 'Gamer styling not for everyone', 'Shorter update window'],
    bestFor: 'Mobile gamers who want the fastest display and the biggest battery.',
  },
  {
    id: 'oneplus-12',
    brand: 'OnePlus',
    name: 'OnePlus 12',
    price: 799,
    category: 'flagship',
    tagline: 'Flagship power and absurdly fast charging for less.',
    colors: ['Silky Black', 'Flowy Emerald', 'White'],
    display: '6.82" QHD+ LTPO AMOLED, 120Hz, 4500 nits peak',
    processor: 'Snapdragon 8 Gen 3',
    ramGb: [12, 16],
    storageGb: [256, 512],
    rearCamera: '50MP main + 64MP 3x periscope + 48MP ultrawide (Hasselblad)',
    frontCamera: '32MP',
    batteryMah: 5400,
    charging: '80W wired, 50W wireless',
    os: 'Android 14, OxygenOS 14 — 4 years of updates',
    weightG: 220,
    waterResistance: 'IP65',
    fiveG: true,
    rating: 4.6,
    reviewCount: 1730,
    releaseYear: 2024,
    highlights: ['80W fast charging', '5400mAh battery', 'Hasselblad cameras', 'Brightest display'],
    pros: ['Charges 0-100 in ~26 min', 'Flagship chip at a lower price', 'Great battery life', 'Fluid display'],
    cons: ['Only IP65 water resistance', 'Shorter update window than rivals', 'No mmWave 5G in some regions'],
    bestFor: 'Buyers who want flagship speed and the fastest charging without paying flagship prices.',
  },
  {
    id: 'galaxy-s24',
    brand: 'Samsung',
    name: 'Galaxy S24',
    price: 799,
    category: 'flagship',
    tagline: 'A pocketable flagship with Galaxy AI and seven years of updates.',
    colors: ['Onyx Black', 'Marble Gray', 'Cobalt Violet', 'Amber Yellow'],
    display: '6.2" FHD+ Dynamic AMOLED 2X, 120Hz, 2600 nits',
    processor: 'Snapdragon 8 Gen 3 for Galaxy',
    ramGb: [8],
    storageGb: [128, 256],
    rearCamera: '50MP main + 10MP 3x tele + 12MP ultrawide',
    frontCamera: '12MP',
    batteryMah: 4000,
    charging: '25W wired, 15W wireless',
    os: 'Android 14, One UI 6.1 — 7 years of updates',
    weightG: 167,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.6,
    reviewCount: 1890,
    releaseYear: 2024,
    highlights: ['Compact flagship', 'Galaxy AI', '7 years of updates', '120Hz display'],
    pros: ['Pocketable size', 'Flagship performance', 'Long update window', 'Bright smooth display'],
    cons: ['Smaller battery', '25W charging is slow', 'No periscope zoom'],
    bestFor: 'People who want a small Samsung flagship with the latest AI features.',
  },
  {
    id: 'xiaomi-14',
    brand: 'Xiaomi',
    name: 'Xiaomi 14',
    price: 869,
    category: 'flagship',
    tagline: 'A compact flagship with Leica optics.',
    colors: ['Black', 'White', 'Jade Green'],
    display: '6.36" LTPO AMOLED, 120Hz, 3000 nits',
    processor: 'Snapdragon 8 Gen 3',
    ramGb: [12],
    storageGb: [256, 512],
    rearCamera: '50MP main + 50MP 3.2x tele + 50MP ultrawide (Leica)',
    frontCamera: '32MP',
    batteryMah: 4610,
    charging: '90W wired, 50W wireless',
    os: 'Android 14, HyperOS — 4 years of updates',
    weightG: 193,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.5,
    reviewCount: 690,
    releaseYear: 2024,
    highlights: ['Leica triple 50MP cameras', 'Compact body', '90W charging', 'Very bright display'],
    pros: ['Pocketable flagship', 'Versatile Leica cameras', 'Fast charging', 'Premium build'],
    cons: ['Software has bloatware', 'Limited availability in some regions', 'Smaller battery than rivals'],
    bestFor: 'People who want a small flagship with serious camera versatility.',
  },
  {
    id: 'pixel-8',
    brand: 'Google',
    name: 'Pixel 8',
    price: 699,
    category: 'flagship',
    tagline: 'Pixel camera magic and Google AI in a smaller flagship.',
    colors: ['Obsidian', 'Hazel', 'Rose'],
    display: '6.2" OLED, 120Hz, 2000 nits',
    processor: 'Google Tensor G3',
    ramGb: [8],
    storageGb: [128, 256],
    rearCamera: '50MP main + 12MP ultrawide',
    frontCamera: '10.5MP',
    batteryMah: 4575,
    charging: '27W wired, 18W wireless',
    os: 'Android 14 — 7 years of updates',
    weightG: 187,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.5,
    reviewCount: 1450,
    releaseYear: 2023,
    highlights: ['Pixel camera magic', 'Magic Editor', '7 years of updates', 'Compact'],
    pros: ['Great cameras', 'Clean software', 'Long update window', 'Compact and comfortable'],
    cons: ['No telephoto lens', 'Tensor runs warm', 'Average charging speed'],
    bestFor: 'Buyers who want Pixel cameras and AI in a smaller flagship.',
  },
  {
    id: 'nothing-phone-2',
    brand: 'Nothing',
    name: 'Nothing Phone (2)',
    price: 599,
    category: 'mid-range',
    tagline: 'Distinctive Glyph design with clean, fast software.',
    colors: ['White', 'Dark Gray'],
    display: '6.7" LTPO OLED, 120Hz, 1600 nits',
    processor: 'Snapdragon 8+ Gen 1',
    ramGb: [8, 12],
    storageGb: [128, 256, 512],
    rearCamera: '50MP main + 50MP ultrawide',
    frontCamera: '32MP',
    batteryMah: 4700,
    charging: '45W wired, 15W wireless',
    os: 'Android 13, Nothing OS 2 — 3 years of updates',
    weightG: 201,
    waterResistance: 'IP54',
    fiveG: true,
    rating: 4.4,
    reviewCount: 1120,
    releaseYear: 2023,
    highlights: ['Glyph LED interface', 'Transparent design', 'Clean near-stock software', 'Wireless charging'],
    pros: ['Unique looks', 'Snappy clean UI', 'Good main camera', 'Solid value'],
    cons: ['Only IP54', 'No telephoto lens', 'Last-gen chip'],
    bestFor: 'Buyers who want a stylish, clutter-free phone that stands out.',
  },
  {
    id: 'iphone-15',
    brand: 'Apple',
    name: 'iPhone 15',
    price: 799,
    category: 'mid-range',
    tagline: 'The Dynamic Island and a 48MP camera, now with USB-C.',
    colors: ['Blue', 'Pink', 'Yellow', 'Green', 'Black'],
    display: '6.1" Super Retina XDR OLED, 60Hz, 2000 nits',
    processor: 'Apple A16 Bionic',
    ramGb: [6],
    storageGb: [128, 256, 512],
    rearCamera: '48MP main + 12MP ultrawide',
    frontCamera: '12MP TrueDepth',
    batteryMah: 3349,
    charging: '20W wired, 15W MagSafe, USB-C',
    os: 'iOS 17',
    weightG: 171,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.7,
    reviewCount: 4080,
    releaseYear: 2023,
    highlights: ['Dynamic Island', '48MP camera', 'USB-C', 'Lightweight'],
    pros: ['Great value iPhone', 'Reliable cameras', 'Long software support', 'Compact and light'],
    cons: ['Stuck at 60Hz', 'No telephoto', 'Slow charging'],
    bestFor: 'iOS buyers who want a modern iPhone without paying Pro prices.',
  },
  {
    id: 'galaxy-a55',
    brand: 'Samsung',
    name: 'Galaxy A55',
    price: 449,
    category: 'mid-range',
    tagline: 'Premium feel and a great screen at a mid-range price.',
    colors: ['Awesome Iceblue', 'Awesome Lilac', 'Awesome Navy', 'Awesome Lemon'],
    display: '6.6" Super AMOLED, 120Hz, 1000 nits',
    processor: 'Exynos 1480',
    ramGb: [8, 12],
    storageGb: [128, 256],
    rearCamera: '50MP main + 8MP ultrawide + 5MP macro',
    frontCamera: '32MP',
    batteryMah: 5000,
    charging: '25W wired',
    os: 'Android 14, One UI 6.1 — 4 years of updates',
    weightG: 213,
    waterResistance: 'IP67',
    fiveG: true,
    rating: 4.4,
    reviewCount: 1560,
    releaseYear: 2024,
    highlights: ['Metal frame', '120Hz AMOLED', '4 years of updates', 'Big battery'],
    pros: ['Premium build for the price', 'Bright smooth display', 'Long battery life', 'Long update support'],
    cons: ['No wireless charging', 'Slower charging', 'Average low-light camera'],
    bestFor: 'Value buyers who want a premium-feeling Samsung without flagship cost.',
  },
  {
    id: 'pixel-8a',
    brand: 'Google',
    name: 'Pixel 8a',
    price: 499,
    category: 'mid-range',
    tagline: 'Flagship-grade Pixel cameras and AI on a budget.',
    colors: ['Obsidian', 'Porcelain', 'Bay', 'Aloe'],
    display: '6.1" OLED, 120Hz, 2000 nits',
    processor: 'Google Tensor G3',
    ramGb: [8],
    storageGb: [128, 256],
    rearCamera: '64MP main + 13MP ultrawide',
    frontCamera: '13MP',
    batteryMah: 4492,
    charging: '18W wired, 7.5W wireless',
    os: 'Android 14 — 7 years of updates',
    weightG: 188,
    waterResistance: 'IP67',
    fiveG: true,
    rating: 4.6,
    reviewCount: 1340,
    releaseYear: 2024,
    highlights: ['Pixel camera magic', '7 years of updates', 'Google AI features', 'Compact'],
    pros: ['Excellent cameras for the price', 'Longest update window in class', 'Clean software', 'Wireless charging'],
    cons: ['Slow charging', 'Tensor runs warm', 'Plastic back'],
    bestFor: 'Buyers who want the best camera and longest support under $500.',
  },
  {
    id: 'motorola-edge-50-pro',
    brand: 'Motorola',
    name: 'Motorola Edge 50 Pro',
    price: 599,
    category: 'mid-range',
    tagline: 'A curved display, fast charging, and a clean Moto experience.',
    colors: ['Black Beauty', 'Luxe Lavender', 'Moonlight Pearl'],
    display: '6.7" pOLED, 144Hz, 2000 nits',
    processor: 'Snapdragon 7 Gen 3',
    ramGb: [8, 12],
    storageGb: [256, 512],
    rearCamera: '50MP main + 10MP 3x tele + 13MP ultrawide',
    frontCamera: '50MP',
    batteryMah: 4500,
    charging: '125W wired, 50W wireless',
    os: 'Android 14 — 3 years of updates',
    weightG: 186,
    waterResistance: 'IP68',
    fiveG: true,
    rating: 4.3,
    reviewCount: 540,
    releaseYear: 2024,
    highlights: ['125W ultra-fast charging', '144Hz curved display', 'Telephoto camera', 'Near-stock software'],
    pros: ['Fastest charging in class', 'Has a real telephoto lens', 'Clean light software', 'Bright display'],
    cons: ['Shorter update window', 'Mid-tier chip', 'Curved screen not for everyone'],
    bestFor: 'Buyers who want fast charging and a telephoto camera in the mid-range.',
  },
  {
    id: 'nothing-phone-2a',
    brand: 'Nothing',
    name: 'Nothing Phone (2a)',
    price: 349,
    category: 'budget',
    tagline: 'Standout Glyph design and clean software on a budget.',
    colors: ['Black', 'Milk', 'Blue'],
    display: '6.7" AMOLED, 120Hz, 1300 nits',
    processor: 'MediaTek Dimensity 7200 Pro',
    ramGb: [8, 12],
    storageGb: [128, 256],
    rearCamera: '50MP main + 50MP ultrawide',
    frontCamera: '32MP',
    batteryMah: 5000,
    charging: '45W wired',
    os: 'Android 14, Nothing OS 2.5 — 3 years of updates',
    weightG: 190,
    waterResistance: 'IP54',
    fiveG: true,
    rating: 4.4,
    reviewCount: 980,
    releaseYear: 2024,
    highlights: ['Glyph interface', 'Big 5000mAh battery', 'Clean fast software', 'Bright AMOLED'],
    pros: ['Standout design', 'Great value', 'Clean fast UI', 'Good main camera'],
    cons: ['Only IP54', 'No wireless charging', 'No telephoto lens'],
    bestFor: 'Budget buyers who want flair and clean software for under $400.',
  },
  {
    id: 'redmi-note-13-pro',
    brand: 'Xiaomi',
    name: 'Redmi Note 13 Pro',
    price: 349,
    category: 'budget',
    tagline: 'A 200MP camera and 67W charging at a budget price.',
    colors: ['Midnight Black', 'Ocean Teal', 'Aurora Purple'],
    display: '6.67" AMOLED, 120Hz, 1300 nits',
    processor: 'Snapdragon 7s Gen 2',
    ramGb: [8, 12],
    storageGb: [128, 256],
    rearCamera: '200MP main + 8MP ultrawide + 2MP macro',
    frontCamera: '16MP',
    batteryMah: 5100,
    charging: '67W wired',
    os: 'Android 13, HyperOS — 3 years of updates',
    weightG: 187,
    waterResistance: 'IP54',
    fiveG: true,
    rating: 4.3,
    reviewCount: 2240,
    releaseYear: 2023,
    highlights: ['200MP camera', '67W fast charging', 'Big 5100mAh battery', '120Hz AMOLED'],
    pros: ['High-res 200MP camera', 'Fast charging', 'Great value', 'Long battery life'],
    cons: ['Only IP54', 'Some bloatware', 'Plastic frame'],
    bestFor: 'Value buyers who want a high-megapixel camera and fast charging for cheap.',
  },
];

const BY_ID: Record<string, Phone> = Object.fromEntries(CATALOG.map((p) => [p.id, p]));

export function getPhone(id: string): Phone | undefined {
  return BY_ID[id];
}

export const BRANDS: string[] = [...new Set(CATALOG.map((p) => p.brand))].sort();

export const CATEGORIES: Category[] = ['flagship', 'mid-range', 'budget'];

/**
 * The two vocabularies the expert and the shop share. Read off the generated
 * actions rather than written down twice — the Python is where they are set.
 */
export type Category = NonNullable<ApplyFilters['category']>;
export type SortKey = Sort['sort_by'];

export const SORT_LABELS: Record<SortKey, string> = {
  price_low: 'Price: low to high',
  price_high: 'Price: high to low',
  rating: 'Top rated',
  newest: 'Newest',
};

export interface CatalogFilters {
  brand?: string;
  maxPrice?: number;
  minPrice?: number;
  category?: string;
  query?: string;
}

export function filterCatalog(f: CatalogFilters): Phone[] {
  const q = (f.query ?? '').toLowerCase().trim();
  return CATALOG.filter((p) => {
    if (f.brand && p.brand.toLowerCase() !== f.brand.toLowerCase()) return false;
    if (f.category && p.category.toLowerCase() !== f.category.toLowerCase()) return false;
    if (f.maxPrice != null && p.price > f.maxPrice) return false;
    if (f.minPrice != null && p.price < f.minPrice) return false;
    if (q) {
      const hay = [p.name, p.brand, p.tagline, p.bestFor, ...p.highlights].join(' ').toLowerCase();
      if (!hay.includes(q) && !q.split(' ').some((w) => hay.includes(w))) return false;
    }
    return true;
  });
}

/** Order a list of phones by a sort key (stable, returns a new array). */
export function sortPhones(phones: Phone[], by: SortKey | undefined): Phone[] {
  const list = [...phones];
  switch (by) {
    case 'price_low':
      return list.sort((a, b) => a.price - b.price);
    case 'price_high':
      return list.sort((a, b) => b.price - a.price);
    case 'rating':
      return list.sort((a, b) => b.rating - a.rating || b.reviewCount - a.reviewCount);
    case 'newest':
      return list.sort((a, b) => b.releaseYear - a.releaseYear);
    default:
      return list;
  }
}

/** Stable color swatch for rendering — derived from product id, not real hex. */
export function phoneAccent(id: string): string {
  const accents: Record<string, string> = {
    'galaxy-s24-ultra': '#2b2b2b',
    'iphone-15-pro-max': '#8a8d8f',
    'iphone-15-pro': '#8a8d8f',
    'pixel-8-pro': '#3b6fb5',
    'asus-rog-8-pro': '#111827',
    'oneplus-12': '#0a5c3e',
    'galaxy-s24': '#3b3b3b',
    'xiaomi-14': '#1f7a3d',
    'pixel-8': '#7d7f6a',
    'nothing-phone-2': '#444444',
    'iphone-15': '#f4a8c0',
    'galaxy-a55': '#9a8cc4',
    'pixel-8a': '#4a7c59',
    'motorola-edge-50-pro': '#6d5b97',
    'nothing-phone-2a': '#4b5563',
    'redmi-note-13-pro': '#0f6e63',
  };
  return accents[id] ?? '#4a5568';
}
