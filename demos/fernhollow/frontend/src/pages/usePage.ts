import { useEffect } from "react";

const STORE = "Fernhollow";

/** Sets the document title; `null` is the home page. */
export function useTitle(title: string | null) {
  useEffect(() => {
    document.title = title ? `${title} — ${STORE}` : `${STORE} — furniture and homeware for calm rooms`;
  }, [title]);
}

/** Superseded by `useScreenReport` in the shell, which reports the layout too. */
export function useVisibleProducts(_ids: string[]) {}
