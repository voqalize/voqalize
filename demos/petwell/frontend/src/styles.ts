/** The Petwell site's stylesheet — one string, mounted once by the site shell. */

export const BOOKING_CSS = `
.pw-app {
  --pw: #5c42bf; --pw-dark: #4a3596; --pw-tint: #f4f1ff; --pw-line: #e4defa;
  --ink: #1f1b2e; --muted: #6b6880; --sos: #d92d20;
  position: absolute; inset: 0; overflow-y: auto; background: var(--pw-tint);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink);
}
.pw-app *, .pw-app *::before, .pw-app *::after { box-sizing: border-box; }
.pw-app button { font: inherit; color: inherit; }
.pw-ticker { display: flex; white-space: nowrap; overflow: hidden; background: var(--pw); color: #fff;
  font-size: 12px; font-weight: 600; padding: 6px 0; }
.pw-ticker span { animation: pw-ticker 28s linear infinite; padding-right: 8px; }
@keyframes pw-ticker { to { transform: translateX(-100%); } }
.pw-top { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 10px 20px; background: #fff; border-bottom: 1px solid var(--pw-line); }
.pw-logo { display: flex; align-items: center; gap: 10px; background: none; border: 0; cursor: pointer; padding: 0; text-align: left; }
.pw-logo-mark { width: 34px; height: 34px; border-radius: 10px; background: var(--pw); color: #fff;
  display: grid; place-items: center; }
.pw-logo-name { display: block; font-weight: 800; font-size: 18px; color: var(--pw); letter-spacing: -.01em; line-height: 1.1; }
.pw-logo-sub { display: block; font-size: 11px; color: var(--muted); }
.pw-top-right { display: flex; align-items: center; gap: 12px; min-width: 0; }
.pw-sos { display: flex; align-items: center; gap: 6px; border: 1.5px solid var(--sos); color: var(--sos) !important;
  background: #fff; border-radius: 999px; padding: 6px 12px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
.pw-sos:hover { background: #fef3f2; }
.pw-body { animation: pw-in .25s ease; }
@keyframes pw-in { from { opacity: 0; transform: translateY(6px); } }

.pw-stepper { display: flex; list-style: none; margin: 0 0 18px; padding: 0; gap: 4px; }
.pw-stepper li { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 11.5px;
  color: var(--muted); position: relative; }
.pw-stepper li:not(:last-child)::after { content: ""; position: absolute; top: 11px; left: calc(50% + 14px);
  right: calc(-50% + 14px); height: 2px; background: var(--pw-line); }
.pw-stepper li.is-done::after { background: var(--pw); }
.pw-stepper li.is-done { cursor: pointer; }
.pw-dot { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-weight: 700;
  font-size: 11px; background: var(--pw-tint); color: var(--pw); border: 1.5px solid var(--pw-line); }
.pw-stepper .is-now .pw-dot { background: var(--pw); color: #fff; border-color: var(--pw); }
.pw-stepper .is-done .pw-dot { background: var(--pw); color: #fff; border-color: var(--pw); }
.pw-stepper .is-now { color: var(--pw); font-weight: 700; }

.pw-summary { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; padding-bottom: 14px; border-bottom: 1px dashed var(--pw-line); }
.pw-h1 { font-size: 28px; line-height: 1.15; margin: 4px 0 8px; color: var(--pw-dark); letter-spacing: -.02em; }
.pw-h2 { display: flex; align-items: center; gap: 8px; font-size: 20px; margin: 6px 0 14px; color: var(--pw-dark); }
.pw-h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 18px 0 8px; }
.pw-lead { color: var(--muted); margin: 0 0 18px; line-height: 1.5; }
.pw-small { color: var(--muted); font-size: 12.5px; text-align: center; margin: 10px 0 0; }
.pw-back { display: inline-flex; align-items: center; gap: 2px; background: none; border: 0; color: var(--muted) !important;
  cursor: pointer; padding: 0; font-size: 13px; }

.pw-visit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pw-visit { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; text-align: left; cursor: pointer;
  border: 1.5px solid var(--pw-line); border-radius: 16px; padding: 18px; background: #fff; transition: all .15s; }
.pw-visit:hover { border-color: var(--pw); box-shadow: 0 4px 18px rgba(92,66,191,.12); transform: translateY(-1px); }
.pw-visit-icon { width: 48px; height: 48px; border-radius: 14px; background: var(--pw-tint); color: var(--pw); display: grid; place-items: center; }
.pw-visit-title { font-weight: 800; font-size: 17px; color: var(--pw-dark); }
.pw-visit-sub { font-size: 13px; color: var(--muted); line-height: 1.4; }
.pw-sos-strip { display: flex; gap: 12px; align-items: flex-start; margin-top: 16px; padding: 14px 16px; border-radius: 14px;
  background: var(--pw-dark); color: #fff; font-size: 14px; }
.pw-sos-lines { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 4px; font-size: 12.5px; opacity: .92; }

.pw-cities { display: flex; flex-wrap: wrap; gap: 8px; }
.pw-chip { display: inline-flex; align-items: center; gap: 6px; border: 1.5px solid var(--pw-line); background: #fff;
  border-radius: 999px; padding: 7px 14px; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: all .15s; }
.pw-chip:hover { border-color: var(--pw); }
.pw-chip.is-chosen { background: var(--pw); border-color: var(--pw); color: #fff !important; }
.pw-summary .pw-chip { font-size: 12px; padding: 4px 10px; background: var(--pw-tint); border-color: transparent; color: var(--pw-dark) !important; }
.pw-chip em { font-style: normal; font-size: 10.5px; background: #fff4e5; color: #b54708; padding: 1px 6px; border-radius: 999px; }
.pw-chip.is-soon { color: var(--muted) !important; }
.pw-note { margin-top: 14px; padding: 12px 14px; border-radius: 12px; background: #fff4e5; color: #93370d; font-size: 14px; }

.pw-list { display: flex; flex-direction: column; gap: 8px; }
.pw-row { display: flex; gap: 12px; align-items: flex-start; text-align: left; width: 100%; cursor: pointer;
  border: 1.5px solid var(--pw-line); border-radius: 14px; padding: 12px 14px; background: #fff; transition: all .15s; }
.pw-row:hover { border-color: var(--pw); }
.pw-row.is-static { cursor: default; margin-bottom: 8px; }
.pw-row.is-chosen { border-color: var(--pw); background: var(--pw-tint); box-shadow: 0 0 0 3px rgba(92,66,191,.15); }
.pw-row-icon { color: var(--pw); flex: 0 0 auto; margin-top: 2px; }
.pw-row-text { display: flex; flex-direction: column; gap: 2px; }
.pw-row-title { font-weight: 700; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.pw-row-sub { font-size: 13px; color: var(--muted); }
.pw-tag { font-size: 10.5px; font-weight: 700; color: var(--sos); background: #fef3f2; padding: 2px 7px; border-radius: 999px; }

.pw-services { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.pw-service { display: flex; flex-direction: column; gap: 3px; text-align: left; cursor: pointer; padding: 12px 14px;
  border: 1.5px solid var(--pw-line); border-radius: 14px; background: #fff; transition: all .15s; }
.pw-service:hover { border-color: var(--pw); }
.pw-service.is-chosen { border-color: var(--pw); background: var(--pw-tint); box-shadow: 0 0 0 3px rgba(92,66,191,.15); }
.pw-service-name { font-weight: 700; font-size: 14.5px; }
.pw-service-blurb { font-size: 12.5px; color: var(--muted); }

.pw-dates { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; margin-bottom: 16px; }
.pw-date { display: flex; flex-direction: column; align-items: center; gap: 1px; padding: 8px 2px; cursor: pointer;
  border: 1.5px solid var(--pw-line); border-radius: 12px; background: #fff; }
.pw-date.is-chosen { background: var(--pw); border-color: var(--pw); color: #fff !important; }
.pw-date-dow { font-size: 11px; font-weight: 600; opacity: .8; }
.pw-date-day { font-size: 18px; font-weight: 800; }
.pw-date-mon { font-size: 11px; opacity: .8; }
.pw-times { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 8px; }
.pw-time { padding: 10px 0; border: 1.5px solid var(--pw-line); border-radius: 10px; background: #fff; cursor: pointer;
  font-weight: 600; font-size: 13.5px; }
.pw-time:hover { border-color: var(--pw); }
.pw-time.is-chosen { background: var(--pw); border-color: var(--pw); color: #fff !important; }

.pw-form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 14px; margin-bottom: 18px; }
.pw-field { display: flex; flex-direction: column; gap: 5px; border-radius: 10px; }
.pw-field:has(textarea), .pw-field:has(.pw-seg) { grid-column: 1 / -1; }
.pw-label { font-size: 13px; font-weight: 600; }
.pw-label i { color: var(--sos); font-style: normal; }
.pw-field input, .pw-field textarea { font: inherit; padding: 10px 12px; border: 1.5px solid var(--pw-line); border-radius: 10px;
  outline: none; background: #fff; resize: vertical; }
.pw-field input:focus, .pw-field textarea:focus { border-color: var(--pw); }
.pw-flash input, .pw-flash textarea, .pw-flash .pw-seg { animation: pw-flash 1.6s ease; }
@keyframes pw-flash { 0%, 40% { background: #ece6ff; border-color: var(--pw); } }
.pw-seg { display: flex; flex-wrap: wrap; gap: 6px; }
.pw-seg button { border: 1.5px solid var(--pw-line); border-radius: 999px; padding: 6px 14px; background: #fff; cursor: pointer; font-size: 13px; font-weight: 600; }
.pw-seg button.is-chosen { background: var(--pw); border-color: var(--pw); color: #fff !important; }

.pw-primary { width: 100%; padding: 14px; border-radius: 12px; border: 0; background: var(--pw); color: #fff !important;
  font-weight: 700; font-size: 15.5px; cursor: pointer; transition: background .15s; }
.pw-primary:hover:not(:disabled) { background: var(--pw-dark); }
.pw-primary:disabled { opacity: .45; cursor: not-allowed; }
.pw-send { margin-top: 18px; box-shadow: 0 6px 20px rgba(92,66,191,.3); animation: pw-pulse 2s ease-in-out infinite; }
@keyframes pw-pulse { 50% { box-shadow: 0 6px 28px rgba(92,66,191,.55); } }
.pw-secondary { width: 100%; margin-top: 16px; padding: 12px; border-radius: 12px; border: 1.5px solid var(--pw);
  background: #fff; color: var(--pw) !important; font-weight: 700; cursor: pointer; }

.pw-facts { margin: 0; border: 1.5px solid var(--pw-line); border-radius: 14px; overflow: hidden; }
.pw-facts > div { display: grid; grid-template-columns: 130px 1fr; gap: 10px; padding: 10px 14px; font-size: 14px; }
.pw-facts > div:nth-child(odd) { background: #faf8ff; }
.pw-facts dt { color: var(--muted); }
.pw-facts dd { margin: 0; font-weight: 600; }
.pw-facts small { display: block; font-weight: 400; color: var(--muted); font-size: 12.5px; }
.pw-done { text-align: center; }
.pw-done .pw-h2 { justify-content: center; }
.pw-done .pw-facts { text-align: left; }
.pw-done-icon { width: 64px; height: 64px; margin: 6px auto 4px; border-radius: 50%; background: #ecfdf3; color: #12b76a; display: grid; place-items: center; }
.pw-ref { color: var(--pw); font-size: 1.1em; letter-spacing: .03em; }

.pw-overlay { position: fixed; inset: 0; z-index: 20; background: rgba(31,27,46,.45); display: grid; place-items: center; padding: 16px; animation: pw-in .2s; }
.pw-sheet { position: relative; width: min(460px, 100%); max-height: 90vh; overflow-y: auto; background: #fff; border-radius: 20px; padding: 22px; }
.pw-close { position: absolute; top: 12px; right: 12px; border: 0; background: none; cursor: pointer; color: var(--muted) !important; }
.pw-sheet-head { display: flex; gap: 12px; color: var(--sos); margin-bottom: 14px; padding-right: 24px; }
.pw-sheet-head h2 { margin: 0 0 4px; font-size: 19px; color: var(--ink); }
.pw-sheet-head p { margin: 0; color: var(--muted); font-size: 13.5px; }
.pw-call { display: flex; align-items: center; gap: 12px; padding: 12px 14px; margin-bottom: 8px; border-radius: 12px;
  background: var(--sos); color: #fff; text-decoration: none; font-weight: 800; font-size: 17px; }
.pw-call small { display: block; font-size: 11.5px; font-weight: 600; opacity: .85; }

@media (max-width: 640px) {
  .pw-top { padding: 8px 12px; }
  .pw-logo-sub, .pw-sos span { display: none; }
  .pw-h1 { font-size: 24px; }
  .pw-visit-grid, .pw-form { grid-template-columns: 1fr; }
  .pw-step-label { display: none; }
  .pw-dates { gap: 4px; }
  .pw-date-day { font-size: 16px; }
  .pw-facts > div { grid-template-columns: 96px 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .pw-ticker span, .pw-send, .pw-body { animation: none; }
}
`;
