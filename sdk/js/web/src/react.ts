/**
 * `@voqalize/web/react`: the elements as React components, and hooks over the
 * controllers' stores.
 *
 *   import { VoqalizeWidget } from "@voqalize/web/react";
 *   <VoqalizeWidget config={{ agent, key, name: "Emily" }} onEnd={(e) => …} />
 *
 * React 18 sets every prop on a custom element as an attribute, which turns
 * an object into "[object Object]". These wrappers set props as properties
 * instead, and turn `onX` props into listeners for the `vql-x` event, so they
 * work the same on React 18 and 19. Rendering one registers the elements.
 *
 * The hooks read a store with `useSyncExternalStore`, so a page drawing its
 * own controls re-renders on exactly the controller's changes.
 */

import {
  type CSSProperties,
  type ForwardRefExoticComponent,
  type PropsWithoutRef,
  type ReactNode,
  type RefAttributes,
  createElement,
  forwardRef,
  useCallback,
  useLayoutEffect,
  useRef,
  useSyncExternalStore,
} from "react";
import type { CaptionsSnapshot } from "./controllers/captions.js";
import type { MicSnapshot } from "./controllers/mic.js";
import type { PlacementSnapshot } from "./controllers/placement.js";
import type { ReadableStore } from "./controllers/store.js";
import type { VqlCaptions } from "./elements/captions.js";
import type { VqlCoach } from "./elements/coach.js";
import { defineElements } from "./elements/define.js";
import type { VqlDevices } from "./elements/devices.js";
import type { VqlEnd } from "./elements/end.js";
import type { VqlFace } from "./elements/face.js";
import type { VqlLauncher } from "./elements/launcher.js";
import type { VqlMic } from "./elements/mic.js";
import type { VqlStatus } from "./elements/status.js";
import type { VqlWidget, WidgetSessionLike } from "./elements/widget.js";
import type { SessionSnapshot } from "./session/adapter.js";

// ------------------------------------------------------------------ wrapper

/** Props every wrapper takes besides the element's own. */
export interface BaseProps {
  id?: string;
  className?: string;
  style?: CSSProperties;
  slot?: string;
  children?: ReactNode;
  /** Plain attributes, set as written (for `data-*`, `aria-*` and the like). */
  attributes?: Record<string, string>;
}

type Handler = (event: CustomEvent) => void;

/** `onHangup` → `vql-hangup`, `onSelectMic` → `vql-select-mic`. */
export function eventName(prop: string): string {
  return `vql-${prop.slice(2).replace(/[A-Z]/g, (c, i: number) => (i === 0 ? c.toLowerCase() : `-${c.toLowerCase()}`))}`;
}

