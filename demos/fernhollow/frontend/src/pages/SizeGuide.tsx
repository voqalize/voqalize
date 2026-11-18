/**
 * /size-guide — the store's size guide (content/size_guide.json) and its
 * finder. The shopper answers by tap; with a call live the agent answers the
 * same chips through the `size.answer` move (src/stage/frontdesk.ts). The
 * answer card shows the guide's size and reason, and the section's products
 * in that size, each opening on the product page with the size selected.
 */
import { ArrowRight, Check, RotateCcw, Ruler } from "lucide-react";
import { Link } from "react-router-dom";
import { Crumbs, EmilyTag, Photo, PriceLine } from "../components/bits";
import type { Product, Variant } from "../data/catalog";
import { persona } from "../persona";
import { GUIDE, type Section, advise, asked, nextQuestion, sectionOfKind, sizedProducts, useSizeFinder } from "../sizing/finder";
import { useTitle } from "./usePage";

export function SizeGuide() {
  useTitle("Size guide");
  return (
    <div className="wrap page-pad frontdesk size-guide">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Help" }, { label: "Size guide" }]} />
      <header className="fd-hero">
        <div>
          <p className="fd-eyebrow">
            <Ruler size={15} aria-hidden /> Help · Size guide
          </p>
          <h1 className="h1">{GUIDE.title}</h1>
          <p className="lede">{GUIDE.intro}</p>
        </div>
        <nav className="fd-jump" aria-label="Sections">
          {GUIDE.sections.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="chip">
              {s.title}
            </a>
          ))}
        </nav>
      </header>

      <Finder />

      {GUIDE.sections.map((s) => (
        <GuideSection key={s.id} s={s} />
      ))}

      <p className="small fd-fine">
        This guide is general advice. Product pages list what each piece is made of and the options it comes in; ask {persona.name} if you are unsure.
      </p>
    </div>
  );
}

// ── The finder ─────────────────────────────────────────────────────────────

