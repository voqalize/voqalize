/**
 * Scenario data for the Sugar Coach demo — 2 patients × 3 days.
 *
 * This file is the demo's script. Each scenario is one evening check-in call:
 * the phone's prefilled state (`app`) and the story the agent walks in with
 * (`objective`, `recent_days`, `prior_calls`) are authored together so the
 * screen and the conversation always agree. `buildBrainPayload` folds a
 * scenario + its patient into the single JSON object that rides the session
 * payload to the `sugar` brain (PATIENT CONTEXT).
 *
 * The arcs:
 *   Meera  — new to the program: onboarding → the 2 PM spike → momentum.
 *   Rajesh — month eight, slipping: routine → re-engagement → sensor renewal.
 */

import type {
  AppDay,
  GlucosePoint,
  Language,
  Patient,
  Scenario,
  TalkMode,
  Video,
} from './types';

export const PROGRAM_NAME = 'Sugar';
export const COACH_NAME = 'Sugar Coach';

// ── Video library (real, embeddable YouTube videos) ──────────────────────────

export const VIDEOS: Video[] = [
  {
    id: 'desk-stretch',
    youtube_id: 'vRQdJQ3Xhzk',
    title: '10-Minute Desk Stretches',
    duration: '10 min',
    good_for:
      'no exercise logged today; patient is stuck at a desk, in a hotel, or travelling — do it right now on the call',
  },
  {
    id: 'breathing',
    youtube_id: 'enJyOTvEn4M',
    title: '5-Minute Guided Breathing',
    duration: '5 min',
    good_for: 'patient sounds stressed or wound up; winding down in the evening',
  },
];

export function videoById(id: string | undefined): Video | undefined {
  return VIDEOS.find((v) => v.id === id || v.youtube_id === id);
}

// ── Patients ─────────────────────────────────────────────────────────────────

export const PATIENTS: Patient[] = [
  {
    id: 'meera',
    name: 'Meera Iyer',
    first_name: 'Meera',
    age: 42,
    city: 'Bengaluru',
    occupation: 'Product manager',
    program_line: 'Week 1 of the program',
    condition_line: 'Type 2, diagnosed six weeks ago — motivated but overwhelmed',
    doctor: 'Dr. Rao',
    hue: 165,
    plan: {
      diet: [
        'Swap white rice for millets at lunch',
        'No sugar in tea or coffee',
        'Early dinner, before 8 PM',
        'One seasonal fruit mid-morning, never with meals',
      ],
      exercise: '30-minute walk daily — evenings work best for her schedule',
      medications: [
        { name: 'Metformin 500mg', timing: 'morning, after breakfast' },
        { name: 'Metformin 500mg', timing: 'night, after dinner' },
      ],
      monitoring: '14-day CGM sensor; monthly review with Dr. Rao',
    },
  },
  {
    id: 'rajesh',
    name: 'Rajesh Nair',
    first_name: 'Rajesh',
    age: 55,
    city: 'Chennai',
    occupation: 'Regional sales manager — travels most weeks',
    program_line: 'Month 8 of the program',
    condition_line: 'Type 2 for nine years — early wins, now plateauing',
    doctor: 'Dr. Mehta',
    hue: 215,
    plan: {
      diet: [
        'Two rotis instead of three at dinner',
        'No fried snacks with evening tea',
        'Prefer grilled over fried when eating out',
        'Last meal by 9 PM',
      ],
      exercise: '40-minute morning walk, five days a week',
      medications: [
        { name: 'Glimepiride 1mg', timing: 'morning, before breakfast' },
        { name: 'Metformin 850mg', timing: 'night, after dinner' },
      ],
      monitoring: '14-day CGM sensor; quarterly review with Dr. Mehta',
    },
  },
];

export function patientById(id: string): Patient {
  const p = PATIENTS.find((x) => x.id === id);
  if (!p) throw new Error(`unknown patient ${id}`);
  return p;
}

// ── Glucose curves (hand-authored, mg/dL, hours as decimals) ─────────────────

/** A calm in-range day: gentle meal rises, nothing notable. */
const CALM_DAY: GlucosePoint[] = [
  { h: 6, v: 102 }, { h: 7, v: 98 }, { h: 8, v: 110 }, { h: 8.5, v: 132 },
  { h: 9, v: 148 }, { h: 10, v: 126 }, { h: 11, v: 112 }, { h: 12, v: 108 },
  { h: 13, v: 122 }, { h: 13.5, v: 150 }, { h: 14, v: 162 }, { h: 15, v: 138 },
  { h: 16, v: 120 }, { h: 17, v: 112 }, { h: 18, v: 108 }, { h: 19, v: 104 },
];

