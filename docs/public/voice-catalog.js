// The voice table on /reference/catalog, read in the reader's browser from the
// roster the speech tier publishes. The docs carry no copy of the voices: a
// copy is a list that goes stale on its own schedule, and this one did.
//
// No framework and no build step: Starlight serves this file as it is from
// public/, and the page's markdown names it with a plain <script> tag.

const ROSTER = "https://speech.prod.voqalize.com/voices.json";

// The shape this script understands. A newer document is reported, not guessed at.
const VERSION = 1;

const mount = document.getElementById("voice-catalog");

/** An element, its attributes and its children, without innerHTML. */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  for (const child of children) node.append(child);
  return node;
}

function code(text) {
  return el("code", {}, text);
}

const languageNames = (() => {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" });
  } catch {
    return null;
  }
})();

/** "Hindi" for "hi", or the bare tag where the browser has no name for it. */
function languageName(tag) {
  try {
    const name = languageNames?.of(tag);
    return name && name !== tag ? name : null;
  } catch {
    return null;
  }
}

function languageCell(tags) {
  const cell = el("td");
  const sorted = [...tags].sort((a, b) => {
    // English first, since every voice speaks it; then by name.
    if (a === "en") return -1;
    if (b === "en") return 1;
    return (languageName(a) ?? a).localeCompare(languageName(b) ?? b);
  });
  sorted.forEach((tag, index) => {
    if (index > 0) cell.append(", ");
    const name = languageName(tag);
    // One unit, so a line never breaks between a name and its tag.
    cell.append(
      el(
        "span",
        { class: "voice-catalog-lang" },
        ...(name ? [`${name} `, code(tag)] : [code(tag)]),
      ),
    );
  });
  return cell;
}

function fail(reason) {
  mount.replaceChildren(
    el(
      "p",
      { class: "voice-catalog-error", role: "alert" },
      `The voice list could not be loaded (${reason}). It is published at `,
      el("a", { href: ROSTER }, ROSTER),
      ": every entry's ",
      code("id"),
      " is a value ",
      code("tts.voice"),
      " accepts, and its ",
      code("languages"),
      " are the values ",
      code("tts.language"),
      " accepts with it.",
    ),
  );
}

function render(document_) {
  const voices = [...document_.voices].sort(
    (a, b) =>
      String(a.engine).localeCompare(String(b.engine)) || String(a.id).localeCompare(String(b.id)),
  );
  const body = el("tbody");
  for (const voice of voices) {
    body.append(
      el(
        "tr",
        {},
        el("td", {}, code(String(voice.id))),
        el("td", {}, String(voice.display ?? "")),
        languageCell(voice.languages ?? []),
      ),
    );
  }
  const table = el(
    "table",
    {},
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        el("th", { scope: "col" }, "Voice ID (", code("tts.voice"), ")"),
        el("th", { scope: "col" }, "Sounds like"),
        el("th", { scope: "col" }, "Speaks (", code("tts.language"), ")"),
      ),
    ),
    body,
  );
  const note = el(
    "p",
    { class: "voice-catalog-note" },
    `${voices.length} voices, read just now from `,
    el("a", { href: ROSTER }, "speech.prod.voqalize.com/voices.json"),
    ".",
  );
  mount.replaceChildren(el("div", { class: "voice-catalog-scroll" }, table), note);
}

async function load() {
  let response;
  try {
    response = await fetch(ROSTER, { headers: { Accept: "application/json" } });
  } catch {
    return fail("the request did not complete");
  }
  if (!response.ok) return fail(`it answered ${response.status}`);
  let document_;
  try {
    document_ = await response.json();
  } catch {
    return fail("it was not JSON");
  }
  if (document_?.version !== VERSION) {
    return fail(
      `it is version ${JSON.stringify(document_?.version)}, and this page reads ${VERSION}`,
    );
  }
  if (!Array.isArray(document_.voices)) return fail("it has no voices list");
  render(document_);
}

const style = el(
  "style",
  {},
  `
#voice-catalog { margin-top: 1rem; }
#voice-catalog .voice-catalog-scroll { overflow-x: auto; }
#voice-catalog table {
  border-collapse: collapse;
  width: 100%;
  font-size: var(--sl-text-sm);
}
#voice-catalog th, #voice-catalog td {
  text-align: start;
  vertical-align: top;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--sl-color-gray-5);
}
#voice-catalog th {
  color: var(--sl-color-white);
  background: var(--sl-color-gray-6);
  font-weight: 600;
}
#voice-catalog td { color: var(--sl-color-gray-2); }
#voice-catalog td:first-child, #voice-catalog td:nth-child(2),
#voice-catalog .voice-catalog-lang { white-space: nowrap; }
#voice-catalog code {
  font-family: var(--__sl-font-mono, var(--sl-font-mono, monospace));
  font-size: 0.875em;
  background: var(--sl-color-bg-inline-code, var(--sl-color-gray-6));
  border-radius: 0.25rem;
  padding: 0.0625rem 0.3rem;
}
#voice-catalog th code { background: var(--sl-color-gray-5); }
#voice-catalog a { color: var(--sl-color-text-accent); }
#voice-catalog .voice-catalog-note {
  margin-top: 0.5rem;
  font-size: var(--sl-text-xs);
  color: var(--sl-color-gray-3);
}
#voice-catalog .voice-catalog-error {
  padding: 0.75rem 1rem;
  border-inline-start: 4px solid var(--sl-color-red);
  background: var(--sl-color-red-low);
  color: var(--sl-color-white);
}
`,
);

if (mount) {
  document.head.append(style);
  load();
}
