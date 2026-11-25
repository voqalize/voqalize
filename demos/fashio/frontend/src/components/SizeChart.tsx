/**
 * The size chart drawer (right, `data-overlay="right"` so the agent moves to
 * the top left): the chart for the product's type and gender from store.json,
 * the size in question ringed by row (`chart-row:<label>`), how to measure,
 * and the product's sizes with their stock.
 */
import { X } from "lucide-react";
import { useEffect } from "react";
import { type Product, index } from "../data/catalog";
import { STORE, type SizeChart } from "../data/shop";
import { useStore } from "../state/store";

/** The chart for a product, or null (one-size products, types with no chart). */
export function chartFor(p: Product): SizeChart | null {
  const charts = index()?.types[p.type]?.chart;
  if (!charts || p.scale === "one") return null;
  const g = p.gender === "unisex" ? (charts.men ? "men" : "women") : p.gender;
  const id = charts[g] ?? (p.gender === "boys" || p.gender === "girls" ? charts.boys ?? charts.girls : undefined);
  return id ? STORE.size_charts[id] ?? null : null;
}

export function SizeChartDrawer({ product: p }: { product: Product }) {
  const open = useStore((s) => s.sizeChart);
  const picked = useStore((s) => s.size[p.id]);
  const close = () => useStore.getState().openSizeChart(null);
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);
  if (!open || open.product_id !== p.id) return null;
  const chart = chartFor(p);
  const mark = open.size ?? picked;
  const stock = new Map(p.sizes);
  return (
    <div className="drawer-scrim" onClick={close}>
      <aside className="drawer" data-overlay="right" role="dialog" aria-modal="true" aria-label="Size chart" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div>
            <h2>Size chart</h2>
            <p className="muted">{chart ? `${chart.title}, in ${chart.unit === "in" ? "inches" : "centimetres"}` : p.name}</p>
          </div>
          <button type="button" className="icon-btn" aria-label="Close the size chart" onClick={close}>
            <X size={22} />
          </button>
        </div>
        {chart ? (
          <div className="chart-wrap" data-stage-group>
            <table className="chart">
              <thead>
                <tr>
                  {chart.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                  <th>Here</th>
                </tr>
              </thead>
              <tbody>
                {chart.rows.map((r) => {
                  const n = stock.get(r[0]);
                  return (
                    <tr key={r[0]} data-stage-part={`chart-row:${r[0]}`} className={`${mark === r[0] ? "is-mark" : ""}${n === undefined ? " is-absent" : ""}`}>
                      {r.map((v, i) => (
                        <td key={i}>{v}</td>
                      ))}
                      <td className="chart-stock">{n === undefined ? "Not made" : n === 0 ? "Out of stock" : n <= 3 ? `Only ${n} left` : "In stock"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="chart-how">{chart.how}</p>
          </div>
        ) : (
          <p className="muted">This product comes in one size.</p>
        )}
        {p.model ? <p className="chart-model">The {p.model.replace(/^model/, "model")}.</p> : null}
        <p className="chart-note">Measurements are body measurements. Between two sizes? Use Find my size on the product page, or pick the larger for a relaxed fit.</p>
      </aside>
    </div>
  );
}
