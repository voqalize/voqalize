/** The brain's catalogue of places, `../backend/knowledge/L3/anchors.json`,
 *  bundled in by `build.mjs` (a stand-in when it is not there yet). */
declare module "virtual:unosalud-anchors" {
  const data: Record<string, unknown>;
  export default data;
}
