/**
 * OrderDesk demo UI — MedSetu's order screen, and the console that stages it.
 *
 * Screen 1 (picker): a distributor's CRM console — two pharmacies, three
 * mornings each. Every cell shows exactly what the order desk walks in knowing,
 * so the personalization on the call reads as data, not script.
 *
 * Screen 2 (phone stage): the pharmacist's handset beside a presenter panel.
 * The sequence is the demo's spine — 9:02 AM lock screen → MedSetu push +
 * chime → Join call → the order screen, where every spoken line lands as a
 * free-text row and walks a *visible* state machine to a confirmed SKU:
 *
 *     resolving  → grey, shimmering, the catalog is still working
 *     multi_variant → amber, pills labelled only by what actually differs
 *     multi_family  → amber, 2–5 option cards
 *     matched    → green, priced, a quantity stepper, orderable
 *     not_found  → muted, with the search bar as the way out
 *
 * The pharmacist confirms manually; nothing on this screen is agent-committed.
 * All navigation is React state (via the store) so the live call survives every
 * screen change.
 */

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { PHARMACIES, scenariosFor } from "./data";
import { OrderDeskCallSession } from "./OrderDeskCall";
import { familyHeldWhole, useOrderDesk, type LineItem } from "./store";
import {
  AMBER,
  AMBER_LINE,
  AMBER_TINT,
  BG,
  BODY,
  CALL_BG,
  CARD,
  FONT_IMPORT,
  GREEN,
  GREEN_LINE,
  GREEN_TINT,
  GREY,
  GREY_TINT,
  INK,
  INK_FAINT,
  INK_SOFT,
  LINE,
  LINE_SOFT,
  MONO,
  NAVY,
  NAVY_DEEP,
  NAVY_TINT,
  RED,
  SAFFRON,
  SAFFRON_DEEP,
  SAFFRON_TINT,
  rupees,
  rupeesExact,
} from "./theme";
import type { FamilyWire, Pharmacy, Scenario, SkuWire } from "./types";

/** MedSetu's own name, and the desk the pharmacist thinks she is calling. */
const BRAND = "MedSetu";
const DESK = "MedSetu Order Desk";
/** Marketing line: the vertical is the demo, not the product. */
const POSITIONING = "B2B order intake, demonstrated on pharma";
/** The morning the whole demo happens on. */
const CLOCK = "9:02";
const CLOCK_LABEL = "9:02 AM";
const DATE_LABEL = "Wednesday, 12 August";

/** Presenter hints are Hindi — put Devanagari first in their stack. */
const DEVA = "'Noto Sans Devanagari', 'Inter', system-ui, sans-serif";

/**
 * Responsive scale. The order screen is a dense trade app inside a device mock,
 * so the sizes that live inline (and a media rule could not reach) come through
 * custom properties. Below 700px the mock drops its bezel and goes full-bleed —
 * a simulated phone inside a real phone is just a clipped phone — and the
 * presenter panel stacks underneath.
 */
const GLOBAL_CSS = `
${FONT_IMPORT}
:root {
  --od-micro: 10px;
  --od-mini: 10.5px;
  --od-h1: 38px;
  --od-picker-pad: 40px 26px 64px;
  --od-stage-pad: 30px 26px;
  --od-stage-gap: 40px;
  --od-screen-radius: 40px;
}
.od-demo-root * { box-sizing: border-box; }
.od-context {
  width: 348px;
  max-width: 92vw;
  max-height: 812px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.od-phone {
  width: 396px;
  height: 812px;
  flex: none;
  border-radius: 50px;
  background: #0A1220;
  padding: 10px;
  box-shadow: 0 30px 80px rgba(9,22,42,.38), inset 0 0 0 2px #23324A;
}
@media (max-width: 700px) {
  :root {
    --od-micro: 11px;
    --od-mini: 11.5px;
    --od-h1: 26px;
    --od-picker-pad: 20px 13px 40px;
    --od-stage-pad: 0px;
    --od-stage-gap: 0px;
    --od-screen-radius: 0px;
  }
  .od-stage { flex-direction: column; align-items: stretch; }
  .od-phone {
    order: 1;
    width: 100%;
    height: 100dvh;
    border-radius: 0;
    padding: 5px;
    box-shadow: none;
  }
  .od-notch { display: none; }
  .od-context {
    order: 2;
    width: 100%;
    max-width: none;
    max-height: none;
    overflow-y: visible;
    padding: 18px 14px 30px;
  }
}
@keyframes odSlideDown { from { transform: translateY(-120%); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
@keyframes odFadeUp { from { transform: translateY(10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
@keyframes odBlink { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
@keyframes odBreathe { 0%,100% { box-shadow: 0 0 0 0 rgba(224,123,14,.5); } 50% { box-shadow: 0 0 0 20px rgba(224,123,14,0); } }
@keyframes odGlow { 0% { box-shadow: 0 0 0 3px rgba(224,123,14,.55); } 100% { box-shadow: 0 0 0 3px rgba(224,123,14,0); } }
@keyframes odSweep { 0% { background-position: -220% 0; } 100% { background-position: 220% 0; } }
@keyframes odPop { 0% { transform: scale(.86); opacity: 0; } 60% { transform: scale(1.04); } 100% { transform: scale(1); opacity: 1; } }
.od-fresh { animation: odFadeUp .42s cubic-bezier(.2,.9,.3,1.15) both; }
.od-blink { animation: odBlink 1.5s ease-in-out infinite; }
.od-hl { animation: odGlow 2.4s ease-out both; }
.od-pop { animation: odPop .5s cubic-bezier(.2,.9,.3,1.3) both; }
/* The catalog is still thinking: a slow sheen across the row's text block. */
.od-shimmer {
  background: linear-gradient(100deg, ${GREY_TINT} 20%, #FFFFFF 42%, ${GREY_TINT} 64%);
  background-size: 220% 100%;
  animation: odSweep 1.5s linear infinite;
}
.od-cell { transition: border-color .16s, box-shadow .16s, transform .16s; }
.od-cell:hover { border-color: ${NAVY}; box-shadow: 0 10px 26px rgba(11,27,51,.12); transform: translateY(-2px); }
.od-pill { transition: background .14s, border-color .14s, transform .12s; }
.od-pill:hover { background: #fff; border-color: ${SAFFRON}; transform: translateY(-1px); }
.od-res { transition: background .12s; }
.od-res:hover { background: ${NAVY_TINT}; }
.od-ghost:hover { background: ${LINE_SOFT}; }
.od-scroll::-webkit-scrollbar { width: 6px; }
.od-scroll::-webkit-scrollbar-thumb { background: #CFD8E4; border-radius: 3px; }
@media (prefers-reduced-motion: reduce) {
  .od-fresh, .od-blink, .od-hl, .od-pop, .od-shimmer, .od-cell, .od-pill { animation: none; transition: none; }
  .od-shimmer { background: ${GREY_TINT}; }
}
`;

// ═════════════════════════════════════════════════════════════════════════════
// Root
// ═════════════════════════════════════════════════════════════════════════════

export function OrderDeskApp() {
  const { phase } = useOrderDesk();
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflow: "auto",
        background: BG,
        color: INK,
        fontFamily: BODY,
      }}
    >
      <style>{GLOBAL_CSS}</style>
      {phase === "picker" ? <PickerScreen /> : <PhoneStage />}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Screen 1 — the distributor CRM console (scenario picker)
// ═════════════════════════════════════════════════════════════════════════════

