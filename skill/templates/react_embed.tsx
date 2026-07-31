/**
 * Embed your Voqalize agent in a React app — with a live, voice-driven UI.
 *
 *   npm install @voqalize/client-react     # or pnpm/yarn add
 *
 * This template shows the full two-way loop a screen-driving app needs:
 *   • voice in / voice out (the SDK handles WebRTC + mic + audio),
 *   • brain → screen: the brain's `interaction.action("add_to_cart", {...})`
 *     arrives here as an `onServerMessage` payload and updates the cart,
 *   • screen → brain: a tap calls `session.sendMessage(...)`, which the brain
 *     receives in `on_app_event`.
 *
 * The message shapes are fixed by the platform:
 *   brain → browser (onServerMessage):
 *     { type: "ui_command", action: <name>, action_id: <int>, ...args }
 *   browser → brain (sendMessage(type, data)):
 *     arrives as on_app_event(name=type, data=data)
 *
 * Publishable keys are origin-allowlisted and safe in the browser — mint one with
 * the `create_api_key` MCP tool (kind="publishable", allowed_origins=[...]).
 * NEVER put an sk_ key in frontend code.
 *
 * Fill in the four values below from your Voqalize agent:
 *   - PUBLISHABLE_KEY: the pk_… you minted
 *   - AGENT_ID:        agent.id from create_agent / list_agents
 *   - TENANT_SLUG:     your tenant slug (the one `list_tenants` returned; pass
 *                      it to every MCP tool)
 *   - API_BASE:        control-plane root INCLUDING the version — the React SDK
 *                      appends `/{tenantSlug}/…`. Prod: https://app.voqalize.com/api/v1
 */

import { useState } from "react";
import { VoqalAgent } from "@voqalize/client-react";

const PUBLISHABLE_KEY = "pk_live_REPLACE_ME";
const AGENT_ID = "REPLACE_WITH_AGENT_ID";
const TENANT_SLUG = "your-tenant-slug";
const API_BASE = "https://app.voqalize.com/api/v1";

interface CartLine {
  sku: string;
  qty: number;
}

export function VoiceCart() {
  const [cart, setCart] = useState<CartLine[]>([]);

  return (
    <VoqalAgent
      apiBase={API_BASE}
      tenantSlug={TENANT_SLUG}
      publishableKey={PUBLISHABLE_KEY}
      agentId={AGENT_ID}
      // What you pass here arrives brain-side as `start.init` in on_session_start.
      payload={{ surface: "web", user: { name: "Ada" } }}
      // Brain → screen. Every `interaction.action(...)` the brain fires lands here.
      onServerMessage={(msg) => {
        if (msg.type !== "ui_command") return;
        switch (msg.action) {
          case "add_to_cart":
            setCart((c) => [...c, { sku: String(msg.sku), qty: Number(msg.qty) }]);
            break;
          case "checkout":
            // drive your checkout flow…
            break;
        }
      }}
    >
      {(session) => (
        <div>
          <ul>
            {cart.map((line, i) => (
              <li key={i}>
                {line.qty}× {line.sku}{" "}
                {/* Screen → brain: report a manual removal so the brain stays in sync. */}
                <button
                  onClick={() => {
                    setCart((c) => c.filter((_, j) => j !== i));
                    session.sendMessage("cart_edited", { removed: line.sku });
                  }}
                >
                  remove
                </button>
              </li>
            ))}
          </ul>
          <button onClick={session.connect} disabled={session.connectionState !== "idle"}>
            Talk ({session.connectionState})
          </button>
        </div>
      )}
    </VoqalAgent>
  );
}
