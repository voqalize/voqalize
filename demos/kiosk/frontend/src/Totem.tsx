/**
 * The totem — the machine, not a page.
 *
 * A branch kiosk is a floor-standing column with the panel recessed behind a
 * bezel, and the demo renders that object rather than a web layout that happens
 * to be portrait. The chrome is not decoration: a customer has to recognise this
 * as a machine they may walk up to and touch, from across a lobby, in one look.
 *
 * The frame is asymmetric because real ones are — hardware lives above and below
 * the glass, never beside it. So the top bezel carries the sensor the kiosk
 * wakes on and the bottom carries the speaker, the card slot and the brand
 * plate. The wordmark is stamped on the machine, not printed on the screen,
 * which is the one place this design spends any boldness.
 *
 * On a phone the chassis is dropped entirely. A handset *is* the device, and
 * drawing a bezel inside a bezel would spend scarce pixels denying it.
 *
 * Inside the glass, three rows:
 *
 *   - **brand bar** — who the customer is talking to, and the language chip.
 *   - **stage** — the record, and the tallest row by a distance. This is the
 *     application; everything else is furniture around it.
 *   - **controls** — every touch target, and Start over is always among them.
 *
 * Rohan sits in a dock in the bottom-right corner, deliberately small. He is
 * helping the customer through the application; he is not the application, and a
 * face at eye height competing with the cards was the wrong hierarchy. The
 * sentence he is speaking runs along a rail beside the dock, where it can be
 * read at a glance and stays legible with the audio off.
 *
 * There is no idle timer. A kiosk that resets while someone is reading has
 * thrown their answers away; Start over is the only reset.
 */

import type { ReactNode } from 'react';
import { CHASSIS, COLOR, SIZE } from './brand';
import { LanguageChip, fontFor, strings, type Language } from './language';
import { TouchButton, UiStyles } from './ui';

export interface TotemProps {
  language: Language;
  onLanguage: (language: Language) => void;
  /** The dock's occupant: the live tile, or the pre-call plate. */
  rohan: ReactNode;
  /** The credit the character artwork's licence requires. */
  credit: ReactNode;
  /** The current screen's record. */
  stage: ReactNode;
  /** The current screen's controls, above the permanent Start over. */
  controls: ReactNode;
  /** The sentence in flight, rendered beside the dock. */
  captions?: ReactNode;
  onRestart: () => void;
}

