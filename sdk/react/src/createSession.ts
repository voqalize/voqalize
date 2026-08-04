/**
 * createSession — mint and start a Voqalize voice session from the browser.
 *
 * Wraps the single public bootstrap call every embed makes:
 *
 *   POST {apiBase}/{tenantSlug}/sessions.create_and_start
 *   Authorization: Bearer <pk_...>
 *   { agent_id, payload: { pipeline, payload } }
 *
 * and normalizes the response into `{ signalingUrl, token }`, which is exactly
 * what {@link VoqalWebRTCTransport} needs to `connect`. Authentication uses a
 * publishable (`pk_`) key — safe to ship in browser code.
 */

/**
 * Per-session STT/TTS overrides. **Most pages should not set this.**
 *
 * ## Voice and language belong to the brain
 *
 * The canonical place to say how an agent sounds is the brain, in Python:
 *
 * ```python
 * class ConciergeBrain(Brain):
 *     voice = "omnivoice/gauri"
 *     language = "hi"          # sets the recognizer AND the TTS voice together
 * ```
 *
 * and, when the language depends on *this* caller, `session.configure_language(...)`
 * inside `on_session_start` — the brain is the only thing that sees the caller.
 * The same call switches language mid-call. Full contract: the Voice & language
 * catalog (`docs/src/content/docs/reference/catalog.md`).
 *
 * That is not a style preference. Voice and language used to be settable from
 * three places — the agent record, this prop, and the brain — and a Hindi demo
 * shipped speaking Devanagari in an English voice because one link in that chain
 * dropped the field. Nothing automated caught it: the words are correct and
 * accent is invisible to transcription-based scoring, so it was found by ear,
 * weeks later. The agent record no longer carries voice or language at all, and
 * every demo in this repo now declares it on the brain.
 *
 * ## When this prop is still right
 *
 * A page that is genuinely the authority on the pipeline — a console that lets a
 * human pick a voice to audition, an A/B harness — sets it here. It layers over
 * the platform defaults at session start, and **a brain that declares or
 * configures a voice overrides it**, since the brain speaks last.
 *
 * If you do set a language here, set the same ISO code on both `stt` and `tts`;
 * each half fails quietly on its own. `tts.language` picks the voice-cloning
 * reference clip (`omnivoice/gauri` carries a Hindi clip and a separate English
 * one), and `stt.language` picks the recognizer (English → Parakeet, the 22
 * Indic languages → IndicConformer). Do not reach for `stt.language_hint`: it is
 * the raw wire field the runtime derives from `stt.language`, and setting it by
 * hand is how a config ends up half-applied.
 */
export interface VoqalPipelineConfig {
  /** Speech-to-text config. Prefer the brain — see the interface docs above. */
  stt?: { model?: string; language?: string } & Record<string, unknown>;
  /** Text-to-speech config. Prefer the brain — see the interface docs above. */
  tts?: { voice?: string; language?: string } & Record<string, unknown>;
}

/** Options for {@link createSession}. */
export interface CreateSessionOptions {
  /** Versioned API root, e.g. `"/api/v1"` or `"https://app.voqalize.com/api/v1"`. */
  apiBase: string;
  /** Tenant slug for the `/{slug}/...` path. */
  tenantSlug: string;
  /** Publishable (`pk_...`) key. Sent as `Authorization: Bearer`. */
  publishableKey: string;
  /** Firestore agent id to start. */
  agentId: string;
  /**
   * Optional STT/TTS pipeline overrides. **Usually omit this** — voice and
   * language belong to the brain (see {@link VoqalPipelineConfig}).
   */
  pipeline?: VoqalPipelineConfig;
  /** Optional app-level payload handed to the brain (surface, user info, …). */
  payload?: Record<string, unknown>;
  /** Optional `fetch` override (SSR / testing). Defaults to global `fetch`. */
  fetchImpl?: typeof fetch;
}

/** Resolved connection details for {@link VoqalWebRTCTransport}. */
export interface VoqalSession {
  /** `wss://.../signal/{session_id}` signaling URL. */
  signalingUrl: string;
  /** RS256 JWT for the PyGato handshake. */
  token: string;
}

/** Thrown when `sessions.create_and_start` fails or returns an unusable body. */
export class VoqalSessionError extends Error {
  /** HTTP status code, or 0 for network/parse failures. */
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "VoqalSessionError";
    this.status = status;
  }
}

interface CreateAndStartResponse {
  connection_details?: {
    signaling_url?: string;
    token?: string;
  };
}

/**
 * Create and start a session, returning the signaling URL + token.
 *
 * @throws {VoqalSessionError} on a non-2xx response or a body missing the
 *   signaling URL / token.
 */
export async function createSession(
  opts: CreateSessionOptions
): Promise<VoqalSession> {
  const {
    apiBase,
    tenantSlug,
    publishableKey,
    agentId,
    pipeline,
    payload,
    fetchImpl = fetch,
  } = opts;

  if (!publishableKey) {
    throw new VoqalSessionError("createSession: publishableKey is required", 0);
  }
  if (!agentId) {
    throw new VoqalSessionError("createSession: agentId is required", 0);
  }

  const url = `${apiBase.replace(/\/$/, "")}/${tenantSlug}/sessions.create_and_start`;

  const inner: { pipeline?: VoqalPipelineConfig; payload?: Record<string, unknown> } = {};
  if (pipeline) inner.pipeline = pipeline;
  if (payload) inner.payload = payload;

  let res: Response;
  try {
    res = await fetchImpl(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${publishableKey}`,
      },
      credentials: "omit",
      body: JSON.stringify({ agent_id: agentId, payload: inner }),
    });
  } catch (err) {
    throw new VoqalSessionError(
      `createSession: network error — ${(err as Error).message}`,
      0
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.text()).slice(0, 500);
    } catch {
      /* ignore */
    }
    throw new VoqalSessionError(
      `createSession: session start failed (${res.status})${detail ? `: ${detail}` : ""}`,
      res.status
    );
  }

  let body: CreateAndStartResponse;
  try {
    body = (await res.json()) as CreateAndStartResponse;
  } catch (err) {
    throw new VoqalSessionError(
      `createSession: could not parse response — ${(err as Error).message}`,
      res.status
    );
  }

  const signalingUrl = body.connection_details?.signaling_url ?? "";
  const token = body.connection_details?.token ?? "";
  if (!signalingUrl) {
    throw new VoqalSessionError(
      "createSession: response missing connection_details.signaling_url — is a worker running for this agent?",
      res.status
    );
  }

  return { signalingUrl, token };
}
