/**
 * What the builder tells each preview frame, and what a frame answers. The
 * frames are same-origin pages; messages are checked against that origin.
 */

import type { Sparse } from "./schema-form.js";

/** The states the preview can show, each reached through the real widget. */
export const PREVIEW_STATES = [
  { id: "closed", label: "Closed" },
  { id: "speaking", label: "Speaking" },
  { id: "collapsed", label: "Collapsed" },
  { id: "asking", label: "Mic asking" },
  { id: "blocked", label: "Mic blocked" },
  { id: "muted", label: "Muted" },
  { id: "silent", label: "Silent mic" },
  { id: "ended", label: "Ended" },
] as const;

export type PreviewState = (typeof PREVIEW_STATES)[number]["id"];

/** A real call: the agent, its publishable key and the control plane to mint from. */
export interface TalkTarget {
  agent: string;
  key: string;
  apiBase?: string;
}

export interface PreviewMessage {
  type: "vql-builder";
  config: Sparse;
  state: PreviewState;
  page: "light" | "dark";
  /** Present while the visitor is talking to a real agent in this frame. */
  talk?: TalkTarget;
}

export interface PreviewReport {
  type: "vql-preview";
  view: string;
  form: string;
  /** The call ended in this frame (a real call, or the preview's own end button). */
  ended?: boolean;
}