/** Meera day 2 — the demo's spike: lunch at 1:30, peak 214 at 2:15. */
const SPIKE_DAY: GlucosePoint[] = [
  { h: 6, v: 104 }, { h: 7, v: 100 }, { h: 8, v: 108 }, { h: 8.5, v: 128 },
  { h: 9, v: 146 }, { h: 9.5, v: 152 }, { h: 10.5, v: 124 }, { h: 11.5, v: 112 },
  { h: 12.5, v: 110 }, { h: 13.5, v: 146 }, { h: 14, v: 196 }, { h: 14.25, v: 214 },
  { h: 14.75, v: 202 }, { h: 15.5, v: 168 }, { h: 16.5, v: 134 }, { h: 17.5, v: 118 },
  { h: 18.5, v: 112 }, { h: 19, v: 110 },
];

/** Meera day 3 — steadier: millet lunch, peak only 158. */
const STEADIER_DAY: GlucosePoint[] = [
  { h: 6, v: 100 }, { h: 7, v: 96 }, { h: 8, v: 106 }, { h: 8.5, v: 124 },
  { h: 9, v: 138 }, { h: 10, v: 118 }, { h: 11, v: 108 }, { h: 12, v: 104 },
  { h: 13, v: 116 }, { h: 13.5, v: 142 }, { h: 14, v: 158 }, { h: 15, v: 136 },
  { h: 16, v: 118 }, { h: 17, v: 110 }, { h: 18, v: 106 }, { h: 19, v: 102 },
];

/** Meera day 1 — sensor fitted after lunch; only a few hours of data. */
const FRESH_SENSOR_DAY: GlucosePoint[] = [
  { h: 14, v: 128 }, { h: 15, v: 122 }, { h: 16, v: 116 }, { h: 17, v: 112 },
  { h: 18, v: 108 }, { h: 19, v: 106 },
];

/** Rajesh day 2 — a bumpy unmanaged travel day. */
const BUMPY_DAY: GlucosePoint[] = [
  { h: 6, v: 118 }, { h: 7, v: 114 }, { h: 8, v: 122 }, { h: 9, v: 158 },
  { h: 10, v: 144 }, { h: 11, v: 130 }, { h: 12, v: 126 }, { h: 13, v: 148 },
  { h: 14, v: 190 }, { h: 15, v: 176 }, { h: 16, v: 150 }, { h: 17, v: 154 },
  { h: 18, v: 146 }, { h: 19, v: 138 },
];

// ── Scenarios ────────────────────────────────────────────────────────────────

function day(app: Partial<AppDay> & Pick<AppDay, 'date_label' | 'glucose' | 'meds'>): AppDay {
  return {
    clock_label: '7:02 PM',
    streak_days: 0,
    meals: [],
    activities: [],
    ...app,
  };
}

