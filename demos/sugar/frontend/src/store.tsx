/**
 * Shared state for the Sugar Coach demo — the patient's phone and the voice
 * call drive one store, so the agent and the patient see the same screen.
 *
 * Same two-way pattern as travel/servicing:
 *   - `handleUiCommand(command, payload)` replays the brain's RTVI `ui-command`
 *     frames onto this store (meals appear, meds tick, the chart zooms, videos
 *     play);
 *   - `snapshot()` is echoed back as `state_sync` (`{ screen: ... }`) so the
 *     brain always knows what's on screen — including taps the patient makes
 *     by hand (confirming the sensor order).
 *
 * Navigation (picker → incoming call → live call → ended) is React state, so
 * the live call survives every screen change.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { buildBrainPayload, patientById, scenarioById, videoById } from './data';
import type {
  ActivityEntry,
  CallSummary,
  CareFlag,
  Commitment,
  GlucoseDay,
  Language,
  MealEntry,
  MedStatus,
  Patient,
  Phase,
  Scenario,
  SensorOrderState,
  TalkMode,
  VideoCommand,
} from './types';

type AgentSend = ((type: string, data: unknown) => void) | null;

interface GlucoseFocus {
  time_label?: string;
  note?: string;
  nonce: number;
}

interface SugarStore {
  // ── Navigation ────────────────────────────────────────────────────────────
  phase: Phase;
  language: Language;
  setLanguage: (l: Language) => void;
  /** How chatty the coach is; seeded from the scenario, overridable by the presenter. */
  talkMode: TalkMode;
  setTalkMode: (m: TalkMode) => void;
  /** Picker → incoming-call screen for one scenario. */
  startScenario: (scenarioId: string) => void;
  /** Incoming-call accept → live call (the widget connects on this). */
  acceptCall: () => void;
  /** Decline / back out to the picker. */
  declineCall: () => void;
  /** Live call hang-up → ended screen (widget disconnects on this). */
  endCall: () => void;
  backToPicker: () => void;

  scenario: Scenario | null;
  patient: Patient | null;
  /** The exact PATIENT CONTEXT payload for this call (also shown to the audience). */
  brainPayload: () => unknown;

  // ── The phone's live screen state ─────────────────────────────────────────
  meals: MealEntry[];
  activities: ActivityEntry[];
  meds: MedStatus[];
  glucose: GlucoseDay | null;
  glucoseFocus: GlucoseFocus | null;
  commitment: Commitment | null;
  flags: CareFlag[];
  summary: CallSummary | null;
  sensorOrder: SensorOrderState;
  highlightSection: string | null;

  // Video (imperative command queue for the YouTube player)
  videoOpen: boolean;
  videoTitle: string | null;
  videoCmd: VideoCommand | null;
  closeVideo: () => void;

  // ── Bridges ───────────────────────────────────────────────────────────────
  handleUiCommand: (command: string, payload: Record<string, unknown>) => void;
  snapshot: () => Record<string, unknown>;
  registerAgentSend: (fn: AgentSend) => void;
  /** Patient taps the sensor-renewal card by hand; the agent sees it via state_sync. */
  tapSensorOrder: () => void;

  /** Bumped on every state change the agent should hear about. */
  rev: number;
}

const Ctx = createContext<SugarStore | null>(null);

export function useSugar(): SugarStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useSugar outside SugarProvider');
  return ctx;
}

let idCounter = 0;
const nextId = () => `s${++idCounter}`;

