/**
 * The "Trip Studio" portal UI — a mock B2B itinerary planner.
 *
 * Plain state-driven navigation (see store.tsx), so the live voice call is never
 * interrupted. Sections carry stable `id`s (`tv-sec-*`) so the agent's `highlight`
 * tool can scroll the travel agent's eye to what it's describing. Flights, hotels,
 * and day plans are LLM-generated and rendered straight from the store.
 *
 * Styled with the Voqalize design tokens (warm-paper light theme) scoped under
 * `.tv-root`.
 */

import { useEffect, type ReactNode } from 'react';
import type { UICommandData } from '@pipecat-ai/client-js';
import { useTravel } from './store';
import {
  paxSummary,
  selectedFlight,
  selectedHotel,
  type FlightOption,
  type HotelOption,
  type HotelStay,
  type Itinerary,
  type Leg,
} from './types';

// Defensive: agent-invented options occasionally omit a numeric field; a single
// missing value must not crash the whole demo (render an em dash instead).
const INR = (n?: number) => (typeof n === 'number' ? `₹${n.toLocaleString('en-IN')}` : '—');

const MEAL_LABEL: Record<string, string> = {
  veg: '🟢 Veg',
  nonveg: '🔴 Non-veg',
  mixed: '🍽 Mixed',
};

