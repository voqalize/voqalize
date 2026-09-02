/**
 * The page's whole stylesheet, in one string.
 *
 * Inline rather than a `.css` file for the same reason every other demo does it:
 * the app is one screen, and a build that has to resolve a stylesheet is one more
 * thing between a reader and the twenty lines they came here to copy.
 *
 * The design, in one paragraph, because the rules below are easier to keep
 * honest with it written down. **The page is paper and the face has its own
 * field.** Nine avatars ship with their own colour, so a page that competes with
 * them makes every face look wrong in a different way — the drawing therefore
 * sits on a fixed stage the size and shape it will really live at in a call, and
 * everything around it is a light, cool paper carrying documentation. The stage
 * is lit rather than dark: these faces are drawn as line art over a light ground
 * and read as a lit room, not a black box, which is also what keeps captions and
 * controls legible in the places a video call puts them. One accent, indigo, and
 * it only ever marks what is live, current, or a link.
 * Radius is differentiated by kind — 12px on the tile because it is a video
 * tile, 3px on code, none anywhere else — so the page cannot collapse into a
 * deck of identical cards. Nothing animates beside the avatar: an idle face is
 * deliberately low-amplitude and a page that pulses around it destroys the
 * effect it was tuned for. The one exception is the section rail, which moves
 * when the conversation moves the page, and is answering the reader.
 */

