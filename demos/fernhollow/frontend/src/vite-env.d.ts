/// <reference types="vite/client" />

declare module "virtual:catalog" {
  import type { CatalogData } from "./data/types";
  const data: CatalogData;
  export default data;
}
