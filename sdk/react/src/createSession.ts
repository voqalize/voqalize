/**
 * createSession — mint and start a Voqalize voice session from the browser.
 *
 * Wraps the single public bootstrap call every embed makes:
 *
 *   POST {apiBase}/sessions.create
 *   Authorization: Bearer <pk_...>
 *   { agent_id, agent_input: { pipeline, payload } }
 *
 * and normalizes the response into {@link VoqalConnectParams} — exactly what
 * `PipecatClient.connect()` hands pipecat's `SmallWebRTCTransport`.
 * Authentication uses a publishable (`pk_`) key, safe to ship in browser code.
 *
 * This is step one of pipecat's two-step connect: *ask someone who holds a
 * credential where the bot is*, then negotiate WebRTC against the address you
 * were given. A page that mints on its own backend instead skips this function
 * entirely and calls {@link toConnectParams} on whatever its server returns.
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
  /** Publishable (`pk_...`) key. Sent as `Authorization: Bearer`. */
  publishableKey: string;
  /** Firestore agent id to start. */
  agentId: string;
  /**
   * Optional STT/TTS pipeline overrides. **Usually omit this** — voice and
   * language belong to the brain (see {@link VoqalPipelineConfig}).
   */
  pipeline?: VoqalPipelineConfig;
  /**
   * Optional app-level context handed to the brain (surface, plan tier, cart id).
   *
   * The server both signs this into the session token and **stores it on the
   * session**, so it is readable later by anyone who can read the session — it
   * is there to answer "what did the page send?" when a call goes wrong. Send
   * identifiers, not personal data.
   */
  payload?: Record<string, unknown>;
  /**
   * Whether to record this one call. Omit it and the agent's stored default
   * decides — which is `false` unless someone turned it on.
   *
   * This is the per-call half of a two-part decision, and it is here because
   * the page is the only party that knows whether *this* caller consented:
   * `PreCallGate` is where you collect that, and this is where you report it.
   * `false` is always honoured, so a caller who declines is never recorded even
   * on an agent that records by default.
   *
   * **`true` is refused on this path.** A publishable (`pk_`) key ships in page
   * source, so anyone holding it could otherwise write voice into your storage,
   * on your bill, for an agent whose owner chose not to record. The call still
   * runs — it connects, it greets, it answers, and nothing about it sounds
   * wrong — so this function warns on the console when it happens. Turn
   * recording on where its owner controls it: the agent's own default, over MCP
   * (`update_agent(recording=true)`) or in the console.
   */
  record?: boolean;
  /** Optional `fetch` override (SSR / testing). Defaults to global `fetch`. */
  fetchImpl?: typeof fetch;
}

/**
 * Where the WebRTC offer goes, and what it must carry to be accepted.
 *
 * The shape pipecat's `SmallWebRTCTransport` reads: it `POST`s the SDP offer to
 * `endpoint` and `PATCH`es trickled ICE candidates to the same URL, sending
 * `headers` on both.
 *
 * `headers` is a real `Headers`, not a plain object, and that is load-bearing:
 * pipecat builds every request with `Object.fromEntries(headers.entries())`, so
 * a plain object — which is what a JSON body naturally gives you — throws a
 * `TypeError` at the offer POST rather than failing anywhere legible. Running
 * a server response through {@link toConnectParams} is what makes it a
 * `Headers`.
 */
export interface VoqalConnectParams {
  webrtcRequestParams: {
    /** Absolute URL of the assigned node's offer endpoint. */
    endpoint: string;
    /** Sent on the offer POST and every ICE PATCH. Carries the session token. */
    headers?: Headers;
  };
  /**
   * The session this call is. Not used to address anything — the endpoint
   * already names the node and the token already names the session — but it is
   * the id every log, recording and transcript is filed under, so it travels
   * with the connection details rather than being derivable from them.
   */
  sessionId?: string;
}

/** Thrown when `sessions.create` fails or returns an unusable body. */
export class VoqalSessionError extends Error {
  /** HTTP status code, or 0 for network/parse failures. */
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "VoqalSessionError";
    this.status = status;
  }
}

/**
 * Normalize a minted session's `connect_params` into {@link VoqalConnectParams}.
 *
 * Accepts the wire form the control plane serves and a customer's own backend
 * is expected to mirror:
 *
 * ```json
 * {
 *   "webrtc_request_params": {
 *     "endpoint": "https://signal.prod.voqalize.com/webrtc",
 *     "headers": { "Authorization": "Bearer <session token>" }
 *   },
 *   "session_id": "..."
 * }
 * ```
 *
 * Both `snake_case` (the wire) and `camelCase` (already-normalized) keys are
 * read, so passing the result of this function back through it is a no-op.
 *
 * @throws {VoqalSessionError} when there is no endpoint to negotiate against.
 */