export function SugarProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>('picker');
  const [language, setLanguage] = useState<Language>('English');
  const [talkMode, setTalkMode] = useState<TalkMode>('quiet');
  const [scenario, setScenario] = useState<Scenario | null>(null);

  const [meals, setMeals] = useState<MealEntry[]>([]);
  const [activities, setActivities] = useState<ActivityEntry[]>([]);
  const [meds, setMeds] = useState<MedStatus[]>([]);
  const [glucose, setGlucose] = useState<GlucoseDay | null>(null);
  const [glucoseFocus, setGlucoseFocus] = useState<GlucoseFocus | null>(null);
  const [commitment, setCommitment] = useState<Commitment | null>(null);
  const [flags, setFlags] = useState<CareFlag[]>([]);
  const [summary, setSummary] = useState<CallSummary | null>(null);
  const [sensorOrder, setSensorOrder] = useState<SensorOrderState>('none');
  const [highlightSection, setHighlightSection] = useState<string | null>(null);
  const [videoOpen, setVideoOpen] = useState(false);
  const [videoTitle, setVideoTitle] = useState<string | null>(null);
  const [videoCmd, setVideoCmd] = useState<VideoCommand | null>(null);
  const [rev, setRev] = useState(0);

  const agentSendRef = useRef<AgentSend>(null);
  const nonceRef = useRef(0);
  const highlightTimer = useRef<number | null>(null);

  const patient = scenario ? patientById(scenario.patient_id) : null;
  const bump = useCallback(() => setRev((r) => r + 1), []);

  // ── Navigation ──────────────────────────────────────────────────────────
  const startScenario = useCallback((scenarioId: string) => {
    const s = scenarioById(scenarioId);
    setScenario(s);
    setTalkMode(s.talk_mode); // seed the coach's pace from the scenario
    // Prefill the phone from the scenario's day.
    setMeals(s.app.meals);
    setActivities(s.app.activities);
    setMeds(s.app.meds);
    setGlucose(s.app.glucose);
    setGlucoseFocus(null);
    setCommitment(null);
    setFlags([]);
    setSummary(null);
    setSensorOrder('none');
    setHighlightSection(null);
    setVideoOpen(false);
    setVideoTitle(null);
    setVideoCmd(null);
    setPhase('incoming');
  }, []);

  const acceptCall = useCallback(() => setPhase('call'), []);
  const declineCall = useCallback(() => setPhase('picker'), []);
  const endCall = useCallback(() => setPhase('ended'), []);
  const backToPicker = useCallback(() => {
    setScenario(null);
    setPhase('picker');
  }, []);

  const brainPayload = useCallback(
    () => (scenario ? buildBrainPayload(scenario, language, talkMode) : {}),
    [scenario, language, talkMode],
  );

  // ── Agent → screen ──────────────────────────────────────────────────────
  const flashHighlight = useCallback((section: string) => {
    setHighlightSection(section);
    if (highlightTimer.current) window.clearTimeout(highlightTimer.current);
    highlightTimer.current = window.setTimeout(() => setHighlightSection(null), 2600);
  }, []);

  const handleUiCommand = useCallback(
    (command: string, payload: Record<string, unknown>) => {
      const cmd = payload;
      switch (command) {
        case 'log_meal': {
          const items = Array.isArray(cmd.items) ? (cmd.items as MealEntry['items']) : [];
          const entry: MealEntry = {
            id: nextId(),
            meal_type: String(cmd.meal_type ?? 'other'),
            time_label: String(cmd.time_label ?? ''),
            items,
            total_calories: Number(cmd.total_calories ?? 0),
            note: cmd.note ? String(cmd.note) : undefined,
            fresh: true,
          };
          // A re-log of the same meal type replaces the fresh entry (the agent
          // re-calls log_meal with corrections).
          setMeals((prev) => {
            const i = prev.findIndex((m) => m.fresh && m.meal_type === entry.meal_type);
            if (i >= 0) return [...prev.slice(0, i), entry, ...prev.slice(i + 1)];
            return [...prev, entry];
          });
          flashHighlight('meals');
          break;
        }
        case 'log_activity': {
          const entry: ActivityEntry = {
            id: nextId(),
            kind: String(cmd.kind ?? ''),
            duration_min: Number(cmd.duration_min ?? 0),
            time_label: String(cmd.time_label ?? ''),
            note: cmd.note ? String(cmd.note) : undefined,
            fresh: true,
          };
          setActivities((prev) => [...prev, entry]);
          flashHighlight('activity');
          break;
        }
        case 'mark_medication': {
          const name = String(cmd.name ?? '').toLowerCase();
          const status = String(cmd.status ?? '') as MedStatus['status'];
          setMeds((prev) =>
            prev.map((m) =>
              m.name.toLowerCase().includes(name) || name.includes(m.name.toLowerCase())
                ? { ...m, status, time_label: cmd.time_label ? String(cmd.time_label) : m.time_label }
                : m,
            ),
          );
          flashHighlight('meds');
          break;
        }
        case 'show_glucose': {
          setGlucoseFocus({
            time_label: cmd.focus_time_label ? String(cmd.focus_time_label) : undefined,
            note: cmd.note ? String(cmd.note) : undefined,
            nonce: ++nonceRef.current,
          });
          flashHighlight('glucose');
          break;
        }
        case 'play_video': {
          const video = videoById(String(cmd.video_id ?? ''));
          if (!video) break;
          setVideoOpen(true);
          setVideoTitle(video.title);
          setVideoCmd({
            action: 'play',
            youtubeId: video.youtube_id,
            startSec: Number(cmd.start_sec ?? 0),
            nonce: ++nonceRef.current,
          });
          break;
        }
        case 'pause_video':
          setVideoCmd({ action: 'pause', nonce: ++nonceRef.current });
          break;
        case 'resume_video':
          setVideoCmd({ action: 'resume', nonce: ++nonceRef.current });
          break;
        case 'set_commitment':
          setCommitment({
            text: String(cmd.text ?? ''),
            when: cmd.when ? String(cmd.when) : undefined,
          });
          flashHighlight('summary');
          break;
        case 'flag_for_care_team':
          setFlags((prev) => [
            ...prev,
            { topic: String(cmd.topic ?? ''), detail: String(cmd.detail ?? '') },
          ]);
          break;
        case 'show_sensor_renewal':
          setSensorOrder((prev) => (prev === 'ordered' ? prev : 'offered'));
          flashHighlight('glucose');
          break;
        case 'confirm_sensor_order':
          setSensorOrder('ordered');
          break;
        case 'show_summary': {
          const lines = Array.isArray(cmd.lines) ? (cmd.lines as string[]).map(String) : [];
          setSummary({ lines, flagged: cmd.flagged ? String(cmd.flagged) : undefined });
          break;
        }
        case 'highlight':
          flashHighlight(String(cmd.section ?? ''));
          break;
        default:
          break;
      }
      bump();
    },
    [bump, flashHighlight],
  );

  // ── Screen → agent ──────────────────────────────────────────────────────
  const snapshot = useCallback((): Record<string, unknown> => {
    return {
      phase,
      meals: meals.map((m) => ({
        meal: m.meal_type,
        time: m.time_label,
        items: m.items.map((i) => `${i.name} × ${i.quantity}`),
        total_kcal: m.total_calories,
      })),
      activity: activities.map((a) => `${a.kind}, ${a.duration_min} min (${a.time_label})`),
      medications: meds.map((m) => ({ name: m.name, status: m.status })),
      commitment,
      care_team_flags: flags.map((f) => f.topic),
      sensor_order: sensorOrder,
      video: videoOpen ? { title: videoTitle, open: true } : null,
      summary_shown: Boolean(summary),
    };
  }, [phase, meals, activities, meds, commitment, flags, sensorOrder, videoOpen, videoTitle, summary]);

  const registerAgentSend = useCallback((fn: AgentSend) => {
    agentSendRef.current = fn;
  }, []);

  const tapSensorOrder = useCallback(() => {
    setSensorOrder('ordered');
    bump(); // state_sync carries the tap to the agent
  }, [bump]);

  const closeVideo = useCallback(() => {
    setVideoOpen(false);
    setVideoCmd({ action: 'pause', nonce: ++nonceRef.current });
    bump();
  }, [bump]);

  const value = useMemo<SugarStore>(
    () => ({
      phase,
      language,
      setLanguage,
      talkMode,
      setTalkMode,
      startScenario,
      acceptCall,
      declineCall,
      endCall,
      backToPicker,
      scenario,
      patient,
      brainPayload,
      meals,
      activities,
      meds,
      glucose,
      glucoseFocus,
      commitment,
      flags,
      summary,
      sensorOrder,
      highlightSection,
      videoOpen,
      videoTitle,
      videoCmd,
      closeVideo,
      handleUiCommand,
      snapshot,
      registerAgentSend,
      tapSensorOrder,
      rev,
    }),
    [
      phase, language, talkMode, startScenario, acceptCall, declineCall, endCall, backToPicker,
      scenario, patient, brainPayload, meals, activities, meds, glucose, glucoseFocus,
      commitment, flags, summary, sensorOrder, highlightSection, videoOpen, videoTitle,
      videoCmd, closeVideo, handleUiCommand, snapshot, registerAgentSend, tapSensorOrder, rev,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
