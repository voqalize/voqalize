/**
 * What "Copy snippet" writes: the script tag and the element, carrying only
 * the fields the visitor changed, so every default stays the widget's own and
 * moves with it.
 *
 * The script is the package's script-tag build, which defines every element
 * so `<vql-widget>` works with no bundler. Its address follows the library
 * design (`cdn.voqalize.com/web/<version>/voqalize.js`); it is served once the
 * package is released.
 */

import type { Sparse } from "./schema-form.js";

export const SCRIPT_BASE = "https://cdn.voqalize.com/web";

/** Placeholders shown where the visitor has not given an agent or a key. */
export const AGENT_PLACEHOLDER = "agt_…";
export const KEY_PLACEHOLDER = "pk_…";

function attr(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function singleQuoted(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/'/g, "&#39;").replace(/</g, "&lt;");
}

/** The configuration without `agent` and `key`, which the snippet writes as attributes. */
export function presentation(config: Sparse): Sparse {
  const { agent: _a, key: _k, ...rest } = config;
  return rest;
}

/** The HTML snippet: the script tag, then the element. */
export function htmlSnippet(config: Sparse, version: string): string {
  const agent = typeof config.agent === "string" && config.agent ? config.agent : AGENT_PLACEHOLDER;
  const key = typeof config.key === "string" && config.key ? config.key : KEY_PLACEHOLDER;
  const rest = presentation(config);
  const lines = [
    `<script type="module" src="${SCRIPT_BASE}/${version}/voqalize.js"></script>`,
    `<vql-widget agent="${attr(agent)}" key="${attr(key)}"`,
  ];
  if (Object.keys(rest).length > 0) {
    lines.push(`  config='${singleQuoted(JSON.stringify(rest))}'`);
  }
  lines[lines.length - 1] += "></vql-widget>";
  return lines.join("\n");
}

/** The same widget from React, through the package's wrappers. */
export function reactSnippet(config: Sparse): string {
  const full: Sparse = {
    agent: typeof config.agent === "string" && config.agent ? config.agent : AGENT_PLACEHOLDER,
    key: typeof config.key === "string" && config.key ? config.key : KEY_PLACEHOLDER,
    ...presentation(config),
  };
  const body = JSON.stringify(full, null, 2)
    .split("\n")
    .map((l, i) => (i === 0 ? l : `  ${l}`))
    .join("\n");
  return [
    `import { VoqalizeWidget } from "@voqalize/web/react";`,
    "",
    "const config = " + body + ";",
    "",
    "export function Voice() {",
    "  return <VoqalizeWidget config={config} />;",
    "}",
  ].join("\n");
}

/** The JSON "Apply to my agent" would save as the agent's widget settings. */
export function settingsJson(config: Sparse): string {
  return JSON.stringify(presentation(config), null, 2);
}