function Finder() {
  const answers = useSizeFinder((s) => s.answers);
  const changed = useSizeFinder((s) => s.changed);
  const set = useSizeFinder((s) => s.set);
  const reset = useSizeFinder((s) => s.reset);
  const questions = asked(answers);
  const next = nextQuestion(answers);
  const advice = advise(answers);
  const sectionId = advice?.section ?? sectionOfKind(answers.kind);
  const agentSet = changed?.by === "emily";

  return (
    <section className="fd-finder" aria-labelledby="finder-h" data-emily-start>
      <div className="fd-finder-q">
        <div className="fd-finder-head">
          <h2 className="h3" id="finder-h">
            Find your size
          </h2>
          {Object.keys(answers).length ? (
            <button type="button" className="btn-quiet fd-reset" onClick={reset}>
              <RotateCcw size={14} aria-hidden /> Start again
            </button>
          ) : null}
        </div>
        <ol className="fd-questions">
          {questions.map((q, i) => {
            const chosen = answers[q.id];
            const current = next?.id === q.id;
            return (
              <li key={q.id} className={`fd-q${current ? " is-current" : ""}${chosen ? " is-done" : ""}`} data-stage-thing={`size:${q.id}`}>
                <p className="fd-q-label">
                  <span className="fd-q-n">{chosen ? <Check size={13} aria-hidden /> : i + 1}</span>
                  {q.label}
                  {chosen && agentSet && changed?.question === q.id ? <EmilyTag /> : null}
                </p>
                <div className="fd-chips" role="group" aria-label={q.label}>
                  {q.options.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      className="chip"
                      aria-pressed={chosen === o.value}
                      data-stage-part={`size:${q.id}:${o.value}`}
                      onClick={() => set(q.id, o.value)}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
      <div className="fd-finder-a" aria-live="polite">
        {advice ? (
          <Answer size={advice.size} why={advice.why} sectionId={advice.section} />
        ) : (
          <div className="fd-answer is-empty">
            <p className="fd-answer-k">Your size</p>
            <p className="fd-answer-size">—</p>
            <p className="small">
              {next ? `Answer “${next.label}” and the guide picks a size.` : "Choose what you are sizing to begin."} Or ask {persona.name}: “I have a queen mattress — which bed?”
            </p>
          </div>
        )}
        {sectionId && !advice ? <SizedStrip sectionId={sectionId} size={null} /> : null}
      </div>
    </section>
  );
}

function Answer({ size, why, sectionId }: { size: string | null; why: string; sectionId: Section["id"] }) {
  const s = GUIDE.sections.find((x) => x.id === sectionId);
  return (
    <>
      <div className="fd-answer" data-stage-thing="size:answer">
        <p className="fd-answer-k">{size ? "The guide picks" : "The guide says"}</p>
        {size ? <p className="fd-answer-size">{size}</p> : null}
        <p className="fd-answer-why">{why}</p>
        <a className="link small" href={`#${sectionId}`}>
          More in {s?.title.toLowerCase()} <ArrowRight size={12} aria-hidden />
        </a>
      </div>
      <SizedStrip sectionId={sectionId} size={size} />
    </>
  );
}

function SizedStrip({ sectionId, size }: { sectionId: string; size: string | null }) {
  const items = sizedProducts(sectionId, size);
  const sized = sectionId === "beds" || sectionId === "vases";
  return (
    <div className="fd-strip">
      <p className="fd-strip-h">
        {sized && size ? `In ${size}` : sized ? "Comes in sizes" : "Sold by fabric"} · {items.length} pieces
      </p>
      <div className="fd-strip-row">
        {items.slice(0, 8).map(({ p, v }) => (
          <SizedCard key={p.id} p={p} v={v} size={sized ? size : null} />
        ))}
      </div>
    </div>
  );
}

export function SizedCard({ p, v, size }: { p: Product; v: Variant; size: string | null }) {
  return (
    <Link to={`/product/${p.id}?variant=${v.id}`} className="fd-mini" data-fh-thing={`product:${p.id}`}>
      <span className="fd-mini-photo">
        <Photo file={p.images[0]} alt="" sizes="160px" />
      </span>
      <span className="fd-mini-title">{p.title}</span>
      <span className="fd-mini-meta">
        <PriceLine price={v.price} compare={v.compareAtPrice} />
        {size ? <span className="fd-pill">{size}</span> : null}
      </span>
    </Link>
  );
}

// ── The guide's sections ───────────────────────────────────────────────────

function GuideSection({ s }: { s: Section }) {
  return (
    <section className="fd-section" id={s.id} aria-labelledby={`${s.id}-h`}>
      <div className="fd-section-head">
        <h2 className="h2" id={`${s.id}-h`}>
          {s.title}
        </h2>
        {s.note ? <p className="section-sub">{s.note}</p> : null}
      </div>
      <div className="fd-section-body">
        <div className="fd-visual">{VISUAL[s.id]?.(s)}</div>
        <div>
          {s.sizes ? (
            <table className="fd-table">
              <thead>
                <tr>
                  <th scope="col">Size</th>
                  <th scope="col">Suits</th>
                </tr>
              </thead>
              <tbody>
                {s.sizes.map((z) => (
                  <tr key={z.size}>
                    <th scope="row">
                      {z.size}
                      {z.standard ? <span className="small fd-std">{z.standard}</span> : null}
                    </th>
                    <td>{z.suits}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {s.layouts || s.drops ? (
            <dl className="fd-defs">
              {(s.layouts ?? s.drops ?? []).map((x) => (
                <div key={x.id}>
                  <dt>{x.label}</dt>
                  <dd>{x.text}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          <ul className="fd-rules">
            {s.rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

const ink = "var(--ink)";
const VISUAL: Record<string, (s: Section) => React.ReactNode> = {
  beds: () => (
    <svg viewBox="0 0 220 150" role="img" aria-label="A Queen and a King mattress side by side, drawn to the standard proportions" className="fd-svg">
      <rect x="14" y="30" width="60" height="80" rx="3" fill="var(--linen)" stroke={ink} />
      <rect x="20" y="36" width="22" height="12" rx="3" fill="#fff" stroke={ink} strokeWidth=".8" />
      <rect x="46" y="36" width="22" height="12" rx="3" fill="#fff" stroke={ink} strokeWidth=".8" />
      <text x="44" y="125" textAnchor="middle" className="fd-svg-t">
        Queen
      </text>
      <rect x="110" y="30" width="76" height="80" rx="3" fill="var(--linen)" stroke={ink} />
      <rect x="116" y="36" width="30" height="12" rx="3" fill="#fff" stroke={ink} strokeWidth=".8" />
      <rect x="150" y="36" width="30" height="12" rx="3" fill="#fff" stroke={ink} strokeWidth=".8" />
      <text x="148" y="125" textAnchor="middle" className="fd-svg-t">
        King
      </text>
      <text x="110" y="16" textAnchor="middle" className="fd-svg-s">
        standard mattress proportions
      </text>
    </svg>
  ),
  vases: () => (
    <svg viewBox="0 0 220 150" role="img" aria-label="A small vase on a shelf and a large vase on a console" className="fd-svg">
      <line x1="10" y1="80" x2="90" y2="80" stroke={ink} />
      <path d="M44 80c-6 0-7-6-5-12s3-9 3-14h6c0 5 1 8 3 14s1 12-5 12z" fill="var(--well)" stroke={ink} />
      <text x="50" y="102" textAnchor="middle" className="fd-svg-t">
        Small · shelf
      </text>
      <rect x="120" y="104" width="86" height="6" fill={ink} />
      <line x1="128" y1="110" x2="128" y2="140" stroke={ink} />
      <line x1="198" y1="110" x2="198" y2="140" stroke={ink} />
      <path d="M163 104c-14 0-17-14-13-30s7-24 7-38h12c0 14 3 22 7 38s1 30-13 30z" fill="var(--well)" stroke={ink} />
      <path d="M160 36c-6-12-14-18-20-20M166 36c4-14 10-22 18-26M163 36V12" stroke="var(--moss)" fill="none" />
      <text x="163" y="20" textAnchor="start" className="fd-svg-t" dx="22">
        Large
      </text>
    </svg>
  ),
  rugs: (s) => (
    <div className="fd-rugs">
      {(s.layouts ?? []).map((l) => (
        <figure key={l.id}>
          <svg viewBox="0 0 120 100" role="img" aria-label={l.label} className="fd-svg">
            {l.id === "all_legs" ? <rect x="10" y="10" width="100" height="80" fill="var(--well)" /> : null}
            {l.id === "front_legs" ? <rect x="16" y="26" width="88" height="64" fill="var(--well)" /> : null}
            {l.id === "table_only" ? <rect x="34" y="40" width="52" height="38" fill="var(--well)" /> : null}
            <rect x="20" y="14" width="80" height="18" rx="3" fill="#fff" stroke={ink} />
            <rect x="44" y="50" width="32" height="20" rx="2" fill="#fff" stroke={ink} />
            <rect x="12" y="46" width="16" height="28" rx="3" fill="#fff" stroke={ink} />
            <rect x="92" y="46" width="16" height="28" rx="3" fill="#fff" stroke={ink} />
          </svg>
          <figcaption>{l.label}</figcaption>
        </figure>
      ))}
    </div>
  ),
  curtains: (s) => (
    <svg viewBox="0 0 220 160" role="img" aria-label="A window with the rod above the frame and three curtain drops" className="fd-svg">
      <line x1="40" y1="20" x2="180" y2="20" stroke={ink} strokeWidth="2" />
      <rect x="70" y="32" width="80" height="70" fill="#fff" stroke={ink} />
      <line x1="110" y1="32" x2="110" y2="102" stroke={ink} strokeWidth=".6" />
      <rect x="64" y="102" width="92" height="4" fill={ink} />
      <line x1="10" y1="150" x2="210" y2="150" stroke={ink} />
      <rect x="46" y="22" width="16" height="78" fill="var(--well)" opacity=".9" />
      <rect x="158" y="22" width="16" height="96" fill="var(--well)" opacity=".9" />
      <rect x="184" y="22" width="16" height="126" fill="var(--well)" opacity=".9" />
      {(s.drops ?? []).map((d, i) => (
        <text key={d.id} x={[54, 166, 192][i]} y={[112, 128, 158][i]} textAnchor="middle" className="fd-svg-s">
          {["sill", "below", "floor"][i]}
        </text>
      ))}
      <text x="110" y="14" textAnchor="middle" className="fd-svg-s">
        rod above the frame, past each side
      </text>
    </svg>
  ),
};
