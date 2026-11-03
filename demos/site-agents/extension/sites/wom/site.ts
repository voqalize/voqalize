/**
 * WOM (www.wom.cl), Chile's mobile, home-internet and prepaid operator: who the
 * site is, for its extension. Javier on WOM's live Site Agent.
 *
 * Read off the site on 2026-11-03 (curl of the home page and its stylesheets,
 * then the page drawn in Chromium):
 *
 *   - Headers: `Content-Security-Policy: frame-ancestors 'self'` and
 *     `X-Frame-Options: SAMEORIGIN` only. Neither limits a script, a fetch or
 *     a frame this page opens, and there is no `Permissions-Policy`, so the
 *     avatar runtime, our API and the microphone grant's frame work as they
 *     are: no header rule (`rules.json`) is needed.
 *   - Palette: the header and `theme-color` are WOM's deep purple #270046,
 *     the logo and links its violet #4D008C, and every call to action
 *     ("Lo quiero", "aceptar", "ver oferta") its magenta #E92070 with white.
 *     The face is Cera Pro, which every page has already loaded.
 *   - Fixed on the page: the header (`#main-header`, 134 px, plus the flash
 *     offer bar under it); the accessibility menu (`.menu-accesibilidad`,
 *     A− / A+, 46 px wide) bottom-left; "Contrata Ahora"
 *     (`.floating-button`) mid-right; reCAPTCHA's badge bottom-right; the
 *     cookie bar (`#msj_aceptacion_cookies`, 60 px, full width) until
 *     accepted; and an offer pop-up (`#popupPlanes`, a Bootstrap modal) on
 *     the first visit. There is no chat or WhatsApp bubble of WOM's own.
 */

import type { SiteAgentSite } from "../../src/site-agent";

/** The ring: a deep teal. WOM's magenta is every one of its buttons, so a
 *  ring in it would read as one more; its purples vanish on the header, the
 *  flash bar and the offer cards. #0097A7 holds on white (3.5:1), on the
 *  header's #270046 (5.1:1) and on the violet cards (#4D008C, 3.5:1), and is
 *  nowhere in WOM's palette. */
const RING = "#0097A7";
const SANS = `"Cera Pro", "Helvetica Neue", Arial, system-ui, sans-serif`;

export default {
  id: "wom",
  siteName: "WOM",
  origin: "https://www.wom.cl",
  matches: ["https://www.wom.cl/*", "https://wom.cl/*"],
  /**
   * WOM's own pages on www.wom.cl and nothing else, whatever the brain
   * sends. Never the visitor's own or a payment: the bill payment and top-ups
   * (`/paga-aqui`, `/paga-tu-cuenta`, `/recargas`, `/pago…`), the identity
   * check (`/validacion-de-identidad`), the prepaid balance lookup
   * (`/consulta-prepago`), the order tracking (`/sigue-tu-compra`) and any
   * login or checkout path. MiWOM (the account) is its own host,
   * miwom.wom.cl, and the phone store store.wom.cl, so neither is opened.
   */
  openable: [
    /^https:\/\/(www\.)?wom\.cl(\/(?!(paga-aqui|paga-tu-cuenta|recargas?|pagos?|validacion-de-identidad|consulta-prepago|sigue-tu-compra|miwom|mi-?cuenta|login|ingresar|checkout|webpay)(\/|\?|#|$))[^\s]*)?$/i,
  ],
  manifestKey:
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA4WhPCoXSKy0edKN061GBnaNApXOB30nJ43V6jIN3Cpps0tcDpFdKRjNJUaODI8sKEqUPjcF9HWEQUP29qbYXzQX2rCbX/5Ibs2W/663Gm+2b2YQpmoLEA2l306FYIK+rCiafKlVGJfiLTFLaVgqw3WAhvWl/XgQAJDoqkue3dHPp2sgRUt9zAw9UJRh6jjLvkf3MMntqSxLN+m0YLonj7rlMtzRijnRZbZHEym5RaeIND80kvMvyHn5Socqq8cZDkNgSRK2EbQUxHJsThCQ+/bnvZNx21vzb7ARCL2G5FiIz+w87uGJ2Q+vJt4UkZ1a9254Ceoqb04GrjmtSGoCs3QIDAQAB",
  extensionId: "jdpnhnchiacekmhpocipljafkmgedclm",
  description:
    "Javier, a voice guide on wom.cl: he finds plans, home internet, phones and prepaid with the visitor, opens the pages and points at what he is talking about, in Spanish or English. WOM's Site Agent, as a Voqalize preview.",
  // "Contrata Ahora" sits mid-right, well above the widget; reCAPTCHA's badge
  // (bottom-right, folded to 70 px) is kept clear of. Bottom-left is WOM's
  // accessibility menu, which a visitor who needs it must always reach.
  corner: "right",
  // Below the header and the flash bar, for the last resort.
  topClear: 196,
  fixed: ["#main-header"],
  obstacles: [
    { selector: "#msj_aceptacion_cookies", fixedOnly: true },
    { selector: ".grecaptcha-badge", fixedOnly: true },
    { selector: ".floating-button", fixedOnly: true },
  ],
  // The offer pop-up WOM opens on a first visit (a Bootstrap modal over the
  // whole page), closed by its own ×. The cookie bar is the visitor's to
  // answer: it is kept clear of, never accepted.
  dismissOnCall: ['#popupPlanes.show [data-dismiss="modal"]'],
  theme: {
    brand: "#E92070",
    brandHover: "#F0468A",
    onBrand: "#ffffff",
    card: "#270046",
    ink: "#ffffff",
    line: "rgba(255, 255, 255, 0.16)",
    muted: "rgba(255, 255, 255, 0.74)",
    raised: "#3A0A63",
    live: "#E92070",
    font: SANS,
    boldFont: SANS,
    radius: 8,
  },
  spotlight: {
    color: RING,
    width: 3,
    radius: 10,
    glow: `color-mix(in srgb, ${RING} 55%, transparent)`,
    holdMs: 5500,
  },
  grantStyle: { ink: "#494C66", button: "#E92070", onButton: "#ffffff", font: SANS },
} satisfies SiteAgentSite;
