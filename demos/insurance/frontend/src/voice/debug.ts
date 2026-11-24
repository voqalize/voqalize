/** `?debug=1` (remembered for the tab): the move console and `window.__chhatri`. */
export function debugMode(): boolean {
  try {
    const on = new URLSearchParams(window.location.search).get("debug");
    if (on === "1") sessionStorage.setItem("chhatri-debug", "1");
    if (on === "0") sessionStorage.removeItem("chhatri-debug");
    return sessionStorage.getItem("chhatri-debug") === "1";
  } catch {
    return new URLSearchParams(window.location.search).get("debug") === "1";
  }
}
