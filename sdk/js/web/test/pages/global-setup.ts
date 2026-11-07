// Start the component page's server and the builder's; the tests read their URLs from the environment.
// @ts-expect-error: a plain ES module beside the tests, with no types of its own.
import { serve } from "./serve.mjs";
// @ts-expect-error: the builder's dev server, a plain ES module.
import { serve as serveBuilder } from "../../builder/serve.mjs";

type Served = { server: { close(cb: () => void): void }; url: string };

export default async function globalSetup(): Promise<() => Promise<void>> {
  const pages = (await serve()) as Served;
  process.env.VQL_PAGE_URL = pages.url;
  process.env.VQL_BUILDER_WATCH = "0";
  const builder = (await serveBuilder(0, { readLocal: false })) as Served;
  process.env.VQL_BUILDER_URL = builder.url;
  const close = (s: Served) => new Promise<void>((resolve) => s.server.close(() => resolve()));
  return async () => {
    await close(pages);
    await close(builder);
  };
}
