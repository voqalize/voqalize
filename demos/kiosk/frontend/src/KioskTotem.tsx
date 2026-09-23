/**
 * The screen switch: store state in, one screen's two halves out.
 *
 * Every screen is split across two bands — its **record** on the stage and its
 * **controls** in the lower band — because a totem is reached at waist height
 * and read at eye height. That split is why the mapping lives here rather than
 * inside each screen: one place decides what goes in which band, and the screens
 * stay two plain components each.
 *
 * `Start over` is not in this switch. It is in the lower band on every screen,
 * unconditionally, and the totem itself renders it.
 */

import type { ReactNode } from 'react';
import { Totem } from './Totem';
import { useKiosk, type Screen } from './store';
import type { Language, LanguageName } from './language';
import { AttractControls, AttractStage } from './screens/Attract';
import { CardDetailControls, CardDetailStage } from './screens/CardDetail';
import { ConsentControls, ConsentStage } from './screens/Consent';
import { DiscoveryControls, DiscoveryStage } from './screens/Discovery';
import { EligibilityControls, EligibilityStage } from './screens/Eligibility';
import { HandoffStage } from './screens/Handoff';
import { ShortlistControls, ShortlistStage } from './screens/Shortlist';
import { ValueEntryControls, ValueEntryStage } from './screens/ValueEntry';

export interface KioskTotemProps {
  language: Language;
  onLanguage: (language: LanguageName) => void;
  /** The dock's occupant: the live tile, or the pre-call plate. */
  rohan: ReactNode;
  /** The character artwork's credit line — only where the rig is mounted. */
  credit: ReactNode;
  /** The sentence in flight, for the rail beside the dock. Absent pre-call. */
  captions?: ReactNode;
}

export function KioskTotem({ language, onLanguage, rohan, credit, captions }: KioskTotemProps) {
  const { state, byHand } = useKiosk();

  let stage: ReactNode = null;
  let controls: ReactNode = null;

  switch (state.screen) {
    case 'attract':
      stage = <AttractStage language={language} />;
      controls = <AttractControls language={language} onBegin={byHand.begin} />;
      break;
    case 'discovery':
      stage = (
        <DiscoveryStage
          language={language}
          question={state.question}
          checking={state.checking}
          ledger={state.ledger}
        />
      );
      controls = (
        <DiscoveryControls
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
      stage = <EligibilityStage language={language} eligibility={state.eligibility} />;
      controls = (
        <EligibilityControls language={language} onAcknowledge={byHand.acknowledgeEligibility} />
      );
      break;
    case 'shortlist':
      stage = (
        <ShortlistStage
          language={language}
          shortlist={state.shortlist}
          comparing={state.comparing}
          onTapCard={byHand.tapCard}
          onChooseCard={byHand.chooseCard}
        />
      );
      controls = <ShortlistControls language={language} onCompare={byHand.compare} />;
      break;
    case 'detail':
      stage = (
        <CardDetailStage
          language={language}
          cardId={state.detailCardId}
          shortlist={state.shortlist}
        />
      );
      controls = <CardDetailControls language={language} onBack={byHand.closeDetail} />;
      break;
    case 'consent':
      stage = (
        <ConsentStage language={language} consent={state.consent} shortlist={state.shortlist} />
      );
      controls = (
        <ConsentControls language={language} consent={state.consent} onConsent={byHand.consent} />
      );
      break;
    case 'value':
      stage = (
        <ValueEntryStage
          language={language}
          entry={state.entry}
          checking={state.checking}
          ledger={state.ledger}
        />
      );
      // Keyed by field: moving from the mobile number to the PAN is a new
      // question, so it gets a new, empty, focused input rather than the
      // previous answer with the cursor after it.
      controls = (
        <ValueEntryControls
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
      stage = <HandoffStage language={language} qr={state.qr} />;
      break;
    default:
      unreachableScreen(state.screen);
  }

  return (
    <Totem
      language={language}
      onLanguage={onLanguage}
      conversation={state.conversation}
      rohan={rohan}
      credit={credit}
      captions={captions}
      stage={stage}
      controls={controls}
      onRestart={byHand.restart}
    />
  );
}

/** An eighth screen fails to compile here until it has a case above. */
function unreachableScreen(screen: never): never {
  throw new Error(`Unhandled screen: ${String(screen as Screen)}`);
}