export function Totem({
  language,
  onLanguage,
  rohan,
  credit,
  stage,
  controls,
  captions,
  onRestart,
}: TotemProps) {
  const copy = strings(language);
  return (
    <div className="kiosk-room">
      <div className="kiosk-machine">
        <div className="kiosk-bezel-top">
          <span className="kiosk-sensor" aria-hidden />
        </div>

        <div className="kiosk-screen" style={{ fontFamily: fontFor(language) }}>
          <header className="kiosk-brand">
            <span className="kiosk-brand-mark" aria-hidden />
            <span className="kiosk-brand-name">
              Vantage Bank
              <span className="kiosk-brand-sub">
                {copy.assistant} · {copy.assistantRole}
              </span>
            </span>
            <LanguageChip value={language} onChange={onLanguage} />
          </header>

          <main className="kiosk-stage">{stage}</main>

          <footer className="kiosk-controls">
            <div className="kiosk-controls-screen">{controls}</div>
            <TouchButton label={copy.restart} tone="quiet" onClick={onRestart} />
          </footer>

          {captions ? <div className="kiosk-caption-rail">{captions}</div> : null}

          <aside className="kiosk-dock">
            {rohan}
            <div className="kiosk-dock-credit">{credit}</div>
          </aside>

          <span className="kiosk-glass" aria-hidden />
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
        /* A lit lobby wall meeting a floor, rather than a gradient for its own
           sake: the horizon is what makes the column read as standing on
           something instead of floating. */
        background:
          linear-gradient(180deg, rgba(0,0,0,0) 62%, rgba(0,0,0,0.42) 62.2%, rgba(0,0,0,0.58) 100%),
          radial-gradient(120% 80% at 50% 0%, #4A1C14 0%, ${COLOR.ink} 72%);
      }

      .kiosk-machine {
        --screen-h: min(calc(100dvh - 215px), calc((100vw - 60px) / 0.75));
        --screen-w: calc(var(--screen-h) * 0.75);
        position: relative;
        display: grid;
        grid-template-rows: ${CHASSIS.top} var(--screen-h) ${CHASSIS.bottom};
        width: calc(var(--screen-w) + ${CHASSIS.sides} * 2);
        padding: 0 ${CHASSIS.sides};
        border-radius: 22px;
        background: linear-gradient(168deg, ${CHASSIS.shellLit} 0%, ${CHASSIS.shell} 46%, ${CHASSIS.shellDark} 100%);
        /* A lip of light along the top edge and a dark one under the bottom:
           two lines doing the work a photograph of a moulded shell would. */
        box-shadow:
          inset 0 1px 0 rgba(255, 255, 255, 0.14),
          inset 0 -1px 0 rgba(0, 0, 0, 0.5),
          0 2px 0 rgba(0, 0, 0, 0.6),
          0 48px 90px rgba(0, 0, 0, 0.62);
      }

      /* Top bezel: the sensor the kiosk wakes on. */
      .kiosk-bezel-top {
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .kiosk-sensor {
        width: 9px;
        height: 9px;
        border-radius: 50%;
        background: #0C0A09;
        box-shadow:
          0 0 0 3px rgba(0, 0, 0, 0.55),
          0 0 0 4px rgba(255, 255, 255, 0.07),
          inset 0 0 3px rgba(120, 190, 255, 0.5);
      }

      /* The glass, recessed behind the bezel. */
      .kiosk-screen {
        position: relative;
        display: grid;
        grid-template-rows: auto 1fr auto;
        min-height: 0;
        overflow: hidden;
        border-radius: 5px;
        background: ${COLOR.paper};
        color: ${COLOR.ink};
        box-shadow:
          inset 0 0 0 1px rgba(0, 0, 0, 0.55),
          inset 0 6px 14px rgba(0, 0, 0, 0.3);
      }

      /* A single diagonal sheen. Kept under 4% — anything a reader can actually
         see is a reader whose contrast you have just spent. */
      .kiosk-glass {
        position: absolute;
        inset: 0;
        pointer-events: none;
        background: linear-gradient(112deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0) 34%);
      }

      /* Bottom bezel: speaker, brand plate, card slot. */
      .kiosk-bezel-bottom {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 9px;
        padding-top: 4px;
      }
      .kiosk-grille {
        width: 124px;
        height: 7px;
        border-radius: 4px;
        background: repeating-linear-gradient(
          90deg,
          rgba(0, 0, 0, 0.62) 0 2px,
          rgba(255, 255, 255, 0.05) 2px 4px
        );
      }
      /* Stamped, not printed: a light top edge and a dark under-edge is all an
         embossed plate is. */
      .kiosk-plate {
        font-family: ${'"Archivo", system-ui, sans-serif'};
        font-size: 15px;
        font-weight: 800;
        letter-spacing: 0.42em;
        text-indent: 0.42em;
        color: rgba(232, 133, 11, 0.9);
        text-shadow: 0 1px 0 rgba(0, 0, 0, 0.7), 0 -1px 0 rgba(255, 255, 255, 0.07);
      }
      .kiosk-cardslot {
        width: 86px;
        height: 4px;
        border-radius: 2px;
        background: #0C0A09;
        box-shadow: inset 0 1px 1px rgba(0,0,0,0.9), 0 1px 0 rgba(255,255,255,0.07);
      }

      /* The plinth. Tapered, because a column that meets the floor at full width
         reads as a box rather than as furniture. */
      .kiosk-column {
        width: calc(var(--col-w, 220px));
        height: ${CHASSIS.base};
        margin-top: -2px;
        clip-path: polygon(14% 0, 86% 0, 100% 100%, 0 100%);
        background: linear-gradient(180deg, ${CHASSIS.shell} 0%, ${CHASSIS.shellDark} 100%);
        box-shadow: 0 26px 30px -14px rgba(0, 0, 0, 0.8);
      }

      /* ── Inside the glass ─────────────────────────────────────────────── */

      .kiosk-brand {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 14px 24px;
        background: ${COLOR.umber};
        color: ${COLOR.paper};
      }
      .kiosk-brand-mark {
        width: 30px;
        height: 30px;
        flex: none;
        border-radius: 8px;
        background: ${COLOR.amber};
        clip-path: polygon(0 0, 100% 0, 50% 100%);
      }
      .kiosk-brand-name {
        display: flex;
        flex-direction: column;
        margin-right: auto;
        font-size: 20px;
        font-weight: 800;
        letter-spacing: -0.01em;
      }
      .kiosk-brand-sub {
        font-size: 13px;
        font-weight: 500;
        color: rgba(251, 247, 242, 0.62);
      }

      /* The stage is the application, so it takes the height. The right gutter
         keeps the record clear of the dock. */
      .kiosk-stage {
        min-height: 0;
        display: flex;
        flex-direction: column;
        padding: 24px calc(${SIZE.dock}px + 40px) 24px 24px;
        overflow-y: auto;
        font-size: ${SIZE.body}px;
        line-height: 1.5;
      }

      .kiosk-controls {
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
        gap: 12px;
        padding: 16px 24px 20px;
        border-top: 1px solid ${COLOR.rule};
        background: #F3EDE5;
      }
      .kiosk-controls-screen {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-content: flex-end;
      }
      .kiosk-controls-screen:empty { display: none; }
      .kiosk-controls .kiosk-btn.is-quiet { align-self: flex-start; }

      /* Rohan's dock: small, cornered, out of the reading path. */
      .kiosk-dock {
        position: absolute;
        right: 18px;
        bottom: 96px;
        width: ${SIZE.dock}px;
        display: flex;
        flex-direction: column;
        gap: 5px;
        pointer-events: none;
      }
      .kiosk-dock > :first-child {
        height: calc(${SIZE.dock}px * 0.78);
        border-radius: 14px;
        overflow: hidden;
        background: ${COLOR.umber};
        box-shadow: 0 10px 26px rgba(23, 19, 16, 0.34), 0 0 0 1px rgba(23, 19, 16, 0.14);
      }
      .kiosk-dock-credit { padding-right: 2px; }

      /* The sentence in flight, beside the dock rather than over the face. */
      .kiosk-caption-rail {
        position: absolute;
        left: 24px;
        right: calc(${SIZE.dock}px + 40px);
        bottom: 102px;
        display: flex;
        pointer-events: none;
      }

      /* A handset is the device. Drop the chassis and let the glass be the page. */
      @media (max-width: 600px) {
        .kiosk-room { background: ${COLOR.ink}; }
        .kiosk-machine {
          --screen-h: 100dvh;
          --screen-w: 100vw;
          width: 100vw;
          grid-template-rows: 0 100dvh 0;
          padding: 0;
          border-radius: 0;
          box-shadow: none;
        }
        .kiosk-bezel-top, .kiosk-bezel-bottom, .kiosk-column, .kiosk-glass { display: none; }
        .kiosk-screen { border-radius: 0; box-shadow: none; }
      }
    `}</style>
  );
}