// ── Scoped Voqalize tokens + component styles ─────────────────────────────────
const STYLES = `
.tv-root{
  --warm-50:#FAF6F0; --warm-100:#F2ECE2; --warm-200:#E3DACD; --warm-300:#D2C6B2;
  --warm-400:#B3A68F; --warm-500:#8C7E6A; --warm-600:#6E665C; --warm-700:#514A40;
  --warm-800:#2B2620; --warm-900:#1A1613;
  --vermilion:#E24E2A; --vermilion-text:#C23F1E; --action:#C2331A; --on-action:#FAF6F0;
  --success:#3F6B3A; --success-bg:#EAF0E7; --success-line:#CBDDC4;
  --info:#5B6770; --warning:#7E5410;
  --background:var(--warm-50); --foreground:var(--warm-900);
  --card:#FFFDFA; --muted:var(--warm-100); --muted-foreground:var(--warm-600);
  --border:var(--warm-200); --border-strong:var(--warm-500);
  --sans:'Inter','Noto Sans Devanagari',system-ui,-apple-system,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,Menlo,monospace;
  background:var(--background); color:var(--foreground); font-family:var(--sans);
  position:absolute; inset:0; display:flex; flex-direction:column; overflow:hidden;
}
.tv-root *{box-sizing:border-box}

/* top bar */
.tv-topbar{display:flex;align-items:center;gap:16px;height:56px;flex:0 0 56px;
  padding:0 22px;background:var(--card);border-bottom:1px solid var(--border)}
.tv-brand{display:flex;align-items:center;gap:9px;font-weight:800;letter-spacing:-.02em;font-size:17px;
  flex:0 0 auto;white-space:nowrap}
.tv-brand .mark{color:var(--vermilion)}
.tv-brand .sub{font-family:var(--mono);font-size:11px;color:var(--muted-foreground);font-weight:500;
  letter-spacing:.04em;padding-left:9px;margin-left:3px;border-left:1px solid var(--border)}
.tv-crumbs{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted-foreground);
  min-width:0;flex:0 1 auto;white-space:nowrap}
.tv-crumbs a{color:var(--vermilion-text);cursor:pointer;text-decoration:none;flex:0 0 auto}
.tv-crumbs .sep{flex:0 0 auto}
.tv-crumbs .cur{color:var(--foreground);font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis}
.tv-spacer{flex:1}
.tv-agentchip{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--muted-foreground);
  background:var(--muted);border-radius:999px;padding:5px 12px;flex:0 0 auto;white-space:nowrap}
.tv-agentchip .av{width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg,#C23F1E,#E24E2A);
  color:#FAF6F0;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}

/* scroll body */
.tv-body{flex:1;overflow-y:auto;scroll-behavior:smooth}
.tv-wrap{max-width:980px;margin:0 auto;padding:28px 24px 120px}

/* buttons */
.tv-btn{font:inherit;font-size:13px;font-weight:700;border-radius:8px;padding:8px 16px;cursor:pointer;
  border:1px solid transparent;line-height:1}
.tv-btn.primary{background:var(--action);color:var(--on-action)}
.tv-btn.primary:hover{background:#AB2D17}
.tv-btn.ghost{background:var(--muted);color:var(--foreground)}
.tv-btn.ghost:hover{background:var(--warm-200)}
.tv-btn.quiet{background:transparent;border-color:var(--border-strong);color:var(--foreground)}
.tv-btn.sm{padding:6px 12px;font-size:12px}

/* dashboard */
.tv-h1{font-size:30px;line-height:1.15;letter-spacing:-.03em;font-weight:800;margin:0 0 6px}
.tv-sub{font-size:14px;color:var(--muted-foreground);margin:0 0 22px}
.tv-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.tv-tripcard{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;
  cursor:pointer;transition:border-color .15s,box-shadow .15s;text-align:left;font:inherit}
.tv-tripcard:hover{border-color:var(--border-strong);box-shadow:0 4px 14px rgba(26,22,19,.08)}
.tv-tripcard .nm{font-size:17px;font-weight:800;letter-spacing:-.01em;margin-bottom:3px}
.tv-tripcard .ds{font-size:13px;color:var(--muted-foreground);margin-bottom:12px;min-height:18px}
.tv-tripcard .meta{display:flex;flex-wrap:wrap;gap:6px;font-size:11.5px;color:var(--muted-foreground)}
.tv-newcard{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
  min-height:118px;border:1.5px dashed var(--border-strong);border-radius:14px;background:transparent;
  cursor:pointer;color:var(--muted-foreground);font:inherit;font-size:13px;font-weight:600}
.tv-newcard:hover{border-color:var(--vermilion);color:var(--vermilion-text)}
.tv-empty{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:34px;
  text-align:center;color:var(--muted-foreground);font-size:14px}

/* pills & chips */
.tv-pill{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;
  border-radius:999px;padding:3px 10px;background:var(--muted);color:var(--muted-foreground)}
.tv-pill.req{background:#FBEDE9;color:var(--vermilion-text)}
.tv-pill.ok{background:var(--success-bg);color:var(--success);border:1px solid var(--success-line)}

/* overview header */
.tv-ovh{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:22px 24px;margin-bottom:18px}
.tv-ovh .dest{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--vermilion-text);margin-bottom:8px}
.tv-ovh .nm{font-size:26px;font-weight:800;letter-spacing:-.025em;margin:0 0 6px}
.tv-ovh .line{display:flex;flex-wrap:wrap;gap:14px;font-size:13.5px;color:var(--muted-foreground);margin-bottom:14px}
.tv-ovh .line b{color:var(--foreground);font-weight:600}
.tv-chips{display:flex;flex-wrap:wrap;gap:8px}

/* sections */
.tv-sec{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:20px 22px;margin-bottom:16px;
  transition:box-shadow .25s,border-color .25s}
.tv-sec.flash{border-color:var(--vermilion);box-shadow:0 0 0 3px rgba(226,78,42,.18)}
.tv-sech{display:flex;align-items:center;gap:10px;margin:0 0 14px}
.tv-sech h2{font-size:13px;font-family:var(--mono);letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted-foreground);margin:0;font-weight:600}
.tv-sech .ct{font-size:11.5px;color:var(--muted-foreground)}

/* leg / hotel rows in overview */
.tv-row{display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--border)}
.tv-row:first-of-type{border-top:none}
.tv-row .lbl{font-weight:700;font-size:14px}
.tv-row .meta{font-size:12.5px;color:var(--muted-foreground)}
.tv-row .pick{font-size:13px}
.tv-row .pick .none{color:var(--warning)}
.tv-row .pick .sel{color:var(--foreground);font-weight:600}
.tv-rowend{margin-left:auto;display:flex;align-items:center;gap:10px}

/* option cards (flights / hotels screens) */
.tv-optgrid{display:flex;flex-direction:column;gap:12px}
.tv-opt{display:flex;gap:16px;align-items:stretch;background:var(--card);border:1px solid var(--border);
  border-radius:14px;padding:16px 18px}
.tv-opt.sel{border-color:var(--success);box-shadow:0 0 0 2px var(--success-line)}
.tv-opt .main{flex:1;min-width:0}
.tv-opt .top{display:flex;align-items:baseline;gap:10px;margin-bottom:4px}
.tv-opt .name{font-size:15.5px;font-weight:800;letter-spacing:-.01em}
.tv-opt .tag{font-size:11px;color:var(--muted-foreground);font-family:var(--mono)}
.tv-opt .det{font-size:13px;color:var(--muted-foreground);display:flex;flex-wrap:wrap;gap:4px 14px}
.tv-opt .note{font-size:12px;color:var(--vermilion-text);margin-top:7px;display:flex;gap:6px;align-items:center}
.tv-opt .amen{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.tv-opt .side{display:flex;flex-direction:column;align-items:flex-end;justify-content:space-between;gap:10px;
  border-left:1px solid var(--border);padding-left:16px;min-width:118px}
.tv-opt .price{font-size:18px;font-weight:800;letter-spacing:-.02em}
.tv-opt .price small{display:block;font-size:10.5px;font-weight:500;color:var(--muted-foreground);text-align:right}
.tv-stars{color:#C9A227;font-size:12px;letter-spacing:1px}

/* day cards */
.tv-day{border-top:1px solid var(--border);padding:16px 0}
.tv-day:first-of-type{border-top:none;padding-top:2px}
.tv-day .dh{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}
.tv-day .dnum{width:26px;height:26px;border-radius:8px;background:var(--action);color:var(--on-action);
  display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;flex:0 0 26px}
.tv-day .dt{font-size:15px;font-weight:800;letter-spacing:-.01em}
.tv-day .dd{font-size:12px;color:var(--muted-foreground)}
.tv-act{display:flex;gap:10px;padding:5px 0 5px 36px;font-size:13.5px}
.tv-act .tm{font-family:var(--mono);font-size:11.5px;color:var(--muted-foreground);min-width:62px;padding-top:2px}
.tv-act .ab{font-weight:600}
.tv-act .ad{color:var(--muted-foreground);font-size:12.5px}
.tv-daymeta{display:flex;flex-wrap:wrap;gap:8px;padding-left:36px;margin-top:8px}

/* incl/excl + terms */
.tv-two{display:grid;grid-template-columns:1fr 1fr;gap:22px}
@media(max-width:680px){.tv-two{grid-template-columns:1fr}}
.tv-list{list-style:none;margin:0;padding:0;font-size:13.5px}
.tv-list li{display:flex;gap:8px;padding:4px 0;color:var(--foreground)}
.tv-list.incl li::before{content:'✓';color:var(--success);font-weight:800}
.tv-list.excl li::before{content:'✕';color:var(--warning);font-weight:800}
.tv-list.terms li{color:var(--muted-foreground);font-size:12.5px}
.tv-list.terms li::before{content:'•';color:var(--border-strong)}
.tv-muted{color:var(--muted-foreground);font-size:13px}

/* screen header (flights/hotels) */
.tv-scrh{display:flex;align-items:center;gap:14px;margin-bottom:18px}
.tv-scrh .t{font-size:21px;font-weight:800;letter-spacing:-.02em}
.tv-scrh .s{font-size:13px;color:var(--muted-foreground)}

/* footer actions */
.tv-foot{display:flex;gap:12px;align-items:center;margin-top:6px}

/* WhatsApp modal */
.tv-modal{position:fixed;inset:0;z-index:1300;display:flex;align-items:center;justify-content:center;
  background:color-mix(in srgb,#110D0A 55%,transparent);padding:20px}
.tv-phone{width:340px;max-width:100%;max-height:88vh;background:#0b141a;border-radius:26px;overflow:hidden;
  display:flex;flex-direction:column;box-shadow:0 24px 60px rgba(0,0,0,.5);border:6px solid #0b141a}
.tv-wahead{background:#075E54;color:#fff;padding:12px 16px;display:flex;align-items:center;gap:10px}
.tv-wahead .av{width:34px;height:34px;border-radius:50%;background:#25D366;display:flex;align-items:center;
  justify-content:center;font-size:16px}
.tv-wahead .nm{font-weight:700;font-size:14px}
.tv-wahead .st{font-size:11px;opacity:.85}
.tv-wabody{flex:1;overflow-y:auto;padding:16px 12px;
  background:#0d1b24 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40'%3E%3Cpath d='M0 39h40M39 0v40' stroke='%23ffffff08' fill='none'/%3E%3C/svg%3E")}
.tv-bubble{background:#005C4B;color:#e9edef;border-radius:10px;border-top-right-radius:3px;padding:9px 11px;
  font-size:12.5px;line-height:1.5;white-space:pre-wrap;word-break:break-word;margin-left:auto;max-width:94%}
.tv-bubble .tick{display:block;text-align:right;font-size:10px;color:#8fc7b9;margin-top:3px}
.tv-wafoot{padding:12px 14px;background:#0b141a;display:flex;gap:10px;align-items:center}
/* sits clear of the 56px top bar — that corner belongs to the presence control */
.tv-close{position:fixed;top:72px;right:20px;z-index:1301;background:rgba(255,255,255,.12);color:#fff;
  border:none;width:34px;height:34px;border-radius:50%;font-size:16px;cursor:pointer}

/* background-task tray (search flights/hotels, build day plan) */
.tv-tasktray{display:flex;align-items:center;gap:10px;flex:0 0 auto;padding:8px 22px;
  background:var(--card);border-bottom:1px solid var(--border);overflow-x:auto}
.tv-tasktray .lead{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--muted-foreground);flex:0 0 auto}
.tv-task{display:flex;align-items:center;gap:8px;flex:0 0 auto;font:inherit;font-size:12.5px;
  border:1px solid var(--border);border-radius:999px;padding:5px 13px;background:var(--warm-50);color:var(--foreground)}
.tv-task.running{cursor:default}
.tv-task.done{border-color:var(--success-line);background:var(--success-bg);cursor:pointer}
.tv-task.done:hover{border-color:var(--success)}
.tv-task .tick{width:13px;height:13px;flex:0 0 13px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:11px;font-weight:800}
.tv-task.running .tick{border:2px solid var(--vermilion);border-top-color:transparent;
  animation:tv-spin .7s linear infinite}
.tv-task.done .tick{color:var(--success)}
.tv-task .tlabel{font-weight:700}
.tv-task .tdetail{color:var(--muted-foreground);font-size:11.5px}
.tv-task.done .tdetail{color:var(--success)}
@keyframes tv-spin{to{transform:rotate(360deg)}}

/* live "searching…" state on the flights/hotels screens */
.tv-searching{display:flex;flex-direction:column;gap:12px}
.tv-searching-head{display:flex;align-items:center;gap:10px;font-size:14px;font-weight:700;
  color:var(--vermilion-text);margin-bottom:2px}
.tv-spindot{width:15px;height:15px;flex:0 0 15px;border-radius:50%;border:2px solid var(--vermilion);
  border-top-color:transparent;animation:tv-spin .7s linear infinite}
.tv-skel{height:86px;border-radius:14px;border:1px solid var(--border);
  background:linear-gradient(90deg,var(--card) 0%,var(--muted) 50%,var(--card) 100%);
  background-size:200% 100%;animation:tv-shimmer 1.3s ease-in-out infinite}
@keyframes tv-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}

/* ── Phone (≤640px) ───────────────────────────────────────────────────────────
   Desktop is untouched. Below this width the portal goes single-column: the top
   bar keeps only the wordmark, the breadcrumb and the presence control; the split
   option cards (detail | price rail) stack; the overview rows put their choice on
   their own line; and nothing is allowed to push the page wider than the screen. */
@media(max-width:640px){
  /* top bar — the desk control is the one thing that never gets dropped */
  .tv-topbar{gap:10px;padding:0 13px}
  .tv-brand{font-size:15.5px;gap:7px}
  .tv-brand .sub{display:none}
  .tv-agentchip{display:none}
  /* the trip name is the H1 right below — the crumb keeps only the way back */
  .tv-crumbs{font-size:12px;gap:6px}
  .tv-crumbs .sep,.tv-crumbs .cur{display:none}

  /* task tray already scrolls in its own lane — just tighten it */
  .tv-tasktray{padding:8px 13px;gap:8px}
  .tv-tasktray .lead{font-size:11px}

  /* page frame */
  .tv-wrap{padding:18px 14px 72px}
  .tv-h1{font-size:24px}
  .tv-sub{font-size:13.5px;margin-bottom:18px}
  .tv-grid{grid-template-columns:1fr;gap:12px}
  .tv-empty{padding:24px 18px}
  .tv-tripcard .meta{font-size:11px}

  /* overview header */
  .tv-ovh{padding:18px 16px;border-radius:14px}
  .tv-ovh .nm{font-size:21px}
  .tv-ovh .line{gap:6px 14px;font-size:13px}
  .tv-ovh .dest{font-size:11px}

  /* sections */
  .tv-sec{padding:16px 15px;border-radius:14px}
  .tv-scrh{flex-wrap:wrap;gap:10px;margin-bottom:14px}
  .tv-scrh .t{font-size:18px}

  /* leg / hotel rows: label on top, the pick + its button on their own line */
  .tv-row{flex-wrap:wrap;align-items:flex-start;gap:8px}
  .tv-row .pick{font-size:12.5px}
  .tv-rowend{margin-left:0;width:100%;justify-content:space-between;gap:8px}

  /* option cards: the price rail becomes a footer strip */
  .tv-opt{flex-direction:column;gap:12px;padding:14px 15px}
  .tv-opt .name{font-size:15px}
  .tv-opt .det{font-size:12.5px;gap:4px 10px}
  .tv-opt .side{flex-direction:row;align-items:center;justify-content:space-between;
    width:100%;min-width:0;border-left:none;border-top:1px solid var(--border);
    padding-left:0;padding-top:11px}
  .tv-opt .price small{text-align:left;font-size:11px}

  /* day plan: tighten the time gutter */
  .tv-act{padding-left:24px;gap:8px}
  .tv-act .tm{min-width:52px;font-size:11px}
  .tv-daymeta{padding-left:24px}

  /* WhatsApp preview — clear of the close button, never wider than the screen */
  .tv-modal{padding:12px}
  .tv-phone{max-height:82vh;border-width:5px}
  /* the top-right corner is the presence control's — dismiss moves under the sheet */
  .tv-close{top:auto;right:auto;bottom:16px;left:50%;transform:translateX(-50%);
    width:38px;height:38px;background:rgba(255,255,255,.18)}
}
`;

