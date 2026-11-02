/** An image the build inlines as a data URL (build.mjs, `loader`). */
declare module "*.webp" {
  const url: string;
  export default url;
}
