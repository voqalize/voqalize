/**
 * The site's own ordering, in one place.
 *
 * Two things need it and they must not drift: Starlight's sidebar (the human
 * reading the site) and `llms.txt` (the agent reading the tree). It lives here
 * rather than inline in `astro.config.mjs` so that adding a page is one edit,
 * not two — a second copy of a table of contents is a second thing to forget.
 *
 * Plain `.mjs` on purpose: `astro.config.mjs` and a `src/pages/` endpoint both
 * import it, and neither has to think about how the other's toolchain handles
 * TypeScript.
 *
 * ── The shape, and why ──────────────────────────────────────────────────────
 *
 * Sections are ordered by what the reader is holding: nothing yet, a brain, a
 * page, an avatar; then what they are running; then the two libraries they
 * consult. Diátaxis governs how a page is *written* and is declared per page in
 * frontmatter — it is deliberately not the navigation, because a top level of
 * "tutorials / how-to / reference / explanation" makes a reader classify their
 * own need before they can move.
 *
 * The two build sections name the halves of the reader's own application rather
 * than splitting the site by role. The same person usually writes both, and a
 * role split makes them read half the site.
 *
 * ── The destination, and what is missing ────────────────────────────────────
 *
 * Sections arrive as their pages do; a `slug` here must resolve or the build
 * fails. Still to be written, in the order they belong:
 *
 *   Start                 quickstart · your first real brain · the MCP door
 *   The brain             the brain surface · speaking · driving the screen ·
 *                         models and tools · context and history · transcripts
 *   The client            receiving actions · sending context · transcript and
 *                         presence · framework notes
 *   The avatar            what it is · in your pipeline · in the browser ·
 *                         authoring a face
 *   Voice and language    choosing a voice · choosing a language · defaults and
 *                         overrides · why there is no provider slot
 *   Reference             the brain API · errors
 *
 * "Designing for voice" is the durable quadrant and it is written from the
 * outlines in `design/explanations/`. Seven of the eleven are published. Two
 * more are held on the same work as the sections above; one — the browser is
 * pipecat's — was promoted into Start when the React client was deleted; and
 * "the framework boundary" waits for a second engine to exist.
 *
 * Two sections are held rather than merely unwritten, and both are held on the
 * same work: the brain section and the voice-and-language section describe
 * surfaces being changed right now by `skill-rewrite/BRAIN-SIMPLIFICATION.md`
 * — the configuration ops are collapsing into one, voices and languages are
 * becoming protobuf enumerations, and the agent record is becoming where a
 * default lives. Writing either against today's tree would publish a page with
 * a known expiry date. The board is `skill-rewrite/SURFACE-BOARD.md`.
 */
export const sidebar = [
  {
    label: "Start",
    items: [
      { label: "What Voqalize is", slug: "start/what-voqalize-is" },
      { label: "Voqalize and pipecat", slug: "start/pipecat" },
    ],
  },
  {
    label: "The brain — your server",
    items: [{ label: "Testing a brain", slug: "brain/testing" }],
  },
  {
    label: "The client — your page",
    items: [{ label: "Connections and the handshake", slug: "client/handshake" }],
  },
  {
    label: "Run and operate",
    items: [
      { label: "Where the brain runs", slug: "deploy/brain-url" },
      { label: "Inbound server", slug: "deploy/inbound" },
      { label: "Cortex relay", slug: "deploy/cortex" },
      { label: "Keys and authentication", slug: "operate/keys" },
      { label: "Reading a call back", slug: "operate/logs" },
      { label: "Recordings", slug: "operate/recordings" },
      { label: "Usage and limits", slug: "operate/usage" },
    ],
  },
  {
    label: "Reference",
    items: [
      { label: "The wire", slug: "reference/wire" },
      { label: "The RTVI plane", slug: "reference/rtvi" },
      { label: "Voice and language catalog", slug: "reference/catalog" },
      { label: "MCP server", slug: "reference/mcp" },
    ],
  },
  {
    label: "Designing for voice",
    items: [
      { label: "Voice points, the screen holds", slug: "design/voice-points-screen-holds" },
      { label: "The turn budget", slug: "design/the-turn-budget" },
      { label: "Interruption and heard truth", slug: "design/interruption-and-heard-truth" },
      { label: "Parallel workstreams", slug: "design/parallel-workstreams" },
      { label: "Prompt design for voice", slug: "design/prompt-design" },
      { label: "Tool design for voice", slug: "design/tool-design" },
      { label: "Misunderstanding and reversal", slug: "design/misunderstanding-and-reversal" },
    ],
  },
];
