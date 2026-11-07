// Bundle the component page and serve it under a strict Content Security
// Policy: no inline script or style, no eval, nothing from another origin.
// Prints the URL; Playwright's global setup starts it.
//
// Split as a page's bundler would split it, so each lazy element is its own
// file (`devices.js`, `coach.js`, `captions-feature.js`, `mic-pill.js`) and a
// test can see which ones a page asked for.

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const here = fileURLToPath(new URL(".", import.meta.url));

export const CSP = [
  "default-src 'none'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self'",
  "media-src 'self'",
  "connect-src 'self'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };

export async function serve(port = 0) {
  const bundle = await build({
    // The lazy elements are named entries too, so each keeps its own name
    // rather than an anonymous chunk's.
    entryPoints: [
      join(here, "page.ts"),
      ...["devices.ts", "coach.ts", "captions-feature.ts", "mic-pill.ts"].map((f) => join(here, "../../src/elements", f)),
    ],
    bundle: true,
    format: "esm",
    target: "es2022",
    write: false,
    splitting: true,
    outdir: join(here, "out"),
    entryNames: "[name]",
    chunkNames: "chunk-[hash]",
    conditions: ["production"],
    define: { "process.env.NODE_ENV": '"production"' },
    logLevel: "silent",
  });
  /** Each output by its file name: `page.js`, the lazy elements, the shared chunks. */
  const scripts = new Map(bundle.outputFiles.map((f) => [f.path.split("/").at(-1), f.contents]));
  const server = createServer(async (req, res) => {
    const path = new URL(req.url ?? "/", "http://x").pathname;
    const name = path === "/" ? "index.html" : path.slice(1);
    let body;
    try {
      body = scripts.get(name) ?? (await readFile(join(here, name.replace(/\.\.+/g, ""))));
    } catch {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, {
      "content-type": TYPES[extname(name)] ?? "application/octet-stream",
      "content-security-policy": CSP,
      "cache-control": "no-store",
    });
    res.end(body);
  });
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  const address = server.address();
  return { server, url: `http://127.0.0.1:${address.port}/` };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { url } = await serve(Number(process.env.PORT ?? 0));
  console.log(url);
}
