import { describe, expect, it, vi } from "vitest";
import {
  READ_KEYWORDS,
  type SchemaNode,
  WIDGET_CONFIG_SCHEMA,
  defaultWidgetConfig,
  parseDuration,
  parseWidgetConfig,
} from "../src/config/parse.js";
import type { WidgetConfig, WidgetConfigInput } from "../src/config/types.js";

/** Every default, written out by hand: the drift check between the schema and `WidgetConfig`. */
const DEFAULTS: WidgetConfig = {
  avatar: { shape: "rounded", framing: "shoulders", background: "none" },
  placement: {
    mode: "corner",
    anchor: "bottom-right",
    move: "snap",
    remember: "tab",
    offset: 16,
    avoid: [],
    topClear: 0,
  },
  launcher: { style: "pill" },
  open: { style: "card", size: "medium" },
  collapsed: { style: "bubble", autoCollapse: true },
  mobile: { open: "sheet", launcher: "face", breakpoint: 480 },
  controls: { mute: true, end: true, minimise: true, devices: true, language: true },
  mic: { level: "ring", instantStart: true, silenceHint: true },
  captions: { mode: "karaoke", lines: 2, linger: "4s", showUser: false, position: "card" },
  theme: { scheme: "auto", font: "inherit", tokens: {} },
  words: {},
  dir: "auto",
};

/** A configuration that sets every field the schema has. */
const FULL: Required<WidgetConfigInput> = {
  agent: "agent_example",
  key: "pk_example",
  name: "Emily",
  avatar: {
    character: "emily",
    shape: "circle",
    framing: "face",
    background: { url: "https://example.com/bg.webp", fit: "contain" },
    still: "/still.webp",
  },
  placement: {
    mode: "inline",
    anchor: "middle-left",
    move: "free",
    remember: "site",
    offset: { x: 24, y: 12 },
    avoid: ["#cookie-banner"],
    topClear: 64,
  },
  launcher: { style: "card", label: "Ask Emily", tagline: "She knows the catalogue" },
  open: { style: "hero", size: "large" },
  collapsed: { style: "pill", autoCollapse: false },
  mobile: { open: "hero", launcher: "pill", breakpoint: 600 },
  controls: { mute: false, end: false, minimise: false, devices: false, language: false },
  mic: { level: "bars", instantStart: false, silenceHint: false },
  captions: { mode: "rolling", lines: 3, linger: 800, showUser: true, position: "page" },
  theme: {
    brand: "#112233",
    background: "#ffffff",
    ink: "#000000",
    scheme: "dark",
    radius: 12,
    font: "Inter, sans-serif",
    tokens: { "--vq-caption-size": "18px" },
  },
  words: { en: { "launcher.label": "Talk to {name}" }, "hi-IN": { "launcher.label": "{name} से बात करें" } },
  dir: "rtl",
};

function collect() {
  const warnings: string[] = [];
  return { warnings, warn: (m: string) => warnings.push(m) };
}

