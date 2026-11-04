// The live tables on /reference/catalog — the voices, the languages the
// recognizer hears, and the avatar characters — read in the reader's browser
// from the public catalog. The docs carry no copy of any of them: a copy is a
// list that goes stale on its own schedule, and the last one did.
//
// The request is same-origin: the docs host rewrites `/api/**` to
// app.voqalize.com, and `astro dev` proxies it. The link a reader is shown is
// the public URL, which answers the same document from anywhere.
//
// No framework and no build step: Starlight serves this file as it is from
// public/, and the page's markdown names it with a plain <script> tag. It does
// not show the characters' stills: those come from the avatar runtime, a
// download far larger than this page, so each character links to the avatar
// page, which mounts it.

const ENDPOINT = "/api/v1/catalog.get";
const PUBLIC_URL = "https://app.voqalize.com/api/v1/catalog.get";
const AVATAR_PAGE = "/build/avatar/";

const mounts = {
  voices: document.getElementById("voice-catalog"),
  languages: document.getElementById("language-catalog"),
  characters: document.getElementById("character-catalog"),
};

/** An element, its attributes and its children, without innerHTML. */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  for (const child of children) node.append(child);
  return node;
}

const code = (text) => el("code", {}, String(text));
const publicLink = () => el("a", { href: PUBLIC_URL }, "app.voqalize.com/api/v1/catalog.get");

const browserNames = (() => {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" });
  } catch {
    return null;
  }
})();

/** The catalog's own name for a tag, else the browser's, else none. */
function nameFor(names, tag) {
  const own = names.get(String(tag).toLowerCase());
  if (own) return own;
  try {
    const name = browserNames?.of(tag);
    return name && name !== tag ? name : null;
  } catch {
    return null;
  }
}

/** English first, since every voice speaks it; then by name. */
function sortTags(names, tags) {
  return [...tags].sort((a, b) => {
    if (a === "en") return -1;
    if (b === "en") return 1;
    return (nameFor(names, a) ?? a).localeCompare(nameFor(names, b) ?? b);
  });
}

/** "Hindi hi", kept on one line so a name never breaks from its tag. */
function languageList(names, tags) {
  const cell = el("td");
  sortTags(names, tags).forEach((tag, index) => {
    if (index > 0) cell.append(", ");
    const name = nameFor(names, tag);
    cell.append(el("span", { class: "catalog-lang" }, ...(name ? [`${name} `, code(tag)] : [code(tag)])));
  });
  return cell;
}

/** Tags alone, the names on hover: a compact column for a wide table. */
function codeList(names, tags) {
  const cell = el("td", { class: "catalog-wrap" });
  sortTags(names, tags).forEach((tag, index) => {
    if (index > 0) cell.append(" ");
    const name = nameFor(names, tag);
    cell.append(el("code", name ? { title: name } : {}, String(tag)));
  });
  return cell;
}

