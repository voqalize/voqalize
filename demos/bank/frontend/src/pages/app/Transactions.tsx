import { ArrowDownLeft, ArrowUpRight, CalendarRange, Flag, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { askConfirm } from "../../app/ConfirmSheet";
import { prevMonth } from "../../app/spending";
import { toast } from "../../app/toast";
import {
  type Txn,
  type TxnFilter,
  accountById,
  cardById,
  daysAgo,
  filterTxns,
  fmtDate,
  inr,
  monthBounds,
  monthKey,
  monthName,
  products,
  today,
} from "../../data/bank";
import { cardEmi } from "../../lib/bankmath";
import { filterIsEmpty, useAllTxns, useBank } from "../../state/bank";
import { ACCOUNT_LABEL, Amount, CatChip, CatIcon, PageHead, plural } from "./ui";

const PAGE = 60;

type Preset = "all" | "this_month" | "last_month" | "last_3" | "custom";

function presetRange(p: Preset, days = 30): Pick<TxnFilter, "from_days_ago" | "to_days_ago"> {
  const thisM = monthKey(today());
  if (p === "this_month") return monthBounds(thisM);
  if (p === "last_month") return monthBounds(prevMonth(thisM));
  if (p === "last_3") return { from_days_ago: 89, to_days_ago: 0 };
  if (p === "custom") return { from_days_ago: days, to_days_ago: 0 };
  return { from_days_ago: null, to_days_ago: null };
}

function presetOf(f: TxnFilter): Preset {
  if (f.from_days_ago == null && f.to_days_ago == null) return "all";
  for (const p of ["this_month", "last_month", "last_3"] as Preset[]) {
    const r = presetRange(p);
    if (r.from_days_ago === f.from_days_ago && (r.to_days_ago ?? 0) === (f.to_days_ago ?? 0)) return p;
  }
  return "custom";
}

export const dateLabel = (d: number) => (d === 0 ? "Today" : d === 1 ? "Yesterday" : fmtDate(daysAgo(d)));

export function Transactions() {
  const all = useAllTxns();
  const filter = useBank((s) => s.filter);
  const selected = useBank((s) => s.selectedTxn);
  const { setFilter, clearFilter, openTxn } = useBank.getState();
  const [showMore, setShowMore] = useState(false);
  const [limit, setLimit] = useState(PAGE);

  const rows = useMemo(() => filterTxns(all, filter), [all, filter]);
  const debits = rows.filter((t) => t.direction === "debit").reduce((a, t) => a + t.amount, 0);
  const credits = rows.filter((t) => t.direction === "credit").reduce((a, t) => a + t.amount, 0);
  const selIndex = selected ? rows.findIndex((t) => t.id === selected) : -1;
  const shown = Math.max(limit, selIndex + 1);
  const groups = useMemo(() => {
    const g: { day: number; txns: Txn[] }[] = [];
    for (const t of rows.slice(0, shown)) {
      const last = g[g.length - 1];
      if (last && last.day === t.days_ago) last.txns.push(t);
      else g.push({ day: t.days_ago, txns: [t] });
    }
    return g;
  }, [rows, shown]);
  const sel = selected ? all.find((t) => t.id === selected) ?? null : null;
  const preset = presetOf(filter);
  const usedCats = useMemo(() => products.spend_categories.filter((c) => all.some((t) => t.category === c.id)), [all]);
  const advanced = filter.min_amount != null || filter.max_amount != null || (!!filter.direction && filter.direction !== "any");

  useEffect(() => {
    if (advanced) setShowMore(true);
  }, [advanced]);
  useEffect(() => {
    setLimit(PAGE);
  }, [filter]);

  const set = (patch: Partial<TxnFilter>) => setFilter({ ...patch, label: null });

  return (
    <div className={`ax-page ax-txns${sel ? " has-detail" : ""}`} data-stage-thing="screen:transactions" data-stage-label="Transactions">
      <PageHead title="Transactions" sub="Savings, current account and credit card, newest first." />

      <div className="ax-filters" data-stage-thing="txn-filters" data-stage-label="Filters">
        <div className="ax-filters__row">
          <label className="ax-search" data-stage-thing="filter:query" data-stage-label="Search">
            <Search size={17} />
            <input type="search" placeholder="Search merchant or statement text" value={filter.query ?? ""} onChange={(e) => set({ query: e.target.value || null })} aria-label="Search transactions" />
          </label>
          <label className="ax-select" data-stage-thing="filter:account" data-stage-label="Account">
            <span>Account</span>
            <select value={filter.account ?? "all"} onChange={(e) => set({ account: e.target.value as TxnFilter["account"] })}>
              <option value="all">All accounts</option>
              <option value="bank">Savings + current</option>
              <option value="sb">Savings •••• {accountById("sb")!.last4}</option>
              <option value="ca">Current •••• {accountById("ca")!.last4}</option>
              <option value="cc">Credit card •••• {cardById("credit")!.last4}</option>
            </select>
          </label>
          <label className="ax-select" data-stage-thing="filter:category" data-stage-label="Category">
            <span>Category</span>
            <select value={filter.category ?? ""} onChange={(e) => set({ category: e.target.value || null })}>
              <option value="">All categories</option>
              {usedCats.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="ax-select" data-stage-thing="filter:dates" data-stage-label="Date range">
            <span>Date range</span>
            <select value={preset} onChange={(e) => set(presetRange(e.target.value as Preset, filter.from_days_ago ?? 30))}>
              <option value="all">All time</option>
              <option value="this_month">This month ({monthName(monthKey(today())).split(" ")[0]})</option>
              <option value="last_month">Last month ({monthName(prevMonth(monthKey(today()))).split(" ")[0]})</option>
              <option value="last_3">Last 3 months</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <button type="button" className={`ax-btn ax-btn--ghost ax-btn--sm${showMore ? " is-on" : ""}`} onClick={() => setShowMore((v) => !v)} aria-expanded={showMore}>
            <SlidersHorizontal size={15} /> More filters
          </button>
        </div>

        {(showMore || preset === "custom") && (
          <div className="ax-filters__row ax-filters__row--more">
            {preset === "custom" && (
              <div className="ax-range" data-stage-thing="filter:custom" data-stage-label="Custom dates">
                <CalendarRange size={16} />
                <label>
                  From
                  <input type="date" value={iso(daysAgo(filter.from_days_ago ?? 30))} max={iso(today())} onChange={(e) => e.target.value && set({ from_days_ago: daysBetween(e.target.value) })} />
                </label>
                <label>
                  To
                  <input type="date" value={iso(daysAgo(filter.to_days_ago ?? 0))} max={iso(today())} onChange={(e) => e.target.value && set({ to_days_ago: daysBetween(e.target.value) })} />
                </label>
              </div>
            )}
            {showMore && (
              <>
                <div className="ax-amtrange" data-stage-thing="filter:amount" data-stage-label="Amount">
                  <span>Amount</span>
                  <input type="number" inputMode="numeric" placeholder="Min ₹" min={0} value={filter.min_amount ?? ""} onChange={(e) => set({ min_amount: e.target.value === "" ? null : Number(e.target.value) })} aria-label="Minimum amount" />
                  <span aria-hidden>to</span>
                  <input type="number" inputMode="numeric" placeholder="Max ₹" min={0} value={filter.max_amount ?? ""} onChange={(e) => set({ max_amount: e.target.value === "" ? null : Number(e.target.value) })} aria-label="Maximum amount" />
                </div>
                <div className="ax-seg" role="radiogroup" aria-label="Direction" data-stage-thing="filter:direction" data-stage-label="Money in or out">
                  {(
                    [
                      ["any", "All"],
                      ["debit", "Money out"],
                      ["credit", "Money in"],
                    ] as const
                  ).map(([v, l]) => (
                    <button key={v} type="button" role="radio" aria-checked={(filter.direction ?? "any") === v} className={(filter.direction ?? "any") === v ? "is-on" : ""} onClick={() => set({ direction: v })}>
                      {l}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div className="ax-summary" data-stage-thing="txn-summary" data-stage-label="Results">
        <div className="ax-summary__count">
          <strong>{plural(rows.length, "transaction")}</strong>
          {filter.label && (
            <span className="ax-pill">
              {filter.label}
            </span>
          )}
        </div>
        <div className="ax-summary__totals">
          <span>
            <ArrowUpRight size={15} /> Out <strong>{inr(Math.round(debits * 100) / 100)}</strong>
          </span>
          <span className="is-in">
            <ArrowDownLeft size={15} /> In <strong>{inr(Math.round(credits * 100) / 100)}</strong>
          </span>
          {!filterIsEmpty(filter) && (
            <button type="button" className="ax-link" onClick={clearFilter}>
              Clear filters
            </button>
          )}
        </div>
      </div>

      <div className="ax-txns__body">
        <div className="ax-ledger" data-stage-thing="txn-list" data-stage-label="Transaction list">
          {groups.length === 0 && (
            <div className="ax-empty">
              <strong>No transactions match these filters.</strong>
              <span>Widen the date range or clear a filter to see more.</span>
              <button type="button" className="ax-btn ax-btn--ghost ax-btn--sm" onClick={clearFilter}>
                Clear filters
              </button>
            </div>
          )}
          {groups.map((g) => (
            <div key={g.day} className="ax-ledger__day">
              <div className="ax-ledger__date">{dateLabel(g.day)}</div>
              {g.txns.map((t) => (
                <button
                  type="button"
                  key={t.id}
                  className={`ax-ledger__row${selected === t.id ? " is-sel" : ""}`}
                  data-stage-thing={`txn:${t.id}`}
                  data-stage-label={t.merchant}
                  onClick={() => openTxn(selected === t.id ? null : t.id)}
                >
                  <CatIcon id={t.category} />
                  <span className="ax-ledger__main">
                    <strong>{t.merchant}</strong>
                    <span className="ax-stmt">{t.description}</span>
                  </span>
                  <span className="ax-ledger__chip">
                    <CatChip id={t.category} />
                  </span>
                  <span className="ax-ledger__mode">
                    {t.mode.charAt(0).toUpperCase() + t.mode.slice(1)}
                    <small>{ACCOUNT_LABEL[t.account]}</small>
                  </span>
                  <Amount t={t} />
                </button>
              ))}
            </div>
          ))}
          {rows.length > shown && (
            <div className="ax-more">
              <span className="ax-k">
                Showing {shown} of {rows.length}
              </span>
              <button type="button" className="ax-btn ax-btn--ghost ax-btn--sm" data-stage-thing="txn-more" data-stage-label="Show more" onClick={() => setLimit(shown + PAGE)}>
                Show {Math.min(PAGE, rows.length - shown)} more
              </button>
            </div>
          )}
        </div>
        {sel && <TxnDetail t={sel} onClose={() => openTxn(null)} />}
      </div>
    </div>
  );
}

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const daysBetween = (isoDate: string) => {
  const [y, m, d] = isoDate.split("-").map(Number);
  return Math.max(0, Math.round((today().getTime() - new Date(y, m - 1, d).getTime()) / 86400000));
};

export function TxnDetail({ t, onClose }: { t: Txn; onClose: () => void }) {
  const conv = useBank((s) => s.emi[t.id]);
  const [tenure, setTenure] = useState(6);
  const acc = t.account === "cc" ? `Credit card •••• ${cardById("credit")!.last4}` : `${accountById(t.account)!.name} •••• ${accountById(t.account)!.last4}`;
  const canEmi = t.account === "cc" && t.emi_eligible && t.amount >= products.emi.min_amount;
  const preview = cardEmi(t.amount, tenure);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !document.querySelector(".ax-sheet") && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="ax-detail-scrim" onClick={onClose} aria-hidden />
      <aside className="ax-detail" data-stage-thing="txn-detail" data-stage-label="Transaction details" aria-label="Transaction details">
        <div className="ax-detail__head">
          <CatIcon id={t.category} size={42} />
          <button type="button" className="ax-iconbtn" aria-label="Close details" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <h2 className="ax-detail__merchant">{t.merchant}</h2>
        <Amount t={t} big />
        <span className="ax-status ax-status--ok">{t.direction === "credit" ? "Received" : "Completed"}</span>

        <dl className="ax-dl">
          <div>
            <dt>Date</dt>
            <dd>{fmtDate(daysAgo(t.days_ago))}</dd>
          </div>
          <div>
            <dt>Account</dt>
            <dd>{acc}</dd>
          </div>
          <div>
            <dt>Category</dt>
            <dd>
              <CatChip id={t.category} />
            </dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>{t.mode.charAt(0).toUpperCase() + t.mode.slice(1)}</dd>
          </div>
          <div>
            <dt>Statement text</dt>
            <dd className="ax-stmt">{t.description}</dd>
          </div>
          <div>
            <dt>Reference no.</dt>
            <dd className="ax-stmt">{t.ref}</dd>
          </div>
          {t.balance_after != null && (
            <div>
              <dt>Balance after</dt>
              <dd>{inr(t.balance_after, { paise: true })}</dd>
            </div>
          )}
          <div>
            <dt>Transaction ID</dt>
            <dd className="ax-stmt">{t.id}</dd>
          </div>
        </dl>
        {t.note && (
          <p className="ax-detail__note" data-stage-thing="txn-note" data-stage-label="Note">
            {t.note}
          </p>
        )}

        {conv ? (
          <div className="ax-emiplan" data-stage-thing={`emi-plan:${t.id}`} data-stage-label="EMI plan">
            <strong>On EMI</strong>
            <span>
              {conv.tenure_months} months of {inr(conv.emi)} at {conv.rate}% a year
            </span>
            <span className="ax-k">Total cost {inr(conv.total_cost)}. Reference {conv.reference}</span>
          </div>
        ) : (
          canEmi && (
            <div className="ax-emibox" data-stage-thing="txn-emi" data-stage-label="Convert to EMI">
              <strong>Convert to EMI</strong>
              <div className="ax-tenures" role="radiogroup" aria-label="Tenure">
                {products.emi.tenures.map((x) => (
                  <button type="button" key={x.months} role="radio" aria-checked={tenure === x.months} className={tenure === x.months ? "is-on" : ""} onClick={() => setTenure(x.months)}>
                    {x.months}m
                  </button>
                ))}
              </div>
              <p>
                {inr(preview.emi)} a month for {tenure} months at {preview.rate}%. Total cost {inr(preview.total_cost)} incl. fee and GST.
              </p>
              <button type="button" className="ax-btn ax-btn--primary ax-btn--sm" onClick={() => askConfirm({ kind: "emi_convert", target: t.id, tenure_months: tenure })}>
                Convert to EMI
              </button>
            </div>
          )
        )}

        <button type="button" className="ax-btn ax-btn--ghost ax-btn--sm ax-detail__dispute" onClick={() => toast(`Dispute noted for ${t.id}. This is a demo, so nothing was sent.`, "info")}>
          <Flag size={15} /> Raise a dispute
        </button>
      </aside>
    </>
  );
}
