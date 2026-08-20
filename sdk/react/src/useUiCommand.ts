/**
 * useUiCommand — the browser half of a typed UI command.
 *
 * A screen-driving brain fires `ui_command`s at the page (`session.action(...)`
 * / `interaction.action(...)`). They arrive as RTVI server messages shaped
 *
 *     { type: "ui_command", action: "open_itinerary", action_id: 7, ...args }
 *
 * — the envelope, then the action's own arguments spread onto the top level.
 * Handling them by hand means the same three lines in every app: subscribe to
 * server messages, filter on `type`, `switch` on `action`, then re-coerce every
 * argument out of an untyped bag. This hook is those three lines, once:
 *
 *     useUiCommand(client, {
 *       open_itinerary: ({ name }) => setItinerary(name),
 *       select_flight: ({ leg_id, option_id }) => choose(leg_id, option_id),
 *     });
 *
 * The handler receives **only the arguments** — `type`, `action` and `action_id`
 * are stripped, because they are the transport's, not yours.
 *
 * ## Typing it against the brain
 *
 * Declare the command map — wire name → argument shape — and pass it as the type
 * argument. Every handler's parameter is then that action's args, so a renamed
 * field is a compile error rather than an `undefined` that reaches the screen:
 *
 *     interface TravelCommands {
 *       open_itinerary: { name: string };
 *       select_flight: { leg_id: string; option_id: string };
 *     }
 *
 *     useUiCommand<TravelCommands>(client, {
 *       open_itinerary: ({ name }) => open(name),          // name: string
 *       select_flight: ({ leg_id, option_id }) => pick(leg_id, option_id),
 *     });
 *
 * Write the type argument explicitly — an inline handler map has nothing for TypeScript
 * to infer it from. The map is checked both ways: an action you didn't declare is
 * rejected, and each handler's parameter is that action's args. Python is the
 * source of truth for the shapes — one `voqalize.sdk.Action` subclass per command.
 *
 * An action with no handler is not an error (the brain and the UI ship
 * separately, and a new command reaching an old page must not break it): it goes
 * to the optional `"*"` wildcard, else to `console.debug`.
 */

import { useEffect, useRef } from "react";
import { type PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";

/** The envelope keys a `ui_command` owns. Stripped before dispatch. */
const ENVELOPE_KEYS = ["type", "action", "action_id"] as const;

/**
 * One command off the wire: the envelope plus the action's own arguments spread
 * onto the top level. You rarely name this type — handlers see the args alone.
 */
export interface UiCommand {
  type: "ui_command";
  /** The wire name, e.g. `"open_itinerary"`. */
  action: string;
  /** Session-monotonic id. Echo it back with `sendMessage("action_result", …)`. */
  action_id: number;
  [arg: string]: unknown;
}

/** Args of any action not declared in a command map. */
export type UiCommandArgs = Record<string, unknown>;

/**
 * A map from wire name to handler, checked against a command-shape map `T`.
 *
 * Every entry is optional (a page may handle a subset), no unknown key is
 * allowed, and `"*"` catches everything unhandled — it receives the whole
 * envelope, since without a name the args alone mean nothing.
 */
export type UiCommandHandlers<T extends object = Record<string, UiCommandArgs>> = {
  [K in keyof T]?: (args: T[K], command: UiCommand) => void;
} & {
  "*"?: (command: UiCommand) => void;
};

/**
 * Identity helper that pins a handler map to a command-shape map without
 * writing the generic at the `useUiCommand` call site — handy when the map is
 * defined away from the hook (a module constant, a `useMemo`).
 *
 *     const handlers = createUiCommandHandlers<TravelCommands>({ ... });
 *     useUiCommand(client, handlers);
 */
export function createUiCommandHandlers<T extends object>(
  handlers: UiCommandHandlers<T>
): UiCommandHandlers<T> {
  return handlers;
}

/** Defensive unwrap for the `RTVIEvent.ServerMessage` `{ data }` quirk. */
function unwrap(raw: unknown): Record<string, unknown> {
  const obj = (raw ?? {}) as Record<string, unknown>;
  const inner = obj["data"] as Record<string, unknown> | undefined;
  return inner && "type" in inner ? inner : obj;
}

/** The command minus the envelope keys — what a handler actually wants. */
export function uiCommandArgs(command: UiCommand): UiCommandArgs {
  const args: UiCommandArgs = { ...command };
  for (const key of ENVELOPE_KEYS) delete args[key];
  return args;
}

/**
 * Subscribe to the brain's `ui_command`s and dispatch each to a named handler.
 *
 * @param client The live `PipecatClient` (`null` before connect — the hook then
 *   does nothing and re-subscribes once one exists).
 * @param handlers Wire name → handler. Read through a ref, so an inline object
 *   literal is fine: re-rendering does not re-subscribe, and a handler always
 *   sees the render it was defined in.
 */
export function useUiCommand<T extends object = Record<string, UiCommandArgs>>(
  client: PipecatClient | null,
  handlers: UiCommandHandlers<T>
): void {
  // Latest-handlers ref: the subscription depends only on the client, so a new
  // object literal every render costs nothing and closures stay fresh.
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!client) return;

    const onServerMessage = (raw: unknown) => {
      const message = unwrap(raw);
      if (message["type"] !== "ui_command") return;

      const command = message as UiCommand;
      const map = handlersRef.current as Record<
        string,
        ((args: UiCommandArgs, command: UiCommand) => void) | undefined
      >;
      const handler = map[command.action];
      if (handler) {
        handler(uiCommandArgs(command), command);
        return;
      }
      const wildcard = handlersRef.current["*"];
      if (wildcard) {
        wildcard(command);
        return;
      }
      console.debug("[voqalize] unhandled ui_command", command.action, command);
    };

    client.on(RTVIEvent.ServerMessage, onServerMessage);
    return () => {
      client.off(RTVIEvent.ServerMessage, onServerMessage);
    };
  }, [client]);
}
