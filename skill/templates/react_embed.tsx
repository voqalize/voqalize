/**
 * Embed your Voqalize agent in a React app — with a live, voice-driven UI.
 *
 *   npm install @voqalize/client-react     # or pnpm/yarn add
 *
 * This template shows the full two-way loop a screen-driving app needs:
 *   • voice in / voice out (the SDK handles WebRTC + mic + audio),
 *   • brain → screen: the brain's `interaction.action(AddToCart(...))` arrives at
 *     the `useUiCommand` handler of that name and updates the cart,
 *   • screen → brain: a tap calls `session.sendMessage(...)`, which the brain
 *     receives in `on_client_message`.
 *
 * The message shapes are fixed by the platform:
 *   brain → browser (a `ui_command` server message):
 *     { type: "ui_command", action: <name>, action_id: <int>, ...args }
 *     `useUiCommand` strips the envelope and hands your handler the args alone.
 *   browser → brain (sendMessage(type, data)):
 *     arrives as on_client_message(message.type, message.data)
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
 *
 * And one you should set deliberately rather than inherit: PIPELINE, the STT/TTS
 * the session opens with (voice + language). See the voice & language catalog at
 * /docs/reference/catalog/. The brain changes it mid-call with the single call
 * session.configure_language("hi").
 */

import { useState } from "react";
import {
  VoqalAgent,
  useUiCommand,
  type VoqalPipelineConfig,
  type VoqalSessionHandle,
} from "@voqalize/client-react";

const PUBLISHABLE_KEY = "pk_live_REPLACE_ME";
const AGENT_ID = "REPLACE_WITH_AGENT_ID";
const TENANT_SLUG = "your-tenant-slug";
const API_BASE = "https://app.voqalize.com/api/v1";

/**
 * Speech config for the session. `vql-stt` is a router covering English plus 22
 * Indic languages — it picks the engine from `language`. `tts.voice` is a catalog
 * voice id. Omit `pipeline` entirely to take the server defaults.
 *
 * SET `language` TO THE SAME CODE ON BOTH LINES. That is the only supported way
 * to pick a language, and the pair is not decorative: `stt.language` picks the
 * recognizer, `tts.language` picks the voice-cloning reference clip (i.e. which
 * recorded speaker you hear). Half-applied, neither one errors — you just get a
 * bad transcript, or the right words in a non-native accent.
 */
const PIPELINE: VoqalPipelineConfig = {
  stt: { model: "vql-stt", language: "en" },
  tts: { voice: "omnivoice/gauri", language: "en" },
};

interface CartLine {
  sku: string;
  qty: number;
}

/**
 * The screen contract, one entry per `voqalize.sdk.Action` subclass in the brain.
 * Python is the source of truth for these shapes; keeping them here means a field
 * renamed brain-side is a compile error, not an `undefined` on screen.
 */
interface ShopCommands {
  add_to_cart: { sku: string; qty: number };
  checkout: { total: number };
}

export function VoiceCart() {
  const [cart, setCart] = useState<CartLine[]>([]);

  return (
    <VoqalAgent
      apiBase={API_BASE}
      tenantSlug={TENANT_SLUG}
      publishableKey={PUBLISHABLE_KEY}
      agentId={AGENT_ID}
      // Voice + language for this session. Distinct from `payload` below: this is
      // speech config the platform consumes, not app data the brain reads.
      pipeline={PIPELINE}
      // What you pass here arrives brain-side as `start.init` in on_session_start.
      payload={{ surface: "web", user: { name: "Ada" } }}
    >
      {(session) => <Cart session={session} cart={cart} setCart={setCart} />}
    </VoqalAgent>
  );
}

function Cart({
  session,
  cart,
  setCart,
}: {
  session: VoqalSessionHandle;
  cart: CartLine[];
  setCart: React.Dispatch<React.SetStateAction<CartLine[]>>;
}) {
  // Brain → screen. Every `interaction.action(...)` the brain fires is dispatched
  // by name; the handler receives the args alone, typed by ShopCommands. Pass the
  // type argument explicitly — an inline map gives TS nothing to infer from.
  useUiCommand<ShopCommands>(session.client, {
    add_to_cart: ({ sku, qty }) => setCart((c) => [...c, { sku, qty }]),
    checkout: ({ total }) => {
      // drive your checkout flow…
      console.log("checkout", total);
    },
  });

  return (
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
  );
}