function PickerScreen() {
  return (
    <div style={{ maxWidth: 1140, margin: "0 auto", padding: "var(--od-picker-pad)" }}>
      <header
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 18,
          marginBottom: 6,
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 13 }}>
            <MedSetuMark size={44} />
            <div>
              <div
                style={{
                  fontWeight: 900,
                  fontSize: "var(--od-h1)",
                  letterSpacing: "-0.03em",
                  color: NAVY_DEEP,
                  lineHeight: 1.05,
                }}
              >
                {BRAND}
                <span
                  style={{
                    fontWeight: 700,
                    fontSize: 12.5,
                    color: INK_SOFT,
                    marginLeft: 12,
                    letterSpacing: ".12em",
                    textTransform: "uppercase",
                    verticalAlign: "middle",
                  }}
                >
                  Distributor CRM
                </span>
              </div>
              <div style={{ fontSize: 12.5, color: INK_FAINT, marginTop: 1, fontWeight: 600 }}>
                India&rsquo;s largest B2B pharma distributor
              </div>
            </div>
          </div>
          <p style={{ margin: "14px 0 0", fontSize: 14.5, color: INK_SOFT, maxWidth: 660, lineHeight: 1.55 }}>
            Every morning the desk calls its retailers. The pharmacist speaks the order in Hindi;
            it lands on screen in English and resolves live against a 20,148-SKU catalog. Pick a
            pharmacy and a day — the card is everything the desk walks in knowing.
          </p>
        </div>

        <div
          style={{
            background: SAFFRON_TINT,
            border: `1px solid #F2DDBB`,
            borderRadius: 14,
            padding: "11px 15px",
            maxWidth: 300,
          }}
        >
          <div
            style={{
              fontSize: 10.5,
              fontWeight: 800,
              letterSpacing: ".1em",
              textTransform: "uppercase",
              color: SAFFRON_DEEP,
            }}
          >
            What this is
          </div>
          <div style={{ fontSize: 13, fontWeight: 700, color: INK, marginTop: 4, lineHeight: 1.4 }}>
            {POSITIONING}
          </div>
          <div style={{ fontSize: 11.5, color: INK_SOFT, marginTop: 4, lineHeight: 1.45 }}>
            The catalog, the search and the ambiguity are real — swap the SKUs and this is any
            distributor&rsquo;s order desk.
          </div>
        </div>
      </header>

      {/* `min(460px, 100%)` keeps the two-up console on desktop and collapses to a
          single column on a handset instead of forcing a 460px track. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(460px, 100%), 1fr))",
          gap: 26,
          marginTop: 26,
        }}
      >
        {PHARMACIES.map((p) => (
          <PharmacyColumn key={p.id} pharmacy={p} />
        ))}
      </div>
    </div>
  );
}

function PharmacyColumn({ pharmacy }: { pharmacy: Pharmacy }) {
  const { startScenario } = useOrderDesk();
  const scenarios = scenariosFor(pharmacy.id);
  return (
    <section>
      <div
        style={{
          background: CARD,
          border: `1px solid ${LINE}`,
          borderTop: `3px solid hsl(${pharmacy.hue} 55% 42%)`,
          borderRadius: 16,
          padding: "16px 18px",
          display: "flex",
          gap: 14,
          alignItems: "flex-start",
        }}
      >
        <StoreMark pharmacy={pharmacy} size={48} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 800, fontSize: 18, letterSpacing: "-0.02em" }}>{pharmacy.name}</span>
            <span style={{ fontSize: 12, color: INK_FAINT, fontFamily: MONO }}>
              {pharmacy.area}, {pharmacy.city}
            </span>
          </div>
          <div style={{ fontSize: 12.5, color: INK_SOFT, marginTop: 3 }}>
            {pharmacy.owner} · {pharmacy.since}
          </div>
          <div style={{ display: "flex", gap: 14, marginTop: 7, flexWrap: "wrap" }}>
            <Metric label="Volume" value={pharmacy.volume_line} />
            <Metric label="Terms" value={pharmacy.credit_line} />
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
            {pharmacy.tags.map((t) => (
              <span
                key={t}
                style={{
                  fontSize: 10.5,
                  fontWeight: 700,
                  color: NAVY,
                  background: NAVY_TINT,
                  borderRadius: 999,
                  padding: "3px 9px",
                }}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 11, marginTop: 11 }}>
        {scenarios.map((s) => (
          <button
            key={s.id}
            className="od-cell"
            onClick={() => startScenario(s.id)}
            style={{
              textAlign: "left",
              background: CARD,
              border: `1px solid ${LINE}`,
              borderRadius: 15,
              padding: "15px 17px",
              cursor: "pointer",
              fontFamily: BODY,
              color: INK,
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
              <span
                style={{
                  fontSize: 10.5,
                  fontWeight: 800,
                  letterSpacing: ".1em",
                  textTransform: "uppercase",
                  color: INK_FAINT,
                }}
              >
                {s.day_label}
              </span>
              <span style={{ fontWeight: 800, fontSize: 16.5, letterSpacing: "-0.015em" }}>{s.title}</span>
              <span
                style={{
                  marginLeft: "auto",
                  fontSize: 10.5,
                  fontWeight: 800,
                  color: SAFFRON_DEEP,
                  background: SAFFRON_TINT,
                  borderRadius: 999,
                  padding: "3px 10px",
                  whiteSpace: "nowrap",
                }}
              >
                {s.chip}
              </span>
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 3 }}>
              {s.context_bullets.map((b, i) => (
                <li key={i} style={{ fontSize: 12.5, color: INK_SOFT, lineHeight: 1.45, display: "flex", gap: 7 }}>
                  <span aria-hidden style={{ color: NAVY, flex: "none" }}>·</span>
                  {b}
                </li>
              ))}
            </ul>
            <div style={{ marginTop: 10, fontSize: 12.5, fontWeight: 800, color: NAVY }}>
              Send the 9 AM nudge →
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: "var(--od-micro)",
          fontWeight: 800,
          letterSpacing: ".09em",
          textTransform: "uppercase",
          color: INK_FAINT,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 12, fontWeight: 700, color: INK, marginTop: 1 }}>{value}</div>
    </div>
  );
}

/** The MedSetu mark — a navy tile with a saffron cross, the trade-app sort. */
function MedSetuMark({ size }: { size: number }) {
  return (
    <div
      aria-hidden
      style={{
        width: size,
        height: size,
        flex: "none",
        borderRadius: size * 0.28,
        background: `linear-gradient(150deg, ${NAVY} 0%, ${NAVY_DEEP} 100%)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 4px 14px rgba(11,27,51,.28)",
      }}
    >
      <svg width={size * 0.52} height={size * 0.52} viewBox="0 0 24 24" fill="none">
        <rect x="10" y="3" width="4" height="18" rx="1.6" fill={SAFFRON} />
        <rect x="3" y="10" width="18" height="4" rx="1.6" fill="#FFFFFF" />
        <rect x="10" y="10" width="4" height="4" fill={SAFFRON} />
      </svg>
    </div>
  );
}

function StoreMark({ pharmacy, size }: { pharmacy: Pharmacy; size: number }) {
  const initials = pharmacy.name
    .split(" ")
    .filter((w) => /^[A-Za-z]/.test(w))
    .slice(0, 2)
    .map((w) => w[0])
    .join("");
  return (
    <div
      aria-hidden
      style={{
        width: size,
        height: size,
        flex: "none",
        borderRadius: 13,
        background: `hsl(${pharmacy.hue} 45% 92%)`,
        color: `hsl(${pharmacy.hue} 52% 30%)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 900,
        fontSize: size * 0.36,
        letterSpacing: ".01em",
      }}
    >
      {initials}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Screen 2 — the phone stage
// ═════════════════════════════════════════════════════════════════════════════

function PhoneStage() {
  const { scenario, pharmacy, backToPicker, phase } = useOrderDesk();
  if (!scenario || !pharmacy) return null;
  return (
    <div
      className="od-stage"
      style={{
        minHeight: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--od-stage-gap)",
        padding: "var(--od-stage-pad)",
        flexWrap: "wrap",
      }}
    >
      <ContextPanel
        scenario={scenario}
        pharmacy={pharmacy}
        onBack={backToPicker}
        showBack={phase !== "call"}
      />
      <PhoneFrame scenario={scenario} pharmacy={pharmacy} />
    </div>
  );
}

/** Audience-facing panel: exactly what the desk walks in with, plus the script. */
function ContextPanel({
  scenario,
  pharmacy,
  onBack,
  showBack,
}: {
  scenario: Scenario;
  pharmacy: Pharmacy;
  onBack: () => void;
  showBack: boolean;
}) {
  return (
    <aside className="od-context od-scroll">
      {showBack && (
        <button
          onClick={onBack}
          style={{
            alignSelf: "flex-start",
            background: "none",
            border: "none",
            color: INK_SOFT,
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
            padding: 0,
            fontFamily: BODY,
          }}
        >
          ← All scenarios
        </button>
      )}

      <div>
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 800,
            letterSpacing: ".11em",
            textTransform: "uppercase",
            color: INK_FAINT,
          }}
        >
          {pharmacy.name} · {scenario.day_label} · {scenario.chip}
        </div>
        <div style={{ fontWeight: 900, fontSize: 24, color: NAVY_DEEP, marginTop: 2, letterSpacing: "-0.025em" }}>
          {scenario.title}
        </div>
      </div>

      <PanelCard title="What the desk walks in knowing">
        <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 }}>
          {scenario.context_bullets.map((b, i) => (
            <li key={i} style={{ fontSize: 12.5, color: INK, lineHeight: 1.5, display: "flex", gap: 8 }}>
              <span aria-hidden style={{ color: NAVY, flex: "none" }}>—</span>
              {b}
            </li>
          ))}
        </ul>
        <div style={{ marginTop: 10, fontSize: 11.5, color: INK_SOFT, lineHeight: 1.5 }}>
          Account, prior calls and order history ride the session payload — nothing on this call is
          scripted, and every SKU it finds comes from the live catalog.
        </div>
      </PanelCard>

      {scenario.prior_calls.length > 0 && (
        <PanelCard title="Previous calls">
          {scenario.prior_calls.map((c, i) => (
            <div key={i} style={{ marginTop: i > 0 ? 11 : 0 }}>
              <div style={{ fontSize: 11.5, fontWeight: 800, color: NAVY }}>{c.day}</div>
              <div style={{ fontSize: 12.5, lineHeight: 1.5, marginTop: 2, color: INK }}>{c.summary}</div>
              {c.commitment && (
                <div style={{ fontSize: 12, color: SAFFRON_DEEP, fontWeight: 700, marginTop: 3 }}>
                  Committed: {c.commitment}
                </div>
              )}
            </div>
          ))}
        </PanelCard>
      )}

      {scenario.order_history.length > 0 && (
        <PanelCard title={`Order history · ${scenario.order_history.length} lines`}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
            <thead>
              <tr>
                {["SKU", "Pack", "Qty"].map((h, i) => (
                  <th
                    key={h}
                    style={{
                      textAlign: i === 2 ? "right" : "left",
                      fontSize: "var(--od-micro)",
                      fontWeight: 800,
                      letterSpacing: ".08em",
                      textTransform: "uppercase",
                      color: INK_FAINT,
                      padding: "0 0 5px",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scenario.order_history.map((h, i) => (
                <tr key={h.sku_code + i} style={{ borderTop: `1px solid ${LINE_SOFT}` }}>
                  <td style={{ padding: "5px 8px 5px 0", lineHeight: 1.35 }}>
                    <div style={{ fontWeight: 700, color: INK }}>{h.name}</div>
                    <div style={{ fontFamily: MONO, fontSize: 10.5, color: INK_FAINT }}>
                      {h.sku_code} · {h.when}
                    </div>
                  </td>
                  <td style={{ padding: "5px 8px 5px 0", fontFamily: MONO, color: INK_SOFT, whiteSpace: "nowrap" }}>
                    {h.pack_size}
                  </td>
                  <td style={{ padding: "5px 0", textAlign: "right", fontFamily: MONO, fontWeight: 700, color: INK }}>
                    {h.qty}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelCard>
      )}

      <PanelCard title="Say this on the call" tint>
        <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 7 }}>
          {scenario.try_hints.map((h, i) => (
            <li key={i} style={{ display: "flex", gap: 9, alignItems: "flex-start" }}>
              <span
                aria-hidden
                style={{
                  flex: "none",
                  width: 17,
                  height: 17,
                  borderRadius: "50%",
                  background: SAFFRON,
                  color: "#fff",
                  fontSize: 10.5,
                  fontWeight: 800,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  marginTop: 1,
                }}
              >
                {i + 1}
              </span>
              <span style={{ fontFamily: DEVA, fontSize: 13.5, lineHeight: 1.5, color: INK }}>{h}</span>
            </li>
          ))}
        </ol>
        <div style={{ marginTop: 9, fontSize: 11.5, color: SAFFRON_DEEP, lineHeight: 1.45 }}>
          Speak Hindi — the screen answers in English.
        </div>
      </PanelCard>
    </aside>
  );
}

function PanelCard({ title, children, tint }: { title: string; children: ReactNode; tint?: boolean }) {
  return (
    <div
      style={{
        background: tint ? SAFFRON_TINT : CARD,
        border: `1px solid ${tint ? "#F2DDBB" : LINE}`,
        borderRadius: 14,
        padding: "13px 15px",
      }}
    >
      <div
        style={{
          fontSize: 10.5,
          fontWeight: 800,
          letterSpacing: ".09em",
          textTransform: "uppercase",
          color: tint ? SAFFRON_DEEP : INK_FAINT,
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

// ── The device ───────────────────────────────────────────────────────────────

function PhoneFrame({ scenario, pharmacy }: { scenario: Scenario; pharmacy: Pharmacy }) {
  const { phase } = useOrderDesk();
  return (
    <div className="od-phone">
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          borderRadius: "var(--od-screen-radius)",
          overflow: "hidden",
          background: phase === "incoming" ? CALL_BG : BG,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* punch-hole camera — dropped on a real handset (.od-notch) */}
        <div
          className="od-notch"
          aria-hidden
          style={{
            position: "absolute",
            top: 11,
            left: "50%",
            transform: "translateX(-50%)",
            width: 82,
            height: 23,
            borderRadius: 13,
            background: "#080D16",
            zIndex: 40,
          }}
        />
        {phase === "incoming" && <IncomingSequence scenario={scenario} />}
        {phase === "call" && <OrderScreen pharmacy={pharmacy} />}
        {phase === "ended" && <EndedScreen pharmacy={pharmacy} />}
      </div>
    </div>
  );
}

function StatusBar({ dark }: { dark?: boolean }) {
  const c = dark ? "rgba(255,255,255,.92)" : INK;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "13px 24px 5px",
        fontSize: 12.5,
        fontWeight: 700,
        color: c,
        zIndex: 30,
        flex: "none",
      }}
    >
      <span>{CLOCK_LABEL}</span>
      <span style={{ display: "flex", gap: 6, alignItems: "center", fontSize: "var(--od-mini)", fontWeight: 600 }}>
        4G
        <span
          aria-hidden
          style={{
            display: "inline-block",
            width: 21,
            height: 11,
            border: `1.5px solid ${c}`,
            borderRadius: 3.5,
            position: "relative",
          }}
        >
          <span style={{ position: "absolute", inset: 1.5, right: "28%", background: c, borderRadius: 1.5 }} />
        </span>
      </span>
    </div>
  );
}

// ── The signature moment: 9:02 AM push notification + chime → Join / Snooze ──
// Deliberately NOT a telephony call screen — this is the distributor's app
// nudging the pharmacist into her morning order, like a calendar reminder.

/** Two short tones — a business-app notification, not a ringtone. */
function useChime(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const AC =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    let alive = true;
    const chime = (gainPeak: number) => {
      if (!alive) return;
      [587.33, 880].forEach((f, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = f;
        const t = ctx.currentTime + i * 0.15;
        gain.gain.setValueAtTime(0, t);
        gain.gain.linearRampToValueAtTime(gainPeak, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.75);
        osc.connect(gain).connect(ctx.destination);
        osc.start(t);
        osc.stop(t + 0.8);
      });
    };
    chime(0.05);
    const iv = window.setInterval(() => chime(0.028), 5200);
    return () => {
      alive = false;
      window.clearInterval(iv);
      ctx.close().catch(() => {});
    };
  }, [active]);
}

function IncomingSequence({ scenario }: { scenario: Scenario }) {
  const { acceptCall, declineCall } = useOrderDesk();
  const [stage, setStage] = useState<"lock" | "invite" | "snoozed">("lock");
  useChime(stage === "invite");

  useEffect(() => {
    const t = window.setTimeout(() => setStage("invite"), 1300);
    return () => window.clearTimeout(t);
  }, []);

  const snooze = () => {
    setStage("snoozed");
    window.setTimeout(declineCall, 1500);
  };

  return (
    <div style={{ position: "relative", flex: 1, display: "flex", flexDirection: "column", color: "#fff" }}>
      <StatusBar dark />
      <div style={{ textAlign: "center", marginTop: 82 }}>
        <div style={{ fontSize: 66, fontWeight: 300, letterSpacing: "-0.03em", fontFamily: BODY }}>{CLOCK}</div>
        <div style={{ fontSize: 14.5, opacity: 0.72, marginTop: 2 }}>{DATE_LABEL}</div>
      </div>

      {stage !== "lock" && (
        <div
          style={{
            margin: "38px 13px 0",
            background: "rgba(255,255,255,.15)",
            backdropFilter: "blur(16px)",
            borderRadius: 20,
            padding: "13px 14px 12px",
            animation: "odSlideDown .55s cubic-bezier(.2,.9,.3,1.1) both",
          }}
        >
          <div style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
            <MedSetuMark size={38} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 12.5, fontWeight: 800 }}>{BRAND} · Order Desk</span>
                <span style={{ fontSize: 11, opacity: 0.7 }}>now</span>
              </div>
              <div
                style={{
                  fontFamily: DEVA,
                  fontSize: 13,
                  lineHeight: 1.45,
                  opacity: 0.95,
                  marginTop: 2,
                }}
              >
                {/* English on screen, always — the Hindi lives in the call audio. */}
                {stage === "snoozed" ? "Snoozed — we'll remind you at 9:30." : scenario.nudge}
              </div>
            </div>
          </div>
          {stage === "invite" && (
            <div style={{ display: "flex", gap: 9, marginTop: 12 }}>
              <button
                onClick={acceptCall}
                style={{
                  flex: 1.4,
                  border: "none",
                  borderRadius: 12,
                  padding: "11px 0",
                  background: SAFFRON,
                  color: "#fff",
                  fontSize: 13.5,
                  fontWeight: 800,
                  fontFamily: BODY,
                  cursor: "pointer",
                  animation: "odBreathe 2s ease-out infinite",
                }}
              >
                Join call
              </button>
              <button
                onClick={snooze}
                style={{
                  flex: 1,
                  border: "none",
                  borderRadius: 12,
                  padding: "11px 0",
                  background: "rgba(255,255,255,.16)",
                  color: "#fff",
                  fontSize: 13.5,
                  fontWeight: 700,
                  fontFamily: BODY,
                  cursor: "pointer",
                }}
              >
                Snooze
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// The order screen (live call) — the hero
// ═════════════════════════════════════════════════════════════════════════════

function OrderScreen({ pharmacy }: { pharmacy: Pharmacy }) {
  const { items, note, dismissNote, highlight, confirmed, searchOpen } = useOrderDesk();
  const listRef = useRef<HTMLDivElement>(null);
  const lastHl = useRef(0);

  // `highlight_item`: bring the row the desk is asking about into view.
  useEffect(() => {
    if (!highlight || highlight.nonce === lastHl.current) return;
    lastHl.current = highlight.nonce;
    const el = listRef.current?.querySelector(`[data-item="${highlight.id}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlight]);

  return (
    <div style={{ position: "relative", flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <StatusBar />

      <div style={{ padding: "6px 10px 0", flex: "none" }}>
        <OrderDeskCallSession />
      </div>

      {confirmed ? (
        <OrderPlacedScreen pharmacy={pharmacy} />
      ) : (
        <>
          <div style={{ padding: "8px 10px 6px", flex: "none", position: "relative", zIndex: 20 }}>
            <SearchBar />
          </div>

          <div
            ref={listRef}
            className="od-scroll"
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "2px 10px 14px",
              display: "flex",
              flexDirection: "column",
              gap: 8,
              opacity: searchOpen ? 0.35 : 1,
              transition: "opacity .16s",
            }}
          >
            {note && (
              <div
                className="od-fresh"
                style={{
                  display: "flex",
                  gap: 9,
                  alignItems: "flex-start",
                  background: SAFFRON_TINT,
                  border: `1px solid #F2DDBB`,
                  borderRadius: 12,
                  padding: "9px 11px",
                }}
              >
                <span aria-hidden style={{ color: SAFFRON_DEEP, fontWeight: 900, flex: "none" }}>★</span>
                <div style={{ flex: 1, fontSize: 12.5, lineHeight: 1.45, color: INK, fontWeight: 600 }}>{note}</div>
                <button
                  onClick={dismissNote}
                  aria-label="Dismiss"
                  style={{
                    border: "none",
                    background: "transparent",
                    color: SAFFRON_DEEP,
                    cursor: "pointer",
                    fontSize: 13,
                    padding: 0,
                    lineHeight: 1,
                  }}
                >
                  ✕
                </button>
              </div>
            )}

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "2px 4px 0",
              }}
            >
              <span
                style={{
                  fontSize: "var(--od-mini)",
                  fontWeight: 800,
                  letterSpacing: ".1em",
                  textTransform: "uppercase",
                  color: INK_FAINT,
                }}
              >
                Today&rsquo;s order
              </span>
              <span style={{ fontSize: "var(--od-mini)", color: INK_FAINT, fontFamily: MONO }}>
                {pharmacy.name}
              </span>
            </div>

            {items.length === 0 ? <EmptyOrder /> : items.map((it) => <LineItemRow key={it.id} item={it} />)}
          </div>

          <CartBar />
        </>
      )}

      {searchOpen && <SearchResultsPanel />}
    </div>
  );
}

