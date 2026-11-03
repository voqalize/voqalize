/**
 * The surfaces Emily builds: the room board, the compare board and her listing.
 * Each also works by hand — a shopper can plan a room, swap pieces, find
 * savings and compare saved pieces without saying a word.
 */
import { ArrowLeftRight, Check, PiggyBank, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ROOMS, type RoomId, getCategory, getProduct, getRoom, imgUrl, money, productsByIds, roomName } from "../data/catalog";
import { site } from "../data/content";
import { Crumbs, EmilyMark, EmilyTag, PriceLine } from "../components/bits";
import { ProductCard, ProductGrid } from "../components/ProductCard";
import { AddButton } from "../components/Overlays";
import { useShortlist } from "../state/shortlist";
import { emily, useEmily } from "../voice/controller";
import { buildCompare, buildRoomSet, findSavings, nextInSlot, pieceFor, suggestedBudget, totalOf } from "../voice/local";
import type { Piece } from "../voice/types";
import { useTitle, useVisibleProducts } from "./usePage";

// ── Room board ─────────────────────────────────────────────────────────────

export function BoardPage() {
  useTitle("Plan a room");
  const board = useEmily((s) => s.board);
  const [sp] = useSearchParams();
  const asked = getRoom(sp.get("room") ?? undefined)?.id;
  const [room, setRoom] = useState<RoomId>(asked ?? (board?.room as RoomId) ?? "living");
  const [budget, setBudget] = useState<number>(() => suggestedBudget(room));
  useEffect(() => {
    if (asked && (!board || board.room !== asked)) setRoom(asked);
  }, [asked, board]);
  useEffect(() => {
    if (!board || board.room !== room) setBudget(suggestedBudget(room));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room]);

  // A new board (from Emily or by hand) carries its own room and budget.
  useEffect(() => {
    if (!board) return;
    setRoom(board.room as RoomId);
    setBudget(board.budget);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [board?.version]);

  const [editing, setEditing] = useState(false);
  const build = () => {
    setEditing(false);
    emily.show_room_set(buildRoomSet(room, budget), "visitor");
  };

  return (
    <div className="wrap page-pad board-page">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Plan a room" }]} />
      <header className="listing-head board-head">
        <div>
          <h1 className="h1">{board ? `Your ${roomName(board.room).toLowerCase()}` : "Plan a room"}</h1>
          <p className="lede">
            {board
              ? "A first set of pieces within your budget. Swap any of them, ask for savings, then add the room to your cart."
              : "Pick a room and a budget, and we lay out a first set of pieces. Or ask Emily to do it while you talk."}
          </p>
        </div>
        {board?.by === "emily" ? <EmilyTag label="Built by Emily" /> : null}
      </header>

      {board ? (
        <button type="button" className="planner-summary only-mobile" aria-expanded={editing} onClick={() => setEditing(!editing)}>
          <span>
            {roomName(board.room)}, {money(board.budget)} budget
          </span>
          <span className="link small">{editing ? "Done" : "Change"}</span>
        </button>
      ) : null}
      <form
        className={`planner${board && !editing ? " is-collapsed" : ""}`}
        onSubmit={(e) => {
          e.preventDefault();
          build();
        }}
      >
        <fieldset className="planner-rooms">
          <legend className="filter-title">Room</legend>
          <div className="band-chips">
            {ROOMS.map((r) => (
              <button type="button" key={r.id} className="chip" aria-pressed={room === r.id} onClick={() => setRoom(r.id)}>
                {r.name}
              </button>
            ))}
          </div>
        </fieldset>
        <label className="planner-budget">
          <span className="filter-title">Budget</span>
          <span className="budget-input">
            <span className="price-prefix">$</span>
            <input
              className="input"
              inputMode="numeric"
              value={budget ? String(budget) : ""}
              onChange={(e) => setBudget(Number(e.target.value.replace(/[^\d]/g, "")) || 0)}
              aria-label="Budget in dollars"
            />
          </span>
        </label>
        <button type="submit" className="btn btn-primary" disabled={!budget}>
          {board ? "Rebuild the room" : "Lay out the room"}
        </button>
      </form>

      {board ? <RoomBoardView /> : <p className="small board-hint">{site.rooms[room]}</p>}
    </div>
  );
}

export function RoomBoardView() {
  const board = useEmily((s) => s.board)!;
  const over = board.total > board.budget;
  const pct = Math.min(100, (board.total / Math.max(1, board.budget)) * 100);
  const lines = board.pieces.map((p) => ({ product_id: p.product_id, variant_id: p.variant_id, qty: 1 }));
  return (
    <section className="board" aria-label="Room board" data-spot="section:room-board">
      <div className="budget" data-spot="section:budget">
        <div className="budget-top">
          <p>
            <span className="price budget-total">{money(board.total)}</span>{" "}
            <span className="small">of {money(board.budget)} budget</span>
          </p>
          <p className={`small budget-left${over ? " is-over" : ""}`}>
            {over ? `${money(Math.round((board.total - board.budget) * 100) / 100)} over` : `${money(Math.round((board.budget - board.total) * 100) / 100)} left`}
          </p>
        </div>
        <div className="budget-bar" role="meter" aria-valuemin={0} aria-valuemax={board.budget} aria-valuenow={board.total} aria-label="Budget used">
          <span className={over ? "is-over" : undefined} style={{ width: `${pct}%` }} />
        </div>
        {board.saved > 0 ? (
          <p className="savings-line">
            <PiggyBank size={16} aria-hidden /> Saved {money(board.saved)} with {board.savings.length} swap{board.savings.length === 1 ? "" : "s"}
            {board.movedTo ? `, moved to ${board.movedTo}` : ""} <EmilyMark k="savings" />
          </p>
        ) : null}
      </div>

      <ul className="board-grid" key={board.version} data-emily-start>
        {board.pieces.map((piece, i) => (
          <BoardTile key={piece.slot} piece={piece} index={i} />
        ))}
      </ul>

      <div className="board-actions">
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => {
            const s = findSavings(board.pieces);
            if (s.swaps.length) void emily.show_savings(s, "visitor");
          }}
        >
          <PiggyBank size={16} /> Find savings
        </button>
        <div className="board-add">
          <AddButton
            lines={lines}
            confirmFirst
            label={`Add the room to cart, ${money(board.total)}`}
            claimsFor={board.pieces.map((p) => p.product_id)}
            disabled={!lines.length}
          />
        </div>
      </div>
    </section>
  );
}

