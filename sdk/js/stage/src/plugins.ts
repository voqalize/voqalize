/**
 * Page plugins: code of ours, compiled into the runtime, that does one typed
 * thing the steps cannot — a same-origin read of a store's live prices.
 *
 * A plugin is declared in the spec (`plugins`: its class, arguments, output
 * fields, the origins it may request, a deadline) and its code is registered
 * here against that declaration. The declaration is the bound, enforced on
 * every run, so a review reads it instead of the code:
 *
 * - it answers within `deadline_ms`, or the run fails and its requests are aborted;
 * - it requests only its `egress` origins, through the `fetch` it is handed, and
 *   never with the visitor's cookies;
 * - only its declared `output` fields leave it, and never one marked private.
 *
 * Plugins are never fetched at run time: there is no loader, only `register`.
 */

import type { ArgSpec, FieldSpec } from "./scene";

export interface PluginSpec {
  readonly name: string;
  readonly major: number;
  readonly side: "brain" | "page";
  readonly class: "look" | "navigate" | "reversible";
  readonly args?: readonly ArgSpec[];
  readonly output?: readonly FieldSpec[];
  readonly egress?: readonly string[];
  readonly deadline_ms: number;
  readonly pii?: boolean;
}

export interface PluginContext {
  /** `fetch`, only to the plugin's own origins, without cookies, aborted at its deadline. */
  fetch: (input: string | URL, init?: RequestInit) => Promise<Response>;
  signal: AbortSignal;
}

export type PluginImpl<A = Record<string, unknown>> = (args: A, ctx: PluginContext) => Promise<unknown>;

/** Why a plugin's run did not answer. */
export class PluginError extends Error {}

function keep(fields: readonly FieldSpec[], value: unknown): unknown {
  if (Array.isArray(value)) return value.map((v) => keep(fields, v));
  if (!value || typeof value !== "object") return value;
  const data = value as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.private || !(f.name in data)) continue;
    out[f.name] = f.fields ? keep(f.fields, data[f.name]) : data[f.name];
  }
  return out;
}

export class Plugins {
  private readonly impls = new Map<string, { decl: PluginSpec; impl: PluginImpl<never> }>();

  constructor(
    private readonly declared: readonly PluginSpec[],
    private readonly base: () => string = () => location.href,
    private readonly fetcher: typeof fetch = (...a) => fetch(...a),
  ) {}

  /** The code for a declared page plugin. One the spec does not declare, or
   *  a brain plugin, is refused here. */
  register<A>(name: string, impl: PluginImpl<A>): void {
    const decl = this.declared.find((p) => p.name === name);
    if (!decl) throw new PluginError(`no plugin ${name} is declared`);
    if (decl.side !== "page") throw new PluginError(`${name} is a brain plugin; it does not run on the page`);
    this.impls.set(name, { decl, impl: impl as PluginImpl<never> });
  }

  has(name: string): boolean {
    return this.impls.has(name);
  }

  /** Run a plugin within its bounds; its declared output, and nothing else. */
  async run(name: string, args: Record<string, unknown> = {}): Promise<unknown> {
    const got = this.impls.get(name);
    if (!got) throw new PluginError(`no plugin ${name} is registered`);
    const { decl, impl } = got;
    const abort = new AbortController();
    const allowed = new Set(decl.egress ?? []);
    const ctx: PluginContext = {
      signal: abort.signal,
      fetch: (input, init = {}) => {
        const url = new URL(String(input), this.base());
        if (!allowed.has(url.origin)) {
          return Promise.reject(new PluginError(`${name} may not request ${url.origin}`));
        }
        return this.fetcher(url, { ...init, credentials: "omit", signal: abort.signal });
      },
    };
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        abort.abort();
        reject(new PluginError(`${name} did not answer within ${decl.deadline_ms} ms`));
      }, decl.deadline_ms);
    });
    try {
      const out = await Promise.race([impl(args as never, ctx), deadline]);
      return decl.output?.length ? keep(decl.output, out) : out;
    } finally {
      clearTimeout(timer);
    }
  }
}