export const SCENARIOS: Scenario[] = [
  // ── Meera ──────────────────────────────────────────────────────────────────
  {
    id: 'meera-d1',
    patient_id: 'meera',
    day_label: 'Day 1',
    title: 'The first call',
    call_type: 'onboarding',
    chip: 'Onboarding',
    talk_mode: 'guided', // new patient — walk her through it
    nudge: "Welcome to Sugar, Meera. Tap to join your first evening check-in — I'll walk you through your plan, just two minutes.",

    context_bullets: [
      'Enrolled this week — diagnosed six weeks ago',
      'CGM fitted today; first readings just coming in',
      'Nothing logged yet; care plan set by Dr. Rao',
      'Goal: welcome her, walk the plan, one starter commitment',
    ],
    try_hints: [
      'Ask "what exactly is this call every day?"',
      'Tell her what you had for dinner — watch it get logged',
      'Ask "when do I take the tablets?" — she gets the plan, not advice',
    ],
    recent_days: [
      'Enrolled three days ago after her diagnosis six weeks back; first consult with Dr. Rao completed and the care plan is set.',
      'CGM sensor fitted at the clinic this afternoon — readings started around 2 PM.',
      'Has not used the app to log anything yet; she is new to all of it and a little overwhelmed.',
    ],
    prior_calls: [],
    objective:
      "FIRST-EVER CALL (onboarding). Welcome Meera to her daily check-ins: every evening around seven, two to three minutes. Walk through the care plan Dr. Rao set — highlight the plan on screen and touch diet, the evening walk, and the two Metformin doses (confirm she knows the timings; if she asks anything beyond timing, that's for Dr. Rao). Explain the sensor in one line: it just reports her glucose curve, and you two will look at it together each evening. If she has eaten dinner, log it by voice as a first taste of how logging works. Close by setting ONE small starter commitment — the evening walk is the natural one — and tell her you'll call tomorrow at the same time.",
    app: day({
      date_label: 'Wednesday, 15 July',
      streak_days: 0,
      meds: [
        { name: 'Metformin 500mg', timing: 'morning, after breakfast', status: 'pending' },
        { name: 'Metformin 500mg', timing: 'night, after dinner', status: 'pending' },
      ],
      glucose: { status: 'active', points: FRESH_SENSOR_DAY, events: [] },
    }),
  },
  {
    id: 'meera-d2',
    patient_id: 'meera',
    day_label: 'Day 2',
    title: 'The 2 PM spike',
    call_type: 'cgm_review',
    chip: 'CGM review',
    talk_mode: 'guided', // an investigative thread to lead — the 2 PM spike
    nudge: "Evening, Meera. Tap to join — tell me what you ate today and let's look at your day together.",

    context_bullets: [
      'Breakfast logged; lunch and dinner missing',
      'Sensor caught a rise to 214 at 2:15 PM',
      'Yesterday she committed to an evening walk',
      'Goal: fill the gaps, ask about the spike, check the walk',
    ],
    try_hints: [
      'Say you had curd rice and papad around 1:30 — watch the chart connect',
      'Admit you skipped the walk — no guilt, just a smaller ask',
      'Ask "is 214 dangerous?" — watch it flag to Dr. Rao',
    ],
    recent_days: [
      'Yesterday was her onboarding call; she was warm but nervous, and committed to a fifteen-minute walk after dinner.',
      'Today she logged breakfast in the app herself (poha and filter coffee) — a good first step worth a word of credit.',
      'Lunch and dinner are not logged, and the sensor shows a clear rise after lunch.',
    ],
    prior_calls: [
      {
        day: 'Yesterday (Day 1)',
        summary:
          'Onboarding call. Walked through Dr. Rao\'s plan; she knows her med timings. She was worried about "doing it all correctly" — reassure, keep asks small.',
        commitment: 'Fifteen-minute walk after dinner',
      },
    ],
    objective:
      "CGM REVIEW. Two threads today. One: lunch is unlogged and the sensor shows a rise to 214 around 2:15 PM — show the chart zoomed to that moment BEFORE asking, then ask the curious question: what did she have around then? Log it as she answers. If white rice features, connect it observationally to the plan's millet swap — the plan already says it; you're just pointing at it, never scolding. Two: yesterday's commitment was a fifteen-minute evening walk — ask how it went, log it if it happened, and if it didn't, shrink the ask (even ten minutes tonight counts). Confirm the morning Metformin and remind about the night dose. Give her genuine credit for logging breakfast on her own. Close with one commitment.",
    app: day({
      date_label: 'Thursday, 16 July',
      streak_days: 1,
      meals: [
        {
          id: 'm1',
          meal_type: 'breakfast',
          time_label: '8:30 AM',
          items: [
            { name: 'Poha', quantity: '1 plate', calories: 250 },
            { name: 'Filter coffee (no sugar)', quantity: '1 cup', calories: 40 },
          ],
          total_calories: 290,
        },
      ],
      meds: [
        { name: 'Metformin 500mg', timing: 'morning, after breakfast', status: 'taken', time_label: '9:00 AM' },
        { name: 'Metformin 500mg', timing: 'night, after dinner', status: 'pending' },
      ],
      glucose: {
        status: 'active',
        points: SPIKE_DAY,
        events: [{ time_label: '2:15 PM', h: 14.25, v: 214, note: 'Rise after lunch' }],
      },
    }),
  },
  {
    id: 'meera-d3',
    patient_id: 'meera',
    day_label: 'Day 3',
    title: 'Momentum',
    call_type: 'momentum',
    chip: 'Momentum',
    talk_mode: 'quiet', // she's in a groove — let her run
    nudge: "Evening, Meera. Tap to join and walk me through your day — I'll note it all down.",

    context_bullets: [
      'Two-day logging streak; millet lunch today',
      'Walked 20 minutes yesterday — commitment kept',
      'Post-lunch peak only 158 today (was 214 yesterday)',
      'Goal: reinforce the streak, keep the habit compounding',
    ],
    try_hints: [
      'Ask "should I double my Metformin since it\'s working?" — hard line, flagged',
      'Sound tired — she may get offered the breathing video',
    ],
    recent_days: [
      'Yesterday she swapped to a millet bowl at lunch after the 2 PM spike conversation, and did a twenty-minute walk after dinner — commitment kept.',
      'Today she logged breakfast and lunch herself; the post-lunch rise stayed under 160.',
      'She is feeling the first win. The risk now is overcorrection — wanting to change too much at once.',
    ],
    prior_calls: [
      {
        day: 'Two days ago (Day 1)',
        summary: 'Onboarding call. Plan walked through; med timings confirmed.',
        commitment: 'Fifteen-minute walk after dinner',
      },
      {
        day: 'Yesterday (Day 2)',
        summary:
          'Reviewed the 2:15 PM rise to 214; lunch had been curd rice. She took the millet-swap idea from the plan well and walked twenty minutes after dinner.',
        commitment: 'Millet lunch and a walk again today',
      },
    ],
    objective:
      "MOMENTUM CALL — light and warm. She kept both commitments: millet lunch (peak stayed near 158 — show the chart and let the difference speak, observationally) and the walk two evenings running. Name the streak; small wins compound. Check dinner plans and log anything she ate. Confirm meds. Watch for overcorrection — if she starts proposing changes to medication or big diet cuts, that's Dr. Rao territory: flag it warmly. If she sounds wound up about work, the five-minute breathing video is in the library. Close with the same simple commitment — the streak IS the story today.",
    app: day({
      date_label: 'Friday, 17 July',
      streak_days: 2,
      meals: [
        {
          id: 'm1',
          meal_type: 'breakfast',
          time_label: '8:15 AM',
          items: [
            { name: 'Ragi dosa', quantity: '2', calories: 240 },
            { name: 'Coconut chutney', quantity: '2 tbsp', calories: 70 },
          ],
          total_calories: 310,
        },
        {
          id: 'm2',
          meal_type: 'lunch',
          time_label: '1:15 PM',
          items: [
            { name: 'Millet bowl with vegetables', quantity: '1 bowl', calories: 380 },
            { name: 'Curd', quantity: '1 katori', calories: 90 },
          ],
          total_calories: 470,
        },
      ],
      activities: [
        { id: 'a1', kind: 'Walk', duration_min: 20, time_label: 'Yesterday, 8:40 PM', note: 'After dinner' },
      ],
      meds: [
        { name: 'Metformin 500mg', timing: 'morning, after breakfast', status: 'taken', time_label: '8:45 AM' },
        { name: 'Metformin 500mg', timing: 'night, after dinner', status: 'pending' },
      ],
      glucose: {
        status: 'active',
        points: STEADIER_DAY,
        events: [{ time_label: '2:00 PM', h: 14, v: 158, note: 'Millet lunch — gentler rise' }],
      },
    }),
  },

  // ── Rajesh ─────────────────────────────────────────────────────────────────
  {
    id: 'rajesh-d1',
    patient_id: 'rajesh',
    day_label: 'Day 1',
    title: 'Routine check-in',
    call_type: 'routine',
    chip: 'Routine',
    talk_mode: 'quiet', // twelve-day streak — the "note it down as I talk" call
    nudge: "Evening check-in, Rajesh. Tap to join and talk me through your day — meals, movement, all of it.",

    context_bullets: [
      'Twelve-day logging streak; two meals already in',
      'Morning walk done; night med still pending',
      'Yesterday\'s commitment: skip the fried tea snacks',
      'Goal: the two-minute daily loop, smooth and familiar',
    ],
    try_hints: [
      'Describe dinner in one breath — "two rotis, bhindi, dal, salad"',
      'Confess to one samosa at tea — watch the honest log',
    ],
    recent_days: [
      'A steady week at the Chennai office — walked four of the last five mornings, logging daily without prompting.',
      'Yesterday evening he admitted the office tea comes with fried snacks; he committed to skipping them today.',
      'Today breakfast and lunch are logged, the morning walk is in, and dinner is the only gap.',
    ],
    prior_calls: [
      {
        day: 'Yesterday',
        summary:
          'Routine check-in. Full day logged; the one wobble is fried snacks at office tea, most days around 5 PM.',
        commitment: 'Skip the fried snacks at tea today',
      },
    ],
    objective:
      'ROUTINE EVENING CHECK-IN — the familiar two-minute loop with a twelve-day streak behind it. Ask about dinner (eaten or planned) and log it. Ask how the tea-time commitment went — if he skipped the snacks, that is the win of the day; if he slipped, log it honestly and move on without a lecture. The walk is already in; a word of credit. Remind about the night Metformin with dinner. The sensor shows a moderate rise after the canteen lunch — worth one curious glance at the chart, nothing more. Close with a small commitment for tomorrow.',
    app: day({
      date_label: 'Monday, 13 July',
      streak_days: 12,
      meals: [
        {
          id: 'm1',
          meal_type: 'breakfast',
          time_label: '7:45 AM',
          items: [
            { name: 'Idli', quantity: '3', calories: 180 },
            { name: 'Sambar', quantity: '1 katori', calories: 120 },
          ],
          total_calories: 300,
        },
        {
          id: 'm2',
          meal_type: 'lunch',
          time_label: '1:00 PM',
          items: [
            { name: 'Office canteen thali', quantity: '1', calories: 620 },
          ],
          total_calories: 620,
          note: 'Rice, sambar, two vegetables, curd',
        },
      ],
      activities: [
        { id: 'a1', kind: 'Walk', duration_min: 40, time_label: '6:20 AM', note: 'Marina loop' },
      ],
      meds: [
        { name: 'Glimepiride 1mg', timing: 'morning, before breakfast', status: 'taken', time_label: '7:30 AM' },
        { name: 'Metformin 850mg', timing: 'night, after dinner', status: 'pending' },
      ],
      glucose: {
        status: 'active',
        points: CALM_DAY,
        events: [{ time_label: '2:00 PM', h: 14, v: 162, note: 'After canteen lunch' }],
      },
    }),
  },
  {
    id: 'rajesh-d2',
    patient_id: 'rajesh',
    day_label: 'Day 2',
    title: 'The travel slump',
    call_type: 'reengage',
    chip: 'Re-engagement',
    talk_mode: 'guided', // a slump to rebuild gently, step by step
    nudge: "Evening, Rajesh. Busy few days on the road? Tap to join — two minutes, let's pick up where we left off.",

    context_bullets: [
      'No food logged for two days; streak broken',
      'Last exercise three days ago; meds unconfirmed',
      'On the road in Coimbatore — hotel evenings',
      'Goal: zero guilt, log today by voice, one tiny restart',
    ],
    try_hints: [
      'Say you\'re in a hotel and skipped everything — no lecture comes',
      'Accept the stretch video — it plays right on the call',
      'Recall lunch vaguely ("some biryani thing") — watch it still log',
    ],
    recent_days: [
      'A client-visit week in Coimbatore since Tuesday — long days, hotel dinners, no logging for two days and the streak reset.',
      'Last recorded exercise was Monday\'s morning walk, three days ago.',
      'Both medications are unconfirmed for two days. The sensor shows a bumpier picture today with a rise to 190 after lunch.',
      'History says travel weeks are where his months of progress leak away — and where a two-minute call earns its keep.',
    ],
    prior_calls: [
      {
        day: 'Monday',
        summary:
          'Routine check-in before travel. Solid day; he mentioned the Coimbatore trip and predicted, half-joking, that the week would go off the rails.',
        commitment: 'Try to keep the morning walk on the road',
      },
    ],
    objective:
      "RE-ENGAGEMENT — no guilt, no lecture. He predicted this slump himself on Monday; open with that, lightly — travel weeks are hard, that's why you call. Rebuild today from his memory: lunch, dinner plans, anything at tea — log each as he talks; vague answers are fine, estimate and move on. Confirm meds for today (missed doses are noted for the record, never judged — if he asks whether to double up or make up a missed dose, that is Dr. Mehta's call: flag it). The restart ask is TINY: he can't walk Marina from a hotel, but the ten-minute desk-stretch video works in a hotel room — offer to play it right now on the call. If he takes it, let it run and stay quiet; log the activity after. The sensor's bumpy day (190 after lunch) gets one curious glance, no more — today is about restarting the habit, not the chart. Close with one small commitment for tomorrow morning.",
    app: day({
      date_label: 'Thursday, 16 July',
      streak_days: 0,
      meds: [
        { name: 'Glimepiride 1mg', timing: 'morning, before breakfast', status: 'pending' },
        { name: 'Metformin 850mg', timing: 'night, after dinner', status: 'pending' },
      ],
      glucose: {
        status: 'active',
        points: BUMPY_DAY,
        events: [{ time_label: '2:00 PM', h: 14, v: 190, note: 'Rise after lunch' }],
      },
    }),
  },
  {
    id: 'rajesh-d3',
    patient_id: 'rajesh',
    day_label: 'Day 3',
    title: 'The dark chart',
    call_type: 'sensor_renewal',
    chip: 'Sensor renewal',
    talk_mode: 'guided', // a specific job to steer — the sensor renewal
    nudge: "Evening, Rajesh. Back on track and it shows — tap to join and let's wrap up the day.",

    context_bullets: [
      'Back on track: meals logged, stretches two days running',
      'CGM sensor expired Thursday — no glucose data since',
      'The chart he rebuilt his habit for is dark',
      'Goal: celebrate the restart, renew the sensor in-call',
    ],
    try_hints: [
      'Say "yes, order it" — or tap the card yourself and watch the coach notice',
      'Ask what the new sensor reads differently — plan facts only',
    ],
    recent_days: [
      'Back home from Coimbatore since Friday night. The restart held: desk stretches on Thursday and Friday, meals logged both days.',
      'Today breakfast and lunch are logged and both medications are confirmed.',
      'The CGM sensor expired on Thursday — there has been no glucose data for three days, so his recovery is invisible on the chart.',
      'A replacement sensor ships next-day; the renewal card is ready to show in the app.',
    ],
    prior_calls: [
      {
        day: 'Thursday',
        summary:
          'Re-engagement call from the Coimbatore hotel. He did the ten-minute desk-stretch video live on the call — the restart moment.',
        commitment: 'Ten minutes of stretches before dinner, again tomorrow',
      },
      {
        day: 'Friday',
        summary: 'Quick check-in from the train home. Stretches done second day running; dinner logged from the station.',
        commitment: 'Log the weekend meals, back to the Marina walk Monday',
      },
    ],
    objective:
      "SENSOR RENEWAL, wrapped in a recovery celebration. Open with the streak that matters: stretches two days running, meals logged since Thursday — the travel slump is over and he did that. Then the catch: his sensor expired Thursday, so the very chart that would SHOW the recovery has been dark for three days — show the glucose section so he sees the gap. You miss the data that makes these calls useful. Offer the replacement: show_sensor_renewal puts the card on screen; he can say yes (confirm_sensor_order) or tap it himself — either way acknowledge it and mention it ships next-day. If he declines, drop it without a second push. Then the routine: dinner plans, log what he ate, night Metformin reminder. Close with Monday's Marina-walk commitment from Friday's call.",
    app: day({
      date_label: 'Sunday, 19 July',
      streak_days: 2,
      meals: [
        {
          id: 'm1',
          meal_type: 'breakfast',
          time_label: '8:00 AM',
          items: [
            { name: 'Upma', quantity: '1 plate', calories: 280 },
            { name: 'Filter coffee (no sugar)', quantity: '1 cup', calories: 40 },
          ],
          total_calories: 320,
        },
        {
          id: 'm2',
          meal_type: 'lunch',
          time_label: '1:30 PM',
          items: [
            { name: 'Grilled fish', quantity: '1 piece', calories: 220 },
            { name: 'Roti', quantity: '2', calories: 180 },
            { name: 'Vegetable salad', quantity: '1 bowl', calories: 80 },
          ],
          total_calories: 480,
        },
      ],
      activities: [
        { id: 'a1', kind: 'Desk stretches', duration_min: 10, time_label: 'Yesterday, 6:30 PM', note: 'Second day running' },
      ],
      meds: [
        { name: 'Glimepiride 1mg', timing: 'morning, before breakfast', status: 'taken', time_label: '7:40 AM' },
        { name: 'Metformin 850mg', timing: 'night, after dinner', status: 'pending' },
      ],
      glucose: {
        status: 'expired',
        expired_since: 'Thursday',
        points: [],
        events: [],
      },
    }),
  },
];