function BoardTile({ piece, index }: { piece: Piece; index: number }) {
  const board = useEmily((s) => s.board)!;
  const p = getProduct(piece.product_id);
  const changed = board.changed.includes(piece.slot);
  const swap = board.savings.find((s) => s.slot === piece.slot);
  const slotName = getCategory(p?.categorySlug)?.name ?? piece.slot;
  const swapTo = (dir: 1 | -1) => {
    const next = nextInSlot(piece, dir);
    if (!next) return;
    const np = pieceFor(next, "Swapped by you", piece.slot);
    const pieces = board.pieces.map((x) => (x.slot === piece.slot ? np : x));
    void emily.swap_piece({ slot: piece.slot, old_product_id: piece.product_id, piece: np, total: totalOf(pieces) }, "visitor");
  };
  return (
    <li
      className={`tile${changed ? " is-changed" : ""}`}
      style={{ animationDelay: `${index * 160}ms` }}
      data-spot={`slot:${piece.slot}`}
      data-fh-thing={`product:${piece.product_id}`}
    >
      <Link to={`/product/${piece.product_id}`} className="tile-photo" key={piece.product_id}>
        <img src={imgUrl(piece.image, 400)} alt={piece.title} loading="lazy" width={768} height={1344} />
        {swap ? (
          <span className="badge badge-sale tile-badge">
            Was {money(swap.was)}, now {money(swap.now)}
          </span>
        ) : null}
      </Link>
      <div className="tile-body">
        <p className="tile-slot small">
          {slotName} {changed && board.by === "emily" ? <EmilyTag /> : null}
        </p>
        <Link to={`/product/${piece.product_id}`} className="tile-title">
          {piece.title}
        </Link>
        <PriceLine price={piece.price} compare={piece.compare_at} />
        {piece.reason ? <p className="small tile-reason">{piece.reason}</p> : null}
        <div className="tile-actions">
          <button type="button" className="tile-btn" onClick={() => swapTo(-1)} aria-label={`Cheaper ${slotName.toLowerCase()}`}>
            Cheaper
          </button>
          <button type="button" className="tile-btn" onClick={() => swapTo(1)} aria-label={`Swap ${slotName.toLowerCase()}`}>
            <ArrowLeftRight size={13} /> Swap
          </button>
          <button type="button" className="tile-btn" onClick={() => emily.removePiece(piece.slot)} aria-label={`Remove ${slotName.toLowerCase()}`}>
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </li>
  );
}

// ── Compare board ──────────────────────────────────────────────────────────

