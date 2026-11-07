/**
 * Read a widget configuration against `widget-config.schema.json`.
 *
 * The schema is the only place a default or a limit is written. This file is
 * a small walker over the subset of JSON Schema the schema uses — `type`,
 * `enum`, `const`, `oneOf`/`anyOf`, `properties`, `additionalProperties` as a
 * map, `propertyNames`, `items`, `minimum`/`maximum`, `minLength`/`maxLength`,
 * `pattern`, `required` and `default` — and nothing more. A keyword the schema
 * starts using that this file does not read is a test failure, not a silent
 * pass: `test/config.test.ts` walks the schema for unread keywords.
 *
 * The parser never throws. Configuration is written by hand, by a builder,
 * and by a Site Agent setting saved months ago, and a page whose widget fails
 * to appear because of a typo in a colour is worse than a page whose widget
 * shows the default colour and says why in the console:
 *
 * - a field this version does not know is ignored, and every such field is
 *   named in one warning, so a configuration saved by a newer builder loads;
 * - a value that is the wrong type, out of range or not one of the allowed
 *   words falls back to that field's default, with a warning naming it;
 * - anything else that goes wrong returns the defaults, with a warning.
 */

import schemaJson from "./widget-config.schema.json";
import type { Warn, WidgetConfig } from "./types.js";

/** The schema keywords this walker reads. Exported for the drift test. */
export const READ_KEYWORDS = new Set([
  "$schema",
  "$id",
  "title",
  "description",
  "type",
  "enum",
  "const",
  "oneOf",
  "anyOf",
  "properties",
  "additionalProperties",
  "propertyNames",
  "items",
  "minimum",
  "maximum",
  "minLength",
  "maxLength",
  "pattern",
  "required",
  "default",
]);

export interface SchemaNode {
  type?: string;
  enum?: unknown[];
  const?: unknown;
  oneOf?: SchemaNode[];
  anyOf?: SchemaNode[];
  properties?: Record<string, SchemaNode>;
  additionalProperties?: SchemaNode | boolean;
  propertyNames?: SchemaNode;
  items?: SchemaNode;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  required?: string[];
  default?: unknown;
  description?: string;
}

export const WIDGET_CONFIG_SCHEMA = schemaJson as unknown as SchemaNode;

const PREFIX = "[voqalize] widget config:";

function defaultWarn(message: string): void {
  // eslint-disable-next-line no-console
  console.warn(message);
}

/** A failed check, with why. */
class Invalid {
  constructor(readonly reason: string) {}
}

interface Walk {
  warn: Warn;
  unknown: string[];
}

function kindOf(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "number") return Number.isFinite(value) ? "number" : "non-finite number";
  return typeof value;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return kindOf(value) === "object";
}

function show(value: unknown): string {
  try {
    const text = JSON.stringify(value);
    if (text === undefined) return String(value);
    return text.length > 60 ? `${text.slice(0, 57)}...` : text;
  } catch {
    return String(value);
  }
}

function join(path: string, key: string): string {
  return path ? `${path}.${key}` : key;
}

function clone<T>(value: T): T {
  return value === undefined ? value : (JSON.parse(JSON.stringify(value)) as T);
}

/** Whether `value` is the kind of thing `node` describes, without looking inside it. */
function shallowMatch(node: SchemaNode, value: unknown): boolean {
  if ("const" in node) return value === node.const;
  if (node.enum) return node.enum.includes(value);
  const branches = node.oneOf ?? node.anyOf;
  if (branches) return branches.some((b) => shallowMatch(b, value));
  if (!node.type) return true;
  const kind = kindOf(value);
  if (node.type === "integer") return kind === "number" && Number.isInteger(value);
  return kind === node.type;
}

function objectBranch(node: SchemaNode): SchemaNode | undefined {
  if (node.properties || node.type === "object") return node;
  return (node.oneOf ?? node.anyOf)?.find((b) => b.properties || b.type === "object");
}

/** The node's default, with the defaults of an object default's own fields filled in. */
function materialize(node: SchemaNode, path: string, walk: Walk): unknown {
  if (node.default === undefined) return undefined;
  if (isPlainObject(node.default)) {
    const branch = objectBranch(node);
    if (branch) return checkObject(branch, node.default, path, walk);
  }
  return clone(node.default);
}

/** The value to use for `value` at `path`: itself if valid, else the default. */
function resolve(node: SchemaNode, value: unknown, path: string, walk: Walk): unknown {
  if (value === undefined) return materialize(node, path, walk);
  const checked = check(node, value, path, walk);
  if (checked instanceof Invalid) {
    const fallback = materialize(node, path, walk);
    walk.warn(
      `${PREFIX} ${path} ${checked.reason}; ${
        fallback === undefined ? "ignoring it" : `using the default, ${show(fallback)}`
      }.`,
    );
    return fallback;
  }
  return checked;
}

