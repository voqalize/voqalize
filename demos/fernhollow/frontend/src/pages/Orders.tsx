/**
 * /orders — "Your orders": every order of the signed-in account (the ones
 * placed in this browser first, then the authored demo orders), and the one
 * selected beside the list with its status, timeline, items and what its
 * status allows: while packed, move the delivery day or cancel; on the way,
 * ask for an earlier delivery (a request, never a promise); delivered, start a
 * return within the window. "Policy in short" sits below both. Works by tap;
 * the agent does the same through the `orders.*` moves (src/stage/orders.ts).
 */
import { ArrowRight, Ban, CalendarClock, Check, Clock, Package, PackageCheck, RotateCcw, Truck, X } from "lucide-react";
import { useEffect, useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Crumbs, EmilyTag, Photo } from "../components/bits";
import { getProduct, money } from "../data/catalog";
import { policies } from "../data/content";
import {
  ACCOUNT_NAME,
  type AccountOrder,
  allOrders,
  bookedSlot,
  cap,
  canCancel,
  canMove,
  dayLabel,
  findOrder,
  isOnTheWay,
  outsideWindowText,
  RETURN_WINDOW_DAYS,
  returnable,
  type Status,
  STATUS_LABEL,
  statusOf,
  TIMELINE,
  useAccount,
  useOrderView,
} from "../orders/tracking";
import { persona } from "../persona";
import { storedReturns, useReturns } from "../returns/store";
import { useOrders } from "../state/orders";
import { navigatedBy } from "../voice/controller";
import { useTitle } from "./usePage";

const P = policies as Record<string, Record<string, string | number>>;
const agentName = (s: string) => s.replace(/\{\{agent\}\}/g, persona.name);

export function Orders() {
  useTitle("Your orders");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const asked = params.get("order");
  const open = useOrderView((s) => s.open);
  const placed = useOrders((s) => s.orders);
  const orders = useMemo(() => allOrders(placed), [placed]);

  // The URL is the source: ?order=FH-31207 opens that order.
  useEffect(() => {
    const o = findOrder(asked);
    const now = useOrderView.getState().open;
    if (o && now !== o.number) useOrderView.getState().setOpen(o.number, navigatedBy());
    if (!o && now) useOrderView.getState().setOpen(null);
  }, [asked]);

  const shown = orders.find((o) => o.number === open) ?? null;
  const choose = (n: string) => {
    navigate(`/orders?order=${n}`);
    // At phone width the detail sits below the list: bring it up.
    if (window.matchMedia?.("(max-width: 899px)").matches) {
      requestAnimationFrame(() => document.querySelector(".fd-order-detail")?.scrollIntoView({ block: "start", behavior: "smooth" }));
    }
  };

  return (
    <div className="wrap page-pad frontdesk orders" data-orders-page>
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Account" }, { label: "Your orders" }]} />
      <header className="fd-hero fd-hero-tight">
        <div>
          <p className="fd-eyebrow">
            <Package size={15} aria-hidden /> Signed in as {ACCOUNT_NAME}
          </p>
          <h1 className="h1">Your orders</h1>
          <p className="lede">Track a delivery, move its day or cancel while it is packed, and start a return once it has arrived.</p>
        </div>
      </header>

      <div className={`fd-orders${shown ? " has-open" : ""}`}>
        <ol className="fd-order-list" aria-label="Orders">
          {orders.map((o) => (
            <OrderCard key={o.number} o={o} active={shown?.number === o.number} onOpen={() => choose(o.number)} />
          ))}
        </ol>
        <div className="fd-order-detail">
          {shown ? (
            <OrderDetail key={shown.number} o={shown} />
          ) : (
            <div className="fd-order-empty">
              <Truck size={28} strokeWidth={1.3} aria-hidden />
              <p className="h3">Choose an order</p>
              <p className="small">You will see where it is, when it arrives, and what you can still change.</p>
            </div>
          )}
        </div>
      </div>

      <PolicyInShort
        rows={[
          ["Returns", `${cap(String(P.returns?.window ?? ""))}. ${P.returns?.condition ?? ""}`],
          ["Cancelling", String(P.returns?.cancellation ?? "")],
          ["Delivery changes", String(P.delivery?.changes ?? "")],
          ["Starting a return", agentName(String(P.returns?.howToStart ?? ""))],
        ]}
        links={[
          ["/policy/returns", "Returns policy"],
          ["/policy/delivery", "Delivery policy"],
        ]}
      />
    </div>
  );
}