export function ComparePage() {
  useTitle("Compare");
  const compare = useEmily((s) => s.compare);
  const saved = useShortlist((s) => s.ids);
  const list = productsByIds(compare?.ids ?? []);
  return (
    <div className="wrap page-pad">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Compare" }]} />
      <header className="listing-head board-head">
        <h1 className="h1">Side by side</h1>
        {compare?.by === "emily" ? <EmilyTag label="Compared by Emily" /> : null}
      </header>
      {!compare || list.length === 0 ? (
        <div className="empty">
          <p className="h3">Nothing to compare yet.</p>
          <p className="small">Save two to four pieces with the heart, then compare them here.</p>
          <button type="button" className="btn btn-ghost btn-sm" disabled={saved.length < 2} onClick={() => emily.show_compare(buildCompare(saved.slice(0, 4)), "visitor")}>
            Compare saved pieces
          </button>
        </div>
      ) : (
        <CompareBoard />
      )}
    </div>
  );
}

export function CompareBoard() {
  const compare = useEmily((s) => s.compare)!;
  const list = productsByIds(compare.ids);
  return (
    <section className="compare" data-spot="section:compare" aria-label="Comparison">
      <div className="compare-scroll" data-emily-start>
        <table className="compare-table" style={{ ["--cols" as string]: list.length }}>
          <thead>
            <tr>
              <th scope="col" className="compare-label">
                <span className="sr-only">Detail</span>
              </th>
              {list.map((p) => (
                <th scope="col" key={p.id} className="compare-head">
                  <ProductCard p={p} sizes="(min-width: 900px) 18vw, 45vw" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {compare.rows.map((r) => (
              <tr key={r.label}>
                <th scope="row" className="compare-label">
                  {r.label}
                </th>
                {list.map((p, i) => (
                  <td key={p.id} className={r.winner === i ? "is-winner" : undefined}>
                    {r.values[i] ?? "—"}
                    {r.winner === i ? (
                      <span className="winner-mark">
                        <Check size={13} aria-hidden /> Best
                      </span>
                    ) : null}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" className="compare-label">
                In short
              </th>
              <td colSpan={list.length} className="compare-summary">
                {compare.summary}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

// ── Emily's listing (show_products / apply_filters) ─────────────────────────

export function PicksPage() {
  const listing = useEmily((s) => s.listing);
  useTitle(listing?.title ?? "Picked for you");
  const list = useMemo(() => productsByIds(listing?.ids ?? []), [listing]);
  useVisibleProducts(list.map((p) => p.id));
  if (!listing) {
    return (
      <div className="wrap page-pad empty-page">
        <h1 className="h1">Picked for you</h1>
        <p className="lede">When Emily shows you a set of pieces, they appear here. Ask her for something, or browse every piece.</p>
        <Link to="/shop" className="btn btn-ghost">
          Browse all pieces
        </Link>
      </div>
    );
  }
  const chips = filterChips(listing.filters);
  return (
    <div className="wrap page-pad">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: listing.title }]} />
      <header className="listing-head">
        <h1 className="h1">
          {listing.title} {listing.by === "emily" ? <EmilyTag /> : null}
        </h1>
        {listing.query ? <p className="lede">For “{listing.query}”</p> : null}
      </header>
      {chips.length || listing.assumption ? (
        <div className="active-filters" data-spot="section:filters" data-emily-start>
          {chips.map((c) => (
            <button key={c.key} type="button" className="chip is-on" data-spot={`filter:${c.key}`} onClick={() => emily.removeFilterByHand(c.key)} aria-label={`Remove filter ${c.label}`}>
              {c.label} <X size={13} className="x" />
            </button>
          ))}
          <EmilyMark k="filters" />
          {listing.assumption ? <p className="assumption small">{listing.assumption}</p> : null}
        </div>
      ) : null}
      <p className="small listing-count" data-emily-start>
        {list.length} {list.length === 1 ? "piece" : "pieces"}
      </p>
      {list.length ? (
        <ProductGrid products={list} />
      ) : (
        <div className="empty">
          <p className="h3">Nothing matches every filter.</p>
          <p className="small">Remove a chip above to widen the search.</p>
        </div>
      )}
    </div>
  );
}

function filterChips(f: import("../data/catalog").ContractFilters | null): { key: string; label: string }[] {
  if (!f) return [];
  const out: { key: string; label: string }[] = [];
  if (f.room) out.push({ key: "room", label: roomName(f.room) });
  if (f.category) out.push({ key: "category", label: getCategory(f.category)?.name ?? f.category });
  for (const field of ["materials", "colours", "styles"] as const)
    for (const w of f[field] ?? []) out.push({ key: `${field}:${w}`, label: w.charAt(0).toUpperCase() + w.slice(1) });
  if (f.price_min != null || f.price_max != null)
    out.push({
      key: "price",
      label:
        f.price_min != null && f.price_max != null
          ? `${money(f.price_min)} – ${money(f.price_max)}`
          : f.price_max != null
            ? `Under ${money(f.price_max)}`
            : `Over ${money(f.price_min!)}`,
    });
  if (f.on_sale) out.push({ key: "on_sale", label: "On sale" });
  return out;
}