function TravelStyles() {
  return <style dangerouslySetInnerHTML={{ __html: STYLES }} />;
}

// ── Top bar ───────────────────────────────────────────────────────────────────
// Carries the wordmark, the breadcrumb, and the one voice affordance — the
// presence control the voice layer hands up, so the desk reads as product chrome.
function TopBar({ presence }: { presence: ReactNode }) {
  const { active, view, openDashboard } = useTravel();
  return (
    <div className="tv-topbar">
      <div className="tv-brand">
        <span className="mark">✈</span> Trip Studio
        <span className="sub">B2B Itineraries</span>
      </div>
      <div className="tv-crumbs">
        <a onClick={openDashboard}>Itineraries</a>
        {active && view !== 'dashboard' && (
          <>
            <span className="sep">/</span>
            <span className="cur">{active.name}</span>
          </>
        )}
      </div>
      <div className="tv-spacer" />
      <div className="tv-agentchip">
        <span className="av">RA</span> Agent: Rahul
      </div>
      {presence}
    </div>
  );
}

// ── Background-task tray ──────────────────────────────────────────────────────
// Searches the Travel Desk kicked off (flights, hotels, a day-plan build) show
// here as running spinners while the agent keeps working; when one finishes it
// turns into a clickable "ready" chip that opens what it produced. This is the
// visible proof that long-running work doesn't block the conversation — the
// behaviour the desk will keep when real fare/hotel APIs are wired in behind it.
function TaskTray() {
  const { tasks, openTaskTarget } = useTravel();
  if (tasks.length === 0) return null;
  return (
    <div className="tv-tasktray">
      <span className="lead">Tasks</span>
      {tasks.map((t) => {
        const done = t.status === 'done';
        return (
          <button
            key={t.id}
            type="button"
            className={`tv-task ${t.status}`}
            disabled={!done}
            onClick={done ? () => openTaskTarget(t) : undefined}
            title={done ? 'Open' : 'Running…'}
          >
            <span className="tick" aria-hidden>
              {done ? '✓' : ''}
            </span>
            <span className="tlabel">{t.label}</span>
            <span className="tdetail">{done ? 'ready — open' : t.detail || 'running…'}</span>
          </button>
        );
      })}
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
function DashboardPage() {
  const { itineraries, openItinerary, newBlankItinerary } = useTravel();
  return (
    <div className="tv-wrap">
      <h1 className="tv-h1">My Itineraries</h1>
      <p className="tv-sub">
        Plan complex group trips by voice or by hand. Open the Travel Desk and say which trip to build —
        हिंदी या English.
      </p>
      {itineraries.length === 0 ? (
        <div className="tv-empty">
          No itineraries yet. Tap <b>Ask the Travel Desk</b> and say something like “एक नई itinerary
          बनाओ — Poddar family का Vietnam group trip”.
          <div style={{ marginTop: 16 }}>
            <button className="tv-btn ghost" onClick={newBlankItinerary}>
              + Start a blank itinerary
            </button>
          </div>
        </div>
      ) : (
        <div className="tv-grid">
          {itineraries.map((it) => (
            <button key={it.id} className="tv-tripcard" onClick={() => openItinerary(it.id)}>
              <div className="nm">{it.name}</div>
              <div className="ds">{it.destination || '—'}</div>
              <div className="meta">
                <span className="tv-pill">{[it.start_date, it.end_date].filter(Boolean).join(' – ') || 'Dates TBD'}</span>
                {it.families.length > 0 && <span className="tv-pill">{paxSummary(it) || `${it.families.length} families`}</span>}
                {it.whatsapp && <span className="tv-pill ok">Shared</span>}
              </div>
            </button>
          ))}
          <button className="tv-newcard" onClick={newBlankItinerary}>
            <span style={{ fontSize: 22 }}>+</span>
            New itinerary
          </button>
        </div>
      )}
    </div>
  );
}

// ── Overview (the spine) ──────────────────────────────────────────────────────
function SpecialChips({ active }: { active: Itinerary }) {
  const chips = active.specialRequests;
  if (chips.length === 0) return null;
  return (
    <div className="tv-chips" id="tv-sec-special_requests">
      {chips.map((r, i) => (
        <span key={i} className="tv-pill req" title={r.detail}>
          {r.type === 'bassinet' ? '🍼' : r.type === 'assistance' ? '♿' : r.type === 'meal' ? '🍽' : '★'}{' '}
          {r.label}
          {r.detail ? ` · ${r.detail}` : ''}
        </span>
      ))}
    </div>
  );
}

function LegRow({ leg }: { leg: Leg }) {
  const { viewFlights } = useTravel();
  const sel = selectedFlight(leg);
  return (
    <div className="tv-row">
      <div>
        <div className="lbl">{leg.label}</div>
        <div className="meta">{leg.date || 'Date TBD'}</div>
      </div>
      <div className="tv-rowend">
        <div className="pick">
          {sel ? (
            <span className="sel">
              {sel.airline} {sel.flight_no ?? ''} · {sel.depart} → {sel.arrive}
            </span>
          ) : (
            <span className="none">{leg.options?.length ? 'Choose a flight' : 'No options yet'}</span>
          )}
        </div>
        {(leg.options?.length ?? 0) > 0 && (
          <button className="tv-btn quiet sm" onClick={() => viewFlights(leg.id)}>
            {sel ? 'Change' : 'Choose'}
          </button>
        )}
      </div>
    </div>
  );
}

function HotelRow({ city, stay }: { city: string; stay: HotelStay }) {
  const { viewHotels } = useTravel();
  const sel = selectedHotel(stay);
  return (
    <div className="tv-row">
      <div>
        <div className="lbl">{city}</div>
        <div className="meta">{stay.nights ? `${stay.nights} nights` : 'Stay'}</div>
      </div>
      <div className="tv-rowend">
        <div className="pick">
          {sel ? (
            <span className="sel">
              {sel.name} <span className="tv-stars">{'★'.repeat(sel.stars ?? 5)}</span>
            </span>
          ) : (
            <span className="none">{stay.options?.length ? 'Choose a hotel' : 'No options yet'}</span>
          )}
        </div>
        {(stay.options?.length ?? 0) > 0 && (
          <button className="tv-btn quiet sm" onClick={() => viewHotels(city)}>
            {sel ? 'Change' : 'Choose'}
          </button>
        )}
      </div>
    </div>
  );
}

function OverviewPage({ active }: { active: Itinerary }) {
  const { highlighted, openWhatsAppPreview } = useTravel();

  // Highlight: pulse + scroll the section the agent is talking about.
  useEffect(() => {
    if (!highlighted) return;
    const el = document.getElementById(`tv-sec-${highlighted.section}`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('flash');
    const t = setTimeout(() => el.classList.remove('flash'), 1600);
    return () => clearTimeout(t);
  }, [highlighted]);

  return (
    <div className="tv-wrap">
      <div className="tv-ovh" id="tv-sec-summary">
        {active.destination && <div className="dest">{active.destination}</div>}
        <h1 className="nm">{active.name}</h1>
        <div className="line">
          {(active.start_date || active.end_date) && (
            <span>
              📅 <b>{[active.start_date, active.end_date].filter(Boolean).join(' – ')}</b>
            </span>
          )}
          {paxSummary(active) && <span>👥 <b>{paxSummary(active)}</b></span>}
          {active.coordinator && <span>📞 <b>{active.coordinator}</b></span>}
        </div>
        <SpecialChips active={active} />
        {active.patchNote && (
          <div style={{ marginTop: 12 }} className="tv-pill ok">
            ↻ {active.patchNote}
          </div>
        )}
      </div>

      {/* Flights */}
      <div className="tv-sec" id="tv-sec-flights">
        <div className="tv-sech">
          <h2>Flights</h2>
          <span className="ct">{active.legs.length} legs</span>
        </div>
        {active.legs.length === 0 ? (
          <div className="tv-muted">No flight legs yet — ask the Travel Desk to add them.</div>
        ) : (
          active.legs.map((leg) => <LegRow key={leg.id} leg={leg} />)
        )}
      </div>

      {/* Hotels */}
      <div className="tv-sec" id="tv-sec-hotels">
        <div className="tv-sech">
          <h2>Hotels</h2>
          <span className="ct">{active.hotels.length} stays</span>
        </div>
        {active.hotels.length === 0 ? (
          <div className="tv-muted">No hotel stays yet.</div>
        ) : (
          active.hotels.map((stay) => <HotelRow key={stay.city} city={stay.city} stay={stay} />)
        )}
      </div>

      {/* Day-wise itinerary */}
      <div className="tv-sec" id="tv-sec-days">
        <div className="tv-sech">
          <h2>Day-wise Itinerary</h2>
          <span className="ct">{active.days.length} days</span>
        </div>
        {active.days.length === 0 ? (
          <div className="tv-muted">The day-by-day plan will appear here as you build it.</div>
        ) : (
          active.days.map((d) => (
            <div className="tv-day" key={d.day}>
              <div className="dh">
                <span className="dnum">{d.day}</span>
                <span className="dt">{d.title}</span>
                {d.date && <span className="dd">{d.date}</span>}
              </div>
              {d.activities.map((a, i) => (
                <div className="tv-act" key={i}>
                  <span className="tm">{a.time || ''}</span>
                  <span>
                    <span className="ab">{a.title}</span>
                    {a.ticket_included && <span className="tv-pill ok" style={{ marginLeft: 8 }}>🎟 ticket</span>}
                    {a.detail && <div className="ad">{a.detail}</div>}
                  </span>
                </div>
              ))}
              <div className="tv-daymeta">
                {d.transport && <span className="tv-pill">🚌 {d.transport}</span>}
                {d.breakfast && <span className="tv-pill">🍳 {d.breakfast}</span>}
                {d.lunch && <span className="tv-pill">🍴 {d.lunch}</span>}
                {d.dinner && <span className="tv-pill">🍽 {d.dinner}</span>}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Inclusions / exclusions */}
      {(active.inclusions.length > 0 || active.exclusions.length > 0) && (
        <div className="tv-sec" id="tv-sec-inclusions">
          <div className="tv-sech">
            <h2>Inclusions &amp; Exclusions</h2>
          </div>
          <div className="tv-two">
            <ul className="tv-list incl">
              {active.inclusions.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
            <ul className="tv-list excl">
              {active.exclusions.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Terms */}
      {active.terms.length > 0 && (
        <div className="tv-sec" id="tv-sec-terms">
          <div className="tv-sech">
            <h2>Terms &amp; Conditions</h2>
          </div>
          <ul className="tv-list terms">
            {active.terms.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="tv-foot">
        <button className="tv-btn primary" onClick={openWhatsAppPreview}>
          {active.whatsapp ? '✓ Shared on WhatsApp — view' : '↗ Share on WhatsApp'}
        </button>
      </div>
    </div>
  );
}

// ── Flights screen ────────────────────────────────────────────────────────────
function FlightCard({ leg, opt }: { leg: Leg; opt: FlightOption }) {
  const { selectFlight } = useTravel();
  const isSel = leg.selectedId === opt.id;
  return (
    <div className={`tv-opt${isSel ? ' sel' : ''}`}>
      <div className="main">
        <div className="top">
          <span className="name">{opt.airline}</span>
          <span className="tag">{opt.flight_no}</span>
          {opt.stops && <span className="tag">· {opt.stops}</span>}
        </div>
        <div className="det">
          <span>🛫 {opt.depart}</span>
          <span>🛬 {opt.arrive}</span>
          {opt.duration && <span>⏱ {opt.duration}</span>}
          {opt.cabin && <span>{opt.cabin}</span>}
          {opt.baggage && <span>🧳 {opt.baggage}</span>}
        </div>
        {opt.note && <div className="note">↳ {opt.note}</div>}
      </div>
      <div className="side">
        <div className="price">
          {INR(opt.price)}
          <small>per person</small>
        </div>
        <button className={`tv-btn ${isSel ? 'ghost' : 'primary'} sm`} onClick={() => selectFlight(leg.id, opt.id)}>
          {isSel ? '✓ Selected' : 'Select'}
        </button>
      </div>
    </div>
  );
}

// Live "searching…" placeholder shown while a background search runs for the
// open leg/city — shimmering skeleton cards that fill in when results land.
function Searching({ label }: { label: string }) {
  return (
    <div className="tv-searching">
      <div className="tv-searching-head">
        <span className="tv-spindot" aria-hidden /> {label}
      </div>
      {[0, 1, 2].map((i) => (
        <div className="tv-skel" key={i} />
      ))}
    </div>
  );
}

function FlightsPage({ active }: { active: Itinerary }) {
  const { flightsLeg, openItinerary, tasks } = useTravel();
  const leg = active.legs.find((l) => l.id === flightsLeg) ?? active.legs[0];
  if (!leg) return <div className="tv-wrap tv-muted">No flight leg selected.</div>;
  const searching = tasks.some(
    (t) => t.status === 'running' && t.kind === 'flights' && t.target?.legId === leg.id,
  );
  const options = leg.options ?? [];
  return (
    <div className="tv-wrap">
      <div className="tv-scrh">
        <button className="tv-btn ghost sm" onClick={() => openItinerary(active.id)}>
          ← Back
        </button>
        <div>
          <div className="t">{leg.label}</div>
          <div className="s">
            {searching ? 'Searching live fares…' : `${leg.date} · ${options.length} options`}
          </div>
        </div>
      </div>
      {searching ? (
        <Searching label="Searching live fares for this leg…" />
      ) : options.length === 0 ? (
        <div className="tv-muted">No options yet — ask the Travel Desk to search this leg.</div>
      ) : (
        <div className="tv-optgrid">
          {options.map((opt) => (
            <FlightCard key={opt.id} leg={leg} opt={opt} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Hotels screen ─────────────────────────────────────────────────────────────
function HotelCard({ city, opt, selectedId }: { city: string; opt: HotelOption; selectedId?: string }) {
  const { selectHotel } = useTravel();
  const isSel = selectedId === opt.id;
  return (
    <div className={`tv-opt${isSel ? ' sel' : ''}`}>
      <div className="main">
        <div className="top">
          <span className="name">{opt.name}</span>
          <span className="tv-stars">{'★'.repeat(opt.stars ?? 5)}</span>
          {opt.rating != null && <span className="tag">· {opt.rating}/10</span>}
        </div>
        <div className="det">
          {opt.area && <span>📍 {opt.area}</span>}
          {opt.board && <span>🍳 {opt.board}</span>}
          {opt.room_type && <span>🛏 {opt.room_type}</span>}
        </div>
        {opt.amenities && opt.amenities.length > 0 && (
          <div className="amen">
            {opt.amenities.map((a, i) => (
              <span key={i} className="tv-pill">
                {a}
              </span>
            ))}
          </div>
        )}
        {opt.note && <div className="note">↳ {opt.note}</div>}
      </div>
      <div className="side">
        <div className="price">
          {INR(opt.price_per_night)}
          <small>per night</small>
        </div>
        <button className={`tv-btn ${isSel ? 'ghost' : 'primary'} sm`} onClick={() => selectHotel(city, opt.id)}>
          {isSel ? '✓ Selected' : 'Select'}
        </button>
      </div>
    </div>
  );
}

function HotelsPage({ active }: { active: Itinerary }) {
  const { hotelsCity, openItinerary, tasks } = useTravel();
  const stay = active.hotels.find((h) => h.city === hotelsCity) ?? active.hotels[0];
  if (!stay) return <div className="tv-wrap tv-muted">No hotel stay selected.</div>;
  const searching = tasks.some(
    (t) => t.status === 'running' && t.kind === 'hotels' && t.target?.city === stay.city,
  );
  const options = stay.options ?? [];
  return (
    <div className="tv-wrap">
      <div className="tv-scrh">
        <button className="tv-btn ghost sm" onClick={() => openItinerary(active.id)}>
          ← Back
        </button>
        <div>
          <div className="t">Hotels · {stay.city}</div>
          <div className="s">
            {searching ? 'Searching 5-star properties…' : '5-star options · breakfast included'}
          </div>
        </div>
      </div>
      {searching ? (
        <Searching label={`Searching 5-star hotels in ${stay.city}…`} />
      ) : options.length === 0 ? (
        <div className="tv-muted">No options yet — ask the Travel Desk to search this city.</div>
      ) : (
        <div className="tv-optgrid">
          {options.map((opt) => (
            <HotelCard key={opt.id} city={stay.city} opt={opt} selectedId={stay.selectedId} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── WhatsApp share modal ──────────────────────────────────────────────────────
function whatsappText(it: Itinerary): string {
  const lines: string[] = [];
  lines.push(`*${it.name}*`);
  if (it.destination) lines.push(it.destination);
  if (it.start_date || it.end_date) lines.push(`🗓 ${[it.start_date, it.end_date].filter(Boolean).join(' – ')}`);
  if (paxSummary(it)) lines.push(`👥 ${paxSummary(it)}`);
  if (it.specialRequests.length) {
    lines.push('');
    lines.push('*Special requests*');
    for (const r of it.specialRequests) lines.push(`• ${r.label}${r.detail ? ` (${r.detail})` : ''}`);
  }
  if (it.legs.some((l) => selectedFlight(l))) {
    lines.push('');
    lines.push('*Flights*');
    for (const l of it.legs) {
      const f = selectedFlight(l);
      if (f) lines.push(`• ${l.label}: ${f.airline} ${f.flight_no ?? ''} ${f.depart}→${f.arrive}`);
    }
  }
  if (it.hotels.some((h) => selectedHotel(h))) {
    lines.push('');
    lines.push('*Hotels*');
    for (const h of it.hotels) {
      const s = selectedHotel(h);
      if (s) lines.push(`• ${h.city}: ${s.name} (${s.stars ?? 5}★, ${s.board ?? 'breakfast'})`);
    }
  }
  if (it.days.length) {
    lines.push('');
    lines.push('*Day-wise plan*');
    for (const d of it.days) lines.push(`Day ${d.day}: ${d.title}`);
  }
  if (it.inclusions.length) {
    lines.push('');
    lines.push('*Inclusions*');
    for (const s of it.inclusions) lines.push(`✓ ${s}`);
  }
  lines.push('');
  lines.push('— Sent via Trip Studio');
  return lines.join('\n');
}

function WhatsAppModal({ active }: { active: Itinerary }) {
  const { closeWhatsApp, sendWhatsApp } = useTravel();
  const sent = Boolean(active.whatsapp);
  const recipient = active.whatsapp?.recipient || active.coordinator || 'Coordinator';
  return (
    <div className="tv-modal" onClick={closeWhatsApp}>
      <button className="tv-close" onClick={closeWhatsApp} aria-label="Close">
        ✕
      </button>
      <div className="tv-phone" onClick={(e) => e.stopPropagation()}>
        <div className="tv-wahead">
          <span className="av">👤</span>
          <div>
            <div className="nm">{recipient}</div>
            <div className="st">{active.whatsapp?.to || 'WhatsApp'}</div>
          </div>
        </div>
        <div className="tv-wabody">
          <div className="tv-bubble">
            {whatsappText(active)}
            <span className="tick">{sent ? '11:24 ✓✓' : 'Draft'}</span>
          </div>
        </div>
        <div className="tv-wafoot">
          {sent ? (
            <span className="tv-pill ok" style={{ width: '100%', justifyContent: 'center', padding: '8px' }}>
              ✓ Sent to {recipient}
            </span>
          ) : (
            <button
              className="tv-btn primary"
              style={{ width: '100%' }}
              onClick={() => sendWhatsApp(active.whatsapp?.to || '', recipient)}
            >
              Send to {recipient}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Dev-only: expose a ui-command dispatcher on window so the agent's screen-driving
// can be exercised deterministically (without a mic) in browser automation / tests.
// Takes the same envelope pipecat delivers — `{ command, payload }` — and routes
// it through the store's typed handlers, exactly as the RTVIEvent.UICommand
// subscription in TravelAdvisor does on the wire.
type DevDispatch = (cmd: UICommandData) => void;

function DevUiExpose() {
  const { uiCommands } = useTravel();
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const dispatch: DevDispatch = (cmd) => {
      const handler = (uiCommands as Record<string, ((args: never) => void) | undefined>)[cmd.command];
      handler?.(cmd.payload as never);
    };
    (window as unknown as { __travelUi?: DevDispatch }).__travelUi = dispatch;
    return () => {
      delete (window as unknown as { __travelUi?: DevDispatch }).__travelUi;
    };
  }, [uiCommands]);
  return null;
}

// ── App shell ─────────────────────────────────────────────────────────────────
export function TravelApp({ presence }: { presence: ReactNode }) {
  const { view, active, whatsappOpen } = useTravel();
  return (
    <div className="tv-root">
      <TravelStyles />
      <DevUiExpose />
      <TopBar presence={presence} />
      <TaskTray />
      <div className="tv-body">
        {view === 'dashboard' || !active ? (
          <DashboardPage />
        ) : view === 'flights' ? (
          <FlightsPage active={active} />
        ) : view === 'hotels' ? (
          <HotelsPage active={active} />
        ) : (
          <OverviewPage active={active} />
        )}
      </div>
      {whatsappOpen && active && <WhatsAppModal active={active} />}
    </div>
  );
}
