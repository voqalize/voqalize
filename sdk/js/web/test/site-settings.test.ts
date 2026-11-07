import { describe, expect, it } from "vitest";
import { defaultWidgetConfig } from "../src/config/parse.js";
import { mergeInput, siteSettingsToInput, widgetConfigFromSiteSettings } from "../src/config/site-settings.js";

describe("widgetConfigFromSiteSettings", () => {
  it("maps the Site Agent's look onto the widget", () => {
    const { config, greeting } = widgetConfigFromSiteSettings(
      {
        assistant_name: "Maya",
        avatar: { enabled: true, character: "priya" },
        colours: { accent: "#ff6600", background: "#101010", text: "#fafafa" },
        position: "bottom-left",
        greeting: "  Hi, I'm Maya. What are you looking for?  ",
      },
      {},
      () => {},
    );
    expect(config.placement.anchor).toBe("bottom-left");
    expect(config.theme.brand).toBe("#ff6600");
    expect(config.theme.background).toBe("#101010");
    expect(config.theme.ink).toBe("#fafafa");
    expect(config.avatar && config.avatar.character).toBe("priya");
    expect(config.name).toBe("Maya");
    expect(greeting).toBe("Hi, I'm Maya. What are you looking for?");
  });

  it("turns a disabled avatar into a voice-only widget", () => {
    const { config } = widgetConfigFromSiteSettings({ avatar: { enabled: false, character: "tara" } });
    expect(config.avatar).toBe(false);
  });

  it("reads the retired character as the Site Agent's fallback", () => {
    const { config } = widgetConfigFromSiteSettings({ avatar: { character: "ira" } });
    expect(config.avatar && config.avatar.character).toBe("tara");
  });

  it("leaves the widget defaults where the settings say nothing", () => {
    const { config, greeting } = widgetConfigFromSiteSettings({}, {}, () => {});
    expect(config).toEqual(defaultWidgetConfig());
    expect(greeting).toBeUndefined();
    expect(widgetConfigFromSiteSettings(null).config).toEqual(defaultWidgetConfig());
  });

  it("ignores nulls the stored settings carry", () => {
    const input = siteSettingsToInput({ colours: { accent: null, text: "#000000" }, greeting: null, avatar: null });
    expect(input).toEqual({ theme: { ink: "#000000" } });
  });

  it("lets a page override one field and keep the rest", () => {
    const { config } = widgetConfigFromSiteSettings(
      { position: "bottom-left", colours: { accent: "#ff6600" } },
      { placement: { move: "fixed" }, theme: { scheme: "dark" } },
      () => {},
    );
    expect(config.placement.anchor).toBe("bottom-left");
    expect(config.placement.move).toBe("fixed");
    expect(config.theme.brand).toBe("#ff6600");
    expect(config.theme.scheme).toBe("dark");
  });

  it("falls back with a warning on a stored value the widget cannot use", () => {
    const warnings: string[] = [];
    const { config } = widgetConfigFromSiteSettings(
      { position: "somewhere", colours: { accent: "orange" } },
      {},
      (m) => warnings.push(m),
    );
    expect(config.placement.anchor).toBe("bottom-right");
    expect(config.theme.brand).toBeUndefined();
    expect(warnings).toHaveLength(2);
  });
});

describe("mergeInput", () => {
  it("merges objects and replaces everything else", () => {
    expect(mergeInput({ a: { b: 1, c: 2 }, d: [1] }, { a: { c: 3 }, d: [2] })).toEqual({ a: { b: 1, c: 3 }, d: [2] });
    expect(mergeInput({ avatar: { character: "x" } }, { avatar: false })).toEqual({ avatar: false });
  });
});
