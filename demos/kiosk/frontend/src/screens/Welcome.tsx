/**
 * The first screen, before the call.
 *
 * **One way in, and it is the Start button.** The gate in front of the kiosk is
 * that button: pressing it opens the call, and Tanvi's greeting is the first
 * thing that happens after it. Nothing here offers a second way to begin, so a
 * customer never has to work out whether to speak or to tap.
 *
 * So this tray only says what the kiosk is for, behind the gate and while Tanvi
 * asks for a name. There is nothing to press: if no name comes, the first
 * question's answers come up by themselves.
 */

import { Cards, ChatCircleDots, QrCode } from '@phosphor-icons/react';
import { COLOR, SIZE } from '../brand';
import { strings, type Language } from '../language';
import { TrayTitle } from '../ui';

const ICONS = [ChatCircleDots, Cards, QrCode] as const;

export function WelcomeTray({ language }: { language: Language }) {
  const copy = strings(language);
  return (
    <div className="kiosk-welcome">
      <TrayTitle>{copy.attractTitle}</TrayTitle>
      <p className="kiosk-welcome-body">{copy.attractBody}</p>
      <ol className="kiosk-welcome-steps">
        {copy.steps.map((step, at) => {
          const Icon = ICONS[at];
          return (
            <li key={step}>
              <span className="kiosk-welcome-icon" aria-hidden>
                <Icon size={22} weight="duotone" />
              </span>
              {step}
            </li>
          );
        })}
      </ol>
      <style>{`
        .kiosk-welcome-body { margin: 0 0 18px; max-width: 34ch; font-size: 17px; color: ${COLOR.muted}; }
        .kiosk-welcome-steps { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
        .kiosk-welcome-steps li {
          display: flex; align-items: center; gap: 14px;
          padding: 12px 14px;
          border-radius: ${SIZE.radius}px;
          background: rgba(142, 30, 42, 0.05);
          font-size: 17px; font-weight: 500;
        }
        .kiosk-welcome-icon {
          display: inline-flex; align-items: center; justify-content: center; flex: none;
          width: 40px; height: 40px; border-radius: 12px;
          background: ${COLOR.brand}; color: ${COLOR.surface};
        }
      `}</style>
    </div>
  );
}