function EmptyOrder() {
  return (
    <div
      style={{
        marginTop: 26,
        textAlign: "center",
        color: INK_FAINT,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 9,
      }}
    >
      <div
        aria-hidden
        className="od-blink"
        style={{
          width: 46,
          height: 46,
          borderRadius: "50%",
          background: NAVY_TINT,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <rect x="9" y="2.5" width="6" height="12" rx="3" fill={NAVY} />
          <path d="M5 11a7 7 0 0 0 14 0" stroke={NAVY} strokeWidth="2" strokeLinecap="round" />
          <path d="M12 18.5V21.5" stroke={NAVY} strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: INK_SOFT }}>Speak your order</div>
      <div style={{ fontSize: 12, lineHeight: 1.5, maxWidth: 250 }}>
        Every item you name lands here and resolves against the catalog. Or search for a product
        yourself, above.
      </div>
    </div>
  );
}

// ── Search (catalog_search → show_search_results) ────────────────────────────

function SearchBar() {
  const { searchQuery, setSearchQuery, searching, closeSearch, searchOpen } = useOrderDesk();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: CARD,
        border: `1px solid ${searchOpen ? NAVY : LINE}`,
        borderRadius: 12,
        padding: "0 11px",
        height: 38,
        boxShadow: searchOpen ? "0 8px 22px rgba(11,27,51,.14)" : "none",
        transition: "border-color .15s, box-shadow .15s",
      }}
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" style={{ flex: "none" }} aria-hidden>
        <circle cx="11" cy="11" r="7" stroke={INK_FAINT} strokeWidth="2" />
        <path d="M16.5 16.5 21 21" stroke={INK_FAINT} strokeWidth="2" strokeLinecap="round" />
      </svg>
      <input
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="Search the catalog — brand, form, pack…"
        style={{
          flex: 1,
          minWidth: 0,
          border: "none",
          outline: "none",
          background: "transparent",
          fontSize: 13,
          fontFamily: BODY,
          color: INK,
        }}
      />
      {searching && (
        <span className="od-blink" style={{ fontSize: "var(--od-mini)", color: INK_FAINT, fontWeight: 700 }}>
          searching…
        </span>
      )}
      {searchQuery.length > 0 && (
        <button
          onClick={closeSearch}
          aria-label="Clear search"
          style={{
            border: "none",
            background: LINE_SOFT,
            borderRadius: "50%",
            width: 18,
            height: 18,
            color: INK_SOFT,
            cursor: "pointer",
            fontSize: 11,
            lineHeight: 1,
            flex: "none",
          }}
        >
          ✕
        </button>
      )}
    </div>
  );
}

