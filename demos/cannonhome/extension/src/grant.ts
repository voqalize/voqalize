/**
 * The extension's microphone grant, asked for once.
 *
 * The call runs in the extension's own document (`holder.ts`), so the
 * microphone is the extension's to ask for, not cannonhome.cl's: Chrome keeps
 * the permission against `chrome-extension://<id>`, and an offscreen document
 * cannot show a prompt. The widget puts this page in a frame
 * (`<iframe allow="microphone">`) on the visitor's first call; it asks at
 * once, and Chrome's prompt names the extension. Should the grant made there
 * not reach the extension (or be for this time only), the service worker
 * opens this page in a tab of its own (`?tab=1`), which asks the same way and
 * is closed once answered.
 *
 * What it reports is the outcome alone: to the page around the frame, and to
 * the service worker from a tab.
 */

const params = new URLSearchParams(location.search);
const inTab = params.get("tab") === "1";
const es = params.get("lang") !== "en";

const WORDS = es
  ? {
      asking: "Chrome te pedirá usar el micrófono para Javier. Elige «Permitir».",
      tab: "Para que Javier te escuche, Chrome te pedirá usar el micrófono. Elige «Permitir»; esta pestaña se cerrará sola.",
      granted: "Listo: Javier ya puede escucharte.",
      refused: "Sin el micrófono Javier no te escucha.",
      again: "Permitir micrófono",
    }
  : {
      asking: "Chrome will ask to use the microphone for Javier. Choose “Allow”.",
      tab: "So Javier can hear you, Chrome will ask to use the microphone. Choose “Allow”; this tab closes by itself.",
      granted: "Done: Javier can hear you now.",
      refused: "Without the microphone Javier can't hear you.",
      again: "Allow microphone",
    };

const say = document.getElementById("say")!;
const again = document.getElementById("again") as HTMLButtonElement;
document.documentElement.lang = es ? "es" : "en";
document.body.classList.toggle("tab", inTab);
again.textContent = WORDS.again;
say.textContent = inTab ? WORDS.tab : WORDS.asking;

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
    say.textContent = WORDS.granted;
  } catch (error) {
    result = error instanceof Error ? error.name : "Error";
    say.textContent = WORDS.refused;
    again.hidden = false;
  }
  report(result);
}

again.addEventListener("click", () => void ask());
void ask();
