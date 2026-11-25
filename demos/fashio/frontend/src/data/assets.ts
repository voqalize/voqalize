/**
 * Where the store's files come from: the public bucket
 * `gs://voqalize-fashio-assets`. Images load straight from it (an `<img>`
 * needs no CORS). The catalogue JSON is fetched, and the bucket's CORS allows
 * GET only from voqalize.com and dev.voqalize.com, so on any other host
 * (localhost, a tunnel, local.voqalize.com) it goes through the Vite proxy at
 * `/demos/fashio/fashio-assets` (vite.config.ts). This file is the one place
 * that picks.
 */
export const BUCKET = "https://storage.googleapis.com/voqalize-fashio-assets";

const CORS_HOSTS = new Set(["voqalize.com", "www.voqalize.com", "dev.voqalize.com"]);

/** The base for fetched JSON on this host. */
export function dataBase(host: string = window.location.hostname): string {
  return CORS_HOSTS.has(host) ? BUCKET : `${import.meta.env.BASE_URL}fashio-assets`;
}

export const CATALOG_VERSION = "v1";
export const indexUrl = () => `${dataBase()}/catalog/${CATALOG_VERSION}/index.json`;
export const detailUrl = (id: number | string) => `${dataBase()}/catalog/${CATALOG_VERSION}/p/${id}.json`;

/** A product image: 400 px wide for cards, 1080 for the product page. */
export const imgUrl = (id: number | string, w: 400 | 1080 = 400) => `${BUCKET}/img/${id}/w${w}.webp`;
export const placeholderUrl = (w: 400 | 1080 = 400) => `${BUCKET}/img/placeholder/w${w}.webp`;