/** "Policy in short", below the working area. */
export function PolicyInShort({ rows, links }: { rows: [string, string][]; links: [string, string][] }) {
  return (
    <section className="fd-policy" aria-labelledby="policy-short-h">
      <h2 className="h3" id="policy-short-h">
        Policy in short
      </h2>
      <dl className="fd-policy-list">
        {rows
          .filter(([, v]) => v.trim())
          .map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
      </dl>
      <p className="fd-policy-links">
        {links.map(([to, label]) => (
          <Link key={to} to={to} className="link small">
            {label} <ArrowRight size={12} aria-hidden />
          </Link>
        ))}
      </p>
    </section>
  );
}

function StatusPill({ status }: { status: Status }) {
  return <span className={`fd-status is-${status}`}>{STATUS_LABEL[status]}</span>;
}

function whenLine(o: AccountOrder, status: Status, slot: ReturnType<typeof bookedSlot>): string {
  if (status === "cancelled") return "Cancelled";
  if (status === "delivered") return `Delivered ${dayLabel(-(o.delivered_days_ago ?? 0))}`;
  if (!slot) return "Arriving soon";
  if (slot.days_from_now === 0) return `Arriving today, ${slot.hours}`;
  return `Arriving ${dayLabel(slot.days_from_now)}, ${slot.window}`;
}

function OrderCard({ o, active, onOpen }: { o: AccountOrder; active: boolean; onOpen: () => void }) {
  const state = useAccount();
  const status = statusOf(o, state);
  const slot = bookedSlot(o, state.moved);
  const items = o.lines.reduce((n, l) => n + l.qty, 0);
  return (
    <li>
      <button
        type="button"
        className={`fd-order-card${active ? " is-active" : ""}${status === "cancelled" ? " is-cancelled" : ""}`}
        aria-current={active ? "true" : undefined}
        onClick={onOpen}
        data-stage-part={`order-card:${o.number}`}
      >
        <span className="fd-order-top">
          <span className="fd-order-no">{o.number}</span>
          <StatusPill status={status} />
        </span>
        <span className="fd-order-when">{whenLine(o, status, slot)}</span>
        <span className="fd-order-thumbs">
          {o.lines.map((l) => {
            const p = getProduct(l.product_id);
            return p ? <Photo key={l.product_id} file={p.images[0]} alt="" sizes="56px" /> : null;
          })}
        </span>
        <span className="small">
          Placed {dayLabel(-o.placed_days_ago)} · {items} item{items === 1 ? "" : "s"} · {money(o.total)}
        </span>
      </button>
    </li>
  );
}

function OrderDetail({ o }: { o: AccountOrder }) {
  const state = useAccount();
  const opened = useOrderView((s) => s.opened);
  const status = statusOf(o, state);
  const slot = bookedSlot(o, state.moved);
  const t = o.tracking;
  const eventOf = (stage: string) => t.events.find((e) => e.stage === stage);
  const stageIndex = TIMELINE.findIndex((s) => s.id === t.stage);
  const steps = status === "cancelled" ? TIMELINE.slice(0, stageIndex + 1) : TIMELINE;

  const summary =
    status === "cancelled"
      ? "This order was cancelled while it was packed. It will not be delivered."
      : status === "packed"
        ? `Packed at our warehouse and waiting for its van.${t.two_person ? " A two-person team brings it in." : ""}`
        : status === "on_the_way"
          ? "On its way to your local depot."
          : status === "out_for_delivery"
            ? `On the van today${slot ? `, due ${slot.hours}` : ""}.${t.delivery.stops_before ? ` ${t.delivery.stops_before} stops before yours.` : ""}`
            : `Delivered ${dayLabel(-(o.delivered_days_ago ?? 0))}.`;

  const fee = o.delivery_fee == null ? "" : o.delivery_fee > 0 ? ` incl. ${money(o.delivery_fee)} delivery` : " · free delivery";

  return (
    <article className="fd-order" data-stage-thing={`order:${o.number}`} data-stage-label={`Order ${o.number}`} aria-labelledby={`h-${o.number}`}>
      <header className="fd-order-head">
        <div>
          <h2 className="h2" id={`h-${o.number}`}>
            {o.number} {opened?.order_number === o.number && opened.by === "emily" ? <EmilyTag /> : null}
          </h2>
          <p className="small">
            Placed {dayLabel(-o.placed_days_ago)} · {money(o.total)}
            {fee}
          </p>
        </div>
        <StatusPill status={status} />
      </header>
      <p className="fd-order-summary">{summary}</p>

      <OrderActions o={o} />

      <ol className="fd-timeline" aria-label="Tracking">
        {steps.map((s, i) => {
          const e = eventOf(s.id);
          const st = i < stageIndex ? "done" : i === stageIndex ? (status === "cancelled" ? "done" : "now") : "next";
          return (
            <li key={s.id} className={`is-${st}`}>
              <span className="fd-dot" aria-hidden>
                {st !== "next" ? <Check size={11} strokeWidth={3} /> : null}
              </span>
              <div>
                <p className="fd-tl-label">{s.label}</p>
                {e ? (
                  <p className="small">
                    {dayLabel(-e.days_ago)}, {e.time} · {e.text}
                  </p>
                ) : s.id === "delivered" && slot && status !== "delivered" ? (
                  <p className="small">Booked for {slot.days_from_now === 0 ? "today" : dayLabel(slot.days_from_now)}, {slot.window} ({slot.hours})</p>
                ) : null}
              </div>
            </li>
          );
        })}
        {status === "cancelled" ? (
          <li className="is-now is-cancel">
            <span className="fd-dot" aria-hidden>
              <X size={11} strokeWidth={3} />
            </span>
            <div>
              <p className="fd-tl-label">Cancelled</p>
            </div>
          </li>
        ) : null}
      </ol>

      <ul className="fd-order-lines">
        {o.lines.map((l) => {
          const p = getProduct(l.product_id);
          return (
            <li key={l.product_id}>
              {p ? <Photo file={p.images[0]} alt="" sizes="72px" /> : null}
              <div>
                <Link to={`/product/${l.product_id}?variant=${l.variant_id}`} className="fd-line-title">
                  {p?.title ?? l.title}
                </Link>
                <p className="small">
                  {l.variant} · Qty {l.qty}
                </p>
              </div>
              <span className="price">{money(l.unit_price * l.qty)}</span>
            </li>
          );
        })}
      </ul>
      <Link to="/policy/delivery" className="link small">
        How delivery works <ArrowRight size={12} aria-hidden />
      </Link>
    </article>
  );
}

/** What the order's status allows, in one panel. */
function OrderActions({ o }: { o: AccountOrder }) {
  const state = useAccount();
  const status = statusOf(o, state);
  if (status === "packed") return <PackedActions o={o} />;
  if (isOnTheWay(status)) return <OnTheWayActions o={o} />;
  if (status === "delivered") return <DeliveredActions o={o} />;
  return (
    <section className="fd-actions is-quiet" aria-label="Order actions">
      <div className="fd-delivery-row">
        <Ban size={20} strokeWidth={1.5} aria-hidden />
        <div>
          <p className="fd-delivery-k">Cancelled {state.cancelledEv?.order_number === o.number && state.cancelledEv.by === "emily" ? <EmilyTag /> : null}</p>
          <p className="fd-delivery-v">Nothing more to do on this order.</p>
        </div>
      </div>
    </section>
  );
}

function PackedActions({ o }: { o: AccountOrder }) {
  const state = useAccount();
  const picking = useOrderView((s) => s.picking);
  const pending = useOrderView((s) => s.pending);
  const confirming = useOrderView((s) => s.confirming);
  const slot = bookedSlot(o, state.moved);
  const movable = canMove(o, state);
  const byAgent = state.movedEv?.order_number === o.number && state.movedEv.by === "emily";
  const view = useOrderView.getState;

  return (
    <section className="fd-actions" aria-label="Order actions" data-reveal-group>
      <div className="fd-delivery-row">
        <CalendarClock size={20} strokeWidth={1.5} aria-hidden />
        <div>
          <p className="fd-delivery-k">Delivery {byAgent ? <EmilyTag /> : null}</p>
          <p className="fd-delivery-v">{slot ? `${dayLabel(slot.days_from_now)}, ${slot.window} · ${slot.hours}` : "We will agree a day with you"}</p>
        </div>
        {movable && !picking ? (
          <button type="button" className="btn btn-ghost btn-sm" data-stage-part={`order:${o.number}:change`} onClick={() => view().setPicking(true, slot?.id ?? null)}>
            Change delivery day
          </button>
        ) : null}
      </div>

      {picking && movable ? (
        <div className="fd-picker" data-reveal-group data-stage-part={`order:${o.number}:slots`}>
          <p className="fd-picker-k">Choose a new delivery day</p>
          <div className="fd-slots" role="radiogroup" aria-label="Delivery days">
            {o.tracking.slots.map((s) => (
              <button
                key={s.id}
                type="button"
                role="radio"
                aria-checked={pending === s.id}
                className={`fd-slot${pending === s.id ? " is-on" : ""}`}
                data-stage-part={`slot:${s.id}`}
                onClick={() => view().setPending(s.id)}
              >
                <span className="fd-slot-day">{dayLabel(s.days_from_now)}</span>
                <span className="fd-slot-win">
                  {cap(s.window)}
                  {s.id === slot?.id ? <span className="fd-slot-now"> · booked</span> : null}
                </span>
                <span className="small">{s.hours}</span>
              </button>
            ))}
          </div>
          <div className="fd-slot-actions">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              data-stage-part={`order:${o.number}:save`}
              disabled={!pending || pending === slot?.id}
              onClick={() => {
                if (pending) useAccount.getState().move(o.number, pending);
                view().setPicking(false);
              }}
            >
              Save
            </button>
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => view().setPicking(false)}>
              Keep {slot ? dayLabel(slot.days_from_now) : "the current day"}
            </button>
          </div>
        </div>
      ) : null}

      <div className="fd-cancel-row">
        {confirming ? (
          <div className="fd-confirm" role="alertdialog" aria-labelledby={`cancel-q-${o.number}`}>
            <p className="fd-confirm-q" id={`cancel-q-${o.number}`}>
              Cancel order {o.number}?
            </p>
            <div className="fd-confirm-actions">
              <button
                type="button"
                className="btn btn-danger btn-sm"
                data-stage-part={`order:${o.number}:cancel-yes`}
                onClick={() => {
                  useAccount.getState().cancel(o.number);
                  view().setConfirming(false);
                }}
              >
                Yes, cancel
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => view().setConfirming(false)}>
                Keep it
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="small">It can be cancelled while it is packed at our warehouse.</p>
            <button
              type="button"
              className="btn btn-quiet btn-sm fd-cancel-btn"
              data-stage-part={`order:${o.number}:cancel`}
              disabled={!canCancel(o, state)}
              onClick={() => view().setConfirming(true)}
            >
              <X size={14} aria-hidden /> Cancel order
            </button>
          </>
        )}
      </div>
    </section>
  );
}

