// Bundle the component page and serve it under a strict Content Security
// Policy: no inline script or style, no eval, nothing from another origin.
// Prints the URL; Playwright's global setup starts it.

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
    entryPoints: [join(here, "page.ts")],
    bundle: true,
    format: "esm",
    target: "es2022",
    write: false,
    conditions: ["production"],
    define: { "process.env.NODE_ENV": '"production"' },
    logLevel: "silent",
  });
  const js = bundle.outputFiles[0].contents;
  const server = createServer(async (req, res) => {
    const path = new URL(req.url ?? "/", "http://x").pathname;
    const name = path === "/" ? "index.html" : path.slice(1);
    let body;
    try {
      body = name === "page.js" ? js : await readFile(join(here, name.replace(/\.\.+/g, "")));
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
