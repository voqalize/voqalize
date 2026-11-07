/**
 * The widget builder: a form over the widget configuration's schema, a live
 * preview in a desktop and a phone frame, and the snippet it writes.
 *
 * Self-contained so it can move to the marketing site once the package is
 * released: it imports the package only through its public entry points
 * (`@voqalize/web`, `/widgets` and the schema).
 *
 * The page takes a publishable key for "Talk to it" from the query string
 * (`?agent=…&key=pk_…&api=…`), or from the dev server's local file (see the
 * README); either way the key never goes into the page's address after load.
 */

import { VERSION } from "@voqalize/web";
import schemaJson from "@voqalize/web/widget-config.schema.json";
import { PREVIEW_STATES, type PreviewMessage, type PreviewReport, type PreviewState, type TalkTarget } from "./protocol.js";
import {
  type Json,
  type Leaf,
  type SchemaNode,
  type Sparse,
  applyLeaf,
  getPath,
  groupLeaves,
  leavesOf,
  shownValue,
} from "./schema-form.js";
import { htmlSnippet, reactSnippet, settingsJson } from "./snippet.js";

const schema = schemaJson as unknown as SchemaNode;

/** Characters offered as suggestions; any catalogue name is accepted. */
const CHARACTER_SUGGESTIONS = ["emily", "tara", "ananya", "javier", "tess", "tanya", "tanvi", "tushar"];

/** Choices shorter than this, in characters across all options, are drawn as a segmented control. */
const SEGMENTED_MAX_CHARS = 30;

// ---------------------------------------------------------------- the state

interface BuilderState {
  config: Sparse;
  state: PreviewState;
  page: "light" | "dark";
  frames: "both" | "desktop" | "phone";
  snippet: "html" | "react";
  talking: boolean;
}

const st: BuilderState = {
  config: readHash(),
  state: "speaking",
  page: "light",
  frames: "both",
  snippet: "html",
  talking: false,
};

let talkTarget: TalkTarget | null = null;

function $(sel: string): HTMLElement {
  const el = document.querySelector<HTMLElement>(sel);
  if (!el) throw new Error(`builder: no ${sel}`);
  return el;
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<Record<string, string>> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined) continue;
    if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  node.append(...children);
  return node;
}

// ------------------------------------------------------- the address's hash

/** The configuration lives in the hash, so a builder link carries it. The key never does. */
function readHash(): Sparse {
  try {
    const raw = location.hash.slice(1);
    if (!raw.startsWith("c=")) return {};
    const json = decodeURIComponent(escape(atob(raw.slice(2).replace(/-/g, "+").replace(/_/g, "/"))));
    const parsed = JSON.parse(json) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const { key: _k, ...rest } = parsed as Sparse;
      return rest;
    }
  } catch {
    // A hand-edited hash: start from the defaults.
  }
  return {};
}

