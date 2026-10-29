/**
 * The extension's microphone grant, asked for once (`grant.html`).
 *
 * The call runs in the extension's own document, so the microphone is the
 * extension's to ask for, not the site's: Chrome keeps the permission against
 * `chrome-extension://<id>`, and an offscreen document cannot show a prompt.
 * The widget puts this page in a frame (`<iframe allow="microphone">`) on the
 * visitor's first call; it asks at once, and Chrome's prompt names the
 * extension. Should that grant not reach the extension (or be for this time
 * only), the service worker opens this page in a tab of its own (`?tab=1`),
 * which asks the same way and is closed once answered.
 *
 * The page needs `<p id="say">` and `<button id="again" hidden>`. What it
 * reports is the outcome alone: to the page around the frame, and to the
 * service worker from a tab.
 */

export interface GrantWords {
  asking: string;
  tab: string;
  granted: string;
  refused: string;
  again: string;
}

/** Run the grant page. `words` per language; `?lang=` picks one, else
 *  `opening`. */
export function startGrant(words: Record<string, GrantWords>, opening: string): void {
  const params = new URLSearchParams(location.search);
  const inTab = params.get("tab") === "1";
  const asked = params.get("lang") ?? opening;
  const lang = words[asked] ? asked : opening;
  const w = words[lang]!;

  const say = document.getElementById("say")!;
  const again = document.getElementById("again") as HTMLButtonElement;
  document.documentElement.lang = lang;
  document.body.classList.toggle("tab", inTab);
  again.textContent = w.again;
  say.textContent = inTab ? w.tab : w.asking;

  function report(result: string): void {
    if (inTab) {
      void chrome.runtime.sendMessage({ to: "sw", op: "grant_done", result }).catch(() => {});
    } else {
      // Only the outcome crosses: "granted" or the error's name.
      window.parent.postMessage({ voqalizeGrant: result }, "*");
    }
  }

  async function ask(): Promise<void> {
    again.hidden = true;
    let result: string;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      result = "granted";
      say.textContent = w.granted;
    } catch (error) {
      result = error instanceof Error ? error.name : "Error";
      say.textContent = w.refused;
      again.hidden = false;
    }
    report(result);
  }

  again.addEventListener("click", () => void ask());
  void ask();
}
