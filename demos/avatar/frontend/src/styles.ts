/**
 * The page's whole stylesheet, in one string.
 *
 * Inline rather than a `.css` file for the same reason every other demo does it:
 * the app is one screen, and a build that has to resolve a stylesheet is one more
 * thing between a reader and the twenty lines they came here to copy.
 *
 * Two constraints from the library shape what is here. The face is the subject,
 * so it gets the largest stable block on the page and nothing animates beside it
 * — an idle avatar is deliberately low-amplitude, and a page that pulses around
 * it destroys the effect it was tuned for. And the palette stays near-black with
 * one accent, because the avatars are separate drawings with their own colour and
 * a page that competes with them makes every face look wrong in a different way.
 */

export const STYLES = `
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #08080a; }

  .av-root {
    min-height: 100vh;
    background: radial-gradient(120% 80% at 50% -10%, #17131f 0%, #08080a 60%);
    color: #e7e5e4;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    display: flex;
    flex-direction: column;
  }

  .av-head {
    display: flex; align-items: center; gap: 10px;
    padding: 14px 22px; border-bottom: 1px solid #1c1a22;
  }
  .av-wordmark { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; color: #d4d4d8; }
  .av-badge {
    font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
    color: #a78bfa; border: 1px solid #3b2f5c; border-radius: 4px; padding: 1px 6px;
  }
  .av-headlink {
    margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
    font-size: 13px; color: #a1a1aa; text-decoration: none;
  }
  .av-headlink:hover { color: #e7e5e4; }

  /* ── the stage ───────────────────────────────────────────────────────── */

  .av-stage {
    flex: 1; width: 100%; max-width: 1080px; margin: 0 auto;
    padding: 28px 22px 40px;
    display: grid; grid-template-columns: minmax(0, 380px) minmax(0, 1fr);
    gap: 34px; align-items: start;
  }
  @media (max-width: 900px) {
    .av-stage { grid-template-columns: minmax(0, 1fr); gap: 22px; }
    .av-column { max-width: 420px; margin: 0 auto; width: 100%; }
  }

  .av-column { display: flex; flex-direction: column; gap: 14px; }

  .av-tile {
    position: relative; border-radius: 16px; overflow: hidden;
    background: #100e16; border: 1px solid #241f30;
  }
  .av-face { display: block; width: 100%; aspect-ratio: 1 / 1; }
  .av-face.is-loading { background: #100e16; }
  .av-face canvas, .av-face svg { display: block; width: 100%; height: 100%; }

  .av-chip, .av-working {
    position: absolute; left: 12px; bottom: 12px;
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(8,8,10,.72); backdrop-filter: blur(6px);
    border: 1px solid #2a2436; border-radius: 999px;
    padding: 5px 12px; font-size: 12px; color: #d4d4d8;
  }
  .av-chip-dot, .av-working-dot {
    width: 7px; height: 7px; border-radius: 50%; background: #8b5cf6;
  }
  .av-chip.is-thinking .av-chip-dot { background: #22d3ee; }
  .av-chip.is-listening .av-chip-dot { background: #4ade80; }
  .av-chip-clock {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: #71717a; padding-left: 8px; border-left: 1px solid #2a2436;
  }
  .av-working { color: #c4b5fd; border-color: #3b2f5c; }
  /* Slow, and under 1.5 Hz on purpose: the same ceiling the avatar's own idle
     motion is held to, so the page does not read as more agitated than the face. */
  .av-working-dot { animation: av-pulse 1.4s ease-in-out infinite; }
  @keyframes av-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }

  .av-controls { display: flex; align-items: center; gap: 10px; }
  .av-mic, .av-hangup {
    display: inline-flex; align-items: center; justify-content: center;
    border-radius: 999px; cursor: pointer; border: 1px solid #2a2436;
    background: #14111c; color: #e7e5e4;
  }
  .av-mic { width: 40px; height: 40px; }
  .av-mic.is-muted { background: #3f1d2b; border-color: #7f1d3a; color: #fda4af; }
  .av-hangup { width: 40px; height: 40px; background: #3f1d1d; border-color: #7f1d1d; color: #fca5a5; }
  .av-mic:hover, .av-hangup:hover { filter: brightness(1.25); }

  .av-strip { display: flex; flex-wrap: wrap; gap: 6px; }
  .av-pick {
    display: flex; flex-direction: column; align-items: flex-start; gap: 1px;
    padding: 6px 10px; border-radius: 9px; cursor: pointer;
    background: #100e16; border: 1px solid #241f30; color: #a1a1aa;
    font: inherit; text-align: left;
  }
  .av-pick:hover { border-color: #3b2f5c; color: #e7e5e4; }
  .av-pick.is-on { background: #1c1630; border-color: #7c3aed; color: #ede9fe; }
  .av-pick-name { font-size: 12px; font-weight: 600; }
  .av-pick-kind { font-size: 10px; opacity: .6; }

  /* ── the panel ───────────────────────────────────────────────────────── */

  .av-panel {
    background: #0d0c11; border: 1px solid #1f1b28; border-radius: 16px;
    padding: 26px 28px; animation: av-rise .28s ease-out;
  }
  @keyframes av-rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
  .av-panel-kicker {
    margin: 0 0 8px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: #a78bfa;
  }
  .av-panel h2 { margin: 0 0 16px; font-size: 25px; line-height: 1.2; font-weight: 650; letter-spacing: -.01em; }
  .av-panel-lede { margin: 0 0 18px; color: #a1a1aa; font-size: 14px; line-height: 1.6; max-width: 46ch; }
  .av-panel-foot { margin: 18px 0 0; color: #71717a; font-size: 13px; }

  .av-beats { margin: 0; padding: 0; list-style: none; display: grid; gap: 10px; }
  .av-beats li {
    position: relative; padding-left: 20px; font-size: 15px; line-height: 1.5; color: #d4d4d8;
  }
  .av-beats li::before {
    content: ""; position: absolute; left: 0; top: 9px;
    width: 6px; height: 6px; border-radius: 50%; background: #7c3aed;
  }

  .av-openers { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }
  .av-openers li {
    font-size: 14px; color: #c4b5fd; background: #14111c;
    border: 1px solid #241f30; border-radius: 9px; padding: 8px 12px; width: fit-content;
  }

  /* ── overlays ────────────────────────────────────────────────────────── */

  .av-connecting {
    position: fixed; left: 50%; bottom: 26px; transform: translateX(-50%);
    display: inline-flex; align-items: center; gap: 8px;
    color: #a1a1aa; font-size: 13px;
  }
  .av-spin { animation: av-rotate 1s linear infinite; }
  @keyframes av-rotate { to { transform: rotate(360deg); } }

  .av-error { color: #fca5a5; font-size: 13px; text-align: center; padding: 10px; }
  .av-error-block { margin: 60px auto; max-width: 460px; border: 1px solid #7f1d1d; border-radius: 12px; }

  .av-end {
    position: fixed; inset: 0; z-index: 900;
    background: rgba(8,8,10,.86); backdrop-filter: blur(8px);
    display: grid; place-items: center; padding: 22px;
  }
  .av-end-card {
    max-width: 460px; background: #0d0c11; border: 1px solid #2a2436;
    border-radius: 16px; padding: 30px;
  }
  .av-end-card h2 { margin: 0 0 12px; font-size: 22px; font-weight: 650; }
  .av-end-card p { margin: 0 0 18px; color: #a1a1aa; font-size: 14px; line-height: 1.6; }
  .av-end-links { display: grid; gap: 10px; margin-bottom: 20px; }
  .av-end-links a { color: #c4b5fd; font-size: 14px; text-decoration: none; }
  .av-end-links a:hover { text-decoration: underline; }
  .av-cta {
    display: inline-flex; align-items: center; gap: 8px; justify-content: center;
    background: #7c3aed; color: #fff !important; font-weight: 600;
    border-radius: 10px; padding: 11px 16px;
  }
  .av-cta:hover { background: #6d28d9; text-decoration: none !important; }
  .av-end-foot { font-size: 13px; color: #71717a; margin: 0 0 18px !important; }
  .av-end-foot a { color: #a1a1aa; }
  .av-again {
    width: 100%; background: transparent; border: 1px solid #2a2436; color: #a1a1aa;
    border-radius: 10px; padding: 9px; cursor: pointer; font: inherit; font-size: 13px;
  }
  .av-again:hover { color: #e7e5e4; border-color: #3b2f5c; }
`;