function SearchResultsPanel() {
  const { searchQuery, searchResults, searching, searchTarget, items, pickFromSearch, closeSearch } =
    useOrderDesk();
  const target = searchTarget ? items.find((it) => it.id === searchTarget) : null;
  const short = searchQuery.trim().length < 2;
  return (
    <div
      style={{
        position: "absolute",
        left: 10,
        right: 10,
        // Clears the status bar + call bar + search field above it.
        top: 144,
        bottom: 14,
        zIndex: 25,
        background: CARD,
        border: `1px solid ${LINE}`,
        borderRadius: 16,
        boxShadow: "0 22px 60px rgba(9,22,42,.30)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        animation: "odFadeUp .22s ease both",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "10px 13px",
          borderBottom: `1px solid ${LINE_SOFT}`,
          background: target ? AMBER_TINT : "transparent",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: "var(--od-micro)",
              fontWeight: 800,
              letterSpacing: ".09em",
              textTransform: "uppercase",
              color: target ? AMBER : INK_FAINT,
            }}
          >
            {target ? "Pick a SKU for this line" : "Catalog search"}
          </div>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: INK, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {target ? target.spoken_text : searchQuery || "Type at least two letters"}
          </div>
        </div>
        <button onClick={closeSearch} className="od-ghost" style={ghostBtn()}>
          Close
        </button>
      </div>

      <div className="od-scroll" style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
        {short ? (
          <PanelEmpty text="Two letters is enough — the catalog answers as you type." />
        ) : searching && searchResults.length === 0 ? (
          <PanelEmpty text="Searching 20,148 SKUs…" />
        ) : searchResults.length === 0 ? (
          <PanelEmpty text={`Nothing in the catalog for “${searchQuery.trim()}”.`} />
        ) : (
          searchResults.map((sku) => (
            <button
              key={sku.code}
              className="od-res"
              onClick={() => pickFromSearch(sku)}
              style={{
                display: "flex",
                width: "100%",
                textAlign: "left",
                alignItems: "center",
                gap: 10,
                border: "none",
                borderTop: `1px solid ${LINE_SOFT}`,
                background: "transparent",
                padding: "9px 13px",
                cursor: "pointer",
                fontFamily: BODY,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: INK, lineHeight: 1.3 }}>{sku.name}</div>
                <div style={{ fontSize: 11, color: INK_FAINT, marginTop: 1, fontFamily: MONO }}>
                  {[sku.pack_size, sku.manufacturer, sku.code].filter(Boolean).join(" · ")}
                </div>
              </div>
              <div style={{ textAlign: "right", flex: "none" }}>
                <div style={{ fontSize: 12.5, fontWeight: 800, color: NAVY, fontFamily: MONO }}>
                  {rupeesExact(sku.ptr)}
                </div>
                <div style={{ fontSize: 10.5, color: INK_FAINT, fontFamily: MONO }}>MRP {rupees(sku.mrp)}</div>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function PanelEmpty({ text }: { text: string }) {
  return (
    <div style={{ padding: "22px 16px", textAlign: "center", fontSize: 12.5, color: INK_FAINT, lineHeight: 1.5 }}>
      {text}
    </div>
  );
}

// ── The line-item row — the state machine, made visible ──────────────────────

const STATUS_STYLE: Record<
  LineItem["status"],
  { border: string; bg: string; accent: string; label: string }
> = {
  resolving: { border: LINE, bg: CARD, accent: GREY, label: "Looking up…" },
  multi_family: { border: AMBER_LINE, bg: AMBER_TINT, accent: AMBER, label: "Which brand?" },
  multi_variant: { border: AMBER_LINE, bg: AMBER_TINT, accent: AMBER, label: "Choose one" },
  matched: { border: GREEN_LINE, bg: CARD, accent: GREEN, label: "Matched" },
  not_found: { border: LINE, bg: GREY_TINT, accent: INK_FAINT, label: "Not in catalog" },
};

/** Which axis of a SkuWire each `differing_axes` entry reads. */
const AXIS_VALUE: Record<string, (s: SkuWire) => string> = {
  variant_label: (s) => s.variant_label,
  form: (s) => s.form,
  strength: (s) => s.strength,
  pack_size: (s) => s.pack_size,
};

/**
 * A pill says only what actually differs between the candidates — that is the
 * whole point of `differing_axes`. "EYE DROPS 5ML" vs "EYE OINTMENT 5GM", never
 * the full name twice over. Falls back to the SKU name if the axes are empty or
 * all read blank.
 */
function pillLabel(sku: SkuWire, axes: string[]): string {
  const source = axes.length > 0 ? axes : ["variant_label", "form", "strength", "pack_size"];
  const parts = source
    .map((a) => AXIS_VALUE[a]?.(sku) ?? "")
    .map((v) => v.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts.join(" ") : sku.name;
}

/**
 * Four pills, hard stop (DESIGN §7-bis). Twenty matches never become twenty pills:
 * the agent asks one question whose 2–4 choices cover the whole candidate set, and
 * anything that still overflows falls back to the search panel rather than a wall.
 */
const PILL_CAP = 4;

/** The one amber pill shape — question choices and variant leaves share it. */
function pillStyle(): CSSProperties {
  return {
    border: `1px solid ${AMBER_LINE}`,
    background: "rgba(255,255,255,.75)",
    borderRadius: 9,
    padding: "6px 10px",
    cursor: "pointer",
    fontFamily: BODY,
    textAlign: "left",
    display: "flex",
    alignItems: "baseline",
    gap: 7,
  };
}

/** Overflow escape hatch: the rest of the options, in the scoped search panel. */
function MorePill({ n, onClick }: { n: number; onClick: () => void }) {
  return (
    <button
      className="od-pill"
      onClick={onClick}
      style={{ ...pillStyle(), borderStyle: "dashed", background: "rgba(255,255,255,.45)" }}
    >
      <span style={{ fontSize: 12, fontWeight: 800, color: NAVY }}>+{n} more</span>
    </button>
  );
}

function stockLine(stock: number): { text: string; color: string } {
  if (stock <= 0) return { text: "Out of stock", color: RED };
  if (stock < 25) return { text: `Only ${stock} left`, color: AMBER };
  return { text: `${stock} in stock`, color: INK_FAINT };
}

function LineItemRow({ item }: { item: LineItem }) {
  const { highlight, removeItem, choosePill, chooseChoice, chooseFamily, narrowToFamily } =
    useOrderDesk();
  const s = STATUS_STYLE[item.status];
  const hot = highlight?.id === item.id;
  // The agent's one sharp question supersedes the raw pill/card rendering: while a
  // question is on the row, THAT is the only thing to answer (DESIGN §7-bis).
  const asking = item.status === "matched" ? null : item.question;
  // Narrowed past the pill cap and nothing to point at yet — the state a group tap
  // leaves behind while the agent works out its next question.
  const narrowed =
    item.status !== "matched" &&
    item.variants.length === 0 &&
    item.families.length === 0 &&
    item.candidates.length > PILL_CAP;
  const scopedSearch = () => chooseFamily(item.id, item.family || item.query || item.spoken_text);

  return (
    <div
      data-item={item.id}
      className={`od-fresh${hot ? " od-hl" : ""}`}
      style={{
        background: s.bg,
        border: `1px solid ${hot ? SAFFRON : s.border}`,
        borderLeft: `3px solid ${s.accent}`,
        borderRadius: 13,
        padding: "9px 11px",
        position: "relative",
      }}
    >
      {/* Header line: what was heard, the status word, and (once matched) delete. */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: "var(--od-micro)",
              fontWeight: 800,
              letterSpacing: ".09em",
              textTransform: "uppercase",
              color: s.accent,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span className={item.status === "resolving" ? "od-blink" : undefined}>{s.label}</span>
            {item.source === "manual" && (
              <span style={{ color: INK_FAINT, fontWeight: 700, letterSpacing: ".06em" }}>· added by hand</span>
            )}
          </div>
          <div
            style={{
              fontSize: 13.5,
              fontWeight: 800,
              color: item.status === "not_found" ? INK_SOFT : INK,
              marginTop: 2,
              lineHeight: 1.3,
              letterSpacing: "-0.01em",
            }}
          >
            {item.status === "matched" && item.sku ? item.sku.name : item.family || item.spoken_text}
          </div>
          {item.status !== "matched" && item.spoken_text && (
            <div style={{ fontSize: 11, color: INK_FAINT, marginTop: 1 }}>heard: “{item.spoken_text}”</div>
          )}
        </div>

        {item.quantity !== null && item.status !== "matched" && (
          <span
            style={{
              flex: "none",
              fontFamily: MONO,
              fontSize: 12,
              fontWeight: 800,
              color: INK_SOFT,
              background: "rgba(255,255,255,.7)",
              borderRadius: 8,
              padding: "3px 8px",
            }}
          >
            ×{item.quantity}
          </span>
        )}

        <button
          onClick={() => removeItem(item.id)}
          aria-label="Remove line"
          className="od-ghost"
          style={{
            flex: "none",
            border: "none",
            background: "transparent",
            color: INK_FAINT,
            cursor: "pointer",
            fontSize: 13,
            borderRadius: 7,
            width: 22,
            height: 22,
            lineHeight: 1,
          }}
        >
          ✕
        </button>
      </div>

      {/* The agent's question, as a speech bubble on the row it belongs to. */}
      {item.note && (
        <div
          className="od-pop"
          style={{
            marginTop: 7,
            display: "inline-flex",
            gap: 6,
            alignItems: "center",
            background: NAVY,
            color: "#fff",
            borderRadius: "12px 12px 12px 3px",
            padding: "5px 10px",
            fontSize: 11.5,
            fontWeight: 600,
            lineHeight: 1.35,
            maxWidth: "100%",
          }}
        >
          <span aria-hidden style={{ opacity: 0.7 }}>💬</span>
          {item.note}
        </div>
      )}

      {item.status === "resolving" && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 5 }}>
          <div className="od-shimmer" style={{ height: 9, borderRadius: 5, width: "72%" }} />
          <div className="od-shimmer" style={{ height: 9, borderRadius: 5, width: "44%" }} />
        </div>
      )}

      {/*
        The sharpest question: 2–4 pills that between them cover every candidate.
        A tap answers on this screen at once — a leaf locks the SKU, a group throws
        the rest away and (if few enough survive) grows the leaves right here. The
        agent hears about it through the snapshot, not the other way round.
      */}
      {asking && (
        <>
          <div style={{ marginTop: 7, fontSize: 11.5, color: AMBER, fontWeight: 700 }}>
            {asking.text}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
            {asking.choices.slice(0, PILL_CAP).map((choice, idx) => {
              const leaf = choice.sku_code
                ? (item.candidates.find((c) => c.code === choice.sku_code) ??
                   item.variants.find((v) => v.code === choice.sku_code) ??
                   null)
                : null;
              return (
                <button
                  key={choice.sku_code ?? `${idx}-${choice.label}`}
                  className="od-pill"
                  onClick={() => chooseChoice(item.id, choice)}
                  style={pillStyle()}
                >
                  <span style={{ fontSize: 12, fontWeight: 800, color: INK }}>{choice.label}</span>
                  {leaf ? (
                    <>
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: NAVY, fontFamily: MONO }}>
                        {rupees(leaf.ptr)}
                      </span>
                      {leaf.scheme && <SchemeBadge scheme={leaf.scheme} small />}
                    </>
                  ) : (
                    <span style={{ fontSize: 10.5, fontWeight: 800, color: AMBER, fontFamily: MONO }}>
                      {choice.narrows_to.length}
                    </span>
                  )}
                </button>
              );
            })}
            {asking.choices.length > PILL_CAP && (
              <MorePill n={asking.choices.length - PILL_CAP} onClick={scopedSearch} />
            )}
          </div>
        </>
      )}

      {/*
        Between rounds: the pharmacist's tap threw most of the candidates away, but
        too many are left to point at. Say how many survived — the count is the
        proof the tap landed — and wait for the agent's next question.
      */}
      {!asking && narrowed && (
        <div style={{ marginTop: 7, fontSize: 11.5, color: AMBER, fontWeight: 700 }}>
          Narrowed — {item.candidates.length} options left
        </div>
      )}

      {!asking && item.status === "multi_variant" && item.variants.length > 0 && (
        <>
          <div style={{ marginTop: 7, fontSize: 11.5, color: AMBER, fontWeight: 700 }}>
            {axesQuestion(item.differing_axes, item.variants.length)}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
            {/* Never more than four pills on a row — past that it is a question, not a list. */}
            {item.variants.slice(0, PILL_CAP).map((v) => (
              <button
                key={v.code}
                className="od-pill"
                onClick={() => choosePill(item.id, v)}
                style={pillStyle()}
              >
                <span style={{ fontSize: 12, fontWeight: 800, color: INK }}>{pillLabel(v, item.differing_axes)}</span>
                <span style={{ fontSize: 11.5, fontWeight: 700, color: NAVY, fontFamily: MONO }}>
                  {rupees(v.ptr)}
                </span>
                {v.scheme && <SchemeBadge scheme={v.scheme} small />}
              </button>
            ))}
            {item.variants.length > PILL_CAP && (
              <MorePill n={item.variants.length - PILL_CAP} onClick={scopedSearch} />
            )}
          </div>
        </>
      )}

      {/*
        Brand cards. A card is only a *pick* when this screen holds that family's
        SKUs whole — then the tap narrows the row here and now. When the candidate
        set arrived truncated the tap can only scope the search panel, and the card
        wears that: dashed edge, navy magnifier, "Search N SKUs". A control that
        looks like a pick and behaves like a search is the bug this row exists to
        stop being.
      */}
      {!asking && item.status === "multi_family" && item.families.length > 0 && (
        <>
          <div style={{ marginTop: 7, fontSize: 11.5, color: AMBER, fontWeight: 700 }}>
            {item.families.length} brands sound like this — pick one
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
            {item.families.map((f: FamilyWire) => {
              const whole = familyHeldWhole(item, f);
              return (
                <button
                  key={f.family}
                  className="od-pill"
                  onClick={() =>
                    whole ? narrowToFamily(item.id, f.family) : chooseFamily(item.id, f.family)
                  }
                  style={{
                    border: `1px ${whole ? "solid" : "dashed"} ${AMBER_LINE}`,
                    background: whole ? "rgba(255,255,255,.75)" : "rgba(255,255,255,.45)",
                    borderRadius: 10,
                    padding: "8px 10px",
                    cursor: "pointer",
                    fontFamily: BODY,
                    textAlign: "left",
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 800, color: INK }}>{f.family}</div>
                    <div style={{ fontSize: 11, color: INK_SOFT, marginTop: 1 }}>{f.hint}</div>
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 800,
                      color: whole ? AMBER : NAVY,
                      flex: "none",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {whole
                      ? `${f.sku_count} SKU${f.sku_count === 1 ? "" : "s"} →`
                      : `Search ${f.sku_count} SKU${f.sku_count === 1 ? "" : "s"} 🔍`}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}

      {item.status === "not_found" && (
        <div
          style={{
            marginTop: 7,
            display: "flex",
            alignItems: "center",
            gap: 9,
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontSize: 11.5, color: INK_SOFT, lineHeight: 1.4, flex: 1, minWidth: 150 }}>
            No catalog match for “{item.spoken_text}”. Search for it yourself, or say it another way.
          </span>
          <button
            onClick={() => chooseFamily(item.id, item.query || item.spoken_text)}
            style={{
              border: `1px solid ${NAVY}`,
              background: CARD,
              color: NAVY,
              borderRadius: 9,
              padding: "6px 11px",
              fontSize: 11.5,
              fontWeight: 800,
              cursor: "pointer",
              fontFamily: BODY,
              flex: "none",
            }}
          >
            Search catalog
          </button>
        </div>
      )}

      {item.status === "matched" && item.sku && <MatchedDetail item={item} sku={item.sku} />}
    </div>
  );
}

/** One short line naming only the axes the catalog could not decide between. */
function axesQuestion(axes: string[], n: number): string {
  const words: Record<string, string> = {
    variant_label: "variant",
    form: "form",
    strength: "strength",
    pack_size: "pack size",
  };
  const named = axes.map((a) => words[a] ?? a).filter(Boolean);
  if (named.length === 0) return `${n} options — pick one`;
  const list =
    named.length === 1
      ? named[0]
      : `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}`;
  return `${n} options differ by ${list}`;
}

function MatchedDetail({ item, sku }: { item: LineItem; sku: SkuWire }) {
  const { openVariants } = useOrderDesk();
  const stock = stockLine(sku.stock);
  const qty = item.quantity ?? 0;
  return (
    <div style={{ marginTop: 7 }}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: INK_SOFT }}>
              {sku.pack_size || "—"}
            </span>
            <span style={{ fontSize: 11, color: INK_FAINT }}>{sku.manufacturer}</span>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: INK_FAINT }}>{sku.code}</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 3, flexWrap: "wrap" }}>
            <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 800, color: GREEN }}>
              {rupeesExact(sku.ptr)}
            </span>
            <span style={{ fontSize: 10.5, fontWeight: 700, color: INK_FAINT, letterSpacing: ".06em" }}>PTR</span>
            <span style={{ fontFamily: MONO, fontSize: 11.5, color: INK_FAINT }}>MRP {rupees(sku.mrp)}</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: stock.color }}>· {stock.text}</span>
          </div>
          {sku.scheme && (
            <div style={{ marginTop: 5 }}>
              <SchemeBadge scheme={sku.scheme} />
            </div>
          )}
        </div>
        <QtyStepper item={item} />
      </div>

      {/*
        The family is usually right and the variant wrong ("ointment wala",
        "hundred gram one"). Deleting the line and re-dictating it is the painful
        path — this is the quiet one, and it stays on the row.
      */}
      <div
        style={{
          marginTop: 6,
          paddingTop: 6,
          borderTop: `1px dashed ${LINE}`,
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 11.5,
        }}
      >
        {sku.family && (
          <button
            className="od-ghost"
            onClick={() => openVariants(item.id, sku.family)}
            style={{ ...ghostBtn(), padding: "4px 9px", fontSize: 11 }}
          >
            Change variant
          </button>
        )}
        {qty >= 1 && (
          <>
            <span style={{ color: INK_FAINT, marginLeft: "auto" }}>
              {item.quantity} × {rupeesExact(sku.ptr)}
            </span>
            <span style={{ fontFamily: MONO, fontWeight: 800, color: INK }}>
              {rupeesExact(sku.ptr * qty)}
            </span>
          </>
        )}
      </div>

      <VariantStrip item={item} sku={sku} />
    </div>
  );
}

