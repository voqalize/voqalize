/** A page plugin runs within the bounds its declaration sets. */

import { afterEach, describe, expect, it, vi } from "vitest";

import { PluginError, Plugins, type PluginSpec } from "../src/plugins";

const PRICES: PluginSpec = {
  name: "magento.prices",
  major: 1,
  side: "page",
  class: "look",
  output: [{ name: "path" }, { name: "price", type: "number" }, { name: "cost", private: true }],
  egress: ["https://shop.test"],
  deadline_ms: 1000,
};

const BRAIN: PluginSpec = { name: "kb.lookup", major: 1, side: "brain", class: "look", deadline_ms: 20 };

function plugins(fetcher = vi.fn(async () => new Response("{}"))) {
  return { p: new Plugins([PRICES, BRAIN], () => "https://shop.test/sabanas", fetcher as never), fetcher };
}

afterEach(() => vi.useRealTimers());

describe("Plugins", () => {
  it("registers only a declared page plugin", () => {
    const { p } = plugins();
    expect(() => p.register("magento.stock", async () => null)).toThrow(/no plugin magento.stock is declared/);
    expect(() => p.register("kb.lookup", async () => null)).toThrow(/brain plugin/);
  });

  it("requests its own origin only, never with cookies", async () => {
    const { p, fetcher } = plugins();
    p.register("magento.prices", async (_, ctx) => {
      await ctx.fetch("/graphql", { method: "POST", credentials: "include" });
      return [];
    });
    await p.run("magento.prices");
    const [url, init] = fetcher.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe("https://shop.test/graphql");
    expect(init.credentials).toBe("omit");

    p.register("magento.prices", async (_, ctx) => ctx.fetch("https://tracker.test/x"));
    await expect(p.run("magento.prices")).rejects.toThrow(/may not request https:\/\/tracker.test/);
  });

  it("gives only the declared output, private fields never", async () => {
    const { p } = plugins();
    p.register("magento.prices", async () => [{ path: "/a", price: 1, cost: 0.5, sku: "X" }]);
    expect(await p.run("magento.prices")).toEqual([{ path: "/a", price: 1 }]);
  });

  it("fails past its deadline and aborts what it asked for", async () => {
    vi.useFakeTimers();
    const { p } = plugins();
    let signal: AbortSignal | null = null;
    p.register("magento.prices", (_, ctx) => {
      signal = ctx.signal;
      return new Promise(() => {});
    });
    const run = p.run("magento.prices");
    const failed = expect(run).rejects.toThrow(PluginError);
    await vi.advanceTimersByTimeAsync(1000);
    await failed;
    expect(signal!.aborted).toBe(true);
  });
});
