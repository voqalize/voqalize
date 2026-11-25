/**
 * Find my size: height, usual size and fit preference, then a pick from this
 * product's sizes by the shared rule (`data/fit.ts`, the brain's too). The
 * agent fills it with `fit.fill` and shows its pick with `fit.recommend`; by
 * hand the button runs the same rule. Each field is a `fit:<field>` part.
 */
import { Ruler } from "lucide-react";
import { type Product, stockOf } from "../data/catalog";
import { type FitAnswer, type FitPref, recommend } from "../data/fit";
import { STORE } from "../data/shop";
import { useStore } from "../state/store";

const FITS: { id: FitPref; label: string }[] = [
  { id: "snug", label: "Snug" },
  { id: "regular", label: "Regular" },
  { id: "relaxed", label: "Relaxed" },
];

const USUAL: Record<string, string[]> = {
  alpha: ["XS", "S", "M", "L", "XL", "XXL", "3XL"],
  waist: ["26", "28", "30", "32", "34", "36", "38", "40"],
  uk: ["UK 3", "UK 4", "UK 5", "UK 6", "UK 7", "UK 8", "UK 9", "UK 10", "UK 11"],
};

/** One sentence: why this size (the page's words for the rule's `why`). */
export function fitReason(a: FitAnswer, usual: string, height?: number): string {
  switch (a.why) {
    case "slim_up":
      return `This is a slim cut, so one size up from your ${usual} gives the relaxed fit you like.`;
    case "loose_down":
      return `This cut runs loose, so one size down from your ${usual} keeps it snug.`;
    case "tall_up":
      return `At ${height} cm, one size up from your ${usual} gives you the length.`;
    default:
      return a.cut === "regular" ? `A regular cut: your usual ${usual} should fit as you like it.` : `Your usual ${usual} fits this ${a.cut} cut the way you like it.`;
  }
}

export function FitPanel({ product: p }: { product: Product }) {
  const panel = useStore((s) => s.fit[p.id]);
  const setFit = useStore((s) => s.setFit);
  const open = !!panel?.open;
  if (p.scale === "one") return null;
  const usualOptions = USUAL[p.scale] ?? p.sizes.map(([l]) => l);
  const run = () => {
    if (!panel?.usual_size) return;
    const a = recommend(p, { usual_size: panel.usual_size, fit: panel.fit, height_cm: panel.height_cm });
    if (!a) {
      setFit(p.id, { pick: { size: "", reason: `We can't match ${panel.usual_size} to this product's sizes; the size chart has the measurements.` } });
      return;
    }
    setFit(p.id, { pick: { size: a.size, wanted: a.wanted, reason: fitReason(a, panel.usual_size, panel.height_cm) } });
    useStore.getState().pickSize(p.id, a.size);
  };
  return (
    <section className={`fit${open ? " is-open" : ""}`} data-stage-thing="fit" data-stage-group>
      <button type="button" className="fit-toggle" aria-expanded={open} onClick={() => setFit(p.id, { open: !open })}>
        <Ruler size={17} aria-hidden /> <span>Find my size</span>
        <span className="fit-hint">{open ? "Hide" : "Height, usual size and fit"}</span>
      </button>
      {open ? (
        <div className="fit-body">
          <div className="fit-fields">
            <label className="field" data-stage-part="fit:height">
              <span>Height (cm)</span>
              <input
                type="number"
                inputMode="numeric"
                min={100}
                max={220}
                value={panel?.height_cm ?? ""}
                placeholder="170"
                onChange={(e) => setFit(p.id, { height_cm: e.target.value ? Number(e.target.value) : undefined, pick: undefined })}
              />
            </label>
            <label className="field" data-stage-part="fit:usual">
              <span>Usual size</span>
              <select value={panel?.usual_size ?? ""} onChange={(e) => setFit(p.id, { usual_size: e.target.value || undefined, pick: undefined })}>
                <option value="">Choose</option>
                {[...new Set([...(panel?.usual_size ? [panel.usual_size] : []), ...usualOptions])].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <div className="field" data-stage-part="fit:fit" role="group" aria-label="How you like it to fit">
              <span>Fit you like</span>
              <div className="seg">
                {FITS.map((f) => (
                  <button key={f.id} type="button" className={panel?.fit === f.id ? "is-on" : ""} aria-pressed={panel?.fit === f.id} onClick={() => setFit(p.id, { fit: f.id, pick: undefined })}>
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <button type="button" className="btn ghost fit-run" disabled={!panel?.usual_size} onClick={run}>
            Recommend a size
          </button>
          {panel?.pick ? (
            <div className="fit-pick" data-stage-part="fit:pick" aria-live="polite">
              {panel.pick.size ? (
                <>
                  <p className="fit-size">
                    <span>Your size</span> <b>{panel.pick.size}</b>
                    {stockOf(p, panel.pick.size) > 0 && stockOf(p, panel.pick.size) <= 3 ? <em>Only {stockOf(p, panel.pick.size)} left</em> : null}
                  </p>
                  <p>{panel.pick.reason}</p>
                  {panel.pick.wanted ? (
                    <p className="fit-oos">
                      {panel.pick.wanted} would be the pick, but it is out of stock; {panel.pick.size} is the nearest size in stock.
                    </p>
                  ) : null}
                </>
              ) : (
                <p>{panel.pick.reason}</p>
              )}
            </div>
          ) : null}
          <p className="fit-small">Over {STORE.fit.tall_cm} cm? Longer styles may need a size up for length.</p>
        </div>
      ) : null}
    </section>
  );
}