export function scenariosFor(patientId: string): Scenario[] {
  return SCENARIOS.filter((s) => s.patient_id === patientId);
}

export function scenarioById(id: string): Scenario {
  const s = SCENARIOS.find((x) => x.id === id);
  if (!s) throw new Error(`unknown scenario ${id}`);
  return s;
}

// ── Brain payload (PATIENT CONTEXT) ──────────────────────────────────────────

/**
 * The wire half of the patient's language choice.
 *
 * The same toggle feeds two things, and they are read by different layers.
 * `buildBrainPayload` puts `language` in `init`, which tells the coach what to
 * *say* — which greeting line, which language the PATIENT CONTEXT names. This
 * puts it in `config`, which tells the runtime how to *speak* it: the
 * recognizer to listen with, and the voice-cloning reference clip to read with.
 *
 * Both legs, always, in one object. `stt.language` alone leaves the coach read
 * by an English clip — the words right on paper and foreign-accented in the
 * ear, which no transcript, log or metric can see. It shipped that way on
 * `/demos/orderdesk` once.
 *
 * It rides the connect request rather than a `session.configure` from the brain
 * because the page knows the answer first: the patient chose it before the call
 * existed. So the session opens in it, and the greeting — the one utterance
 * nobody gets to re-run — is synthesized in the right voice with no round trip
 * to have ordered correctly. What the brain still owns is a change of mind
 * mid-call, which is what its `switch_language` tool is for.
 *
 * Enums spell by value name: that is proto3's JSON mapping, not our choice.
 */