function writeHash(): void {
  const { key: _k, ...rest } = st.config;
  const json = JSON.stringify(rest);
  const hash = json === "{}" ? "" : `#c=${btoa(unescape(encodeURIComponent(json))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;
  history.replaceState(null, "", `${location.pathname}${location.search}${hash}`);
}

// ------------------------------------------------------------------ the form

const leaves = leavesOf(schema);
const controls = new Map<string, { leaf: Leaf; root: HTMLElement; sync: () => void }>();

function setLeaf(leaf: Leaf, value: Json | undefined): void {
  st.config = applyLeaf(st.config, leaf, value);
  changed();
}

function idFor(path: string): string {
  return `f-${path.replace(/\./g, "-")}`;
}

function describe(leaf: Leaf, field: HTMLElement): void {
  if (!leaf.description) return;
  const help = el("p", { class: "help", id: `${idFor(leaf.path)}-help`, text: leaf.description });
  field.append(help);
}

function clearButton(leaf: Leaf): HTMLButtonElement {
  const b = el("button", { type: "button", class: "clear", "aria-label": `Reset ${leaf.label}`, title: "Back to the default", text: "Reset" });
  b.addEventListener("click", () => setLeaf(leaf, undefined));
  return b;
}

function choiceControl(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  const options = leaf.options ?? [];
  const segmented = options.join("").length <= SEGMENTED_MAX_CHARS;
  if (segmented) {
    const group = el("div", { class: "segmented", role: "radiogroup", "aria-labelledby": `${idFor(leaf.path)}-label` });
    const inputs: HTMLInputElement[] = [];
    for (const option of options) {
      const input = el("input", { type: "radio", name: idFor(leaf.path), value: option, id: `${idFor(leaf.path)}-${option}` });
      input.addEventListener("change", () => input.checked && setLeaf(leaf, option));
      inputs.push(input);
      group.append(el("label", { for: input.id }, input, el("span", { text: option })));
    }
    return {
      node: group,
      sync: () => {
        const v = String(shownValue(st.config, leaf) ?? "");
        for (const i of inputs) i.checked = i.value === v;
      },
    };
  }
  const select = el("select", { id: idFor(leaf.path) });
  for (const option of options) select.append(el("option", { value: option, text: option }));
  select.addEventListener("change", () => setLeaf(leaf, select.value));
  return { node: select, sync: () => (select.value = String(shownValue(st.config, leaf) ?? options[0] ?? "")) };
}

function switchControl(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  const input = el("input", { type: "checkbox", role: "switch", id: idFor(leaf.path), class: "switch" });
  input.addEventListener("change", () => setLeaf(leaf, input.checked));
  return { node: input, sync: () => (input.checked = shownValue(st.config, leaf) === true) };
}

function colourControl(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  const wrap = el("div", { class: "colour" });
  const picker = el("input", { type: "color", id: idFor(leaf.path), "aria-label": leaf.label });
  const text = el("input", { type: "text", class: "hex", placeholder: "auto", maxlength: "7", "aria-label": `${leaf.label} as hex`, spellcheck: "false" });
  const reset = clearButton(leaf);
  picker.addEventListener("input", () => setLeaf(leaf, picker.value));
  text.addEventListener("change", () => {
    const v = text.value.trim();
    if (v === "") setLeaf(leaf, undefined);
    else if (/^#[0-9a-fA-F]{6}$/.test(v)) setLeaf(leaf, v.toLowerCase());
    else text.setAttribute("aria-invalid", "true");
  });
  wrap.append(picker, text, reset);
  return {
    node: wrap,
    sync: () => {
      const v = getPath(st.config, leaf.path);
      text.removeAttribute("aria-invalid");
      text.value = typeof v === "string" ? v : "";
      picker.value = typeof v === "string" ? v : "#888888";
      wrap.classList.toggle("unset", typeof v !== "string");
      reset.hidden = typeof v !== "string";
    },
  };
}

function sliderControl(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  const wrap = el("div", { class: "slider" });
  const range = el("input", {
    type: "range",
    id: idFor(leaf.path),
    min: String(leaf.min ?? 0),
    max: String(leaf.max ?? 100),
    step: String(leaf.step ?? 1),
  });
  const out = el("output", { for: range.id });
  const reset = clearButton(leaf);
  range.addEventListener("input", () => setLeaf(leaf, Number(range.value)));
  wrap.append(range, out, reset);
  return {
    node: wrap,
    sync: () => {
      const v = shownValue(st.config, leaf);
      const n = typeof v === "number" ? v : undefined;
      range.value = String(n ?? leaf.min ?? 0);
      out.textContent = n === undefined ? "auto" : String(n);
      reset.hidden = getPath(st.config, leaf.path) === undefined;
    },
  };
}

function textControl(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  const input = el("input", {
    type: "text",
    id: idFor(leaf.path),
    spellcheck: "false",
    autocomplete: "off",
    ...(leaf.maxLength ? { maxlength: String(leaf.maxLength) } : {}),
  });
  if (leaf.path === "agent") input.placeholder = "agt_…";
  if (leaf.path === "key") input.placeholder = "pk_…";
  if (leaf.path === "name") input.placeholder = "Emily";
  if (leaf.path.endsWith("character")) {
    const list = el("datalist", { id: `${idFor(leaf.path)}-list` });
    for (const c of CHARACTER_SUGGESTIONS) list.append(el("option", { value: c }));
    input.setAttribute("list", list.id);
    input.placeholder = "the agent's own";
    const wrap = el("div", {}, input, list);
    input.addEventListener("input", () => setLeaf(leaf, input.value.trim() || undefined));
    return { node: wrap, sync: () => syncText(input, leaf) };
  }
  if (leaf.default !== undefined && !input.placeholder) input.placeholder = String(leaf.default);
  input.addEventListener("input", () => {
    const v = input.value.trim();
    if (leaf.kind === "number") setLeaf(leaf, v === "" ? undefined : Number(v));
    else setLeaf(leaf, v === "" ? undefined : leaf.path === "captions.linger" && /^\d+$/.test(v) ? Number(v) : v);
  });
  return { node: input, sync: () => syncText(input, leaf) };
}

function syncText(input: HTMLInputElement, leaf: Leaf): void {
  if (document.activeElement === input) return;
  const v = getPath(st.config, leaf.path);
  input.value = v === undefined || v === null ? "" : String(v);
}

function listControl(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  const input = el("input", { type: "text", id: idFor(leaf.path), placeholder: "#cart-drawer, .chat-bubble", spellcheck: "false" });
  input.addEventListener("input", () => {
    const items = input.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setLeaf(leaf, items.length ? items : undefined);
  });
  return {
    node: input,
    sync: () => {
      if (document.activeElement === input) return;
      const v = getPath(st.config, leaf.path);
      input.value = Array.isArray(v) ? v.join(", ") : "";
    },
  };
}

function jsonControl(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  const area = el("textarea", { id: idFor(leaf.path), rows: "3", spellcheck: "false", placeholder: "{}" });
  area.addEventListener("input", () => {
    const raw = area.value.trim();
    if (raw === "") {
      area.removeAttribute("aria-invalid");
      setLeaf(leaf, undefined);
      return;
    }
    try {
      const v = JSON.parse(raw) as Json;
      area.removeAttribute("aria-invalid");
      setLeaf(leaf, v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0 ? undefined : v);
    } catch {
      area.setAttribute("aria-invalid", "true");
    }
  });
  return {
    node: area,
    sync: () => {
      if (document.activeElement === area) return;
      const v = getPath(st.config, leaf.path);
      area.value = v === undefined ? "" : JSON.stringify(v, null, 2);
    },
  };
}

const GRADIENT_EXAMPLE = "linear-gradient(160deg, #fde68a, #fb923c)";

function backgroundControl(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  const wrap = el("div", { class: "background" });
  const kind = el("select", { id: idFor(leaf.path) });
  for (const [v, t] of [
    ["none", "None"],
    ["colour", "Colour"],
    ["gradient", "Gradient"],
    ["url", "Image, GIF or video"],
  ] as const) {
    kind.append(el("option", { value: v, text: t }));
  }
  const colour = el("input", { type: "color", "aria-label": "Background colour" });
  const gradient = el("input", { type: "text", "aria-label": "CSS gradient", spellcheck: "false" });
  const url = el("input", { type: "url", "aria-label": "Image or video URL", placeholder: "https://…/loop.mp4" });
  const fit = el("select", { "aria-label": "Fit" }, el("option", { value: "cover", text: "cover" }), el("option", { value: "contain", text: "contain" }));
  wrap.append(kind, colour, gradient, url, fit);

  const kindOf = (v: Json | undefined): string => {
    if (v && typeof v === "object" && !Array.isArray(v)) return "url";
    if (typeof v !== "string" || v === "none") return "none";
    if (v.includes("gradient(")) return "gradient";
    return "colour";
  };
  const write = () => {
    const k = kind.value;
    if (k === "none") setLeaf(leaf, undefined);
    else if (k === "colour") setLeaf(leaf, colour.value);
    else if (k === "gradient") setLeaf(leaf, gradient.value.trim() || GRADIENT_EXAMPLE);
    else if (url.value.trim()) setLeaf(leaf, { url: url.value.trim(), ...(fit.value === "cover" ? {} : { fit: fit.value }) });
    else syncVisible();
  };
  const syncVisible = () => {
    const k = kind.value;
    colour.hidden = k !== "colour";
    gradient.hidden = k !== "gradient";
    url.hidden = k !== "url";
    fit.hidden = k !== "url";
  };
  kind.addEventListener("change", write);
  colour.addEventListener("input", write);
  gradient.addEventListener("change", write);
  url.addEventListener("change", write);
  fit.addEventListener("change", write);
  return {
    node: wrap,
    sync: () => {
      const v = getPath(st.config, leaf.path);
      const k = kindOf(v);
      if (!(k === "none" && kind.value === "url")) kind.value = k;
      if (k === "colour" && typeof v === "string") colour.value = /^#[0-9a-f]{6}$/i.test(v) ? v : "#888888";
      if (document.activeElement !== gradient) gradient.value = k === "gradient" && typeof v === "string" ? v : GRADIENT_EXAMPLE;
      if (k === "url" && v && typeof v === "object" && !Array.isArray(v)) {
        if (document.activeElement !== url) url.value = String(v.url ?? "");
        fit.value = String(v.fit ?? "cover");
      }
      syncVisible();
    },
  };
}

function controlFor(leaf: Leaf): { node: HTMLElement; sync: () => void } {
  switch (leaf.kind) {
    case "choice":
      return choiceControl(leaf);
    case "switch":
    case "presence":
      return switchControl(leaf);
    case "colour":
      return colourControl(leaf);
    case "slider":
      return sliderControl(leaf);
    case "list":
      return listControl(leaf);
    case "json":
      return jsonControl(leaf);
    case "background":
      return backgroundControl(leaf);
    default:
      return textControl(leaf);
  }
}

function renderForm(): void {
  const form = $("#form");
  form.replaceChildren();
  controls.clear();
  for (const group of groupLeaves(leaves)) {
    const details = el("details", { class: "group", "data-group": group.id });
    if (group.id !== "more") details.open = true;
    details.append(el("summary", {}, el("h2", { text: group.title })));
    for (const leaf of group.leaves) {
      const field = el("div", { class: `field kind-${leaf.kind}`, "data-path": leaf.path });
      const { node, sync } = controlFor(leaf);
      const labelId = `${idFor(leaf.path)}-label`;
      const label =
        leaf.kind === "choice" && node.getAttribute("role") === "radiogroup"
          ? el("span", { class: "label", id: labelId, text: leaf.label })
          : el("label", { class: "label", id: labelId, for: idFor(leaf.path), text: leaf.label });
      field.append(label, node);
      describe(leaf, field);
      details.append(field);
      controls.set(leaf.path, { leaf, root: field, sync });
    }
    form.append(details);
  }
  syncForm();
}

function syncForm(): void {
  for (const { leaf, root, sync } of controls.values()) {
    sync();
    const off = leaf.dependsOn !== undefined && getPath(st.config, leaf.dependsOn) === false;
    root.classList.toggle("off", off);
    for (const input of root.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | HTMLButtonElement>(
      "input, select, textarea, button",
    )) {
      input.disabled = off;
    }
    root.classList.toggle("changed", getPath(st.config, leaf.path) !== undefined);
  }
}

// --------------------------------------------------------------- the preview

const frames = new Map<"desktop" | "phone", HTMLIFrameElement>();
const FRAME_SIZE = { desktop: { width: 1280, height: 800 }, phone: { width: 390, height: 780 } } as const;

function send(which: "desktop" | "phone"): void {
  const frame = frames.get(which);
  if (!frame?.contentWindow) return;
  const talk = st.talking && which === "desktop" && talkTarget ? talkTarget : undefined;
  const msg: PreviewMessage = { type: "vql-builder", config: st.config, state: st.state, page: st.page, ...(talk ? { talk } : {}) };
  frame.contentWindow.postMessage(msg, location.origin);
}

function sendAll(): void {
  send("desktop");
  send("phone");
}

function fitFrames(): void {
  for (const [which, frame] of frames) {
    const box = frame.parentElement as HTMLElement;
    const size = FRAME_SIZE[which];
    const scale = Math.min(1, box.clientWidth / size.width);
    box.style.setProperty("--scale", String(scale));
    box.style.setProperty("--frame-h", `${Math.round(size.height * scale)}px`);
  }
}

function renderPreview(): void {
  const chips = $("#states");
  chips.replaceChildren();
  for (const s of PREVIEW_STATES) {
    const b = el("button", { type: "button", class: "chip", "data-state": s.id, "aria-pressed": String(st.state === s.id), text: s.label });
    b.addEventListener("click", () => {
      if (st.talking) stopTalking();
      st.state = s.id;
      renderChips();
      sendAll();
    });
    chips.append(b);
  }
  for (const which of ["desktop", "phone"] as const) {
    const frame = $(`#frame-${which}`) as HTMLIFrameElement;
    frames.set(which, frame);
    frame.addEventListener("load", () => send(which));
    frame.src = "preview.html";
  }
  addEventListener("message", (e: MessageEvent) => {
    if (e.origin !== location.origin) return;
    const r = e.data as PreviewReport;
    if (r?.type !== "vql-preview") return;
    const which = [...frames].find(([, f]) => f.contentWindow === e.source)?.[0];
    if (!which) return;
    const caption = $(`#caption-${which}`);
    if (r.view !== "loading") caption.textContent = `${which === "desktop" ? "Desktop" : "Phone"} · ${r.view}, ${r.form}`;
    frames.get(which)?.setAttribute("data-view", r.view);
    if (r.ended && st.talking && which === "desktop") stopTalking(false);
  });
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-page]")) {
    b.addEventListener("click", () => {
      st.page = b.dataset.page === "dark" ? "dark" : "light";
      renderChips();
      sendAll();
    });
  }
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-frames]")) {
    b.addEventListener("click", () => {
      st.frames = (b.dataset.frames as BuilderState["frames"]) ?? "both";
      renderChips();
      fitFrames();
    });
  }
  new ResizeObserver(fitFrames).observe($("#frames"));
  renderChips();
}