const voiceAnchor = (id) => `voice-${String(id).toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

function table(headings, rows) {
  return el(
    "div",
    { class: "catalog-scroll" },
    el(
      "table",
      {},
      el("thead", {}, el("tr", {}, ...headings.map((h) => el("th", { scope: "col" }, ...h)))),
      el("tbody", {}, ...rows),
    ),
  );
}

function note(...children) {
  return el("p", { class: "catalog-note" }, ...children);
}

function notice(...children) {
  return el("p", { class: "catalog-notice", role: "status" }, ...children);
}

// ── The three tables ────────────────────────────────────────────────────────

function renderVoices(catalog, names) {
  const mount = mounts.voices;
  if (!mount) return;
  const voices = Array.isArray(catalog.voices) ? catalog.voices : [];
  if (catalog.stale?.voices || voices.length === 0) {
    mount.replaceChildren(
      notice(
        "The voice roster is being read right now, so there is no list to show yet. Reload in a minute, or read ",
        publicLink(),
        " directly.",
      ),
    );
    return;
  }
  const sorted = [...voices].sort(
    (a, b) => String(a.engine).localeCompare(String(b.engine)) || String(a.id).localeCompare(String(b.id)),
  );
  const rows = sorted.map((voice) =>
    el(
      "tr",
      { id: voiceAnchor(voice.id) },
      el("td", {}, code(voice.id)),
      el("td", {}, String(voice.display ?? "")),
      languageList(names, voice.languages ?? []),
    ),
  );
  const parts = [
    table(
      [
        ["Voice ID (", code("tts.voice"), ")"],
        ["Sounds like"],
        ["Speaks (", code("tts.language"), ")"],
      ],
      rows,
    ),
  ];
  for (const open of Array.isArray(catalog.open) ? catalog.open : []) {
    parts.push(
      note(
        "Also accepted: any id under ",
        code(`${open.prefix}`),
        `, which the ${open.engine} engine judges itself`,
        ...(open.languages?.length ? [", in ", ...sortTags(names, open.languages).flatMap((t, i) => [i ? ", " : "", code(t)])] : []),
        ".",
      ),
    );
  }
  parts.push(note(`${voices.length} voices, read just now from `, publicLink(), "."));
  mount.replaceChildren(...parts);
}

function renderLanguages(catalog) {
  const mount = mounts.languages;
  if (!mount) return;
  const languages = Array.isArray(catalog.languages) ? catalog.languages : [];
  if (catalog.stale?.languages || languages.length === 0) {
    mount.replaceChildren(
      notice(
        "The recognizer's languages are being read right now, so there is no list to show yet. Reload in a minute, or read ",
        publicLink(),
        " directly.",
      ),
    );
    return;
  }
  const sorted = [...languages].sort((a, b) =>
    a.code === "en" ? -1 : b.code === "en" ? 1 : String(a.display_name).localeCompare(String(b.display_name)),
  );
  mount.replaceChildren(
    el(
      "ul",
      { class: "catalog-languages" },
      ...sorted.map((l) => el("li", {}, code(l.code), " ", String(l.display_name ?? l.code))),
    ),
    note(`${languages.length} languages, read just now from `, publicLink(), "."),
  );
}

function renderCharacters(catalog, names) {
  const mount = mounts.characters;
  if (!mount) return;
  const characters = Array.isArray(catalog.characters) ? catalog.characters : [];
  if (characters.length === 0) {
    mount.replaceChildren(notice("No characters are listed right now. Read ", publicLink(), " directly."));
    return;
  }
  // A suggested voice links to its row above, when the roster lists it.
  const listed = new Set(
    catalog.stale?.voices ? [] : (catalog.voices ?? []).map((v) => String(v.id).toLowerCase()),
  );
  const rows = characters.map((c) => {
    const voices = el("td");
    (c.suggested_voices ?? []).forEach((id, index) => {
      if (index > 0) voices.append(el("br"));
      voices.append(
        listed.has(String(id).toLowerCase())
          ? el("a", { href: `#${voiceAnchor(id)}` }, code(id))
          : code(id),
      );
    });
    const age = c.age && c.age.min != null ? `${c.age.min} to ${c.age.max}` : "";
    return el(
      "tr",
      {},
      el(
        "td",
        {},
        el("a", { href: `${AVATAR_PAGE}?avatar=${encodeURIComponent(c.name)}` }, code(c.name)),
        el("br"),
        el("span", { class: "catalog-sub" }, [c.gender, age].filter(Boolean).join(", ")),
      ),
      el("td", { class: "catalog-wrap" }, (c.tags ?? []).join(", ")),
      voices,
      codeList(names, c.languages ?? []),
    );
  });
  mount.replaceChildren(
    table(
      [["Character"], ["Tags"], ["Suggested voices"], ["Languages"]],
      rows,
    ),
    note(
      `${characters.length} characters`,
      ". Each name opens it on the ",
      el("a", { href: AVATAR_PAGE }, "avatar page"),
      ".",
    ),
  );
}

// ── Loading ─────────────────────────────────────────────────────────────────