function attributeName(prop: string): string {
  return prop.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

const PASSTHROUGH = new Set(["id", "className", "style", "slot", "children", "attributes"]);

let defined = false;
function ensureDefined(): void {
  if (defined) return;
  defined = true;
  defineElements();
}

/**
 * A React component for a custom element: props become properties, `onX`
 * props become `vql-x` listeners. Exported for an element of your own built
 * on these.
 */
export function createComponent<E extends HTMLElement, P extends object>(
  tag: string,
): ForwardRefExoticComponent<PropsWithoutRef<P & BaseProps> & RefAttributes<E>> {
  const Component = forwardRef<E, P & BaseProps>((props, ref) => {
    ensureDefined();
    const local = useRef<E | null>(null);
    const handlers = useRef<Record<string, Handler>>({});
    const listening = useRef<Map<string, (e: Event) => void>>(new Map());
    const all = props as Record<string, unknown>;

    const setRef = useCallback(
      (el: E | null) => {
        local.current = el;
        if (typeof ref === "function") ref(el);
        else if (ref) ref.current = el;
      },
      [ref],
    );

    useLayoutEffect(() => {
      const el = local.current as unknown as (HTMLElement & Record<string, unknown>) | null;
      if (!el) return;
      const nextHandlers: Record<string, Handler> = {};
      for (const [name, value] of Object.entries(all)) {
        if (PASSTHROUGH.has(name)) continue;
        if (/^on[A-Z]/.test(name)) {
          if (typeof value === "function") nextHandlers[eventName(name)] = value as Handler;
          continue;
        }
        if (name in el) {
          if (el[name] !== value) el[name] = value;
        } else if (value === undefined || value === null || value === false) {
          el.removeAttribute(attributeName(name));
        } else {
          // An element with attributes only, such as the launcher.
          el.setAttribute(attributeName(name), value === true ? "" : String(value));
        }
      }
      handlers.current = nextHandlers;
      for (const type of Object.keys(nextHandlers)) {
        if (listening.current.has(type)) continue;
        const listener = (e: Event) => handlers.current[type]?.(e as CustomEvent);
        listening.current.set(type, listener);
        el.addEventListener(type, listener);
      }
      for (const [type, listener] of listening.current) {
        if (nextHandlers[type]) continue;
        el.removeEventListener(type, listener);
        listening.current.delete(type);
      }
    });

    const { id, className, style, slot, children, attributes } = props as BaseProps;
    return createElement(tag, { ref: setRef, id, class: className, style, slot, ...attributes }, children);
  });
  Component.displayName = tag;
  return Component;
}

// --------------------------------------------------------------- components

type EventProp<D = unknown> = (event: CustomEvent<D>) => void;
type Props<E, K extends keyof E> = Partial<Pick<E, K>>;

export type VoqalizeWidgetProps = Props<
  VqlWidget,
  "config" | "session" | "sessionSource" | "init" | "apiBase" | "statusLabel" | "instantStartOnIOS" | "browser"
> & {
  onView?: EventProp<{ view: string; form: string }>;
  onOpen?: EventProp;
  onCollapse?: EventProp;
  onClose?: EventProp;
  onEnd?: EventProp<{ reason: string }>;
  onMic?: EventProp<{ state: string; hint: boolean }>;
  onAgent?: EventProp<{ state: string }>;
  onPlace?: EventProp<{ anchor: string; point: { x: number; y: number }; free: boolean }>;
};

export const VoqalizeWidget = createComponent<VqlWidget, VoqalizeWidgetProps>("vql-widget");

export const VoqalizeLauncher = createComponent<
  VqlLauncher,
  { variant?: string; name?: string; label?: string; tagline?: string; still?: string; onLaunch?: EventProp; onPreload?: EventProp }
>("vql-launcher");

export const VoqalizeFace = createComponent<
  VqlFace,
  Props<VqlFace, "shape" | "framing" | "background" | "still" | "character" | "voiceOnly" | "agentState" | "client" | "scheme">
>("vql-face");

export const VoqalizeMic = createComponent<
  VqlMic,
  Props<VqlMic, "state" | "level" | "meter" | "hint" | "devices" | "expanded" | "scheme" | "t"> & {
    onMute?: EventProp<{ muted: boolean }>;
    onDevices?: EventProp<{ open: boolean }>;
  }
>("vql-mic");

export const VoqalizeDevices = createComponent<
  VqlDevices,
  Props<VqlDevices, "mics" | "speakers" | "micId" | "speakerId" | "canPickSpeaker" | "level" | "hint" | "t"> & {
    onSelectMic?: EventProp<{ id: string }>;
    onSelectSpeaker?: EventProp<{ id: string }>;
    onClose?: EventProp;
  }
>("vql-devices");

export const VoqalizeCaptions = createComponent<
  VqlCaptions,
  Props<VqlCaptions, "controller" | "snapshot" | "mode" | "scheme" | "t">
>("vql-captions");

export const VoqalizeCoach = createComponent<
  VqlCoach,
  Props<VqlCoach, "state" | "browser" | "placement" | "scheme" | "t"> & { onDismiss?: EventProp }
>("vql-coach");

export const VoqalizeStatus = createComponent<
  VqlStatus,
  Props<VqlStatus, "status" | "agent" | "mic" | "label" | "since" | "scheme" | "t">
>("vql-status");

export const VoqalizeEnd = createComponent<VqlEnd, Props<VqlEnd, "scheme" | "t"> & { onHangup?: EventProp }>("vql-end");

// -------------------------------------------------------------------- hooks

const NO_STORE: ReadableStore<undefined> = { subscribe: () => () => {}, getSnapshot: () => undefined };

/** A store's snapshot, re-read whenever the store changes. */
export function useVoqalizeStore<T>(store: ReadableStore<T>): T;
export function useVoqalizeStore<T>(store: ReadableStore<T> | null | undefined): T | undefined;
export function useVoqalizeStore<T>(store: ReadableStore<T> | null | undefined): T | undefined {
  const s = (store ?? NO_STORE) as ReadableStore<T | undefined>;
  const subscribe = useCallback((listener: () => void) => s.subscribe(listener), [s]);
  const read = useCallback(() => s.getSnapshot(), [s]);
  return useSyncExternalStore(subscribe, read, read);
}

/** The session's status, the agent's state, devices and the end reason. */
export function useSessionState(session: WidgetSessionLike | null | undefined): SessionSnapshot | undefined {
  return useVoqalizeStore(session ?? undefined);
}

/** The mic's state, level and hint. */
export function useMicState(session: WidgetSessionLike | null | undefined): MicSnapshot | undefined {
  return useVoqalizeStore(session?.mic);
}

/** The captions' lines, word by word. */
export function useCaptions(captions: ReadableStore<CaptionsSnapshot> | null | undefined): CaptionsSnapshot | undefined {
  return useVoqalizeStore(captions);
}

/** Where a placement controller has the widget. */
export function usePlacement(placement: ReadableStore<PlacementSnapshot> | null | undefined): PlacementSnapshot | undefined {
  return useVoqalizeStore(placement);
}