function renderChips(): void {
  for (const b of document.querySelectorAll<HTMLButtonElement>("#states .chip")) {
    b.setAttribute("aria-pressed", String(!st.talking && b.dataset.state === st.state));
  }
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-page]")) b.setAttribute("aria-pressed", String(b.dataset.page === st.page));
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-frames]")) b.setAttribute("aria-pressed", String(b.dataset.frames === st.frames));
  $("#frames").dataset.show = st.frames;
}

// ------------------------------------------------------------- the snippet

function renderSnippet(): void {
  const text = st.snippet === "html" ? htmlSnippet(st.config, VERSION) : reactSnippet(st.config);
  $("#snippet").textContent = text;
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-snippet]")) {
    b.setAttribute("aria-selected", String(b.dataset.snippet === st.snippet));
  }
}

async function copy(text: string, status: HTMLElement): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = "Copied.";
  } catch {
    // No clipboard here (an insecure origin, or permission refused): select it to copy by hand.
    const range = document.createRange();
    range.selectNodeContents($("#snippet"));
    getSelection()?.removeAllRanges();
    getSelection()?.addRange(range);
    status.textContent = "Selected. Copy it with your keyboard.";
  }
}

// ---------------------------------------------------------------- talk to it

function currentTalkTarget(): TalkTarget | null {
  const agent = getPath(st.config, "agent");
  const key = getPath(st.config, "key");
  if (typeof agent === "string" && typeof key === "string" && agent && key.startsWith("pk_")) {
    return { agent, key, ...(talkTarget?.apiBase ? { apiBase: talkTarget.apiBase } : {}) };
  }
  return talkTarget;
}

