import { ChevronRight, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { prevMonth, spendByCategory, spendingTxns, txnMonths } from "../../app/spending";
import { inr, monthBounds, monthName } from "../../data/bank";
import { useAllTxns, useBank } from "../../state/bank";
import { CatIcon, PageHead, Panel, catColor, plural } from "./ui";

const shortMonth = (m: string) => monthName(m).slice(0, 3);
const r = (n: number) => inr(Math.round(n));

function Donut({ parts, total, label, count }: { parts: { id: string; amount: number }[]; total: number; label: string; count: number }) {
  const R = 70;
  const C = 2 * Math.PI * R;
  let acc = 0;
  return (
    <svg viewBox="0 0 200 200" className="ax-donut" role="img" aria-label={`Spending by category, ${label}`}>
      <circle cx="100" cy="100" r={R} fill="none" stroke="var(--sand)" strokeWidth="26" />
      {total > 0 &&
        parts.map((p) => {
          const len = (p.amount / total) * C;
          const el = (
            <circle
              key={p.id}
              cx="100"
              cy="100"
              r={R}
              fill="none"
              stroke={catColor(p.id)}
              strokeWidth="26"
              strokeDasharray={`${Math.max(0, len - 1.5)} ${C}`}
              strokeDashoffset={-acc}
              transform="rotate(-90 100 100)"
            />
          );
          acc += len;
          return el;
        })}
      <text x="100" y="94" textAnchor="middle" className="ax-donut__k">
        {parts.length} categories
      </text>
      <text x="100" y="120" textAnchor="middle" className="ax-donut__v">
        {count} spends
      </text>
    </svg>
  );
}

export function Insights() {
  const all = useAllTxns();
  const month = useBank((s) => s.insightsMonth);
  const setMonth = useBank((s) => s.setInsightsMonth);
  const navigate = useNavigate();
  const months = useMemo(() => txnMonths(all), [all]);
  const m = months.includes(month) ? month : months[0];
  const data = useMemo(() => spendByCategory(m, all), [all, m]);
  const prev = useMemo(() => spendByCategory(prevMonth(m), all), [all, m]);
  const hasPrev = months.includes(prevMonth(m));
  const trend = useMemo(() => months.slice(0, 6).reverse().map((k) => ({ k, total: spendByCategory(k, all).total })), [all, months]);
  const maxTrend = Math.max(1, ...trend.map((t) => t.total));
  const merchants = useMemo(() => {
    const by = new Map<string, { amount: number; count: number; category: string }>();
    for (const t of spendingTxns(m, all)) {
      const e = by.get(t.merchant) ?? { amount: 0, count: 0, category: t.category };
      e.amount += t.amount;
      e.count++;
      by.set(t.merchant, e);
    }
    return [...by.entries()].sort((a, b) => b[1].amount - a[1].amount).slice(0, 6);
  }, [all, m]);
  const delta = data.total - prev.total;
  const maxCat = Math.max(1, ...data.categories.map((c) => c.amount));

  const openCategory = (id: string) => {
    const b = monthBounds(m);
    useBank.getState().setFilter({ account: "all", category: id, direction: "debit", query: null, min_amount: null, max_amount: null, ...b, label: `${data.categories.find((c) => c.id === id)?.name ?? id}, ${monthName(m)}` });
    navigate("/app/transactions");
  };

  return (
    <div className="ax-page" data-stage-thing="screen:insights" data-stage-label="Insights">
      <PageHead title="Spending insights" sub="Savings account and credit card spends by category. Transfers, investments, income and refunds are left out." />

      <div className="ax-months" role="tablist" aria-label="Month" data-stage-thing="insights-month" data-stage-group="" data-stage-label="Month">
        {months.map((k) => (
          <button key={k} type="button" role="tab" aria-selected={k === m} className={k === m ? "is-on" : ""} onClick={() => setMonth(k)} data-stage-thing={`month:${k}`} data-stage-label={monthName(k)}>
            {monthName(k)}
          </button>
        ))}
      </div>

      <div className="ax-ins">
        <Panel className="ax-ins__summary" thing="insights-total" label="Total spent">
          <Donut parts={data.categories} total={data.total} label={monthName(m)} count={spendingTxns(m, all).length} />
          <div className="ax-ins__totals">
            <span className="ax-k">{monthName(m)}</span>
            <strong className="ax-fig ax-fig--xl">{r(data.total)}</strong>
            <span className="ax-k">Spent, savings and credit card</span>
            {hasPrev && (
              <div className={`ax-delta ${delta > 0 ? "is-up" : "is-down"}`} data-stage-thing="insights-compare" data-stage-label="Compared with last month">
                {delta > 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                {r(Math.abs(delta))} {delta > 0 ? "more" : "less"} than {monthName(prevMonth(m))} ({r(prev.total)})
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Last six months" className="ax-ins__trend" thing="insights-trend" label="Monthly trend">
          <div className="ax-trend">
            {trend.map((t) => (
              <button type="button" key={t.k} className={`ax-trend__col${t.k === m ? " is-on" : ""}`} onClick={() => setMonth(t.k)} aria-label={`${monthName(t.k)}: ${r(t.total)}`}>
                <span className="ax-trend__v">{t.total >= 1000 ? `₹${Math.round(t.total / 1000)}k` : r(t.total)}</span>
                <span className="ax-trend__bar" style={{ height: `${(t.total / maxTrend) * 100}%` }} />
                <span className="ax-trend__k">{shortMonth(t.k)}</span>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      <div className="ax-split ax-split--wide">
        <Panel title="By category" pad={false} thing="insights-categories" label="Categories">
          {data.categories.length === 0 ? (
            <div className="ax-empty">
              <strong>No spends in {monthName(m)} yet.</strong>
            </div>
          ) : (
            <ul className="ax-catrows">
              {data.categories.map((c) => {
                const p = prev.categories.find((x) => x.id === c.id)?.amount ?? 0;
                return (
                  <li key={c.id} data-stage-thing={`category:${c.id}`} data-stage-label={c.name}>
                    <button type="button" onClick={() => openCategory(c.id)}>
                      <CatIcon id={c.id} />
                      <span className="ax-catrows__main">
                        <span className="ax-catrows__top">
                          <strong>{c.name}</strong>
                          <span className="ax-catrows__amt">{r(c.amount)}</span>
                        </span>
                        <span className="ax-catrows__bar">
                          <span style={{ width: `${(c.amount / maxCat) * 100}%`, background: catColor(c.id) }} />
                        </span>
                        <span className="ax-catrows__meta">
                          <span>
                            {Math.round((c.amount / data.total) * 100)}% of spending, {plural(c.count, "spend")}
                          </span>
                          {hasPrev && <span>{p ? `${shortMonth(prevMonth(m))} ${r(p)}` : `none in ${shortMonth(prevMonth(m))}`}</span>}
                        </span>
                      </span>
                      <ChevronRight size={16} className="ax-catrows__go" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        <Panel title="Top merchants" pad={false} thing="insights-merchants" label="Top merchants">
          <ol className="ax-merchants">
            {merchants.map(([name, e]) => (
              <li key={name}>
                <CatIcon id={e.category} size={30} />
                <span>
                  <strong>{name}</strong>
                  <span className="ax-k">{plural(e.count, "spend")}</span>
                </span>
                <span className="ax-merchants__amt">{r(e.amount)}</span>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </div>
  );
}