function fail(reason) {
  for (const [what, mount] of Object.entries(mounts)) {
    mount?.replaceChildren(
      el(
        "p",
        { class: "catalog-error", role: "alert" },
        `The ${what === "languages" ? "language" : what.slice(0, -1)} list could not be loaded (${reason}). The catalog is published at `,
        el("a", { href: PUBLIC_URL }, PUBLIC_URL),
        ", public JSON that needs no key.",
      ),
    );
  }
}

async function load() {
  let response;
  try {
    response = await fetch(ENDPOINT, { headers: { Accept: "application/json" } });
  } catch {
    return fail("the request did not complete");
  }
  if (!response.ok) return fail(`it answered ${response.status}`);
  let catalog;
  try {
    catalog = await response.json();
  } catch {
    return fail("it was not JSON");
  }
  if (!catalog || typeof catalog !== "object" || !Array.isArray(catalog.voices)) {
    return fail("it has no voices list");
  }
  const names = new Map(
    (Array.isArray(catalog.languages) ? catalog.languages : [])
      .filter((l) => l?.code && l.display_name)
      .map((l) => [String(l.code).toLowerCase(), String(l.display_name)]),
  );
  renderVoices(catalog, names);
  renderLanguages(catalog);
  renderCharacters(catalog, names);
}

const style = el(
  "style",
  {},
  `
.catalog-live { margin-top: 1rem; }
.catalog-live .catalog-scroll { overflow-x: auto; }
.catalog-live table {
  border-collapse: collapse;
  width: 100%;
  font-size: var(--sl-text-sm);
}
.catalog-live th, .catalog-live td {
  text-align: start;
  vertical-align: top;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--sl-color-gray-5);
}
.catalog-live th {
  color: var(--sl-color-white);
  background: var(--sl-color-gray-6);
  font-weight: 600;
  white-space: nowrap;
}
.catalog-live td { color: var(--sl-color-gray-2); white-space: nowrap; }
.catalog-live td:last-child, .catalog-live td.catalog-wrap { white-space: normal; min-width: 8rem; }
.catalog-live td.catalog-wrap code { display: inline-block; margin-bottom: 0.2rem; }
.catalog-live .catalog-lang { white-space: nowrap; }
.catalog-live .catalog-sub { font-size: var(--sl-text-xs); color: var(--sl-color-gray-3); }
.catalog-live tr:target td { background: var(--sl-color-accent-low); }
.catalog-live code {
  font-family: var(--__sl-font-mono, var(--sl-font-mono, monospace));
  font-size: 0.875em;
  background: var(--sl-color-bg-inline-code, var(--sl-color-gray-6));
  border-radius: 0.25rem;
  padding: 0.0625rem 0.3rem;
}
.catalog-live th code { background: var(--sl-color-gray-5); }
.catalog-live a { color: var(--sl-color-text-accent); }
.catalog-live .catalog-languages {
  list-style: none;
  padding: 0;
  margin: 0;
  columns: 11rem;
  column-gap: 1.5rem;
  font-size: var(--sl-text-sm);
  color: var(--sl-color-gray-2);
}
.catalog-live .catalog-languages li { margin: 0 0 0.25rem; break-inside: avoid; }
.catalog-live .catalog-note {
  margin-top: 0.5rem;
  font-size: var(--sl-text-xs);
  color: var(--sl-color-gray-3);
}
.catalog-live .catalog-notice {
  padding: 0.75rem 1rem;
  border-inline-start: 4px solid var(--sl-color-blue, var(--sl-color-accent));
  background: var(--sl-color-blue-low, var(--sl-color-accent-low));
  color: var(--sl-color-white);
}
.catalog-live .catalog-error {
  padding: 0.75rem 1rem;
  border-inline-start: 4px solid var(--sl-color-red);
  background: var(--sl-color-red-low);
  color: var(--sl-color-white);
}
`,
);

if (Object.values(mounts).some(Boolean)) {
  document.head.append(style);
  load();
}