function OnTheWayActions({ o }: { o: AccountOrder }) {
  const state = useAccount();
  const slot = bookedSlot(o, state.moved);
  const status = statusOf(o, state);
  const asked = !!state.earlier[o.number];
  const byAgent = state.earlierEv?.order_number === o.number && state.earlierEv.by === "emily";
  const stops = o.tracking.delivery.stops_before;
  return (
    <section className="fd-actions" aria-label="Order actions" data-reveal-group>
      <div className="fd-delivery-row">
        <Truck size={20} strokeWidth={1.5} aria-hidden />
        <div>
          <p className="fd-delivery-k">Expected</p>
          <p className="fd-delivery-v">
            {slot ? `${slot.days_from_now === 0 ? "Today" : dayLabel(slot.days_from_now)}, ${slot.window} · ${slot.hours}` : "We will be in touch with a day"}
          </p>
          {status === "out_for_delivery" && stops ? (
            <p className="small fd-stops">
              <Clock size={13} aria-hidden /> {stops} stops before yours
            </p>
          ) : null}
        </div>
      </div>
      {o.tracking.why_not ? <p className="small fd-why">{o.tracking.why_not}</p> : null}
      {asked ? (
        <p className="fd-note" role="status" data-stage-part={`order:${o.number}:earlier`}>
          <Check size={15} aria-hidden /> Earlier delivery requested — we've passed it to the driver. It's a request, not a promise. {byAgent ? <EmilyTag /> : null}
        </p>
      ) : (
        <div className="fd-action-row">
          <button type="button" className="btn btn-ghost btn-sm" data-stage-part={`order:${o.number}:earlier`} onClick={() => useAccount.getState().requestEarlier(o.number)}>
            Request an earlier delivery
          </button>
          <p className="small">We pass it to the driver as a request, not a promise.</p>
        </div>
      )}
    </section>
  );
}