/**
 * The siblings of a matched SKU, inline on its row — never the search panel, which
 * would throw away the family the call already established. `PILL_CAP` governs
 * *questions*; this is a browse the pharmacist asked for, so a long family scrolls
 * inside the strip rather than taking over the screen.
 */
function VariantStrip({ item, sku }: { item: LineItem; sku: SkuWire }) {
  const { variantStrip, closeVariants, pickVariant } = useOrderDesk();
  if (!variantStrip || variantStrip.itemId !== item.id) return null;
  const { results, differingAxes, loading, family } = variantStrip;
  const others = results.filter((v) => v.code !== sku.code);

  return (
    <div
      className="od-pop"
      style={{
        marginTop: 7,
        background: GREY_TINT,
        border: `1px solid ${LINE}`,
        borderRadius: 11,
        padding: "8px 9px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: "var(--od-micro)",
            fontWeight: 800,
            letterSpacing: ".09em",
            textTransform: "uppercase",
            color: INK_FAINT,
          }}
        >
          Other variants in {family}
        </div>
        <button onClick={closeVariants} className="od-ghost" style={{ ...ghostBtn(), padding: "3px 8px", fontSize: 11 }}>
          Done
        </button>
      </div>

      {loading ? (
        <div className="od-blink" style={{ marginTop: 7, fontSize: 11.5, color: INK_FAINT }}>
          Loading variants…
        </div>
      ) : others.length === 0 ? (
        <div style={{ marginTop: 7, fontSize: 11.5, color: INK_FAINT, lineHeight: 1.4 }}>
          {family} has no other variants in the catalog.
        </div>
      ) : (
        <div
          className="od-scroll"
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
            marginTop: 7,
            // A strip, not a takeover — a long family scrolls in place.
            maxHeight: 132,
            overflowY: "auto",
          }}
        >
          {others.map((v) => (
            <button
              key={v.code}
              className="od-pill"
              onClick={() => pickVariant(item.id, v)}
              style={pillStyle()}
            >
              <span style={{ fontSize: 12, fontWeight: 800, color: INK }}>
                {pillLabel(v, differingAxes)}
              </span>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: NAVY, fontFamily: MONO }}>
                {rupees(v.ptr)}
              </span>
              {v.scheme && <SchemeBadge scheme={v.scheme} small />}
            </button>
          ))}
        </div>
      )}

      {/* What the row is locked to right now — so "change" is a comparison, not a leap. */}
      <div style={{ marginTop: 7, fontSize: 11, color: INK_SOFT, lineHeight: 1.35 }}>
        <span style={{ fontWeight: 800, color: GREEN }}>Current</span> · {sku.name}
        {" · "}
        <span style={{ fontFamily: MONO }}>{rupeesExact(sku.ptr)}</span>
      </div>
    </div>
  );
}

