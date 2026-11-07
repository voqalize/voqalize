// Start the component page's server; the tests read its URL from the environment.
// @ts-expect-error: a plain ES module beside the tests, with no types of its own.
import { serve } from "./serve.mjs";

export default async function globalSetup(): Promise<() => Promise<void>> {
  const { server, url } = (await serve()) as { server: { close(cb: () => void): void }; url: string };
  process.env.VQL_PAGE_URL = url;
  return () => new Promise<void>((resolve) => server.close(() => resolve()));
}
