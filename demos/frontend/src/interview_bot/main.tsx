/**
 * Interview demo entrypoint — the `interview_bot` screening bot.
 *
 * A throwaway test harness: paste the `agent_input` JSON (job + candidate +
 * interview plan) and start a live voice interview. The whole session lifecycle
 * runs through the public SDK's `useVoqalSession`; the brain paces the interview
 * and drives the on-screen section/summary via `ui_command` server-messages.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { InterviewDemo } from "./InterviewDemo";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <InterviewDemo />
  </StrictMode>,
);