export function toConnectParams(raw: unknown): VoqalConnectParams {
  if (!raw || typeof raw !== "object") {
    throw new VoqalSessionError(
      "toConnectParams: expected an object of connection parameters",
      0
    );
  }
  const body = raw as Record<string, unknown>;
  const request = (body["webrtc_request_params"] ??
    body["webrtcRequestParams"] ??
    {}) as Record<string, unknown>;

  const endpoint = request["endpoint"];
  if (typeof endpoint !== "string" || !endpoint) {
    throw new VoqalSessionError(
      "toConnectParams: no webrtc_request_params.endpoint — nothing to send the offer to",
      0
    );
  }

  const params: VoqalConnectParams = { webrtcRequestParams: { endpoint } };

  const headers = request["headers"];
  if (headers instanceof Headers) {
    params.webrtcRequestParams.headers = headers;
  } else if (headers && typeof headers === "object") {
    params.webrtcRequestParams.headers = new Headers(
      headers as Record<string, string>
    );
  }

  const sessionId = body["session_id"] ?? body["sessionId"];
  if (typeof sessionId === "string" && sessionId) params.sessionId = sessionId;

  return params;
}

interface CreateSessionResponse {
  connection_details?: {
    connect_params?: unknown;
  };
  /**
   * What the server decided about recording for this call — the resolved
   * answer, not the request. Read to tell a refusal from a grant, since both
   * arrive as a 2xx with working connection parameters.
   */
  recording_enabled?: boolean;
}

/**
 * Create and start a session, returning the parameters to connect with.
 *
 * @throws {VoqalSessionError} on a non-2xx response or a body that carries no
 *   usable connection parameters.
 */
export async function createSession(
  opts: CreateSessionOptions
): Promise<VoqalConnectParams> {
  const {
    apiBase,
    publishableKey,
    agentId,
    pipeline,
    payload,
    record,
    fetchImpl = fetch,
  } = opts;

  if (!publishableKey) {
    throw new VoqalSessionError("createSession: publishableKey is required", 0);
  }
  if (!agentId) {
    throw new VoqalSessionError("createSession: agentId is required", 0);
  }

  // No workspace anywhere in the URL. A `pk_` key belongs to exactly one, so
  // the server reads it off the credential; naming one here would be a second
  // answer to a question the key has already answered.
  const url = `${apiBase.replace(/\/$/, "")}/sessions.create`;

  // `agent_input` is what this page hands the agent, and it has two
  // destinations on the server: it is signed into the session token — which is
  // how the runtime and then the brain receive it — and stored on the session,
  // so "what did this page actually send?" survives the token expiring five
  // minutes later. Stored means readable by anyone who can read the session, so
  // keep PII out of it.
  //
  // The runtime splits it by key: `pipeline` is per-call media config, `payload`
  // is opaque business context for the brain. Two keys, one field, because they
  // travel together and arrive together.
  const inner: { pipeline?: VoqalPipelineConfig; payload?: Record<string, unknown> } = {};
  if (pipeline) inner.pipeline = pipeline;
  if (payload) inner.payload = payload;

  // `record` sits beside `agent_input`, not inside it: `agent_input` is what
  // this page hands the *brain*, and recording is not the brain's business —
  // it is a decision about what the service does with the audio. Omitted
  // entirely when unset, because omission is what "use the agent's default"
  // means on the server, and `null` is not the same word.
  const body: Record<string, unknown> = { agent_id: agentId, agent_input: inner };
  if (record !== undefined) body.record = record;

  let res: Response;
  try {
    res = await fetchImpl(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${publishableKey}`,
      },
      credentials: "omit",
      body: JSON.stringify(body),
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

  let parsed: CreateSessionResponse;
  try {
    parsed = (await res.json()) as CreateSessionResponse;
  } catch (err) {
    throw new VoqalSessionError(
      `createSession: could not parse response — ${(err as Error).message}`,
      res.status
    );
  }

  // The one outcome of this call that is invisible from inside it. A `pk_` key
  // may turn recording off but never on, so a page that asked for recording is
  // answered with a working session that keeps no audio. Nothing later says so:
  // the recording is simply not there, weeks after the calls it was wanted for.
  if (record === true && parsed.recording_enabled === false) {
    console.warn(
      "createSession: this call is NOT being recorded. `record: true` was sent " +
        "with a publishable (pk_) key, and a pk_ key may turn recording off but " +
        "never on — it ships in page source. Turn recording on where its owner " +
        "controls it: the agent's own default, via MCP `update_agent(recording=true)` " +
        "or the console. `record: false` from here is still honoured, for a caller " +
        "who declines."
    );
  }

  const connectParams = parsed.connection_details?.connect_params;
  if (!connectParams) {
    throw new VoqalSessionError(
      "createSession: response missing connection_details.connect_params — is a voice runtime node configured for this environment?",
      res.status
    );
  }

  try {
    return toConnectParams(connectParams);
  } catch (err) {
    // Re-thrown with the HTTP status attached: a malformed body is a server
    // problem, and `status: 0` would read as a network failure in the browser.
    throw new VoqalSessionError((err as Error).message, res.status);
  }
}
