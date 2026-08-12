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
 * the `create_api_key` MCP tool (agent_id=<this agent>, kind="publishable",
 * allowed_origins=[...]). The key names one agent — the one this embed talks to.
 * NEVER put an sk_ key in frontend code.
 *
 * Fill in the three values below from your Voqalize agent:
 *   - PUBLISHABLE_KEY: the pk_… you minted
 *   - AGENT_ID:        agent.id from create_agent / list_agents
 *   - API_BASE:        control-plane root INCLUDING the version — the React SDK
 *                      appends `/sessions.create_and_start`.
 *                      Prod: https://app.voqalize.com/api/v1
 *
 * There is no workspace to fill in: the pk_ key belongs to exactly one, so the
 * control plane reads it off the key. (MCP tools still take a `tenant` — they are
 * stateless and hold no credential that names one.)
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
  type VoqalSessionHandle,
} from "@voqalize/client-react";

const PUBLISHABLE_KEY = "pk_live_REPLACE_ME";
const AGENT_ID = "REPLACE_WITH_AGENT_ID";
const API_BASE = "https://app.voqalize.com/api/v1";

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
      publishableKey={PUBLISHABLE_KEY}
      agentId={AGENT_ID}
      // No voice or language here: the brain declares them (`Brain.voice` /
      // `Brain.language`, or `session.configure_language(...)` per caller). One
      // owner — a language split across a page and an agent record fails silently,
      // because `language` picks BOTH the recognizer and the voice-cloning
      // reference clip, and a wrong clip is the right words in the wrong accent.
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