function DeliveredActions({ o }: { o: AccountOrder }) {
  const navigate = useNavigate();
  const state = useAccount();
  const r = returnable(o, state);
  const returns = storedReturns().filter((x) => x.order_number === o.number);
  const start = () => {
    useReturns.getState().start(o.number);
    navigate(`/orders/return?order=${o.number}`);
  };
  return (
    <section className="fd-actions" aria-label="Order actions" data-reveal-group>
      <div className="fd-delivery-row">
        <PackageCheck size={20} strokeWidth={1.5} aria-hidden />
        <div>
          <p className="fd-delivery-k">Returns</p>
          <p className="fd-delivery-v">
            {r.kind === "eligible"
              ? `${r.daysLeft} day${r.daysLeft === 1 ? "" : "s"} left to start a return`
              : r.kind === "outside_window"
                ? outsideWindowText(r.days)
                : `Unused pieces can go back within ${RETURN_WINDOW_DAYS} days of delivery.`}
          </p>
        </div>
        <button type="button" className="btn btn-primary btn-sm" data-stage-part={`order:${o.number}:return`} disabled={r.kind !== "eligible"} onClick={start}>
          <RotateCcw size={14} aria-hidden /> Start a return
        </button>
      </div>
      {r.kind === "outside_window" ? (
        <p className="small fd-why">
          Our{" "}
          <Link className="link" to="/policy/care">
            care guides
          </Link>{" "}
          may help, or{" "}
          <Link className="link" to="/contact">
            write to the studio
          </Link>
          .
        </p>
      ) : null}
      {returns.length ? (
        <ul className="fd-returns-made">
          {returns.map((x) => (
            <li key={x.reference} className="small">
              Return <strong>{x.reference}</strong> submitted {dayLabel(-Math.max(0, Math.floor((Date.now() - Date.parse(x.submitted_at)) / 86_400_000)))}:{" "}
              {x.items.map((it) => `${it.qty} × ${it.title}`).join(", ")}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
