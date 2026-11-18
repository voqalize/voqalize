/** `?debug=1`: the dev console and the `window.__anvaya` hook. */
export const debugMode = (): boolean => {
  try {
    return new URLSearchParams(window.location.search).get("debug") === "1" || sessionStorage.getItem("anvaya.debug") === "1";
  } catch {
    return false;
  }
};

/** Keep debug on across the site's own navigation (links drop the query). */
export function rememberDebug(): void {
  try {
    if (new URLSearchParams(window.location.search).get("debug") === "1") sessionStorage.setItem("anvaya.debug", "1");
  } catch {
    /* no storage */
  }
}
