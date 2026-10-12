/**
 * The voice adapter. The shell only ever talks to this interface, so the simulated
 * voice used today and the live Voqalize call (pipecat + @voqalize/client-transport +
 * @voqalize/avatar, see platform/frontend/apps/marketing/src/agent/session.ts) are
 * interchangeable.
 *
 * In the live version the brain drives the page with actions instead of the shell
 * routing text itself: `open_section(id)`, `close_section()`, `set_mode(mode)`. The
 * shell exposes those as `window.vq` (see shell.ts) so the action handler is one line each.
 */
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface Voice {
  readonly kind: 'simulated' | 'live';
  /** Speak a line. `onWord` fires as each word is spoken, for the captions. */
  say(text: string, onWord?: (index: number) => void): Promise<void>;
  /** Stop speaking now (an interruption). */
  stop(): void;
  onState(cb: (s: VoiceState) => void): void;
  setState(s: VoiceState): void;
}

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

export class SimulatedVoice implements Voice {
  readonly kind = 'simulated' as const;
  /** Milliseconds per word. Roughly a calm speaking pace. */
  wordMs = 230;
  private timer: number | undefined;
  private cancel: (() => void) | undefined;
  private listeners: Array<(s: VoiceState) => void> = [];

  onState(cb: (s: VoiceState) => void) { this.listeners.push(cb); }
  setState(s: VoiceState) { this.listeners.forEach((cb) => cb(s)); }

  say(text: string, onWord?: (index: number) => void): Promise<void> {
    this.stop();
    const words = text.split(/\s+/).filter(Boolean);
    return new Promise((resolve) => {
      if (reduced()) { words.forEach((_, i) => onWord?.(i)); this.setState('listening'); resolve(); return; }
      this.setState('speaking');
      let i = 0;
      this.cancel = resolve;
      this.timer = window.setInterval(() => {
        if (i >= words.length) { this.finish(); return; }
        onWord?.(i++);
      }, this.wordMs);
    });
  }

  stop() { if (this.timer !== undefined) { window.clearInterval(this.timer); this.timer = undefined; this.cancel?.(); this.cancel = undefined; } }

  private finish() { this.stop(); this.setState('listening'); }
}
