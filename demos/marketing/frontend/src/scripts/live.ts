/**
 * The live call: pipecat's client on @voqalize/client-transport, the Tanvi avatar,
 * and the brain in `../backend` reached through Voqalize.
 *
 * The browser half is the same as today's homepage agent
 * (platform/frontend/apps/marketing/src/agent/session.ts): one request to
 * `sessions.connect` with the publishable key, then pipecat's connect with the
 * session credential that comes back. `/api` is proxied to the dev control plane
 * by `astro.config.mjs`, so the call is same-origin, as it will be in production.
 *
 * Tanvi's face is mounted before any call: `prepare()` builds a client that is not
 * connected yet and mounts the avatar on it, so the hero shows her idling in her
 * own framing, and "Talk to Tanvi" connects that same client. After a call ends a
 * fresh client and face are prepared for the next one.
 *
 * This module knows nothing about the page. The shell hands it callbacks and gets
 * back a handle; brain actions and visitor gestures cross through those two.
 */
import { PipecatClient, type APIRequest, type TransportState } from '@pipecat-ai/client-js';
import { createAvatar, preloadAvatar, type AvatarInstance } from '@voqalize/avatar';
import { createVoqalizeTransport, VoqalizeMediaManager } from '@voqalize/client-transport';

import { asUiAction, sendAppEvent, type AppEvent, type UiAction } from './actions.gen';
import type { VoiceState } from './voice';

export const CHARACTER = 'tanvi';

const agentId = import.meta.env.PUBLIC_AGENT_ID ?? '';
const publishableKey = import.meta.env.PUBLIC_PUBLISHABLE_KEY ?? '';
const apiBase = import.meta.env.PUBLIC_API_BASE || '/api/v1';

/** Whether this build has both halves of the browser credential and can open a call. */
export const provisioned = Boolean(agentId && publishableKey);

export type CallStatus = 'connecting' | 'live' | 'ended' | 'error';

export interface LiveCallbacks {
  status(s: CallStatus, message?: string): void;
  state(s: VoiceState): void;
  /** Tanvi started a new spoken turn: clear the caption. */
  botTurn(): void;
  /** A piece of what Tanvi is saying, as the voice reaches it. */
  botText(text: string): void;
  /** What the visitor said, interim or final. */
  heard(text: string, final: boolean): void;
  action(a: UiAction): void;
}

export interface LiveCall {
  event(e: AppEvent): void;
  /** End the conversation for good: the End control, or switching to Read mode. */
  hangUp(): void;
  /** End once Tanvi finishes the line she is saying (her sign-off before Read mode). */
  endWhenQuiet(): void;
  /** Mute or unmute the visitor's microphone. Tanvi keeps talking. */
  mute(on: boolean): void;
}

type Transport = ReturnType<typeof createVoqalizeTransport>;
interface Prepared { client: PipecatClient; avatar: AvatarInstance; mediaManager: VoqalizeMediaManager; transport: Transport }

let prepared: Prepared | null = null;
let face: HTMLElement | null = null;
let onFaceReady: () => void = () => {};
// The callbacks of the call in progress. The client is built before the call, so
// it reaches the page through this rather than through its own closure.
let cb: LiveCallbacks | null = null;
let speaking = false;
let ending = false;

/**
 * Build the client and mount Tanvi's face, idle, before any call. Safe to call
 * again; it does nothing while a face is mounted.
 */
export function prepare(mount: HTMLElement, faceReady: () => void): void {
  face = mount;
  onFaceReady = faceReady;
  if (!provisioned || prepared) return;
  const mediaManager = new VoqalizeMediaManager();
  // keepAcrossPageLoads: the transport remembers this tab's call, so a refresh
  // rejoins the same conversation (same session, same brain context) instead of
  // ending it. The voice node holds a call for 10 s after its page goes away.
  const transport = createVoqalizeTransport({ mediaManager, keepAcrossPageLoads: true });
  const client = new PipecatClient({
    transport,
    enableMic: true,
    callbacks: {
      onTransportStateChanged: (state: TransportState) => {
        if (state === 'connected' || state === 'ready') cb?.status('live');
        if (state === 'disconnected' && cb) finish();
      },
      onUserStartedSpeaking: () => cb?.state('listening'),
      onUserTranscript: (data) => cb?.heard(data.text, Boolean(data.final)),
      onBotLlmStarted: () => cb?.state('thinking'),
      onBotStartedSpeaking: () => { speaking = true; cb?.botTurn(); cb?.state('speaking'); },
      onBotTtsText: (data) => { if (data.text) cb?.botText(data.text); },
      onBotStoppedSpeaking: () => {
        speaking = false;
        if (ending) { window.setTimeout(hangUp, 400); return; }
        cb?.state('listening');
      },
      onTrackStarted: (track, participant) => {
        if (participant?.local || track.kind !== 'audio') return;
        const audio = document.getElementById('voice-audio') as HTMLAudioElement | null;
        if (!audio) return;
        audio.srcObject = new MediaStream([track]);
        void audio.play().catch(() => {});
      },
      onUICommand: ({ command, payload }) => {
        const a = asUiAction(command, payload);
        if (a) cb?.action(a);
      },
    },
  });
  const audio = document.getElementById('voice-audio') as HTMLAudioElement | null;
  if (audio) mediaManager.bindOutputElement(audio);
  const avatar = createAvatar({ mount, client, character: CHARACTER });
  prepared = { client, avatar, mediaManager, transport };
  void preloadAvatar(CHARACTER).ready.then(() => onFaceReady(), () => {});
}

