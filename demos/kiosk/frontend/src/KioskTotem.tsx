/**
 * The screen switch: store state in, one tray out.
 *
 * Tess is on the glass on every screen, so what changes from one step to the
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
import type { Language, LanguageName } from './language';
import { CardDetailTray } from './screens/CardDetail';
import { ConsentTray } from './screens/Consent';
import { DiscoveryTray } from './screens/Discovery';
import { EligibilityTray } from './screens/Eligibility';
import { HandoffTray } from './screens/Handoff';
import { ShortlistTray } from './screens/Shortlist';
import { ValueEntryTray } from './screens/ValueEntry';
import { WelcomeTray } from './screens/Welcome';

export interface KioskTotemProps {
  language: Language;
  onLanguage: (language: LanguageName) => void;
  /** Whether the call is up. Before it, the gate is the only way in. */
  live: boolean;
  /** Tess: the live tile, or the pre-call plate. */
  tess: ReactNode;
  /** The sentence in flight, under her face. Absent pre-call. */
  captions?: ReactNode;
}

export function KioskTotem({ language, onLanguage, live, tess, captions }: KioskTotemProps) {
  const { state, byHand } = useKiosk();

  let tray: ReactNode = null;
  let weight: TrayWeight = 'light';
  // A new key is a new tray, which is what lets it arrive rather than jump. The
  // field is in it because the next question is a new tray on the same screen.
  let key: string = state.screen;

  switch (state.screen) {
    case 'attract':
      // Once the call is up there is nothing to press here: Tess has asked for a
      // name, and the first question comes up by itself if none is given.
      tray = live ? null : <WelcomeTray language={language} />;
      break;
    case 'discovery':
      key = `discovery:${state.question?.field ?? ''}`;
      tray = (
        <DiscoveryTray
          language={language}
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
          language={language}
          eligibility={state.eligibility}
          onAcknowledge={byHand.acknowledgeEligibility}
        />
      );
      break;
    case 'shortlist':
      weight = 'heavy';
      tray = (
        <ShortlistTray
          language={language}
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
          language={language}
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
          language={language}
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
          language={language}
          entry={state.entry}
          checking={state.checking}
          onEnter={byHand.enterValue}
          onConfirm={byHand.confirm}
        />
      );
      break;
    case 'handoff':
      tray = <HandoffTray language={language} qr={state.qr} />;
      break;
    default:
      unreachableScreen(state.screen);
  }
  // A value being read back sits above the answers, and both have to fit.
  if (state.checking) weight = 'heavy';

  return (
    <Totem
      language={language}
      onLanguage={onLanguage}
      conversation={state.conversation}
      tess={tess}
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