export function buildSessionConfig(language: Language) {
  const code = language === 'Hindi' ? 'LANGUAGE_HI' : 'LANGUAGE_EN';
  return {
    tts: { language: code, voice: 'VOICE_OMNIVOICE_GAURI' },
    stt: { language: code },
  };
}

/**
 * Fold a scenario into the single object the `sugar` brain receives as
 * PATIENT CONTEXT. Everything the agent "knows" is here — the pitch is that
 * this is what a real integration would assemble from the customer's backend.
 */
export function buildBrainPayload(
  scenario: Scenario,
  language: Language,
  talkMode: TalkMode = scenario.talk_mode,
) {
  const p = patientById(scenario.patient_id);
  const g = scenario.app.glucose;
  return {
    language,
    scenario: {
      call_type: scenario.call_type,
      talk_mode: talkMode,
      // The nudge the patient just tapped Join on — the coach's opener continues from it.
      joined_from_nudge: scenario.nudge,
      patient: {
        name: p.name,
        age: p.age,
        city: p.city,
        occupation: p.occupation,
        program: `${PROGRAM_NAME} diabetes-care program, ${p.program_line.toLowerCase()}`,
      },
      care_team: { doctor: p.doctor },
      care_plan: p.plan,
      today: {
        date: scenario.app.date_label,
        time: `${scenario.app.clock_label} — the scheduled evening check-in`,
        logging_streak_days: scenario.app.streak_days,
        logged_meals: scenario.app.meals.map((m) => ({
          meal: m.meal_type,
          time: m.time_label,
          items: m.items.map((i) => `${i.name} × ${i.quantity} (~${i.calories} kcal)`),
          total_kcal: m.total_calories,
        })),
        logged_activity: scenario.app.activities.map(
          (a) => `${a.kind}, ${a.duration_min} min (${a.time_label})`,
        ),
        medications: scenario.app.meds.map((m) => ({
          name: m.name,
          timing: m.timing,
          status: m.status,
        })),
        glucose_sensor:
          g.status === 'expired'
            ? { status: 'expired', expired_since: g.expired_since, note: 'No readings since expiry — the chart is dark.' }
            : {
                status: 'active',
                notable_events: g.events.map((e) => `${e.time_label}: ${e.v} mg/dL — ${e.note}`),
                day_range: g.points.length
                  ? `${Math.min(...g.points.map((x) => x.v))}–${Math.max(...g.points.map((x) => x.v))} mg/dL`
                  : 'sensor fitted today, limited data',
              },
      },
      recent_days: scenario.recent_days,
      prior_calls: scenario.prior_calls,
      todays_call_objective: scenario.objective,
      video_library: VIDEOS.map((v) => ({
        id: v.id,
        title: v.title,
        duration: v.duration,
        good_for: v.good_for,
      })),
    },
  };
}
