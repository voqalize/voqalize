/**
 * The extension's microphone grant, asked for once (`grant.html`): in the
 * widget's frame on cannonhome.cl, or in a tab of its own. The shared one from
 * `@voqalize/stage/extension`, with Javier's words.
 */

import { startGrant } from "@voqalize/stage/extension";

import { SITE } from "./site";

startGrant(
  {
    es: {
      asking: "Chrome te pedirá usar el micrófono para Javier. Elige «Permitir».",
      tab: "Para que Javier te escuche, Chrome te pedirá usar el micrófono. Elige «Permitir»; esta pestaña se cerrará sola.",
      granted: "Listo: Javier ya puede escucharte.",
      refused: "Sin el micrófono Javier no te escucha.",
      again: "Permitir micrófono",
    },
    en: {
      asking: "Chrome will ask to use the microphone for Javier. Choose “Allow”.",
      tab: "So Javier can hear you, Chrome will ask to use the microphone. Choose “Allow”; this tab closes by itself.",
      granted: "Done: Javier can hear you now.",
      refused: "Without the microphone Javier can't hear you.",
      again: "Allow microphone",
    },
  },
  SITE.opening,
);
