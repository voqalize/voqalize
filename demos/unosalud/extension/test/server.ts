/**
 * The site, served the way the visitor's browser gets it: over HTTPS, at
 * www.unosalud.cl's own address (the browser maps the name to this server),
 * from the saved pages in `demos/unosalud/fixtures/`, with the site's real
 * response headers (`site-headers.ts`). A response the extension's header
 * rules (`rules.json`) act on must come from the network, which a test's
 * `page.route` answer does not; this server is that network.
 *
 * It also answers the made-up API (`api.voqalize.test`, the session mint) and
 * avatar host (`avatar.voqalize.test`, the face's runtime), and adds the
 * stand-ins for the site's own scripts the saved pages do not carry: the
 * booking's Dentalsoft wizard (`fake-dentalsoft.js`, with the real IMask) and
 * Brevo's delayed helpers (`fake-brevo.js`).
 *
 * Nothing leaves the machine: the browser resolves every other name to
 * nothing (`--host-resolver-rules`).
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { createServer, type Server } from "node:https";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { headersFor } from "./site-headers";

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(here, "..", "..", "fixtures");

/** The site's pages the tests load, by path. */
export const PAGES: Record<string, string> = {
  "/": "home.html",
  "/clinicas/": "clinicas.html",
  "/clinicas/moneda/": "clinica-moneda.html",
  "/especialidades/": "especialidades.html",
  "/especialidades/ortodoncia/": "ortodoncia.html",
  "/preguntas-frecuentes/": "preguntas-frecuentes.html",
  "/promociones/": "promociones.html",
  "/por-que-elegirnos/": "por-que-elegirnos.html",
  "/quienes-somos/": "nosotros.html",
  "/contactanos/": "contacto.html",
  "/beneficios-y-reembolso/": "beneficios-y-reembolso.html",
  "/landing/planes-sonrisa-protegida/": "planes-sonrisa-protegida.html",
  "/urgencias/": "cta-urgencias.html",
  "/landing/solicitar-diagnostico/": "cta-te-llamamos.html",
  "/landing/convenio-empresa/": "cta-convenio-empresa.html",
  "/agenda-tu-hora/": "cta-agenda-tu-hora.html",
  "/contactanos/convenios/": "cta-convenios-contacto.html",
};

const STAND_INS: Record<string, string> = {
  "/__test/fake-dentalsoft.js": join(here, "fake-dentalsoft.js"),
  "/__test/fake-brevo.js": join(here, "fake-brevo.js"),
  "/__test/site.css": join(here, "site.css"),
  "/__test/imask.js": join(here, "..", "node_modules", "imask", "dist", "imask.js"),
};

/** Third-party tags in the saved pages: dropped, as they never answer here. */
const TAGS = /<script\b[^>]*\bsrc="https:\/\/(?!www\.unosalud\.cl)[^"]*"[^>]*><\/script>/g;

function page(path: string): string | null {
  const file = PAGES[path];
  if (!file) return null;
  let html = readFileSync(join(FIXTURES, file), "utf8").replace(TAGS, "");
  const extra =
    path === "/agenda-tu-hora/"
      ? `<script src="/__test/imask.js"></script><script src="/__test/fake-dentalsoft.js"></script>`
      : html.includes('id="sib-form"')
        ? `<script src="/__test/fake-brevo.js"></script>`
        : "";
  if (extra) html = html.replace(/<\/body>/i, `${extra}</body>`);
  html = html.replace(/<\/head>/i, `<link rel="stylesheet" href="/__test/site.css"></head>`);
  return html;
}

export interface Site {
  port: number;
  /** The browser's flags that point the site's names at this server. */
  args: string[];
  /** The session mints the API saw, with their Origin. */
  connects: { origin: string | undefined; body: unknown }[];
  /** Requests for documents, by path. */
  documents: string[];
  close(): Promise<void>;
}

let cert: { key: Buffer; cert: Buffer } | null = null;
function selfSigned(): { key: Buffer; cert: Buffer } {
  if (cert) return cert;
  const dir = mkdtempSync(join(tmpdir(), "unosalud-cert-"));
  execFileSync("openssl", [
    "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=www.unosalud.cl",
    "-addext", "subjectAltName=DNS:www.unosalud.cl,DNS:unosalud.cl,DNS:api.voqalize.test,DNS:avatar.voqalize.test",
    "-keyout", join(dir, "key.pem"), "-out", join(dir, "cert.pem"),
  ], { stdio: "ignore" });
  cert = { key: readFileSync(join(dir, "key.pem")), cert: readFileSync(join(dir, "cert.pem")) };
  return cert;
}

export async function serveSite(): Promise<Site> {
  const connects: Site["connects"] = [];
  const documents: string[] = [];
  const server: Server = createServer(selfSigned(), (req, res) => {
    const host = (req.headers.host ?? "").replace(/:\d+$/, "");
    const url = new URL(req.url ?? "/", `https://${host}`);
    if (host === "api.voqalize.test") {
      const cors = {
        "access-control-allow-origin": req.headers.origin ?? "*",
        "access-control-allow-headers": "authorization, content-type",
        "access-control-allow-methods": "POST, OPTIONS",
      };
      if (req.method === "OPTIONS") return res.writeHead(204, cors).end();
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        connects.push({ origin: req.headers.origin, body: JSON.parse(body || "null") });
        res.writeHead(200, { ...cors, "content-type": "application/json" });
        res.end(JSON.stringify({ session_id: "s-test", webrtc_request_params: { endpoint: "https://rtc.voqalize.test/offer", headers: {} } }));
      });
      return;
    }
    if (host === "avatar.voqalize.test") {
      res.writeHead(200, { "content-type": "text/javascript", "access-control-allow-origin": "*" });
      return res.end("export const loaded = true;");
    }
    if (host === "www.unosalud.cl" || host === "unosalud.cl") {
      const stand = STAND_INS[url.pathname];
      if (stand) {
        res.writeHead(200, { "content-type": stand.endsWith(".css") ? "text/css" : "text/javascript" });
        return res.end(readFileSync(stand));
      }
      const html = page(url.pathname);
      if (html !== null) {
        documents.push(url.pathname);
        res.writeHead(200, { "content-type": "text/html; charset=utf-8", ...headersFor(url.pathname) });
        return res.end(html);
      }
    }
    res.writeHead(404, { "content-type": "text/plain" }).end("");
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  const names = ["www.unosalud.cl", "unosalud.cl", "api.voqalize.test", "avatar.voqalize.test"];
  return {
    port,
    args: [
      `--host-resolver-rules=${names.map((n) => `MAP ${n}:443 127.0.0.1:${port}`).join(", ")}, MAP * ~NOTFOUND`,
      "--ignore-certificate-errors",
    ],
    connects,
    documents,
    close: () => new Promise<void>((r) => server.close(() => r())),
  };
}
