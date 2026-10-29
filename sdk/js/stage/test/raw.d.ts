/** A file's text, imported with Vite's `?raw` suffix in a test. */
declare module "*?raw" {
  const text: string;
  export default text;
}