function SchemeBadge({ scheme, small }: { scheme: string; small?: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        background: GREEN_TINT,
        border: `1px solid ${GREEN_LINE}`,
        color: GREEN,
        borderRadius: 7,
        padding: small ? "1px 6px" : "3px 8px",
        fontSize: small ? 10 : 11,
        fontWeight: 800,
        letterSpacing: ".01em",
        whiteSpace: "nowrap",
      }}
    >
      {!small && <span aria-hidden>%</span>}
      {scheme}
    </span>
  );
}

/**
 * Quantity in strips. Typing is the fast path for a bulk order (nobody taps `+`
 * fifty times), so the field keeps a local draft while it is being edited and
 * commits any legible number straight to the store — which is what fires
 * `state_sync`, so the desk hears the change as you type it.
 */
function QtyStepper({ item }: { item: LineItem }) {
  const { setQuantity } = useOrderDesk();
  const [draft, setDraft] = useState<string | null>(null);
  const qty = item.quantity ?? 0;
  const shown = draft ?? (qty > 0 ? String(qty) : "");
  const missing = qty < 1;

  const commit = (raw: string) => {
    setDraft(raw);
    const n = parseInt(raw.replace(/\D/g, ""), 10);
    if (!Number.isNaN(n) && n >= 1) setQuantity(item.id, n);
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        flex: "none",
        border: `1px solid ${missing ? AMBER : LINE}`,
        background: missing ? AMBER_TINT : CARD,
        borderRadius: 10,
        overflow: "hidden",
        height: 32,
      }}
    >
      <button
        onClick={() => {
          setDraft(null);
          setQuantity(item.id, Math.max(1, qty - 1));
        }}
        aria-label="Decrease quantity"
        style={stepBtn()}
      >
        −
      </button>
      <input
        value={shown}
        inputMode="numeric"
        onChange={(e) => commit(e.target.value)}
        onBlur={() => setDraft(null)}
        placeholder="qty"
        aria-label="Quantity in strips"
        style={{
          width: 44,
          height: "100%",
          border: "none",
          outline: "none",
          background: "transparent",
          textAlign: "center",
          fontFamily: MONO,
          fontSize: 13,
          fontWeight: 800,
          color: INK,
        }}
      />
      <button
        onClick={() => {
          setDraft(null);
          setQuantity(item.id, qty + 1);
        }}
        aria-label="Increase quantity"
        style={stepBtn()}
      >
        +
      </button>
    </div>
  );
}

