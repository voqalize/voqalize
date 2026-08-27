/**
 * Types for the Sugar Coach demo (`/sugar`).
 *
 * Two surfaces share these: the presenter-facing scenario picker (Screen 1) and
 * the patient's phone (Screen 2). `Scenario.app` is the phone's prefilled state
 * for that day; the brain-facing payload is derived from the same objects in
 * `data.ts` (`buildBrainPayload`) so the screen and the agent can never drift.
 *
 * **The action payloads are not written here.** `actions.gen.ts` is generated
 * from the brain's `Action` classes by `voqalize types`, and every screen type
 * that mirrors one is derived from it below rather than typed out a second
 * time. What the screen adds on top — a list key, an enter-animation flag, the
 * care plan's dosing timing — is the page's own bookkeeping and has no business
 * in the Python.
 */

import type {
  FlagForCareTeam,
  LogActivity,
  LogMeal,
  MarkMedication,
  SetCommitment,
  ShowSummary,
} from './actions.gen';

/** A logged meal, plus what the list needs to render and animate it. */
export type MealEntry = LogMeal & {
  id: string;
  /** True when the agent just logged it — drives the enter animation. */
  fresh?: boolean;
};

export type ActivityEntry = LogActivity & {
  id: string;
  fresh?: boolean;
};

export interface MedPlanItem {
  name: string; // e.g. 'Metformin 500mg'
  timing: string; // e.g. 'morning, after breakfast'
}

/** What the brain can mark, plus the state a dose starts the day in. */
export type MedState = MarkMedication['status'] | 'pending';

/**
 * A row on the meds card. Not `MarkMedication`: the row exists before anyone
 * marks it, carries the plan's `timing`, and may never be marked at all.
 */
export interface MedStatus {
  name: string;
  timing: string;
  status: MedState;
  time_label?: string;
}

/** One CGM reading; `h` is the hour of day as a decimal (13.5 = 1:30 PM). */
export interface GlucosePoint {
  h: number;
  v: number; // mg/dL
}

export interface GlucoseEvent {
  time_label: string; // '2:15 PM'
  h: number;
  v: number;
  note: string;
}

export type SensorStatus = 'active' | 'expired';

export interface GlucoseDay {
  status: SensorStatus;
  expired_since?: string; // 'Thursday' — only when expired
  points: GlucosePoint[];
  events: GlucoseEvent[];
}

export interface Video {
  id: string; // library id the brain uses, e.g. 'desk-stretch'
  youtube_id: string;
  title: string;
  duration: string;
  good_for: string;
}

export interface CarePlan {
  diet: string[];
  exercise: string;
  medications: MedPlanItem[];
  monitoring: string;
}

export interface Patient {
  id: string;
  name: string;
  first_name: string;
  age: number;
  city: string;
  occupation: string;
  program_line: string; // 'Week 1 of the program'
  condition_line: string; // non-clinical one-liner for the picker card
  doctor: string;
  plan: CarePlan;
  /** Card accent hue (H in HSL) so the two patients read apart at a glance. */
  hue: number;
}

export interface PriorCall {
  day: string;
  summary: string;
  commitment?: string;
}

/** Prefilled phone state for the scenario's day. */
export interface AppDay {
  date_label: string; // 'Thursday, 16 July'
  clock_label: string; // '7:02 PM'
  streak_days: number;
  meals: MealEntry[];
  activities: ActivityEntry[];
  meds: MedStatus[];
  glucose: GlucoseDay;
}

export interface Scenario {
  id: string;
  patient_id: string;
  day_label: string; // 'Day 2'
  title: string; // 'The 2 PM spike'
  call_type: string; // onboarding | routine | cgm_review | reengage | momentum | sensor_renewal
  chip: string; // short picker chip, e.g. 'CGM review'
  /** What the agent walks in knowing — shown on the picker cell. */
  context_bullets: string[];
  /** Presenter hints — things to say on the call to hit the demo beats. */
  try_hints: string[];
  /** Extra narrative context for the brain (recent days, travel, mood). */
  recent_days: string[];
  prior_calls: PriorCall[];
  /** TODAY'S CALL OBJECTIVE — the paragraph that steers the whole call. */
  objective: string;
  /** How chatty the coach is by default for this day (presenter can override). */
  talk_mode: TalkMode;
  /**
   * The push-notification body. Doubles as the cue for what the patient should
   * say on joining, so the coach's opener is a natural continuation of it (it
   * also rides the brain payload, so the greeting can pick up where it left off).
   */
  nudge: string;
  app: AppDay;
}

// ── The rest of the live screen ──────────────────────────────────────────────

/**
 * A queued imperative command for the YouTube player (re-fires via `nonce`).
 * Page-internal: three of the brain's actions collapse into it, and the player
 * needs a `nonce` to re-fire a repeat of the same command, which no wire
 * payload carries.
 */
export interface VideoCommand {
  action: 'play' | 'pause' | 'resume';
  youtubeId?: string;
  startSec?: number;
  nonce: number;
}

export type Commitment = SetCommitment;

export type CareFlag = FlagForCareTeam;

export type CallSummary = ShowSummary;

export type SensorOrderState = 'none' | 'offered' | 'ordered';

export type Phase = 'picker' | 'incoming' | 'call' | 'ended';

export type Language = 'English' | 'Hindi';

/**
 * How much the coach leads the conversation:
 *   - `quiet`  — the patient narrates the whole day; the coach logs silently
 *     and interjects minimally (best for routine, familiar days).
 *   - `guided` — the coach walks the patient through beat by beat, one question
 *     at a time (onboarding, a hard restart, anyone who needs a hand).
 * Either way the coach stays to two or three short sentences per turn.
 */
export type TalkMode = 'quiet' | 'guided';
