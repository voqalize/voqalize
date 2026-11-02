import { Check, GitCompare, Heart, X } from "lucide-react";
import { useEffect, useLayoutEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { marked } from "marked";
import { getProduct, money, productsByIds, roomName } from "../data/catalog";
import { getPage, pagePath, policies } from "../data/content";
import { useCart } from "../state/cart";
import { useShortlist } from "../state/shortlist";
import { mira, useMarked, useMira } from "../voice/controller";
import { buildCompare } from "../voice/local";
import type { CartLine } from "../voice/events";
import { useFocusTrap } from "./CartDrawer";
import { MiraTag, Photo, ProductPrice } from "./bits";

// ── Spotlight ring ─────────────────────────────────────────────────────────

/** A ring drawn over whatever `[data-spot=<target>]` is, for the length of its animation. */
export function Spotlight() {
  const spot = useMira((s) => s.spotlight);
  const [box, setBox] = useState<DOMRect | null>(null);
  useLayoutEffect(() => {
    if (!spot) return;
    let frame = 0;
    const started = Date.now();
    const track = () => {
      const el = document.querySelector(`[data-spot="${CSS.escape(spot.target)}"]`);
      setBox(el ? el.getBoundingClientRect() : null);
      if (Date.now() - started < 2300) frame = requestAnimationFrame(track);
      else setBox(null);
    };
    track();
    return () => cancelAnimationFrame(frame);
  }, [spot]);
  if (!spot || !box) return null;
  const pad = 6;
  return (
    <div
      key={spot.stamp}
      className="spotlight"
      aria-hidden
      style={{ left: box.left - pad, top: box.top - pad, width: box.width + pad * 2, height: box.height + pad * 2 }}
    />
  );
}

// ── Brief chips ────────────────────────────────────────────────────────────

export function BriefBar() {
  const brief = useMira((s) => s.brief);
  if (!brief) return null;
  const chips: string[] = [
    ...(brief.room ? [roomName(brief.room)] : []),
    ...(brief.uses ?? []),
    ...(brief.materials ?? []),
    ...(brief.colours ?? []),
    ...(brief.styles ?? []),
    ...(brief.budget ? [`Up to ${money(brief.budget)}`] : []),
  ];
  return (
    <div className="brief-bar" data-spot="section:brief">
      <div className="wrap brief-row">
        <span className="brief-label">Your brief</span>
        <ul className="brief-chips">
          {chips.map((c) => (
            <li key={c} className="chip brief-chip">
              {c.charAt(0).toUpperCase() + c.slice(1)}
            </li>
          ))}
        </ul>
        <span className="small brief-left">{brief.productsLeft} pieces match</span>
        {brief.by === "mira" ? <MiraTag /> : null}
        <button type="button" className="icon-btn" aria-label="Clear brief" onClick={() => mira.clearBrief()}>
          <X size={16} />
        </button>
      </div>
    </div>
  );
}

// ── Shortlist tray ─────────────────────────────────────────────────────────

export function ShortlistTray() {
  const { ids, open, setOpen, toggle, by } = useShortlist();
  const marked = useMarked("shortlist");
  const navigate = useNavigate();
  const ref = useFocusTrap(open);
  const list = productsByIds(ids);
  if (!open) return null;
  return (
    <div className="drawer-root" role="dialog" aria-modal="true" aria-label="Saved pieces" onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
      <button type="button" className="scrim" aria-label="Close saved pieces" onClick={() => setOpen(false)} />
      <div className="tray" ref={ref} data-spot="section:shortlist">
        <div className="tray-head">
          <h2 className="h3">
            Saved pieces {marked && by === "mira" ? <MiraTag label="Updated by Mira" /> : null}
          </h2>
          <div className="tray-tools">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={list.length < 2}
              onClick={() => {
                setOpen(false);
                mira.show_compare(buildCompare(ids.slice(0, 4)), "visitor");
                navigate("/compare");
              }}
            >
              <GitCompare size={15} /> Compare {Math.min(list.length, 4) || ""}
            </button>
            <button type="button" className="icon-btn" aria-label="Close saved pieces" onClick={() => setOpen(false)} data-autofocus>
              <X size={20} strokeWidth={1.6} />
            </button>
          </div>
        </div>
        {list.length === 0 ? (
          <p className="tray-empty small">
            <Heart size={15} aria-hidden /> Tap the heart on any piece to keep it here while you decide.
          </p>
        ) : (
          <ul className="tray-list">
            {list.map((p) => (
              <li key={p.id} className="tray-item" data-spot={`product:${p.id}`}>
                <Link to={`/product/${p.id}`} onClick={() => setOpen(false)} className="tray-photo">
                  <Photo file={p.images[0]} alt={p.title} sizes="160px" />
                </Link>
                <Link to={`/product/${p.id}`} onClick={() => setOpen(false)} className="tray-title">
                  {p.title}
                </Link>
                <ProductPrice p={p} />
                <button type="button" className="tray-remove" aria-label={`Remove ${p.title}`} onClick={() => toggle(p.id)}>
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── Policy slide-in ────────────────────────────────────────────────────────

export function PolicyPanel() {
  const topic = useMira((s) => s.policy);
  const ref = useFocusTrap(!!topic);
  if (!topic) return null;
  const page = getPage(topic);
  const summary = policies[topic];
  const html = page ? (marked.parse(page.body, { async: false }) as string) : "";
  return (
    <div className="drawer-root" role="dialog" aria-modal="true" aria-label={page?.title ?? "Policy"} onKeyDown={(e) => e.key === "Escape" && mira.closePolicy()}>
      <button type="button" className="scrim" aria-label="Close" onClick={() => mira.closePolicy()} />
      <div className="drawer drawer-right drawer-wide" ref={ref}>
        <div className="drawer-head">
          <h2 className="h3">{page?.title ?? topic}</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={() => mira.closePolicy()} data-autofocus>
            <X size={20} strokeWidth={1.6} />
          </button>
        </div>
        <div className="drawer-body">
          {page?.dek ? <p className="lede policy-dek">{page.dek}</p> : null}
          {summary?.summary ? <p className="policy-summary">{String(summary.summary)}</p> : null}
          <div className="prose prose-sm" dangerouslySetInnerHTML={{ __html: html }} />
          <Link to={pagePath(topic)} className="link small" onClick={() => mira.closePolicy()}>
            Open the full page
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Confirm before adding ──────────────────────────────────────────────────

const claims = new Set<string>();
const claimListeners = new Set<() => void>();
function useClaim(key: string, on: boolean) {
  useEffect(() => {
    if (!on) return;
    claims.add(key);
    claimListeners.forEach((l) => l());
    return () => {
      claims.delete(key);
      claimListeners.forEach((l) => l());
    };
  }, [key, on]);
}
function useClaimCount() {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((n) => n + 1);
    claimListeners.add(l);
    return () => void claimListeners.delete(l);
  }, []);
  return claims.size;
}

const linesLabel = (lines: CartLine[]) => {
  const n = lines.reduce((s, l) => s + l.qty, 0);
  if (lines.length === 1) {
    const p = getProduct(lines[0].product_id);
    return `${n > 1 ? `${n} × ` : ""}${p?.title ?? "this piece"}`;
  }
  return `${n} pieces`;
};

export function ConfirmBubble({ inline = false }: { inline?: boolean }) {
  const c = useMira((s) => s.confirm);
  if (!c) return null;
  return (
    <div className={`confirm${inline ? " is-inline" : " is-floating"}`} role="alertdialog" aria-label="Confirm add to cart" aria-live="assertive">
      <p className="confirm-q">
        {c.by === "mira" ? <MiraTag /> : null} {c.label || `Add ${linesLabel(c.lines)} to your cart?`}
      </p>
      <div className="confirm-actions">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => mira.answerConfirm(true)} autoFocus>
          <Check size={15} /> Add to cart
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => mira.answerConfirm(false)}>
          Not now
        </button>
      </div>
    </div>
  );
}

/**
 * An Add button that also hosts Mira's confirm prompt. `lines` is what it adds
 * by click; a confirm_add for any of `claimsFor` (product ids) shows here.
 */
export function AddButton({
  lines,
  label,
  claimsFor,
  confirmFirst = false,
  disabled,
}: {
  lines: CartLine[];
  label: string;
  claimsFor: string[];
  /** Ask before adding (used for multi-piece adds such as a whole room). */
  confirmFirst?: boolean;
  disabled?: boolean;
}) {
  const confirm = useMira((s) => s.confirm);
  const mine = !!confirm && confirm.lines.some((l) => claimsFor.includes(l.product_id));
  useClaim(claimsFor.join(","), mine);
  return (
    <div className="add-wrap">
      {mine ? <ConfirmBubble inline /> : null}
      <button
        type="button"
        className="btn btn-primary btn-block add-btn"
        data-spot="button:add-to-cart"
        data-dock-avoid
        disabled={disabled}
        onClick={() => {
          if (confirmFirst) void mira.confirm_add({ lines, label: "" }, "visitor");
          else useCart.getState().add(lines);
        }}
      >
        {label}
      </button>
    </div>
  );
}

/** Mira's confirm prompt when no Add button on screen owns it. */
export function FloatingConfirm() {
  const c = useMira((s) => s.confirm);
  const claimed = useClaimCount();
  if (!c || claimed > 0) return null;
  return <ConfirmBubble />;
}
