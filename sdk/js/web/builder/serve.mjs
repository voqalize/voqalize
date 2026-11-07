// The builder's dev server: bundles the builder and its preview frame and
// serves them on 127.0.0.1 under a Content Security Policy as strict as a
// customer's (no inline script or style, no eval).
//
//   pnpm builder              # prints the URL
//   PORT=… pnpm builder       # a fixed port
//
// "Talk to it" needs an agent and a publishable key. Give them in the page's
// address (?agent=…&key=pk_…&api=…), or in `builder/.env.local`, which is
// gitignored and served to the page as `local.json`:
//
//   VQL_BUILDER_AGENT=…
//   VQL_BUILDER_KEY=pk_…
//   VQL_BUILDER_API=https://…/api/v1     # optional; the production API otherwise

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { context } from "esbuild";

const here = fileURLToPath(new URL(".", import.meta.url));

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".webm": "audio/webm",
};

/** The preview's recorded voice: the clips `fixtures/make.mjs` writes. */
const CLIP = /^fixtures\/[a-z]+-[a-z]+\.webm$/;

/**
 * Where `@voqalize/avatar` loads its runtime and characters from: the
 * avatar's host, and its name before 0.7. Named in each directive the avatar's
 * README asks for, and nowhere else.
 */
const AVATAR_HOSTS = "https://cdn.voqalize.com https://avatar.voqalize.com";

/** The files a browser may fetch, besides the bundles. Nothing else under the folder is served. */
const STATIC = new Set(["index.html", "preview.html", "builder.css", "preview.css", "still.svg"]);

async function readLocalEnv() {
  let text;
  try {
    text = await readFile(join(here, ".env.local"), "utf8");
  } catch {
    return null;
  }
  const env = {};
  for (const line of text.split("\n")) {
    const m = /^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/.exec(line);
    if (m) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  if (!env.VQL_BUILDER_AGENT || !env.VQL_BUILDER_KEY?.startsWith("pk_")) return null;
  return { agent: env.VQL_BUILDER_AGENT, key: env.VQL_BUILDER_KEY, ...(env.VQL_BUILDER_API ? { api: env.VQL_BUILDER_API } : {}) };
}

function csp(apiOrigin) {
  return [
    "default-src 'none'",
    // The avatar's runtime is a module imported from its host.
    `script-src 'self' ${AVATAR_HOSTS}`,
    "style-src 'self'",
    `img-src 'self' ${AVATAR_HOSTS} https: data:`,
    "media-src 'self' https: blob:",
    // A real call mints its session from the control plane and signals to the
    // voice tier; the avatar fetches its character from its host.
    `connect-src 'self' ${AVATAR_HOSTS} https: wss:${apiOrigin ? ` ${apiOrigin}` : ""}`,
    "base-uri 'none'",
    "form-action 'none'",
    "frame-src 'self'",
    "frame-ancestors 'self'",
  ].join("; ");
}

/**
 * `readLocal: false` ignores `builder/.env.local`, so the tests see the page as
 * a visitor with no agent of their own does, whatever the working copy holds.
 */
export async function serve(port = 0, { readLocal = true } = {}) {
  const ctx = await context({
    entryPoints: { builder: join(here, "builder.ts"), preview: join(here, "preview.ts") },
    bundle: true,
    format: "esm",
    target: "es2022",
    write: false,
    outdir: here,
    entryNames: "[name]",
    conditions: ["production"],
    define: { "process.env.NODE_ENV": '"production"' },
    logLevel: "warning",
  });
  let bundles = new Map();
  const rebuild = async () => {
    const result = await ctx.rebuild();
    bundles = new Map(result.outputFiles.map((f) => [f.path.slice(f.path.lastIndexOf("/") + 1), f.contents]));
  };
  await rebuild();
  const watching = process.env.VQL_BUILDER_WATCH !== "0";

  const server = createServer(async (req, res) => {
    const path = new URL(req.url ?? "/", "http://x").pathname;
    const name = path === "/" ? "index.html" : path.slice(1);
    const local = readLocal ? await readLocalEnv() : null;
    let apiOrigin = "";
    try {
      if (local?.api) apiOrigin = new URL(local.api).origin;
    } catch {
      // A malformed API address: the page reports the failed connect.
    }
    let body;
    try {
      if (name === "local.json") {
        // `null` rather than a 404 when there is no local file, so the console stays clean.
        body = JSON.stringify(local);
      } else if (bundles.has(name)) {
        if (watching && name === "builder.js") await rebuild();
        body = bundles.get(name);
      } else if (STATIC.has(name) || CLIP.test(name)) {
        body = await readFile(join(here, name));
      } else {
        res.writeHead(404).end();
        return;
      }
    } catch (e) {
      res.writeHead(500, { "content-type": "text/plain" }).end(String(e));
      return;
    }
    res.writeHead(200, {
      "content-type": TYPES[extname(name)] ?? "application/octet-stream",
      "content-security-policy": csp(apiOrigin),
      "cache-control": "no-store",
    });
    res.end(body);
  });
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  const address = server.address();
  const close = (cb) => server.close(() => void ctx.dispose().then(() => cb?.()));
  return { server: { close }, url: `http://127.0.0.1:${address.port}/` };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { url } = await serve(Number(process.env.PORT ?? 0));
  console.log(`widget builder: ${url}`);
}
