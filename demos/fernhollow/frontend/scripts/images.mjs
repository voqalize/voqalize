/**
 * Product photography, served from our own origin.
 *
 * The catalog references each image by its original CDN `src`. The site's CSP
 * allows only self-hosted images, and a store should not depend on someone
 * else's CDN at runtime anyway, so this script makes two WebP renditions of
 * every image once, at build time:
 *
 *   public/img/<file>-400.webp    grid thumbnails
 *   public/img/<file>-1000.webp   product page (never upscaled past the original)
 *
 * `<file>` is the catalog's `images[].file` (`<product-id>/<n>`). Existing
 * outputs are skipped, so a second run is instant. Originals are read from a
 * local copy when one exists (`FERNHOLLOW_IMAGE_SOURCE`, default
 * `~/Desktop/voqalize/havenly-data/images/<sourceHandle>/<n>.png`) and fetched
 * from `src` otherwise.
 *
 * It also copies the gallery favicon from `demos/public`, because this app has
 * its own `public/` for the images.
 */
import { copyFile, mkdir, readFile, readdir, rm, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const out = join(app, "public", "img");
const catalogPath = join(app, "..", "data", "catalog.json");
const localSource =
  process.env.FERNHOLLOW_IMAGE_SOURCE ?? join(homedir(), "Desktop", "voqalize", "havenly-data", "images");
const SIZES = [400, 1000];
const CONCURRENCY = 8;

async function copyFavicon() {
  const gallery = join(app, "..", "..", "public");
  for (const name of await readdir(gallery)) {
    const target = join(app, "public", name);
    if (!existsSync(target)) await copyFile(join(gallery, name), target);
  }
}

async function original(product, image) {
  const n = image.file.split("/").pop();
  const local = join(localSource, product.sourceHandle ?? product.id, `${n}.png`);
  if (existsSync(local)) return readFile(local);
  // No local copy (a CI build): download, with a few retries for a flaky CDN.
  let last;
  for (let attempt = 1; attempt <= 4; attempt++) {
    try {
      const res = await fetch(image.src, { signal: AbortSignal.timeout(30_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return Buffer.from(await res.arrayBuffer());
    } catch (err) {
      last = err;
      await new Promise((r) => setTimeout(r, 500 * attempt ** 2));
    }
  }
  throw new Error(`${image.src}: ${last instanceof Error ? last.message : last}`);
}

async function render(product, image) {
  const targets = SIZES.map((w) => ({ w, path: join(out, `${image.file}-${w}.webp`) }));
  const missing = targets.filter((t) => !existsSync(t.path));
  if (missing.length === 0) return false;
  const input = await original(product, image);
  await mkdir(dirname(missing[0].path), { recursive: true });
  for (const t of missing) {
    await sharp(input)
      .resize({ width: t.w, withoutEnlargement: true })
      .webp({ quality: t.w <= 400 ? 74 : 80, effort: 4 })
      .toFile(t.path);
  }
  return true;
}

async function main() {
  await mkdir(out, { recursive: true });
  await copyFavicon();
  const catalog = JSON.parse(await readFile(catalogPath, "utf8"));
  const jobs = catalog.products.flatMap((p) => p.images.map((img) => [p, img]));
  let done = 0;
  let made = 0;
  let failed = 0;
  const started = Date.now();
  const queue = [...jobs];
  async function worker() {
    for (;;) {
      const job = queue.shift();
      if (!job) return;
      try {
        if (await render(...job)) made += 1;
      } catch (err) {
        failed += 1;
        console.error(`images: ${job[1].file}: ${err instanceof Error ? err.message : err}`);
      }
      done += 1;
      if (made && done % 100 === 0) console.log(`images: ${done}/${jobs.length}`);
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  // Renditions of products no longer in the catalog (a renamed id) go.
  const ids = new Set(catalog.products.map((p) => p.id));
  for (const dir of await readdir(out)) if (!ids.has(dir)) await rm(join(out, dir), { recursive: true, force: true });
  const secs = ((Date.now() - started) / 1000).toFixed(1);
  console.log(`images: ${jobs.length} images, ${made} rendered, ${failed} failed, ${secs}s`);
  if (failed) process.exitCode = 1;
}

await stat(catalogPath);
await main();
