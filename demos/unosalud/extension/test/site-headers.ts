/**
 * The response headers www.unosalud.cl sends with its documents (read off the
 * live site on 2026-10-27; see the research notes, "Headers"), for the tests
 * to serve the fixtures with: a strict Content-Security-Policy and a
 * Permissions-Policy that keeps the microphone to the page itself on every
 * page, and on the booking a loose policy that allows no microphone at all.
 */

export const SITE_HEADERS: Record<string, string> = {
  "content-security-policy":
    "default-src 'self'; script-src 'self' blob: data: 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://analytics.google.com https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://www.googleadservices.com https://*.clarity.ms https://cdn.brevo.com https://sibautomation.com https://*.facebook.net https://*.facebook.com https://maps.googleapis.com https://analytics.tiktok.com https://business.tiktok.com https://*.wonderpush.com; script-src-elem 'self' blob: data: 'unsafe-inline' https://sibforms.com https://cdn.trustindex.io https://www.googletagmanager.com https://www.google-analytics.com https://analytics.google.com https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://www.googleadservices.com https://*.clarity.ms https://cdn.brevo.com https://sibautomation.com https://*.facebook.net https://*.facebook.com https://maps.googleapis.com https://analytics.tiktok.com https://business.tiktok.com https://*.youtube.com https://*.wonderpush.com; style-src 'self' https: 'unsafe-inline'; img-src 'self' https: data: https://analytics.tiktok.com https://stats.g.doubleclick.net https://www.facebook.com; font-src 'self' https: data:; connect-src 'self' https://*.run.app https://*.conversionsapigateway.com https://cdn.trustindex.io https://www.google-analytics.com https://analytics.google.com https://business.tiktok.com https://www.googletagmanager.com https://www.google.com https://www.google.cl https://www.googleadservices.com https://googleads.g.doubleclick.net https://stats.g.doubleclick.net https://ad.doubleclick.net https://*.clarity.ms https://api.brevo.com https://in-automate.brevo.com https://cdn.brevo.com https://static.brevo.com https://*.sibforms.com https://www.facebook.com https://graph.facebook.com https://analytics.tiktok.com https://analytics-ipv6.tiktokw.us https://maps.googleapis.com https://script.google.com https://script.googleusercontent.com https://*.wonderpush.com; frame-src https://www.google.com https://www.googletagmanager.com https://www.youtube.com https://www.youtube-nocookie.com https://googleads.g.doubleclick.net; object-src 'none'; base-uri 'self'; frame-ancestors 'self';",
  "permissions-policy": "accelerometer=(self), autoplay=(self), camera=(self), encrypted-media=(self), fullscreen=(self), geolocation=(self), gyroscope=(self), magnetometer=(self), microphone=(self), midi=(self), payment=(self), usb=(self)",
  "x-frame-options": "sameorigin",
};

export const BOOKING_HEADERS: Record<string, string> = {
  "content-security-policy": "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval';",
  "permissions-policy": "geolocation=(), camera=(), microphone=()",
  "x-frame-options": "SAMEORIGIN",
};

/** The headers for a document at `path`. */
export const headersFor = (path: string) => (/^\/agenda-tu-hora(\/|$)/.test(path) ? BOOKING_HEADERS : SITE_HEADERS);