function stepBtn(): CSSProperties {
  return {
    border: "none",
    background: "transparent",
    color: NAVY,
    width: 26,
    height: "100%",
    fontSize: 15,
    fontWeight: 800,
    cursor: "pointer",
    fontFamily: BODY,
    lineHeight: 1,
  };
}

function ghostBtn(): CSSProperties {
  return {
    border: `1px solid ${LINE}`,
    background: CARD,
    color: INK_SOFT,
    borderRadius: 8,
    padding: "5px 10px",
    fontSize: 11.5,
    fontWeight: 700,
    cursor: "pointer",
    fontFamily: BODY,
    flex: "none",
  };
}

// ── The sticky cart bar ─────────────────────────────────────────────────────

function CartBar() {
  const { items, blockedIds, canConfirm, totalPtr, confirmOrder } = useOrderDesk();
  const ready = items.filter((it) => !blockedIds.includes(it.id)).length;

  // What is holding Confirm back, in the fewest words that still tell the truth.
  const needChoice = items.filter((it) => it.status !== "matched").length;
  const needQty = items.filter((it) => it.status === "matched" && (it.quantity ?? 0) < 1).length;
  const blocker =
    items.length === 0
      ? "Nothing on the order yet"
      : needChoice > 0 && needQty > 0
        ? `${needChoice} line${needChoice === 1 ? "" : "s"} to resolve · ${needQty} without a quantity`
        : needChoice > 0
          ? `${needChoice} line${needChoice === 1 ? "" : "s"} still to resolve`
          : needQty > 0
            ? `${needQty} line${needQty === 1 ? "" : "s"} need a quantity`
            : "";

  return (
    <div
      style={{
        flex: "none",
        borderTop: `1px solid ${LINE}`,
        background: CARD,
        padding: "9px 12px 14px",
        boxShadow: "0 -8px 22px rgba(9,22,42,.07)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
            <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 900, color: INK, letterSpacing: "-0.02em" }}>
              {rupees(totalPtr)}
            </span>
            <span style={{ fontSize: 10.5, fontWeight: 700, color: INK_FAINT, letterSpacing: ".06em" }}>
              PTR TOTAL
            </span>
          </div>
          <div style={{ fontSize: 11.5, color: blocker ? AMBER : INK_FAINT, marginTop: 1, fontWeight: 600 }}>
            {items.length} item{items.length === 1 ? "" : "s"} · {ready} ready
            {blocker ? ` · ${blocker}` : ""}
          </div>
        </div>
        <button
          onClick={confirmOrder}
          disabled={!canConfirm}
          style={{
            flex: "none",
            border: "none",
            borderRadius: 12,
            padding: "12px 20px",
            fontSize: 14,
            fontWeight: 800,
            fontFamily: BODY,
            cursor: canConfirm ? "pointer" : "not-allowed",
            color: "#fff",
            background: canConfirm ? SAFFRON : "#C3CDDB",
            boxShadow: canConfirm ? "0 8px 20px rgba(224,123,14,.35)" : "none",
            transition: "background .18s, box-shadow .18s",
          }}
        >
          Confirm order
        </button>
      </div>
    </div>
  );
}

