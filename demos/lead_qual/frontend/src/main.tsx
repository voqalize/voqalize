/**
 * Lead-qualification demo entrypoint — Auric Gold Finance gold-loan advisor.
 *
 * A mock lender landing page with an enquiry form that hands off to a voice
 * verification call. The hosted `lead_qual` brain (advisor "Priya") confirms the
 * applicant's details, checks eligibility, and drives the results screen via the
 * `ui-command` / `call_ended` RTVI channel.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { GoldLoanAdvisor } from "./GoldLoanAdvisor";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <GoldLoanAdvisor />
  </StrictMode>,
);
