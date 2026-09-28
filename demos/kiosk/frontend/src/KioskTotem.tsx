/**
 * The screen switch: store state in, one tray out.
 *
 * Tanvi is on the glass on every screen, so what changes from one step to the
 * next is only the tray under her — and how much room it needs. That is why the
 * mapping lives here rather than inside each screen: one place decides what a
 * hand can do right now and how heavy it is, and the screens stay one plain
 * component each.
 *
 * `Start over` is not in this switch either. It is in the header, on every
 * screen once the call is up, and the totem itself renders it.
 */

import type { ReactNode } from 'react';
import { Totem, type TrayWeight } from './Totem';
import { useKiosk, type Screen } from './store';
import { CardDetailTray } from './screens/CardDetail';
import { ConsentTray } from './screens/Consent';
import { DiscoveryTray } from './screens/Discovery';
import { EligibilityTray } from './screens/Eligibility';
import { HandoffTray } from './screens/Handoff';
import { ShortlistTray } from './screens/Shortlist';
import { ValueEntryTray } from './screens/ValueEntry';
import { WelcomeTray } from './screens/Welcome';

export interface KioskTotemProps {
  /** Whether the call is up. Before it, the gate is the only way in. */
  live: boolean;
  /** Tanvi: the live tile, or the pre-call plate. */
  tanvi: ReactNode;
  /** The sentence in flight, under her face. Absent pre-call. */
  captions?: ReactNode;
}

export function KioskTotem({ live, tanvi, captions }: KioskTotemProps) {
  const { state, byHand } = useKiosk();

  let tray: ReactNode = null;
  let weight: TrayWeight = 'light';
  // A new key is a new tray, which is what lets it arrive rather than jump. The
  // field is in it because the next question is a new tray on the same screen.
  let key: string = state.screen;

  switch (state.screen) {
    case 'attract':
      // Nothing to press here, before the call or after: Tanvi asks for a name,
      // and the first question comes up by itself if none is given.
      tray = <WelcomeTray />;
      break;
    case 'discovery':
      key = `discovery:${state.question?.field ?? ''}`;
      tray = (
        <DiscoveryTray
          question={state.question}
          checking={state.checking}
          picked={state.picked}
          onAnswer={byHand.answer}
          onConfirm={byHand.confirm}
        />
      );
      break;
    case 'eligibility':
      weight = 'heavy';
      tray = (
        <EligibilityTray
          eligibility={state.eligibility}
          onAcknowledge={byHand.acknowledgeEligibility}
        />
      );
      break;
    case 'shortlist':
      weight = 'heavy';
      tray = (
        <ShortlistTray
          shortlist={state.shortlist}
          onTapCard={byHand.tapCard}
          onChooseCard={byHand.chooseCard}
        />
      );
      break;
    case 'detail':
      weight = 'heavy';
      key = `detail:${state.detailCardId ?? ''}`;
      tray = (
        <CardDetailTray
          cardId={state.detailCardId}
          shortlist={state.shortlist}
          onBack={byHand.closeDetail}
          onChoose={byHand.chooseCard}
        />
      );
      break;
    case 'consent':
      weight = 'heavy';
      tray = (
        <ConsentTray
          consent={state.consent}
          shortlist={state.shortlist}
          onConsent={byHand.consent}
        />
      );
      break;
    case 'value':
      key = `value:${state.entry?.field ?? ''}`;
      // Keyed by field: moving from the mobile number to the PAN is a new
      // question, so it gets a new, empty input rather than the previous answer.
      tray = (
        <ValueEntryTray
          key={state.entry?.field}
          entry={state.entry}
          checking={state.checking}
          onEnter={byHand.enterValue}
          onConfirm={byHand.confirm}
        />
      );
      break;
    case 'handoff':
      tray = <HandoffTray qr={state.qr} />;
      break;
    default:
      unreachableScreen(state.screen);
  }
  // A value being read back sits above the answers, and both have to fit.
  if (state.checking) weight = 'heavy';

  return (
    <Totem
      tanvi={tanvi}
      captions={captions}
      tray={tray}
      trayKey={key}
      weight={weight}
      onRestart={live && state.screen !== 'attract' ? byHand.restart : undefined}
    />
  );
}

/** A ninth screen fails to compile here until it has a case above. */
function unreachableScreen(screen: never): never {
  throw new Error(`Unhandled screen: ${String(screen as Screen)}`);
}
