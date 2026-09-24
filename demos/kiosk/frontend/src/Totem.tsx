/**
 * The totem — the machine, not a page.
 *
 * A branch kiosk is a floor-standing column with a tall panel recessed behind a
 * bezel, and the demo renders that object rather than a web layout that happens
 * to be portrait. The glass is 9:16, the shape a floor-standing panel actually
 * is, and the frame is deeper above and below it than beside it, because that is
 * where the hardware lives: the sensor on top, the speaker, the card slot and
 * the brand plate below.
 *
 * On a phone the chassis is dropped entirely. A handset *is* the device, and
 * drawing a bezel inside a bezel would spend scarce pixels denying it.
 *
 * Inside the glass, three rows, and the order is the design:
 *
 *   - **header** — who this is, and Start over. There is no language picker:
 *     Tanvi hears the customer's language and switches to it herself.
 *   - **Tanvi** — at the top, with her captions under her. The kiosk is driven
 *     by voice first, so the customer talks to a face; she steps back further
 *     when the cards are up.
 *   - **tray** — the lower half and everything left: the question she just
 *     asked and its answers, the cards, the one button. It always fills the
 *     glass, so there is no empty panel waiting for something to happen.
 *
 * Nothing overlaps. Tanvi and the tray are two grid rows, not layers.
 *
 * There is no idle timer. A kiosk that resets while someone is reading has
 * thrown their answers away; Start over is the only reset.
 */

import type { ReactNode } from 'react';
import { ArrowCounterClockwise } from '@phosphor-icons/react';
import { CHASSIS, COLOR, SIZE } from './brand';
import { fontFor, strings, type Language } from './language';
import { UiStyles } from './ui';

/** How much of the glass the tray takes, which is how much Tanvi gives up. */
export type TrayWeight = 'light' | 'heavy';

export interface TotemProps {
  language: Language;
  /** Tanvi: the live tile, or the pre-call plate. */
  tanvi: ReactNode;
  /** The sentence in flight, under her face. Absent before the call. */
  captions?: ReactNode;
  /** What a hand can do on this screen. `null` when there is nothing to do but talk. */
  tray: ReactNode;
  /** Changes whenever the tray's content does, so it can arrive rather than jump. */
  trayKey: string;
  weight: TrayWeight;
  /** Start over is offered only once there is something to start over. */
  onRestart?: () => void;
}

export function Totem({
  language,
  tanvi,
  captions,
  tray,
  trayKey,
  weight,
  onRestart,
}: TotemProps) {
  const copy = strings(language);
  return (
    <div className="kiosk-room">
      <div className="kiosk-machine">
        <div className="kiosk-bezel-top">
          <span className="kiosk-sensor" aria-hidden />
        </div>

        <div className={`kiosk-screen is-${weight}`} style={{ fontFamily: fontFor(language) }}>
          <header className="kiosk-header">
            <span className="kiosk-brand">
              <span className="kiosk-brand-mark" aria-hidden />
              <span className="kiosk-brand-name">Vantage Bank</span>
            </span>
            {onRestart ? (
              <button
                type="button"
                className="kiosk-restart"
                onClick={onRestart}
                aria-label={copy.restart}
                title={copy.restart}
              >
                <ArrowCounterClockwise size={20} weight="bold" aria-hidden />
              </button>
            ) : null}
          </header>

          <section className="kiosk-presence" aria-label={copy.assistant}>
            <div className="kiosk-presence-tile">{tanvi}</div>
          </section>

          {/* The counter she stands behind: its top edge covers where the
              character's shoulders end, and what she is saying rides along it. */}
          <main className="kiosk-tray">
            {captions ? <div className="kiosk-tray-captions">{captions}</div> : null}
            {tray ? (
              <div className="kiosk-tray-body" key={trayKey}>
                {tray}
              </div>
            ) : null}
          </main>
        </div>

        <div className="kiosk-bezel-bottom">
          <span className="kiosk-grille" aria-hidden />
          <span className="kiosk-plate">VANTAGE</span>
          <span className="kiosk-cardslot" aria-hidden />
        </div>
      </div>
      <div className="kiosk-column" aria-hidden />
      <UiStyles />
      <TotemStyles />
    </div>
  );
}