describe("parseWidgetConfig", () => {
  it("fills every default from an empty object", () => {
    const { warnings, warn } = collect();
    expect(parseWidgetConfig({}, warn)).toEqual(DEFAULTS);
    expect(warnings).toEqual([]);
    expect(defaultWidgetConfig()).toEqual(DEFAULTS);
  });

  it("reads a configuration that sets every field, with no warning", () => {
    const { warnings, warn } = collect();
    const config = parseWidgetConfig(FULL, warn);
    expect(warnings).toEqual([]);
    expect(config).toEqual(FULL);
  });

  it("covers every field of the schema in the full sample", () => {
    // A field added to the schema and not to FULL (and so not to the types) fails here.
    const missing: string[] = [];
    const walk = (node: SchemaNode, value: unknown, path: string) => {
      const object = node.properties ? node : (node.oneOf ?? node.anyOf)?.find((b) => b.properties);
      if (!object?.properties) return;
      for (const [key, child] of Object.entries(object.properties)) {
        const v = (value as Record<string, unknown> | undefined)?.[key];
        if (v === undefined) missing.push(path ? `${path}.${key}` : key);
        else if (typeof v === "object" && v !== null && !Array.isArray(v)) walk(child, v, path ? `${path}.${key}` : key);
      }
    };
    walk(WIDGET_CONFIG_SCHEMA, FULL, "");
    expect(missing).toEqual([]);
  });

  it("uses only the schema keywords the parser reads", () => {
    const unread = new Set<string>();
    const walk = (node: unknown) => {
      if (Array.isArray(node)) return node.forEach(walk);
      if (typeof node !== "object" || node === null) return;
      for (const [key, value] of Object.entries(node)) {
        if (!READ_KEYWORDS.has(key)) unread.add(key);
        if (key === "properties") Object.values(value as object).forEach(walk);
        else if (key !== "default" && key !== "enum" && key !== "const") walk(value);
      }
    };
    walk(WIDGET_CONFIG_SCHEMA);
    expect([...unread]).toEqual([]);
  });

  it("never throws, whatever it is given", () => {
    const warn = vi.fn();
    for (const input of [null, undefined, 42, "nope", "[1]", [], true, { placement: null }, { avatar: "yes" }]) {
      expect(() => parseWidgetConfig(input, warn)).not.toThrow();
      expect(parseWidgetConfig(input, warn).placement.anchor).toBe("bottom-right");
    }
  });

  it("names every unknown field in one warning and ignores them", () => {
    const { warnings, warn } = collect();
    const config = parseWidgetConfig(
      { future: 1, placement: { anchor: "top-left", gravity: "up" }, mic: { echo: true } },
      warn,
    );
    expect(config.placement.anchor).toBe("top-left");
    expect(config).not.toHaveProperty("future");
    expect(config.placement).not.toHaveProperty("gravity");
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain("future");
    expect(warnings[0]).toContain("placement.gravity");
    expect(warnings[0]).toContain("mic.echo");
  });

  it("falls back to the default for an invalid value, with a warning naming it", () => {
    const { warnings, warn } = collect();
    const config = parseWidgetConfig(
      {
        placement: { anchor: "bottom-middle", offset: -3, topClear: "lots" },
        captions: { lines: 2.5, linger: "soon" },
        theme: { brand: "red", tokens: { "--vq-ok": "1px", "--not-ours": "x" } },
        mobile: { breakpoint: 99999 },
        key: "sk_secret",
      },
      warn,
    );
    expect(config.placement.anchor).toBe("bottom-right");
    expect(config.placement.offset).toBe(16);
    expect(config.placement.topClear).toBe(0);
    expect(config.captions.lines).toBe(2);
    expect(config.captions.linger).toBe("4s");
    expect(config.theme.brand).toBeUndefined();
    expect(config.theme.tokens).toEqual({ "--vq-ok": "1px" });
    expect(config.mobile.breakpoint).toBe(480);
    expect(config.key).toBeUndefined();
    const text = warnings.join("\n");
    for (const path of [
      "placement.anchor",
      "placement.offset",
      "placement.topClear",
      "captions.lines",
      "captions.linger",
      "theme.brand",
      "--not-ours",
      "mobile.breakpoint",
      "key",
    ]) {
      expect(text).toContain(path);
    }
  });

  it("keeps the valid fields beside an invalid one", () => {
    const config = parseWidgetConfig({ avatar: { shape: "hexagon", framing: "face" } }, () => {});
    expect(config.avatar).toEqual({ shape: "rounded", framing: "face", background: "none" });
  });

  it("reads avatar: false as a voice-only widget", () => {
    expect(parseWidgetConfig({ avatar: false }, () => {}).avatar).toBe(false);
    const { warnings, warn } = collect();
    expect(parseWidgetConfig({ avatar: true }, warn).avatar).toEqual(DEFAULTS.avatar);
    expect(warnings).toHaveLength(1);
  });

  it("takes either form where the schema offers a choice", () => {
    const c = parseWidgetConfig(
      { placement: { offset: { x: 30 } }, avatar: { background: "linear-gradient(#fff, #000)" } },
      () => {},
    );
    expect(c.placement.offset).toEqual({ x: 30, y: 16 });
    expect(c.avatar && c.avatar.background).toBe("linear-gradient(#fff, #000)");
    const { warnings, warn } = collect();
    const d = parseWidgetConfig({ avatar: { background: { fit: "cover" } } }, warn);
    expect(d.avatar && d.avatar.background).toBe("none");
    expect(warnings.join()).toContain("avatar.background");
  });

  it("drops invalid items of a list and keeps the rest", () => {
    const { warnings, warn } = collect();
    const c = parseWidgetConfig({ placement: { avoid: ["#a", "", 3, ".b"] } }, warn);
    expect(c.placement.avoid).toEqual(["#a", ".b"]);
    expect(warnings).toHaveLength(2);
  });

  it("reads JSON text, as an attribute carries it", () => {
    expect(parseWidgetConfig('{"placement":{"anchor":"top-left"}}', () => {}).placement.anchor).toBe("top-left");
    const { warnings, warn } = collect();
    expect(parseWidgetConfig("{oops", warn)).toEqual(DEFAULTS);
    expect(warnings).toHaveLength(1);
  });

  it("does not share default objects between results", () => {
    const a = parseWidgetConfig({}, () => {});
    a.placement.avoid.push("#x");
    a.theme.tokens["--vq-x"] = "1";
    const b = parseWidgetConfig({}, () => {});
    expect(b.placement.avoid).toEqual([]);
    expect(b.theme.tokens).toEqual({});
  });

  it("warns on the console by default", () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    parseWidgetConfig({ nope: 1 });
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});

describe("parseDuration", () => {
  it("reads seconds, milliseconds and numbers", () => {
    expect(parseDuration("4s")).toBe(4000);
    expect(parseDuration("1.5s")).toBe(1500);
    expect(parseDuration("800ms")).toBe(800);
    expect(parseDuration(250)).toBe(250);
  });

  it("falls back on anything else", () => {
    expect(parseDuration("soon")).toBe(4000);
    expect(parseDuration(-1, 10)).toBe(10);
    expect(parseDuration(Number.NaN, 10)).toBe(10);
  });
});
