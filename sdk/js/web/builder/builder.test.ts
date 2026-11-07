import { describe, expect, it } from "vitest";
import { VERSION } from "@voqalize/web";
import { parseWidgetConfig } from "@voqalize/web/widgets";
import schemaJson from "@voqalize/web/widget-config.schema.json";
import { type SchemaNode, type Sparse, GROUPS, applyLeaf, getPath, groupLeaves, leavesOf, setPath, shownValue } from "./schema-form.js";
import { AGENT_PLACEHOLDER, KEY_PLACEHOLDER, htmlSnippet, reactSnippet, settingsJson } from "./snippet.js";

const schema = schemaJson as unknown as SchemaNode;
const leaves = leavesOf(schema);
const leaf = (path: string) => {
  const l = leaves.find((x) => x.path === path);
  if (!l) throw new Error(`no leaf ${path}`);
  return l;
};

describe("the form from the schema", () => {
  it("has a control for every field the schema names", () => {
    const paths = leaves.map((l) => l.path);
    for (const p of ["avatar", "avatar.shape", "avatar.background", "placement.anchor", "mic.instantStart", "captions.mode", "theme.brand", "words", "dir"]) {
      expect(paths).toContain(p);
    }
  });

  it("reads the control from the schema", () => {
    expect(leaf("placement.anchor").kind).toBe("choice");
    expect(leaf("placement.anchor").default).toBe("bottom-right");
    expect(leaf("mic.instantStart").kind).toBe("switch");
    expect(leaf("mic.instantStart").default).toBe(true);
    expect(leaf("theme.brand").kind).toBe("colour");
    expect(leaf("theme.radius").kind).toBe("slider");
    expect(leaf("captions.lines").step).toBe(1);
    expect(leaf("placement.offset").kind).toBe("slider");
    expect(leaf("placement.avoid").kind).toBe("list");
    expect(leaf("theme.tokens").kind).toBe("json");
    expect(leaf("avatar").kind).toBe("presence");
    expect(leaf("avatar.shape").dependsOn).toBe("avatar");
    expect(leaf("avatar.background").kind).toBe("background");
    expect(leaf("captions.linger").kind).toBe("text");
  });

  it("names every grouped path that exists, and puts the rest in More", () => {
    const paths = new Set(leaves.map((l) => l.path));
    for (const g of GROUPS) for (const p of g.paths) expect(paths, p).toContain(p);
    const groups = groupLeaves(leaves);
    const placed = groups.flatMap((g) => g.leaves.map((l) => l.path));
    expect(new Set(placed)).toEqual(paths);
    expect(groups.at(-1)?.id).toBe("more");
    expect(groups.at(-1)?.leaves.map((l) => l.path)).toContain("words");
  });

  it("lands a field added to the schema in More with a control", () => {
    const grown: SchemaNode = {
      ...schema,
      properties: { ...schema.properties, glow: { type: "object", properties: { strength: { enum: ["soft", "bright"], default: "soft" } } } },
    };
    const more = groupLeaves(leavesOf(grown)).find((g) => g.id === "more");
    expect(more?.leaves.find((l) => l.path === "glow.strength")?.kind).toBe("choice");
  });
});

describe("the sparse configuration", () => {
  it("sets and removes nested fields, dropping emptied objects", () => {
    let c: Sparse = {};
    c = setPath(c, "theme.brand", "#0f766e");
    expect(c).toEqual({ theme: { brand: "#0f766e" } });
    c = setPath(c, "theme.brand", undefined);
    expect(c).toEqual({});
  });

  it("keeps only values that differ from the default", () => {
    let c: Sparse = {};
    c = applyLeaf(c, leaf("placement.anchor"), "bottom-left");
    expect(getPath(c, "placement.anchor")).toBe("bottom-left");
    c = applyLeaf(c, leaf("placement.anchor"), "bottom-right");
    expect(c).toEqual({});
  });

  it("turns the face off and on", () => {
    let c: Sparse = { avatar: { shape: "circle" } };
    c = applyLeaf(c, leaf("avatar"), false);
    expect(c.avatar).toBe(false);
    expect(shownValue(c, leaf("avatar"))).toBe(false);
    c = applyLeaf(c, leaf("avatar"), true);
    expect(c).toEqual({});
  });

  it("shows the default for a field left out", () => {
    expect(shownValue({}, leaf("captions.mode"))).toBe("karaoke");
    expect(shownValue({ captions: { mode: "off" } }, leaf("captions.mode"))).toBe("off");
  });

  it("only writes configurations the widget accepts without a warning", () => {
    let c: Sparse = {};
    c = applyLeaf(c, leaf("theme.brand"), "#0f766e");
    c = applyLeaf(c, leaf("launcher.style"), "face");
    c = applyLeaf(c, leaf("avatar.background"), { url: "https://example.com/loop.mp4" });
    c = applyLeaf(c, leaf("placement.avoid"), ["#cart"]);
    c = applyLeaf(c, leaf("captions.lines"), 3);
    const warnings: string[] = [];
    parseWidgetConfig(c, (m) => warnings.push(m));
    expect(warnings).toEqual([]);
  });
});

describe("the snippet", () => {
  it("writes the script tag and the element with only what changed", () => {
    const s = htmlSnippet({}, VERSION);
    expect(s).toContain(`/web/${VERSION}/voqalize.js`);
    expect(s).toContain(`agent="${AGENT_PLACEHOLDER}"`);
    expect(s).toContain(`key="${KEY_PLACEHOLDER}"`);
    expect(s).not.toContain("config=");
  });

  it("carries the agent and key as attributes and the rest as config", () => {
    const s = htmlSnippet({ agent: "agt_x", key: "pk_y", theme: { brand: "#0f766e" } }, "0.1.0");
    expect(s).toContain(`agent="agt_x" key="pk_y"`);
    expect(s).toContain(`config='{"theme":{"brand":"#0f766e"}}'`);
  });

  it("escapes what would break the attribute", () => {
    const s = htmlSnippet({ name: "O'Brien <b>" }, "0.1.0");
    expect(s).toContain("O&#39;Brien &lt;b>");
  });

  it("writes the React form and the settings JSON without the key", () => {
    expect(reactSnippet({ launcher: { style: "face" } })).toContain('"style": "face"');
    expect(settingsJson({ key: "pk_y", agent: "a", dir: "rtl" })).toBe('{\n  "dir": "rtl"\n}');
  });
});