let localTarget: TalkTarget | null = null;

function renderTalk(): void {
  const button = $("#talk") as HTMLButtonElement;
  const target = currentTalkTarget() ?? localTarget;
  button.disabled = !target && !st.talking;
  button.textContent = st.talking ? "End the call" : "Talk to it";
  button.title = target ? "A real call with the agent, in the desktop frame" : "Give the page an agent and a publishable key to call it";
  $("#talk-note").hidden = Boolean(target) || st.talking;
}

function startTalking(): void {
  const target = currentTalkTarget() ?? localTarget;
  if (!target) return;
  talkTarget = target;
  st.talking = true;
  renderChips();
  renderTalk();
  send("desktop");
}

function stopTalking(resend = true): void {
  st.talking = false;
  renderChips();
  renderTalk();
  if (resend) send("desktop");
  else st.state = "ended";
}

/** The query string's agent, key and control plane, then the dev server's local file. */
async function loadTalkTarget(): Promise<void> {
  const q = new URLSearchParams(location.search);
  const fromQuery = (agent: string | null, key: string | null, api: string | null): TalkTarget | null =>
    agent && key?.startsWith("pk_") ? { agent, key, ...(api ? { apiBase: api } : {}) } : null;
  localTarget = fromQuery(q.get("agent"), q.get("key"), q.get("api"));
  if (q.has("key")) {
    // Take the key out of the address bar, so it is not shared with the link.
    q.delete("key");
    const search = q.toString();
    history.replaceState(null, "", `${location.pathname}${search ? `?${search}` : ""}${location.hash}`);
  }
  if (!localTarget) {
    try {
      const r = await fetch("local.json", { cache: "no-store" });
      if (r.ok) {
        // `null` when the server has no local file.
        const j = ((await r.json()) ?? {}) as { agent?: string; key?: string; api?: string };
        localTarget = fromQuery(j.agent ?? null, j.key ?? null, j.api ?? null);
      }
    } catch {
      // No local file: "Talk to it" waits for an agent and key in the form.
    }
  }
  talkTarget = localTarget;
  renderTalk();
}

