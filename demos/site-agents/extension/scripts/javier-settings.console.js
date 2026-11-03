// Javier on a Site Agent's own side: his voice, Spanish first and English, and
// his name and face in the site's settings — what sitebrain speaks with. The
// extension draws Javier whatever the settings say; the voice and the
// languages are the brain's, so they are set here.
//
// The settings are staff-only (`sites.update_settings`, the console's own
// session; no MCP tool and no key can write them), so this runs in DevTools on
// an https://app.voqalize.com tab, signed in, with the site's workspace
// selected. Sites are found by their origin among the workspace's own
// (`sites.list`), so no id is written here. It reads each site's settings,
// changes only what is named below, and writes the whole object back (the
// route replaces it). No version or publish: embed.config and sitebrain read
// settings live (embed.config is cached 5 minutes).
//
// "spanish" is refused (400 language_unsupported) until sitebrain's Spanish
// support is in production; SPANISH = false applies only the voice, name and
// face.

const SPANISH = true;
const ORIGINS = ["https://www.wom.cl"];

const sites = [];
for (let cursor = ""; ; ) {
  const page = await (await fetch(`/api/v1/sites.list?limit=100${cursor ? `&cursor=${cursor}` : ""}`, { credentials: "include" })).json();
  sites.push(...page.items);
  if (!page.next_cursor) break;
  cursor = encodeURIComponent(page.next_cursor);
}

for (const origin of ORIGINS) {
  const site = sites.find((s) => s.primary_origin === origin);
  if (!site) {
    console.error(origin, "is not a site of this workspace");
    continue;
  }
  const detail = await (await fetch(`/api/v1/sites.get?site_id=${site.id}`, { credentials: "include" })).json();
  const settings = structuredClone(detail.settings);
  settings.assistant_name = "Javier";
  settings.avatar = { ...settings.avatar, enabled: true, character: "javier" };
  settings.voice = {
    voice: "VOICE_OMNIVOICE_JAVIER",
    default_language: SPANISH ? "spanish" : "english",
    languages: SPANISH ? ["spanish", "english"] : ["english"],
  };
  settings.greeting = SPANISH ? "¡Hola! Soy Javier. ¿En qué te ayudo?" : "Hi! I'm Javier. How can I help?";
  const put = await fetch("/api/v1/sites.update_settings", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ site_id: site.id, settings }),
  });
  console.log(origin, put.status, await put.json());
}