function TotemStyles() {
  return (
    <style>{`
      .kiosk-room {
        position: fixed;
        inset: 0;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        /* A lit lobby wall meeting a floor: the horizon is what makes the column
           read as standing on something instead of floating. */
        background:
          linear-gradient(180deg, rgba(0,0,0,0) 64%, rgba(0,0,0,0.38) 64.2%, rgba(0,0,0,0.55) 100%),
          radial-gradient(110% 80% at 50% 0%, #6E1822 0%, ${COLOR.brandDeep} 70%);
      }

      .kiosk-machine {
        --screen-h: min(
          calc(100dvh - ${CHASSIS.top} - ${CHASSIS.bottom} - ${CHASSIS.base} - 28px),
          calc((100vw - 48px) * ${CHASSIS.aspect})
        );
        --screen-w: calc(var(--screen-h) / ${CHASSIS.aspect});
        position: relative;
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: ${CHASSIS.top} var(--screen-h) ${CHASSIS.bottom};
        width: calc(var(--screen-w) + ${CHASSIS.sides} * 2);
        padding: 0 ${CHASSIS.sides};
        border-radius: 26px;
        background: linear-gradient(168deg, ${CHASSIS.shellLit} 0%, ${CHASSIS.shell} 46%, ${CHASSIS.shellDark} 100%);
        box-shadow:
          inset 0 1px 0 rgba(255, 255, 255, 0.12),
          inset 0 -1px 0 rgba(0, 0, 0, 0.5),
          0 2px 0 rgba(0, 0, 0, 0.55),
          0 48px 90px rgba(30, 6, 9, 0.6);
      }

      .kiosk-bezel-top { display: flex; align-items: center; justify-content: center; }
      .kiosk-sensor {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #0B0E0D;
        box-shadow:
          0 0 0 3px rgba(0, 0, 0, 0.5),
          0 0 0 4px rgba(255, 255, 255, 0.06),
          inset 0 0 3px rgba(120, 190, 255, 0.5);
      }

      .kiosk-bezel-bottom {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 8px;
      }
      .kiosk-grille {
        width: 110px;
        height: 6px;
        border-radius: 3px;
        background: repeating-linear-gradient(90deg, rgba(0,0,0,0.6) 0 2px, rgba(255,255,255,0.05) 2px 4px);
      }
      .kiosk-plate {
        font-family: "Geist", system-ui, sans-serif;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.42em;
        text-indent: 0.42em;
        color: rgba(243, 115, 33, 0.85);
        text-shadow: 0 1px 0 rgba(0, 0, 0, 0.7), 0 -1px 0 rgba(255, 255, 255, 0.06);
      }
      .kiosk-cardslot {
        width: 78px;
        height: 4px;
        border-radius: 2px;
        background: #0B0E0D;
        box-shadow: inset 0 1px 1px rgba(0,0,0,0.9), 0 1px 0 rgba(255,255,255,0.06);
      }
      .kiosk-column {
        width: 200px;
        height: ${CHASSIS.base};
        margin-top: -2px;
        clip-path: polygon(14% 0, 86% 0, 100% 100%, 0 100%);
        background: linear-gradient(180deg, ${CHASSIS.shell} 0%, ${CHASSIS.shellDark} 100%);
        box-shadow: 0 26px 30px -14px rgba(0, 0, 0, 0.8);
      }

      /* ── The glass ────────────────────────────────────────────────────── */

      .kiosk-screen {
        position: relative;
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        /* Header, Tanvi, then the tray taking everything left — the bottom half and
           more, so the content has the room and nothing floats in empty glass. */
        grid-template-rows: auto auto minmax(0, 1fr);
        min-height: 0;
        overflow: hidden;
        border-radius: 6px;
        /* Warm light falling from the top of the panel: a saffron glow behind
           Tanvi, a maroon wash at the edges, and faint rings radiating from her —
           the one piece of decoration, and it points at the one who is talking. */
        background:
          repeating-radial-gradient(circle at 50% 24%, rgba(142, 30, 42, 0.05) 0 1px, transparent 1px 34px),
          radial-gradient(70% 34% at 50% 24%, rgba(243, 115, 33, 0.22) 0%, rgba(243, 115, 33, 0) 100%),
          radial-gradient(60% 40% at 0% 0%, rgba(142, 30, 42, 0.16) 0%, rgba(142, 30, 42, 0) 100%),
          radial-gradient(60% 40% at 100% 8%, rgba(142, 30, 42, 0.12) 0%, rgba(142, 30, 42, 0) 100%),
          linear-gradient(180deg, #F6E4DF 0%, ${COLOR.paper} 58%);
        color: ${COLOR.ink};
        font-size: ${SIZE.body}px;
        line-height: 1.45;
        box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.5), inset 0 6px 14px rgba(0, 0, 0, 0.22);
      }

      .kiosk-header {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 14px 16px 6px;
      }
      .kiosk-brand { display: flex; align-items: center; gap: 10px; margin-right: auto; min-width: 0; }
      .kiosk-brand-mark {
        width: 26px;
        height: 26px;
        flex: none;
        border-radius: 8px;
        background: ${COLOR.brand};
        box-shadow: inset -9px -9px 0 0 ${COLOR.accent};
      }
      .kiosk-brand-name {
        font-size: 17px;
        font-weight: 700;
        letter-spacing: -0.01em;
        color: ${COLOR.brand};
        white-space: nowrap;
      }
      .kiosk-restart {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex: none;
        width: 44px;
        height: 44px;
        padding: 0;
        border: 1px solid ${COLOR.rule};
        border-radius: 50%;
        background: ${COLOR.surface};
        color: ${COLOR.brand};
        font: inherit;
        font-size: 15px;
        font-weight: 600;
        white-space: nowrap;
        cursor: pointer;
      }
      .kiosk-restart:hover { border-color: ${COLOR.brand}; }
      .kiosk-restart:active { transform: scale(0.98); }
      .kiosk-restart:focus-visible { outline: 3px solid ${COLOR.brand}; outline-offset: 2px; }

      /* Tanvi: top and centre, as large as the tray leaves room for. */
      .kiosk-presence {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        justify-items: center;
        padding: 0 20px;
      }
      /* Capped well short of the row: she leads the conversation, but the glass
         is not a portrait of her, and the space between is what lets it breathe. */
      .kiosk-presence-tile {
        height: calc(var(--screen-h) * 0.34);
        /* The full width of the glass: the character decides how wide she is, and
           a narrower box would crop her shoulders. */
        width: 100%;
        min-height: 0;
        transition: height .45s cubic-bezier(0.16, 1, 0.3, 1);
      }
      /* With the cards up she steps back, so they get the glass. */
      .kiosk-screen.is-heavy .kiosk-presence-tile { height: calc(var(--screen-h) * 0.22); }

      /* The tray: a sheet lifted off the glass, filling the lower half. */
      .kiosk-tray {
        position: relative;
        /* Tucked a few pixels over her: the character is a bust with a straight
           cut, and the counter's edge is what hides it. */
        margin-top: -10px;
        min-height: 0;
        display: flex;
        flex-direction: column;
        border-radius: 28px 28px 0 0;
        background: ${COLOR.surface};
        box-shadow: 0 -1px 0 ${COLOR.rule}, 0 -18px 40px -24px rgba(78, 15, 23, 0.35);
        overflow: hidden;
      }
      /* Only as tall as what she is saying, so a silent moment leaves no band. */
      .kiosk-tray-captions {
        flex: none;
        padding: 16px 20px 0;
        color: ${COLOR.muted};
      }
      .kiosk-tray-body {
        min-height: 0;
        overflow-y: auto;
        padding: 20px 20px 22px;
        overscroll-behavior: contain;
      }
      @media (prefers-reduced-motion: no-preference) {
        .kiosk-tray-body { animation: kiosk-tray-in .42s cubic-bezier(0.16, 1, 0.3, 1) both; }
      }
      @keyframes kiosk-tray-in {
        from { opacity: 0; transform: translateY(14px); }
        to { opacity: 1; transform: none; }
      }

      /* A handset is the device. Drop the chassis and let the glass be the page. */
      @media (max-width: 600px) {
        .kiosk-room { background: ${COLOR.paper}; }
        .kiosk-machine {
          --screen-h: 100dvh;
          --screen-w: 100vw;
          width: 100vw;
          grid-template-rows: 0 100dvh 0;
          padding: 0;
          border-radius: 0;
          box-shadow: none;
          background: none;
        }
        .kiosk-bezel-top, .kiosk-bezel-bottom, .kiosk-column { display: none; }
        /* Pinned to its row: with the top bezel gone it would slide into the first. */
        .kiosk-screen { grid-row: 2; border-radius: 0; box-shadow: none; }
        .kiosk-header { padding: max(12px, env(safe-area-inset-top)) 16px 4px; }
        .kiosk-tray-body { padding-bottom: max(22px, env(safe-area-inset-bottom)); }
      }
    `}</style>
  );
}