function check(node: SchemaNode, value: unknown, path: string, walk: Walk): unknown {
  const branches = node.oneOf ?? node.anyOf;
  if (branches) {
    const branch = branches.find((b) => shallowMatch(b, value));
    if (!branch) return new Invalid(`is ${show(value)}, which is none of the accepted forms`);
    return check(branch, value, path, walk);
  }
  if ("const" in node) {
    return value === node.const ? value : new Invalid(`is ${show(value)}, not ${show(node.const)}`);
  }
  if (node.enum) {
    return node.enum.includes(value)
      ? value
      : new Invalid(`is ${show(value)}, not one of ${node.enum.map(show).join(", ")}`);
  }
  if (node.type && !shallowMatch(node, value)) {
    return new Invalid(`is ${show(value)}, not ${node.type === "integer" ? "a whole number" : `a ${node.type}`}`);
  }
  switch (kindOf(value)) {
    case "string":
      return checkString(node, value as string);
    case "number":
      return checkNumber(node, value as number);
    case "array":
      return checkArray(node, value as unknown[], path, walk);
    case "object":
      return checkObject(node, value as Record<string, unknown>, path, walk);
    default:
      return value;
  }
}

function checkString(node: SchemaNode, value: string): unknown {
  if (node.minLength !== undefined && value.length < node.minLength) {
    return new Invalid(value.length === 0 ? "is empty" : `is shorter than ${node.minLength} characters`);
  }
  if (node.maxLength !== undefined && value.length > node.maxLength) {
    return new Invalid(`is longer than ${node.maxLength} characters`);
  }
  if (node.pattern !== undefined && !new RegExp(node.pattern, "u").test(value)) {
    return new Invalid(`is ${show(value)}, which does not match ${node.pattern}`);
  }
  return value;
}

function checkNumber(node: SchemaNode, value: number): unknown {
  if (node.minimum !== undefined && value < node.minimum) return new Invalid(`is ${value}, below ${node.minimum}`);
  if (node.maximum !== undefined && value > node.maximum) return new Invalid(`is ${value}, above ${node.maximum}`);
  return value;
}

function checkArray(node: SchemaNode, value: unknown[], path: string, walk: Walk): unknown {
  if (!node.items) return clone(value);
  const out: unknown[] = [];
  value.forEach((item, index) => {
    const checked = check(node.items as SchemaNode, item, `${path}[${index}]`, walk);
    if (checked instanceof Invalid) walk.warn(`${PREFIX} ${path}[${index}] ${checked.reason}; dropping it.`);
    else out.push(checked);
  });
  return out;
}

function checkObject(node: SchemaNode, value: Record<string, unknown>, path: string, walk: Walk): unknown {
  for (const name of node.required ?? []) {
    if (value[name] === undefined) return new Invalid(`has no ${name}`);
  }
  const out: Record<string, unknown> = {};
  const properties = node.properties ?? {};
  for (const [key, child] of Object.entries(properties)) {
    const resolved = resolve(child, value[key], join(path, key), walk);
    if (resolved !== undefined) out[key] = resolved;
  }
  const extra = node.additionalProperties;
  for (const [key, item] of Object.entries(value)) {
    if (key in properties) continue;
    if (typeof extra !== "object") {
      walk.unknown.push(join(path, key));
      continue;
    }
    const childPath = join(path, key);
    if (node.propertyNames) {
      const name = check(node.propertyNames, key, childPath, walk);
      if (name instanceof Invalid) {
        walk.warn(`${PREFIX} ${path} has a field named ${show(key)}, which does not match ${node.propertyNames.pattern}; ignoring it.`);
        continue;
      }
    }
    const checked = check(extra, item, childPath, walk);
    if (checked instanceof Invalid) {
      walk.warn(`${PREFIX} ${childPath} ${checked.reason}; ignoring it.`);
      continue;
    }
    out[key] = checked;
  }
  return out;
}

/** Every default, as the widget uses them when nothing is configured. */
export function defaultWidgetConfig(): WidgetConfig {
  return parseWidgetConfig({}, () => {});
}

/**
 * Read `input` into a complete configuration. Never throws; see the file
 * header for what happens to a field it cannot use.
 *
 * `input` may be the object itself or its JSON text, as an attribute carries it.
 */
export function parseWidgetConfig(input: unknown, warn: Warn = defaultWarn): WidgetConfig {
  const walk: Walk = { warn, unknown: [] };
  try {
    let value = input;
    if (typeof value === "string") {
      try {
        value = JSON.parse(value);
      } catch {
        warn(`${PREFIX} the configuration is not valid JSON; using the defaults.`);
        value = {};
      }
    }
    if (value === undefined || value === null) value = {};
    if (!isPlainObject(value)) {
      warn(`${PREFIX} the configuration is ${show(value)}, not an object; using the defaults.`);
      value = {};
    }
    const out = checkObject(WIDGET_CONFIG_SCHEMA, value as Record<string, unknown>, "", walk);
    if (walk.unknown.length > 0) {
      warn(`${PREFIX} ignoring fields this version does not know: ${walk.unknown.join(", ")}.`);
    }
    return out as WidgetConfig;
  } catch (error) {
    warn(`${PREFIX} could not be read (${String(error)}); using the defaults.`);
    return checkObject(WIDGET_CONFIG_SCHEMA, {}, "", { warn: () => {}, unknown: [] }) as WidgetConfig;
  }
}

/**
 * Milliseconds from a duration the schema accepts: "4s", "800ms", "1.5s", or
 * a number of milliseconds. Anything else is `fallback`.
 */
export function parseDuration(value: string | number, fallback = 4000): number {
  if (typeof value === "number") return Number.isFinite(value) && value >= 0 ? value : fallback;
  const match = /^([0-9]+(?:\.[0-9]+)?)(ms|s)$/.exec(value.trim());
  if (!match) return fallback;
  const amount = Number(match[1]);
  return match[2] === "s" ? amount * 1000 : amount;
}
