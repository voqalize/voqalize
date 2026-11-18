/** Building blocks shared by the banking app's screens. */
import {
  Banknote,
  Bus,
  CircleDollarSign,
  Clapperboard,
  Coins,
  Fuel,
  HeartPulse,
  Home,
  Landmark,
  type LucideIcon,
  Receipt,
  RotateCcw,
  ShoppingBag,
  ShoppingBasket,
  TrendingUp,
  Utensils,
  ArrowLeftRight,
  Wallet,
} from "lucide-react";
import type { ReactNode } from "react";
import { type Txn, cardById, categoryName, inr } from "../../data/bank";
import type { CardId } from "../../state/bank";

export const CATEGORY: Record<string, { color: string; icon: LucideIcon }> = {
  food: { color: "#d9822b", icon: Utensils },
  groceries: { color: "#5a9a3c", icon: ShoppingBasket },
  shopping: { color: "#b8558a", icon: ShoppingBag },
  travel: { color: "#2f7fb5", icon: Bus },
  fuel: { color: "#8c6d1f", icon: Fuel },
  bills: { color: "#5b6bbf", icon: Receipt },
  entertainment: { color: "#8a4fbf", icon: Clapperboard },
  health: { color: "#c2412d", icon: HeartPulse },
  rent: { color: "#1d7468", icon: Home },
  emi: { color: "#0e4d45", icon: Landmark },
  investments: { color: "#3f8f7a", icon: TrendingUp },
  transfers: { color: "#6b7a77", icon: ArrowLeftRight },
  cash: { color: "#7c8a3a", icon: Banknote },
  fees: { color: "#9a5b45", icon: Coins },
  income: { color: "#1f8a5b", icon: Wallet },
  refunds: { color: "#2a8f8f", icon: RotateCcw },
};
export const catColor = (id: string) => CATEGORY[id]?.color ?? "#6b7a77";

export function CatIcon({ id, size = 34 }: { id: string; size?: number }) {
  const Icon = CATEGORY[id]?.icon ?? CircleDollarSign;
  return (
    <span className="ax-caticon" style={{ width: size, height: size, color: catColor(id), background: `color-mix(in srgb, ${catColor(id)} 12%, white)` }} aria-hidden>
      <Icon size={Math.round(size * 0.5)} strokeWidth={2} />
    </span>
  );
}

export function CatChip({ id }: { id: string }) {
  return (
    <span className="ax-chip" style={{ color: `color-mix(in srgb, ${catColor(id)} 80%, black)`, background: `color-mix(in srgb, ${catColor(id)} 11%, white)` }}>
      {categoryName(id)}
    </span>
  );
}

export function Amount({ t, big }: { t: Pick<Txn, "amount" | "direction">; big?: boolean }) {
  const credit = t.direction === "credit";
  return (
    <span className={`ax-amt${credit ? " ax-amt--cr" : ""}${big ? " ax-amt--big" : ""}`}>
      {credit ? "+" : "−"}
      {inr(t.amount).replace("−", "")}
    </span>
  );
}

/** ₹3,42,815.40 with the paise set smaller. */
export function Money({ n, className }: { n: number; className?: string }) {
  const s = inr(n, { paise: true });
  const [whole, paise] = s.split(".");
  return (
    <span className={`ax-money ${className ?? ""}`}>
      {whole}
      <small>.{paise}</small>
    </span>
  );
}

export function PageHead({ title, sub, actions, children }: { title: string; sub?: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <header className="ax-pagehead">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
        {children}
      </div>
      {actions && <div className="ax-pagehead__actions">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  action,
  children,
  thing,
  label,
  className,
  pad = true,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  thing?: string;
  label?: string;
  className?: string;
  pad?: boolean;
}) {
  return (
    <section className={`ax-panel ${pad ? "" : "ax-panel--flush"} ${className ?? ""}`} data-stage-thing={thing} data-stage-label={label}>
      {(title || action) && (
        <div className="ax-panel__head">
          {title && <h2>{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  thing,
  disabled,
  danger,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  hint?: string;
  thing?: string;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <div className={`ax-toggle-row${disabled ? " is-disabled" : ""}`} data-stage-thing={thing} data-stage-label={label}>
      <div>
        <div className="ax-toggle-row__label">{label}</div>
        {hint && <div className="ax-toggle-row__hint">{hint}</div>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        className={`ax-switch${checked ? " is-on" : ""}${danger ? " ax-switch--danger" : ""}`}
        onClick={onChange}
      >
        <span />
      </button>
    </div>
  );
}

/** A CSS card face. */
export function CardFace({ card, blocked, small, color, name, network, last4, expiry }: {
  card?: CardId;
  blocked?: boolean;
  small?: boolean;
  color?: string;
  name?: string;
  network?: string;
  last4?: string;
  expiry?: string;
}) {
  const c = card ? cardById(card)! : null;
  const kind = c?.kind ?? "credit";
  const bg = color ?? (kind === "debit" ? "#0e4d45" : "#E8613C");
  return (
    <div className={`ax-cardface${small ? " ax-cardface--sm" : ""}${blocked ? " is-blocked" : ""} ax-cardface--${kind}`} style={{ ["--card" as string]: bg }}>
      <div className="ax-cardface__top">
        <span className="ax-cardface__brand">Anvaya</span>
        <span className="ax-cardface__name">{name ?? c?.name}</span>
      </div>
      <div className="ax-cardface__chip" aria-hidden />
      <div className="ax-cardface__num">{small ? "••••" : "•••• •••• ••••"} {last4 ?? c?.last4 ?? "0000"}</div>
      <div className="ax-cardface__bottom">
        <div>
          <span className="ax-cardface__k">Valid thru</span>
          <span>{expiry ?? c?.expiry ?? "--/--"}</span>
        </div>
        <span className="ax-cardface__net">{network ?? c?.network}</span>
      </div>
      {blocked && <div className="ax-cardface__blocked">Blocked</div>}
    </div>
  );
}

export function Meter({ value, max, tone = "teal" }: { value: number; max: number; tone?: "teal" | "gold" }) {
  const pct = Math.max(0, Math.min(100, (value / Math.max(1, max)) * 100));
  return (
    <div className={`ax-meter ax-meter--${tone}`} role="presentation">
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

export const ACCOUNT_LABEL: Record<string, string> = { sb: "Savings", ca: "Current", cc: "Credit card" };

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export function inDays(n: number) {
  if (n === 0) return "today";
  if (n === 1) return "tomorrow";
  return `in ${n} days`;
}
