/** `?debug=1`, remembered for the tab: the dev console and `window.__tkRun`. */
export function debugMode(): boolean {
  try {
    if (new URLSearchParams(window.location.search).has("debug")) sessionStorage.setItem("tk-debug", "1");
    return sessionStorage.getItem("tk-debug") === "1";
  } catch {
    return new URLSearchParams(window.location.search).get("debug") === "1";
  }
}