function connectRequest(init: Record<string, unknown>): APIRequest {
  return {
    endpoint: `${apiBase}/sessions.connect`,
    // Authorization only: pipecat adds Content-Type itself, and a second copy
    // arrives as "application/json, application/json", which the API rejects.
    headers: new Headers({ Authorization: `Bearer ${publishableKey}` }),
    requestData: { agent_id: agentId, init } as APIRequest['requestData'],
  };
}

/** The connect answer carries the session credential as JSON; pipecat wants a real Headers. */
function withRealHeaders(response: unknown) {
  const body = response as { webrtc_request_params?: { endpoint?: string; headers?: Record<string, string> }; session_id?: string };
  return {
    ...body,
    webrtc_request_params: { ...body.webrtc_request_params, headers: new Headers(body.webrtc_request_params?.headers ?? {}) },
  };
}

function finish(message?: string) {
  const callbacks = cb;
  if (!callbacks) return;
  cb = null;
  ending = false;
  speaking = false;
  const old = prepared;
  prepared = null;
  old?.avatar.destroy();
  const audio = document.getElementById('voice-audio') as HTMLAudioElement | null;
  if (audio) audio.srcObject = null;
  callbacks.status(message ? 'error' : 'ended', message);
  // A fresh, unconnected client and an idle face for the next conversation.
  if (face) prepare(face, onFaceReady);
}

function hangUp() {
  const client = prepared?.client;
  if (!cb) return;
  finish();
  // disconnectBot ends the call on the server and makes the transport forget it,
  // so the next page load does not rejoin a conversation the visitor ended.
  try { client?.disconnectBot(); } catch { /* not connected yet */ }
  void client?.disconnect();
}

/** Whether this tab has a conversation to rejoin (it was live when the page reloaded). */
export function hasLiveCall(): boolean {
  return Boolean(prepared?.transport.hasLiveCall);
}

export async function startCall(callbacks: LiveCallbacks, opts: { rejoin?: boolean } = {}): Promise<LiveCall> {
  if (!prepared && face) prepare(face, onFaceReady);
  const current = prepared;
  if (!current) throw new Error('Live voice is not configured');
  cb = callbacks;
  callbacks.status('connecting');
  try {
    if (opts.rejoin) {
      // No sessions.connect on a rejoin: that would start a second session.
      await current.client.connect();
    } else {
      const started = await current.client.startBot(connectRequest({ page: 'home' }));
      await current.client.connect(withRealHeaders(started));
    }
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    finish(text || 'Could not start the call');
    await current.client.disconnect().catch(() => {});
    throw error;
  }
  return {
    event: (e) => sendAppEvent(current.client.sendUIEvent.bind(current.client), e),
    hangUp,
    endWhenQuiet: () => {
      ending = true;
      current.client.enableMic(false);
      // If she is not mid-line, or the line never arrives, end shortly anyway.
      window.setTimeout(() => { if (!speaking) hangUp(); }, 1500);
      window.setTimeout(hangUp, 12000);
    },
    mute: (on) => current.client.enableMic(!on),
  };
}

// No hang-up on pagehide or beforeunload, on purpose: a refresh rejoins the call
// (keepAcrossPageLoads), and a page that never comes back ends the call when the
// voice node's 10 s hold runs out. A page restored from the back/forward cache
// has a dead connection, so it reloads and rejoins.
addEventListener('pageshow', (e) => { if (e.persisted && prepared?.transport.hasLiveCall) location.reload(); });
