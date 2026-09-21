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
 * Five sections, and each one owns its URLs
 *
 * **A URL is navigation that survives being copied.** Until 2026-08-25 ours did
 * not: pages grouped under "Build" lived at `/deploy/`, `/client/`, `/brain/`
 * and `/operate/`, so the path predicted nothing about the section and the
 * section predicted nothing about the path. A human reading the sidebar never
 * noticed. An agent reading `llms.txt` has no sidebar — the path is the only
 * structure it sees, and we had made the path lie.
 *
 * So: five sections, five namespaces, and their names describe the reader's
 * next decision.
 *
 *   Overview /overview/   evaluation, support and current status
 *   Build    /build/      everything you write, from ten minutes to the whole
 *                         SDK surface
 *   Design   /design/     what changes when the output is spoken
 *   Operate  /operate/    keeping it working
 *   Reference /reference/ the contracts, consulted from all three
 *
 * `Start` was dissolved into Build on the same day. Its three pages were the
 * prologue of the next section — the Build hub opened by sending the reader back
 * out to two of them — and the site was telling one story four times at four
 * lengths. `what-voqalize-is` merged into the apex; the other two are
 * `build/session` and `build/pipecat`.
 *
 * **The IA is built top-down from the MCP handshake.** L0 is the paragraph the
 * MCP server hands a coding agent; L1 is the apex; L2 is evaluation plus the
 * four task-oriented hubs; L3 is what they link to. Task sections therefore
 * answer at `/{section}.md`. Overview is deliberately a decision page rather
 * than another hub.
 *
 * Diátaxis governs how a page is *written* and is declared per page. It is
 * deliberately not the navigation: the reader would have to classify their own
 * problem before they could move.
 *
 * ── Naming rules, earned the hard way ───────────────────────────────────────
 *
 * **A slug may not name an internal service.** `pygato` and `vql-stt` are ours
 * and appear nowhere a customer reads. `cortex` is the one exception and it is
 * a deliberate one — `design/lexicon.yaml` carries **Cortex** as sanctioned
 * vocabulary for the relay, because a reader has to name the thing they dial —
 * but it still loses as a *slug*, because a slug is read by someone who has met
 * the concept and not the name.
 * `/deploy/cortex` became `/build/outbound` because an agent that has read only
 * the handshake has met the concept and never the name. It is now a section of
 * `/build/hosting`, which is where the choice between the two paths is made.
 *
 * **A slug is read without its page.** In `llms.txt` it is a path and one line.
 * `/client/handshake` lost to `/build/connect` because "handshake" is three
 * different things here — WebRTC's, TLS's, and the MCP paragraph's own word for
 * itself.
 *
 * ── What is still missing ───────────────────────────────────────────────────
 *
 * Sections arrive as their pages do; a `slug` here must resolve or the build
 * fails. **A page that is an outline carries a `:::note[Scaffold]` aside**, and
 * that is a rule a reader and a checker can both apply — the marker was on
 * three of nine outlines until 2026-08-25, which made it mean nothing, and
 * `design/facts.yaml` now counts it.
 *
 * **No page carries it today.** `reference/management-api` was the last, and
 * it was held open on a product decision rather than on effort: it described a
 * bearer-key HTTP API the control plane does not have. That decision was taken
 * on 2026-08-26 — MCP is the programmatic management surface and the console is
 * the interactive one. The page then stayed titled after the absence and
 * opening with it, which is a page that answers a question before establishing
 * that anyone asked it; on 2026-09-21 it became `reference/http-api` and now
 * opens with the route that does exist, `sessions.connect`. The `ak_` reasoning
 * is still there, under "Why management is MCP and not a bearer key".
 *
 * `build/quickstart` left the list on 2026-08-25; the other eight —
 * `build/brain/{speaking,actions,tools,context,transcripts}`,
 * `build/existing-agent`, `reference/brain` and `reference/errors` — were
 * written from source and verified against it on 2026-08-26.
 *
 * Still unwritten and not yet listed: the avatar's browser surface, the faces
 * and authoring a face. They were held because the surface they describe was
 * about to be replaced, and three pages written against it would have been work
 * done twice. That replacement shipped on 2026-09-19 and every consumer moved
 * with it, so the hold has expired: what is left is effort, not a wait, and the
 * library's own `docs/` is what they get written from.
 *
 * No version appears in that sentence any more, and none should. The numbers
 * live once in `design/facts.yaml` as `avatar.npm.version` and
 * `avatar.pypi.version` — two facts because the two ends publish independently,
 * so a sentence naming *the* avatar version is wrong about one of them before
 * it is stale about both.
 *
 * ── Design is one page, and that is deliberate ──────────────────────────────
 *
 * It had seven under it until 2026-09-20. They were one argument seen from
 * seven sides — the two channels, the turn budget, heard truth, reversal,
 * parallelism, the prompt, the tool — and every one of them opened by restating
 * the other six before it could start, because none of them stands up alone.
 * Splitting an argument across seven URLs made the sidebar look like a
 * curriculum and made the writing repeat itself. So the section is one page
 * with seven headings, each old URL redirects to the heading it became
 * (`src/redirects.mjs`), and the sidebar entry is the page rather than a hub
 * over pages.
 *
 * This is not the rule for the other sections. Build and Reference are lookup:
 * a reader arrives knowing which page they want and a URL per topic is what
 * they need. Design is read once, in order, by someone who does not yet know
 * what they are looking for.
 */
export const sidebar = [
  {
    label: "Start here",
    items: [
      { label: "Current status and support", slug: "overview/status" },
    ],
  },
  {
    label: "Build an agent",
    items: [
      { label: "Overview", slug: "build" },
      { label: "How a session works", slug: "build/session" },
      { label: "Quickstart: first call", slug: "build/quickstart" },
      { label: "Connect your app", slug: "build/connect" },
      { label: "Pipecat client SDKs", slug: "build/pipecat" },
      {
        label: "Your first brain",
        items: [
          { label: "Overview", slug: "build/brain" },
          { label: "Speaking", slug: "build/brain/speaking" },
          { label: "Actions", slug: "build/brain/actions" },
          { label: "TypeScript types", slug: "build/brain/typescript" },
          { label: "Tools", slug: "build/brain/tools" },
          { label: "Context and history", slug: "build/brain/context" },
          { label: "Transcripts", slug: "build/brain/transcripts" },
        ],
      },
      { label: "Use another agent framework", slug: "build/existing-agent" },
      { label: "Deploy the brain", slug: "build/hosting" },
      { label: "Testing a brain", slug: "build/testing" },
      { label: "Keys and authentication", slug: "build/keys" },
      { label: "Add an avatar", slug: "build/avatar" },
    ],
  },
  {
    label: "Improve the agent",
    items: [
      { label: "Designing for voice", slug: "design" },
    ],
  },
  {
    label: "Operate",
    items: [
      { label: "Overview", slug: "operate" },
      { label: "Reading a call back", slug: "operate/reading-a-call" },
      { label: "Recordings", slug: "operate/recordings" },
      { label: "Usage and limits", slug: "operate/usage" },
    ],
  },
  {
    label: "API and protocols",
    items: [
      { label: "Overview", slug: "reference" },
      { label: "The Brain API", slug: "reference/brain" },
      { label: "The wire", slug: "reference/wire" },
      { label: "The RTVI plane", slug: "reference/rtvi" },
      { label: "Voice and language", slug: "reference/catalog" },
      { label: "Error codes", slug: "reference/errors" },
      { label: "The HTTP API", slug: "reference/http-api" },
      { label: "MCP server", slug: "reference/mcp" },
    ],
  },
];
