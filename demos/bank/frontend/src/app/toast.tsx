/** Small, quiet notices ("Statement download started"), bottom of the screen. */
import { CheckCircle2, Info, XCircle } from "lucide-react";
import { create } from "zustand";

export type Tone = "ok" | "info" | "bad";
interface Toast {
  id: number;
  text: string;
  tone: Tone;
}

const useToasts = create<{ list: Toast[] }>(() => ({ list: [] }));
let n = 0;

export function toast(text: string, tone: Tone = "info", ms = 4200) {
  const id = ++n;
  useToasts.setState((s) => ({ list: [...s.list.slice(-2), { id, text, tone }] }));
  setTimeout(() => useToasts.setState((s) => ({ list: s.list.filter((t) => t.id !== id) })), ms);
}

export function Toaster() {
  const list = useToasts((s) => s.list);
  return (
    <div className="ax-toasts" role="status" aria-live="polite">
      {list.map((t) => (
        <div key={t.id} className={`ax-toast ax-toast--${t.tone}`}>
          {t.tone === "ok" ? <CheckCircle2 size={18} /> : t.tone === "bad" ? <XCircle size={18} /> : <Info size={18} />}
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}
