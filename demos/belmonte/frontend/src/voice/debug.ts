/** `?debug=1`: the hand-fired move console and the fake call tile. Never on otherwise. */
export const debugMode = () => {
  try {
    return new URLSearchParams(window.location.search).get("debug") === "1" || sessionStorage.getItem("bm-debug") === "1";
  } catch {
    return false;
  }
};
if (typeof window !== "undefined") {
  try {
    if (new URLSearchParams(window.location.search).get("debug") === "1") sessionStorage.setItem("bm-debug", "1");
  } catch {
    /* no storage */
  }
}
