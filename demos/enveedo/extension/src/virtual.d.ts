/** The brain's catalogue of places, `../backend/knowledge/L3/anchors.json`,
 *  bundled in by `build.mjs` (`src/anchors.stub.json` while it is not there). */
declare module "virtual:enveedo-anchors" {
  const data: Record<string, unknown>;
  export default data;
}
