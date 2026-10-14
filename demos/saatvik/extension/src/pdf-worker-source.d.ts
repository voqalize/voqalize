// pdf.js's worker as text, which build.mjs bundles under this name so the
// viewer can start it from a Blob.
declare module "pdf-worker-source" {
  const source: string;
  export default source;
}
