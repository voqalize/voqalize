/**
 * The live page: one `<vql-widget>` against a real stack. The test injects
 * the agent, the publishable key and the API base at runtime
 * (`window.__vqlE2EConfig`), so none of them is in the page or the repo.
 * Every `vql-*` event is recorded on the probe's clock.
 */

import { defineElements, setAvatarLoader } from "../../src/widgets.js";

interface E2EConfig {
  agent: string;
  key: string;
  api: string;
  attributes?: Record<string, string>;
  avatar?: boolean;
}

const cfg = (window as unknown as { __vqlE2EConfig: E2EConfig }).__vqlE2EConfig;
// The avatar is its own release; this page tests the widget around it.
if (!cfg.avatar) setAvatarLoader(() => Promise.reject(new Error("no avatar on the live page")));
defineElements();

const widget = document.createElement("vql-widget");
widget.setAttribute("agent", cfg.agent);
widget.setAttribute("key", cfg.key);
widget.setAttribute("api-base", cfg.api);
for (const [name, value] of Object.entries(cfg.attributes ?? {})) widget.setAttribute(name, value);

for (const type of ["vql-open", "vql-collapse", "vql-close", "vql-view", "vql-place", "vql-mic", "vql-agent", "vql-end"]) {
  widget.addEventListener(type, (e) => window.__vqlE2E?.push("ui", type, (e as CustomEvent).detail));
}
document.body.append(widget);
