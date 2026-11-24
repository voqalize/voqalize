/** `?debug=1`: the hand-fired move console and the fake call tile. Never on otherwise. */
export const debugMode = () => {
  try {
    return new URLSearchParams(window.location.search).get("debug") === "1" || sessionStorage.getItem("wl-debug") === "1";
  } catch {
    return false;
  }
};
if (typeof window !== "undefined") {
  try {
    if (new URLSearchParams(window.location.search).get("debug") === "1") sessionStorage.setItem("wl-debug", "1");
  } catch {
    /* no storage */
  }
}
