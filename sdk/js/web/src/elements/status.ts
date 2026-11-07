/**
 * `<vql-status>`: a dot and a word for where the call is, with an optional
 * timer.
 *
 * Which word shows, first match wins:
 * - `label`, when the page or a brain's action set one ("Checking catalog…");
 * - connecting, or ended;
 * - the mic, when the agent cannot hear the visitor (`asking`, `blocked`,
 *   `missing`) or the visitor muted it;
 * - the agent: listening, thinking or speaking.
 *
 * Properties: `status` (the session's), `agent`, `mic`, `label`, `since`
 * (a start time in ms; shows a running mm:ss timer when set), `t`.
 *
 * Parts: `status`, `dot`, `word`, `timer`.
 */

import { LitElement, type PropertyValues, css, html, nothing } from "lit";
import type { MicState } from "../controllers/mic.js";
import type { AgentState, SessionStatus } from "../session/adapter.js";
import { themeStyles } from "./theme.js";
import { type Translate, translator } from "./words.js";

/** The words key and the dot's tone for a state. */
export function statusOf(
  status: SessionStatus,
  agent: AgentState,
  mic: MicState,
): { key: string; tone: "idle" | "listening" | "thinking" | "speaking" | "warn" | "muted" } {
  if (status === "connecting") return { key: "status.connecting", tone: "thinking" };
  if (status === "ended") return { key: "status.ended", tone: "idle" };
  if (status === "idle") return { key: "status.idle", tone: "idle" };
  if (mic === "asking" || mic === "blocked" || mic === "missing") return { key: `status.${mic}`, tone: "warn" };
  if (mic === "muted" && agent !== "speaking") return { key: "status.muted", tone: "muted" };
  if (agent === "idle") return { key: "status.listening", tone: "listening" };
  return { key: `status.${agent}`, tone: agent };
}

function clock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export class VqlStatus extends LitElement {
  static override properties = {
    status: { reflect: true },
    agent: { reflect: true },
    mic: { reflect: true },
    label: {},
    since: { type: Number },
    tone: { reflect: true },
    scheme: { reflect: true },
    t: { attribute: false },
    now: { state: true },
  };

  declare status: SessionStatus;
  declare agent: AgentState;
  declare mic: MicState;
  declare label: string | undefined;
  declare since: number | undefined;
  declare tone: string;
  declare scheme: string | undefined;
  declare t: Translate;
  declare protected now: number;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    super();
    this.status = "idle";
    this.agent = "idle";
    this.mic = "idle";
    this.tone = "idle";
    this.now = Date.now();
    this.t = translator(undefined, "en", "");
  }

  static override styles = [
    themeStyles,
    css`
      :host {
        display: inline-block;
      }
      .status {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 999px;
        background: var(--_surface);
        border: 1px solid var(--_line);
        font-size: 12px;
        font-weight: 600;
        line-height: 1.2;
        white-space: nowrap;
      }
      .dot {
        width: 8px;
        height: 8px;
        border-radius: 999px;
        background: var(--_muted);
      }
      :host([tone="listening"]) .dot {
        background: var(--_listening);
      }
      :host([tone="thinking"]) .dot {
        background: var(--_thinking);
        animation: vql-pulse 1s ease-in-out infinite;
      }
      :host([tone="speaking"]) .dot {
        background: var(--_speaking);
      }
      :host([tone="warn"]) .dot {
        background: var(--_danger);
      }
      :host([tone="muted"]) .dot {
        background: var(--_ink);
      }
      .timer {
        font-variant-numeric: tabular-nums;
        font-weight: 500;
        color: var(--_muted);
      }
      @keyframes vql-pulse {
        50% {
          opacity: 0.35;
        }
      }
    `,
  ];

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.stopTimer();
  }

  protected override willUpdate(changed: PropertyValues<this>): void {
    this.tone = statusOf(this.status, this.agent, this.mic).tone;
    if (changed.has("since") || changed.has("status")) {
      if (this.since !== undefined && this.status === "connected") this.startTimer();
      else this.stopTimer();
    }
  }

  private startTimer(): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      this.now = Date.now();
    }, 1000);
  }

  private stopTimer(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  protected override render() {
    const { key } = statusOf(this.status, this.agent, this.mic);
    const word = this.label || this.t(key);
    return html`<span class="status" part="status" role="status">
      <span class="dot" part="dot" aria-hidden="true"></span>
      <span part="word">${word}</span>
      ${this.since !== undefined && this.status === "connected"
        ? html`<span class="timer" part="timer">${clock(this.now - this.since)}</span>`
        : nothing}
    </span>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-status": VqlStatus;
  }
}