// ── Order placed ────────────────────────────────────────────────────────────

function OrderPlacedScreen({ pharmacy }: { pharmacy: Pharmacy }) {
  const { items, orderNo, totalPtr } = useOrderDesk();
  return (
    <div
      className="od-scroll"
      style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "10px 12px 22px" }}
    >
      <div
        className="od-pop"
        style={{
          background: `linear-gradient(150deg, ${GREEN} 0%, #0B6647 100%)`,
          color: "#fff",
          borderRadius: 18,
          padding: "20px 18px",
          textAlign: "center",
          boxShadow: "0 14px 34px rgba(18,128,90,.30)",
        }}
      >
        <div
          aria-hidden
          style={{
            width: 46,
            height: 46,
            borderRadius: "50%",
            background: "rgba(255,255,255,.18)",
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 22,
            fontWeight: 900,
          }}
        >
          ✓
        </div>
        <div style={{ fontSize: 19, fontWeight: 900, marginTop: 11, letterSpacing: "-0.02em" }}>Order placed</div>
        <div style={{ fontFamily: MONO, fontSize: 13.5, fontWeight: 700, marginTop: 3, opacity: 0.92 }}>
          {orderNo ?? "—"}
        </div>
        <div style={{ fontSize: 12, opacity: 0.8, marginTop: 6, lineHeight: 1.45 }}>
          {items.length} line{items.length === 1 ? "" : "s"} · {rupees(totalPtr)} at PTR
          <br />
          Dispatching today to {pharmacy.name}, {pharmacy.area}
        </div>
      </div>

      <div
        style={{
          marginTop: 12,
          background: CARD,
          border: `1px solid ${LINE}`,
          borderRadius: 14,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            fontSize: "var(--od-micro)",
            fontWeight: 800,
            letterSpacing: ".09em",
            textTransform: "uppercase",
            color: INK_FAINT,
            padding: "10px 12px 6px",
          }}
        >
          On this order
        </div>
        {items.map((it) => (
          <div
            key={it.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 12px",
              borderTop: `1px solid ${LINE_SOFT}`,
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: INK, lineHeight: 1.3 }}>
                {it.sku?.name ?? it.spoken_text}
              </div>
              <div style={{ fontSize: 10.5, color: INK_FAINT, fontFamily: MONO }}>
                {[it.sku?.pack_size, it.sku?.code].filter(Boolean).join(" · ")}
              </div>
            </div>
            <div style={{ fontFamily: MONO, fontSize: 12, color: INK_SOFT, flex: "none" }}>×{it.quantity ?? 0}</div>
            <div style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 800, color: INK, flex: "none" }}>
              {rupees((it.sku?.ptr ?? 0) * (it.quantity ?? 0))}
            </div>
          </div>
        ))}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            padding: "10px 12px",
            borderTop: `1px solid ${LINE}`,
            background: NAVY_TINT,
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 800, color: NAVY }}>Total at PTR</span>
          <span style={{ fontFamily: MONO, fontSize: 13.5, fontWeight: 900, color: NAVY_DEEP }}>
            {rupees(totalPtr)}
          </span>
        </div>
      </div>

      <div style={{ marginTop: 11, fontSize: 11.5, color: INK_FAINT, textAlign: "center", lineHeight: 1.5 }}>
        The desk can see the order is confirmed — it will close the call in a line.
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Ended screen
// ═════════════════════════════════════════════════════════════════════════════

function EndedScreen({ pharmacy }: { pharmacy: Pharmacy }) {
  const { items, confirmed, orderNo, totalPtr, backToPicker } = useOrderDesk();
  return (
    <div
      className="od-scroll"
      style={{
        flex: 1,
        minHeight: 0,
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        color: "#fff",
        background: CALL_BG,
        padding: "0 22px 28px",
      }}
    >
      <StatusBar dark />
      <div style={{ textAlign: "center", marginTop: 40 }}>
        <div style={{ display: "inline-block" }}>
          <MedSetuMark size={64} />
        </div>
        <div style={{ fontWeight: 900, fontSize: 22, marginTop: 13, letterSpacing: "-0.02em" }}>Call ended</div>
        <div style={{ fontSize: 12.5, opacity: 0.7, marginTop: 3 }}>
          {DESK} · {pharmacy.name}
        </div>
      </div>

      <div
        style={{
          marginTop: 24,
          background: "rgba(255,255,255,.10)",
          borderRadius: 16,
          padding: "14px 15px",
          backdropFilter: "blur(8px)",
        }}
      >
        <div
          style={{
            fontSize: "var(--od-mini)",
            fontWeight: 800,
            letterSpacing: ".09em",
            textTransform: "uppercase",
            opacity: 0.7,
            marginBottom: 9,
          }}
        >
          {confirmed ? "Order confirmed" : "Nothing confirmed"}
        </div>

        {confirmed ? (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ fontFamily: "inherit", fontSize: 13, fontWeight: 700 }}>{orderNo}</span>
              <span style={{ fontSize: 15, fontWeight: 900 }}>{rupees(totalPtr)}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 10 }}>
              {items.map((it) => (
                <div key={it.id} style={{ fontSize: 12.5, lineHeight: 1.4, display: "flex", gap: 8 }}>
                  <span aria-hidden style={{ color: "#7BD8B8", flex: "none", fontWeight: 800 }}>✓</span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    {it.sku?.name ?? it.spoken_text}
                    {it.sku?.pack_size ? ` · ${it.sku.pack_size}` : ""}
                  </span>
                  <span style={{ opacity: 0.8, flex: "none" }}>×{it.quantity ?? 0}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 11, paddingTop: 10, borderTop: "1px solid rgba(255,255,255,.16)", fontSize: 12 }}>
              <span style={{ fontWeight: 800, color: "#F5C36B" }}>Dispatch: </span>
              today, to {pharmacy.area}, {pharmacy.city}
            </div>
          </>
        ) : (
          <div style={{ fontSize: 12.5, lineHeight: 1.5, opacity: 0.85 }}>
            The call ended before the order was confirmed
            {items.length > 0 ? ` — ${items.length} line${items.length === 1 ? "" : "s"} left in the cart.` : "."}{" "}
            Nothing was placed: the desk never confirms on the pharmacist&rsquo;s behalf.
          </div>
        )}
      </div>

      <button
        onClick={backToPicker}
        style={{
          marginTop: "auto",
          alignSelf: "center",
          background: "rgba(255,255,255,.14)",
          border: "1px solid rgba(255,255,255,.25)",
          color: "#fff",
          borderRadius: 13,
          padding: "11px 22px",
          fontSize: 13.5,
          fontWeight: 700,
          cursor: "pointer",
          fontFamily: BODY,
        }}
      >
        Back to scenarios
      </button>
    </div>
  );
}