export const STYLES = `
  :root {
    --paper: #e8e9eb;
    --ink: #15171c;
    --graphite: #565c68;
    --chalk: #f7f8fa;
    --indigo: #2e2fc9;

    --rule: #cfd2d6;
    --field: #dee0e3;
    --stage-top: #f4f5fb;
    --stage-bottom: #dfe2ee;

    --sans: "Archivo", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;

    --head-h: 58px;
    color-scheme: light;
  }

  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  @media (prefers-reduced-motion: reduce) {
    html { scroll-behavior: auto; }
    * { animation: none !important; transition: none !important; }
  }
  body { margin: 0; background: var(--paper); }

  .av-root {
    min-height: 100vh;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--sans);
    font-size: 15px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }

  .av-root a { color: var(--indigo); text-underline-offset: 2px; }
  .av-root a:hover { text-decoration-thickness: 2px; }
  :focus-visible { outline: 2px solid var(--indigo); outline-offset: 2px; }
  .av-sr {
    position: absolute; width: 1px; height: 1px; overflow: hidden;
    clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap;
  }

  /* ── masthead ─────────────────────────────────────────────────────────── */

  .av-head {
    position: sticky; top: 0; z-index: 20;
    height: var(--head-h);
    display: flex; align-items: center; gap: 18px;
    padding: 0 26px;
    background: var(--paper);
    border-bottom: 1px solid var(--rule);
  }
  .av-wordmark {
    font-family: var(--mono); font-size: 14px; font-weight: 500;
    color: var(--ink); text-decoration: none; letter-spacing: -.01em;
  }
  .av-root a.av-wordmark { color: var(--ink); }
  .av-wordmark:hover { text-decoration: underline; }
  .av-licence {
    font-family: var(--mono); font-size: 11px; color: var(--graphite);
    border: 1px solid var(--rule); padding: 1px 5px;
  }
  .av-headnav { margin-left: auto; display: flex; align-items: center; gap: 18px; }
  .av-headnav a {
    font-size: 13.5px; color: var(--graphite); text-decoration: none;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .av-headnav a:hover { color: var(--ink); }

  /* ── the three columns ────────────────────────────────────────────────── */

  .av-main {
    max-width: 1300px; margin: 0 auto;
    column-gap: 0;
    display: grid;
    grid-template-columns: minmax(300px, 1fr) 26px minmax(0, 2fr);
    gap: 0 34px 0 0;
    padding: 0 26px 96px;
    align-items: start;
  }

  .av-call {
    position: sticky; top: calc(var(--head-h) + 26px);
    padding: 26px 0 0;
    display: flex; flex-direction: column; gap: 14px;
  }

  /* ── the tile: a lit stage, the one place with a real radius ───────────── */

  .av-tile {
    position: relative;
    aspect-ratio: 4 / 3;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--rule);
    background: linear-gradient(168deg, var(--stage-top) 0%, var(--stage-bottom) 100%);
    display: flex; align-items: stretch; justify-content: center;
  }
  .av-face { width: 100%; height: 100%; display: block; }

  /* The one chrome element left on the picture: who and what is happening,
     top-left. A dark plate, because it reads over a face rather than the page —
     the captions moved off the picture and are set on the page below it. */
  .av-chip {
    position: absolute; top: 10px; left: 10px; z-index: 2;
    display: flex; align-items: center; gap: 7px;
    padding: 4px 10px; border-radius: 999px;
    background: rgba(21, 23, 28, .66);
    backdrop-filter: blur(6px);
    color: #fff; font-size: 11.5px; font-weight: 500;
  }
  .av-chip .av-clock { font-family: var(--mono); font-size: 11px; opacity: .78; }

  /* ── the caption track, under the picture ─────────────────────────────── */
  /*
     A fixed band rather than one that grows: it holds the newest line at the
     bottom and clips what has scrolled off the top, so nothing below it ever
     moves — a hang-up button that slides out from under the cursor while the
     bot is mid-sentence is worse than a little empty space before the call.

     The fade duration is CAPTION_LIFE_MS in AvatarDemo.tsx. The animation takes
     a retired line to zero and the timer removes it at the same moment, so the
     removal is never a visible cut. Change one and change the other.
  */

  .av-captions {
    height: 4.6em;
    overflow: hidden;
    display: flex; flex-direction: column; justify-content: flex-end; gap: 2px;
    font-size: 13.5px; line-height: 1.5;
    max-width: 48ch;
  }
  .av-caption-past {
    margin: 0; color: var(--graphite);
    animation: av-caption-fade 11000ms linear forwards;
  }
  @keyframes av-caption-fade { from { opacity: .6 } to { opacity: 0 } }
  .av-caption-live { color: var(--ink); }
  .av-captions .vkui-root { display: block; }
  /* The kit's overlay is authored to sit on a video frame — a dark plate with
     its own radius. Here it is set on the page, so only its karaoke timing is
     wanted and none of its surface. */
  .av-caption-live .vkui-root *,
  .av-caption-live.vkui-root * {
    background: transparent; box-shadow: none; border-radius: 0;
    color: inherit; padding: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    .av-caption-past { animation: none; opacity: .45; }
  }

  .av-invite { display: flex; flex-direction: column; gap: 9px; }
  .av-invite p { margin: 0; font-size: 13px; color: var(--graphite); max-width: 44ch; }

  .av-start {
    align-self: flex-start;
    font-family: var(--sans); font-size: 14.5px; font-weight: 600;
    color: var(--chalk); background: var(--indigo);
    border: 0; border-radius: 6px; padding: 10px 20px; cursor: pointer;
  }
  .av-start:hover { background: #2426ad; }
  .av-start:disabled { opacity: .6; cursor: default; }

  .av-dot { width: 7px; height: 7px; border-radius: 50%; background: #98a0ae; flex: none; }
  .av-chip.is-listening .av-dot { background: #34d399; }
  .av-chip.is-speaking .av-dot { background: #7f80ee; }
  .av-chip.is-thinking .av-dot,
  .av-chip.is-working .av-dot { background: #f0a020; animation: av-pulse 1.4s ease-in-out infinite; }
  @keyframes av-pulse { 0%,100% { opacity: 1 } 50% { opacity: .25 } }

  /* ── the meeting controls, directly under the picture ─────────────────── */

  .av-bar { display: flex; justify-content: center; }
  .av-controls {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    border: 0; background: none; box-shadow: none; padding: 0;
  }
  .av-hangup {
    display: flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; margin-left: 2px;
    border: 0; border-radius: 9px;
    background: #c2352a; color: #fff; cursor: pointer;
  }
  .av-hangup:hover { background: #a72c22; }

  /* ── the avatar picker ────────────────────────────────────────────────── */

  .av-picker { display: flex; flex-direction: column; gap: 8px; }
  .av-picker-head {
    font-size: 12px; color: var(--graphite);
    display: flex; justify-content: space-between; align-items: baseline;
    border-top: 1px solid var(--rule); padding-top: 12px;
  }
  .av-picker-kind { font-family: var(--mono); font-size: 11px; }
  .av-strip { display: flex; flex-wrap: wrap; gap: 6px; }
  .av-pick {
    font-family: var(--sans); font-size: 13px; color: var(--graphite);
    background: transparent; border: 1px solid var(--rule); border-radius: 4px;
    padding: 4px 10px; cursor: pointer;
  }
  .av-pick:hover { color: var(--ink); border-color: var(--graphite); }
  .av-pick.is-on { color: var(--chalk); background: var(--ink); border-color: var(--ink); }

  /* ── the openers ──────────────────────────────────────────────────────── */

  .av-openers { border-top: 1px solid var(--rule); padding-top: 12px; }
  .av-openers p { margin: 0 0 8px; font-size: 12px; color: var(--graphite); }
  .av-openers ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 5px; }
  .av-openers li { font-size: 13.5px; color: var(--ink); }

  /* ── the end card, in place of the tile ───────────────────────────────── */

  .av-end {
    position: absolute; inset: 0; z-index: 4;
    background: rgba(244, 245, 249, .93);
    backdrop-filter: blur(3px);
    color: var(--ink);
    padding: 26px; display: flex; flex-direction: column; justify-content: center; gap: 12px;
  }
  .av-end h2 { margin: 0; font-size: 19px; font-weight: 600; letter-spacing: -.015em; }
  .av-end p { margin: 0; font-size: 13.5px; color: var(--graphite); }
  .av-again {
    align-self: flex-start; margin-top: 6px;
    font-family: var(--sans); font-size: 13.5px; font-weight: 600;
    color: var(--chalk); background: var(--indigo);
    border: 0; border-radius: 6px; padding: 8px 16px; cursor: pointer;
  }

  .av-error {
    font-size: 13px; color: #8f2d20;
    border-left: 2px solid #b0382a; padding-left: 10px;
  }

  /* ── the section rail ─────────────────────────────────────────────────── */
  /*
     A dope sheet, which is the drawing this library is made of: one tick per
     section, top to bottom, the current one filled. It moves when the avatar
     moves the page, which is the only motion on the page that is not the face.
  */

  .av-rail {
    position: sticky; top: calc(var(--head-h) + 26px);
    padding: 30px 0 0;
    display: flex; flex-direction: column; align-items: center;
  }
  .av-rail-track { display: flex; flex-direction: column; gap: 8px; align-items: center; }
  .av-tick {
    position: relative;
    width: 26px; height: 26px; padding: 0;
    background: transparent; border: 0; cursor: pointer;
  }
  .av-tick::before {
    content: ""; position: absolute; left: 50%; top: 6px; bottom: 6px;
    width: 2px; margin-left: -1px; background: var(--rule);
    transition: background-color .25s ease, transform .25s ease;
  }
  .av-tick:hover::before { background: var(--graphite); }
  .av-tick.is-on::before { background: var(--indigo); transform: scaleX(2.5); }
  .av-tick-label {
    position: absolute; right: calc(100% + 8px); top: 50%; transform: translateY(-50%);
    font-size: 11.5px; white-space: nowrap; color: var(--ink);
    background: var(--paper); padding: 2px 6px; border: 1px solid var(--rule);
    opacity: 0; pointer-events: none; transition: opacity .15s ease;
  }
  .av-tick:hover .av-tick-label, .av-tick:focus-visible .av-tick-label { opacity: 1; }

  /* ── the documentation ────────────────────────────────────────────────── */

  .av-docs { padding: 30px 0 0; max-width: 68ch; }

  .doc-section { scroll-margin-top: calc(var(--head-h) + 22px); padding: 0 0 40px; }
  .doc-section + .doc-section { border-top: 1px solid var(--rule); padding-top: 34px; }

  .doc-section h2 {
    margin: 0 0 14px; font-size: 26px; line-height: 1.2; font-weight: 600;
    letter-spacing: -.02em; color: var(--ink);
  }
  .doc-section.is-current h2 { position: relative; }
  .doc-section.is-current h2::before {
    content: ""; position: absolute; left: -18px; top: 4px; bottom: 4px;
    width: 3px; background: var(--indigo);
  }
  .doc-section h3 {
    margin: 26px 0 10px; font-size: 15.5px; font-weight: 600; color: var(--ink);
  }
  .doc-section p { margin: 0 0 14px; }
  .doc-lede { font-size: 17px; line-height: 1.5; color: var(--ink); }
  .doc-req { font-size: 13.5px; color: var(--graphite); }
  .doc-section code {
    font-family: var(--mono); font-size: .88em;
    background: var(--field); padding: 1px 4px; border-radius: 3px;
  }

  .doc-code { margin: 0 0 16px; }
  .doc-code figcaption {
    font-family: var(--mono); font-size: 11px; color: var(--graphite);
    padding-bottom: 5px;
  }
  .doc-code pre {
    margin: 0; padding: 14px 16px; overflow-x: auto;
    background: var(--ink); border-radius: 3px;
  }
  .doc-code code {
    font-family: var(--mono); font-size: 12.5px; line-height: 1.65;
    color: var(--chalk); background: none; padding: 0;
    white-space: pre;
  }

  .doc-grid { width: 100%; border-collapse: collapse; margin: 0 0 18px; font-size: 14px; }
  .doc-grid thead th {
    text-align: left; font-size: 12px; font-weight: 500; color: var(--graphite);
    padding: 0 12px 6px 0; border-bottom: 1px solid var(--rule);
  }
  .doc-grid tbody th {
    text-align: left; font-family: var(--mono); font-size: 12.5px; font-weight: 400;
    color: var(--ink); vertical-align: top; white-space: pre-line;
    padding: 11px 14px 11px 0; width: 30%;
    border-bottom: 1px solid var(--rule);
  }
  .doc-grid td {
    vertical-align: top; padding: 11px 0; color: var(--graphite);
    border-bottom: 1px solid var(--rule);
  }
  .doc-grid td code, .doc-grid tbody th code { background: none; padding: 0; }

  .doc-note {
    border-left: 2px solid var(--indigo); padding: 2px 0 2px 14px;
    font-size: 14px; color: var(--graphite);
  }

  .doc-step { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 0 12px; margin-bottom: 26px; }
  .doc-step-n {
    font-family: var(--mono); font-size: 13px; color: var(--graphite);
    padding-top: 1px;
  }
  .doc-step-body > h3:first-child { margin-top: 0; }

  .doc-limits { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 16px; }
  .doc-limits li { padding-left: 14px; border-left: 1px solid var(--rule); color: var(--graphite); }
  .doc-limits strong { color: var(--ink); font-weight: 600; }

  /* ── the close ────────────────────────────────────────────────────────── */

  .av-outro { border-top: 1px solid var(--rule); padding-top: 26px; max-width: 68ch; }
  .av-outro h2 { margin: 0 0 10px; font-size: 20px; font-weight: 600; letter-spacing: -.015em; }
  .av-outro p { margin: 0 0 14px; color: var(--graphite); }
  .av-outro-links { display: flex; flex-wrap: wrap; gap: 18px; font-size: 14px; }

  /* ── narrow ───────────────────────────────────────────────────────────── */

  /* The rail is the first thing to go: it is an index, and an index is a
     luxury before the reading column is safe. The two columns survive well
     below the desktop width because the prose is capped at 68ch either way. */
  @media (max-width: 1000px) {
    .av-main {
      grid-template-columns: minmax(230px, 1fr) minmax(0, 1.9fr);
      gap: 0 26px; padding: 26px 22px 64px;
    }
    .av-rail { display: none; }
    .doc-code code { font-size: 11.5px; }
    .doc-section.is-current h2::before { left: -12px; }
  }

  @media (max-width: 760px) {
    .av-main { grid-template-columns: minmax(0, 1fr); gap: 0; }
    .av-call { position: static; max-width: 440px; }
    .av-docs { padding-top: 34px; }
  }
`;
