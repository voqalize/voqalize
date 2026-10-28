#!/usr/bin/env node
/**
 * `stage build <scene.ts> [-o scene.json]`: a `defineScene` module, evaluated
 * in Node, written out as the Stage Spec the brain reads.
 *
 * The module exports its scene as `scene` (or as its default export). A
 * TypeScript module runs on Node's own type stripping (Node 22.18 or later;
 * earlier, run Node with --experimental-strip-types), so nothing is compiled
 * and no bundler is needed. Check the result with `voqalize stage check`.
 */

import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const USAGE = "usage: stage build <scene module> [-o scene.json]";

async function build(args) {
  const out = args.indexOf("-o");
  const target = out >= 0 ? args[out + 1] : null;
  const source = args.find((a, i) => !a.startsWith("-") && (out < 0 || i !== out + 1));
  if (!source || (out >= 0 && !target)) throw new Error(USAGE);
  const mod = await import(pathToFileURL(resolve(source)).href);
  const scene = mod.scene ?? mod.default;
  if (!scene || typeof scene !== "object" || !("spec" in scene)) {
    throw new Error(`${source} exports no scene: export the defineScene(...) result as \`scene\``);
  }
  const text = `${JSON.stringify(scene.spec, null, 2)}\n`;
  if (target) {
    writeFileSync(target, text);
    console.error(`${scene.spec.moves.length} moves → ${target}`);
  } else {
    process.stdout.write(text);
  }
}

const [command, ...rest] = process.argv.slice(2);
try {
  if (command !== "build") throw new Error(USAGE);
  await build(rest);
} catch (e) {
  console.error(`stage: ${e instanceof Error ? e.message : e}`);
  process.exit(1);
}