// ---------------------------------------------------------------- the stubs

function openDialog(id: string): void {
  const d = $(id) as HTMLDialogElement;
  if (id === "#apply-dialog") $("#apply-json").textContent = settingsJson(st.config);
  d.showModal();
}

function wireActions(): void {
  $("#talk").addEventListener("click", () => (st.talking ? stopTalking() : startTalking()));
  $("#copy").addEventListener("click", () => void copy($("#snippet").textContent ?? "", $("#copy-status")));
  $("#apply").addEventListener("click", () => openDialog("#apply-dialog"));
  $("#from-site").addEventListener("click", () => openDialog("#site-dialog"));
  $("#reset").addEventListener("click", () => {
    st.config = {};
    renderForm();
    changed();
  });
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-snippet]")) {
    b.addEventListener("click", () => {
      st.snippet = b.dataset.snippet === "react" ? "react" : "html";
      renderSnippet();
    });
  }
  for (const b of document.querySelectorAll<HTMLButtonElement>("dialog [data-close]")) {
    b.addEventListener("click", () => (b.closest("dialog") as HTMLDialogElement).close());
  }
  ($("#site-form") as HTMLFormElement).addEventListener("submit", (e) => {
    e.preventDefault();
    const url = ($("#site-url") as HTMLInputElement).value.trim();
    $("#site-result").textContent = url
      ? `Not connected yet. When it is, the builder will read ${url} and start you from its accent colour, the corner its other chat widgets leave free, and a character and voice for its language.`
      : "Enter your site's address.";
  });
}

// ------------------------------------------------------------------ changes

function changed(): void {
  syncForm();
  renderSnippet();
  renderTalk();
  writeHash();
  sendAll();
}

renderForm();
renderPreview();
renderSnippet();
wireActions();
fitFrames();
void loadTalkTarget();
$("#version").textContent = VERSION;
document.body.dataset.ready = "builder";
