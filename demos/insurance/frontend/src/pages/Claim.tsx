import { Car, Check, ChevronDown, FileUp, HeartPulse, Landmark, Paperclip, Pencil, Trash2, TriangleAlert } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { claimForm, customer } from "../data";
import type { ClaimField, ClaimSection } from "../data/types";
import {
  type ClaimType,
  checkClaimValue,
  claimPolicies,
  claimTypes,
  displayClaimValue,
  documentsFor,
  optionsFor,
  sampleFile,
  sectionProgress,
  sectionsFor,
  visibleFields,
} from "../claim/logic";
import { TalkButton } from "../components/bits";
import { fileSize, groupIndian } from "../lib/format";
import { persona } from "../persona";
import {
  claimMissing,
  openSection,
  removeDocument,
  setClaimField,
  setDeclaration,
  startClaim,
  submitClaim,
  uploadDocument,
  uploadedIds,
  applyAccountOnFile,
  useClaim,
} from "../state/claim";

const TYPE_ICON = { motor: Car, health: HeartPulse } as const;

function scrollToSection(id: string) {
  requestAnimationFrame(() =>
    document.querySelector(`[data-stage-part="claim-section:${id}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" }),
  );
}

export function ClaimPage() {
  const type = useClaim((s) => s.type);
  return (
    <div className="wrap page claim-page">
      <div className="page-head">
        <div>
          <p className="crumbs">
            <Link to="/">Home</Link> / Make a claim
          </p>
          <h1 className="h1">Make a claim</h1>
          <p className="muted">Your answers are kept as you go. Nothing is sent until you press Submit claim on the last step.</p>
        </div>
        <TalkButton className="btn btn-ghost btn-sm" label={`Fill it with ${persona.name}`} />
      </div>
      <TypeChooser type={type} />
      {type ? <ClaimForm type={type} /> : null}
    </div>
  );
}

function TypeChooser({ type }: { type: ClaimType | null }) {
  return (
    <div className={`claim-types${type ? " is-compact" : ""}`} data-stage-part="claim-types" role="radiogroup" aria-label="Claim type">
      {claimTypes.map((t) => {
        const I = TYPE_ICON[t.id];
        const n = claimPolicies(t.id).length;
        return (
          <button
            key={t.id}
            type="button"
            role="radio"
            aria-checked={type === t.id}
            className={`claim-type${type === t.id ? " is-on" : ""}`}
            data-stage-part={`claim-type:${t.id}`}
            onClick={() => startClaim(t.id)}
          >
            <span className="claim-type-icon"><I size={type ? 18 : 26} strokeWidth={1.7} aria-hidden /></span>
            <span className="claim-type-text">
              <span className="claim-type-label">{t.label}</span>
              {!type ? <span className="claim-type-hint">{t.hint}</span> : null}
              {!type ? <span className="small muted">{n} {n === 1 ? "policy" : "policies"} you can claim on</span> : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function ClaimForm({ type }: { type: ClaimType }) {
  const s = useClaim();
  const sections = sectionsFor(type);
  const uploaded = uploadedIds(s);
  const missing = claimMissing(s);
  const totalMissing = missing.fields.length + missing.documents.length;
  return (
    <div className="claim-layout" data-stage-part="claim-form">
      <nav className="rail" aria-label="Claim steps">
        <ol>
          {sections.map((sec, i) => {
            const pr = sectionProgress(type, sec, s.answers, uploaded);
            const complete = sec.id !== "review" && pr.done === pr.of;
            return (
              <li key={sec.id}>
                <button
                  type="button"
                  className={`rail-step${s.section === sec.id ? " is-on" : ""}${complete ? " is-done" : ""}`}
                  onClick={() => {
                    openSection(sec.id);
                    scrollToSection(sec.id);
                  }}
                >
                  <span className="rail-n">{complete ? <Check size={13} strokeWidth={3} aria-hidden /> : i + 1}</span>
                  <span className="rail-t">{sec.title}</span>
                </button>
              </li>
            );
          })}
        </ol>
        <p className="rail-foot small">
          {totalMissing ? `${totalMissing} required ${totalMissing === 1 ? "item" : "items"} left` : "Everything required is in"}
        </p>
      </nav>
      <div className="claim-sections">
        {sections.map((sec, i) => (
          <SectionCard key={sec.id} type={type} section={sec} index={i} last={i === sections.length - 1} next={sections[i + 1]?.id} />
        ))}
      </div>
    </div>
  );
}

function SectionCard({ type, section: sec, index, next }: { type: ClaimType; section: ClaimSection; index: number; last: boolean; next?: string }) {
  const s = useClaim();
  const open = s.section === sec.id;
  const uploaded = uploadedIds(s);
  const pr = sectionProgress(type, sec, s.answers, uploaded);
  const complete = sec.id !== "review" && pr.done === pr.of;
  const fields = visibleFields(type, sec, s.answers);
  const summary =
    sec.id === "documents"
      ? `${uploaded.length} uploaded`
      : sec.id === "review"
        ? ""
        : fields
            .map((f) => displayClaimValue(type, f, s.answers[f.id], s.answers))
            .filter(Boolean)
            .slice(0, 3)
            .join(" · ");
  return (
    <section className={`claim-card${open ? " is-open" : ""}${complete ? " is-done" : ""}`} data-stage-part={`claim-section:${sec.id}`} aria-labelledby={`cs-${sec.id}`}>
      <button type="button" className="claim-card-head" aria-expanded={open} onClick={() => openSection(open ? "" : sec.id)}>
        <span className="claim-card-n">{complete ? <Check size={14} strokeWidth={3} aria-hidden /> : index + 1}</span>
        <span className="claim-card-title" id={`cs-${sec.id}`}>
          {sec.title}
          {!open && summary ? <span className="claim-card-sum">{summary}</span> : null}
        </span>
        {sec.id !== "review" && pr.of ? (
          <span className="claim-card-pr small">
            {pr.done}/{pr.of}
          </span>
        ) : null}
        <ChevronDown size={18} className="chev" aria-hidden />
      </button>
      {open ? (
        <div className="claim-card-body">
          {sec.note ? <p className="small muted section-note">{sec.note}</p> : null}
          {sec.id === "bank" ? (
            <button type="button" className="btn btn-soft btn-sm onfile" onClick={() => applyAccountOnFile()} data-stage-part="bank-on-file">
              <Landmark size={15} aria-hidden /> Use my account on file ({customer.bank_on_file.masked})
            </button>
          ) : null}
          {sec.id === "documents" ? <Documents type={type} /> : null}
          {sec.id === "review" ? <Review type={type} /> : null}
          {fields.length ? (
            <div className="field-grid">
              {fields.map((f) => (
                <ClaimFieldControl key={f.id} type={type} field={f} />
              ))}
            </div>
          ) : null}
          {next ? (
            <div className="claim-card-foot">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  openSection(next);
                  scrollToSection(next);
                }}
              >
                {next === "review" ? "Review your claim" : "Continue"}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function ClaimFieldControl({ type, field: f }: { type: ClaimType; field: ClaimField }) {
  const answers = useClaim((s) => s.answers);
  const showMissing = useClaim((s) => s.showMissing);
  const value = answers[f.id] ?? "";
  const checked = value ? checkClaimValue(type, f, value, answers) : null;
  const error = checked && !checked.ok ? checked.why : null;
  const opts = f.type === "select" ? optionsFor(type, f, answers) : [];
  const segmented = f.type === "select" && !f.options_from && opts.length <= 3;
  const id = `cf-${f.id}`;
  const ref = useRef<HTMLDivElement>(null);
  const prev = useRef(value);
  useEffect(() => {
    if (prev.current === value || !ref.current) return;
    prev.current = value;
    ref.current.classList.remove("is-flash");
    void ref.current.offsetWidth;
    ref.current.classList.add("is-flash");
  }, [value]);
  const set = (v: string) => setClaimField(f.id, v);
  let control: ReactNode;
  if (segmented) {
    control = (
      <div className="seg" role="radiogroup" aria-labelledby={`${id}-l`}>
        {opts.map((o) => (
          <button key={o.value} type="button" role="radio" aria-checked={value === o.value} className={`seg-btn${value === o.value ? " is-on" : ""}`} onClick={() => set(o.value)}>
            {o.label}
          </button>
        ))}
      </div>
    );
  } else if (f.type === "select") {
    control = (
      <select id={id} className="input" value={value} onChange={(e) => set(e.target.value)}>
        <option value="" disabled>
          {opts.length ? "Choose…" : f.options_from === "members" ? "Choose the policy first" : "Choose…"}
        </option>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  } else if (f.type === "textarea") {
    control = <textarea id={id} className="input" rows={3} value={value} onChange={(e) => set(e.target.value)} />;
  } else if (f.type === "money") {
    control = (
      <div className="input-affix">
        <span aria-hidden>₹</span>
        <input id={id} className="input" inputMode="numeric" value={value ? groupIndian(Number(value)) : ""} onChange={(e) => set(e.target.value.replace(/\D/g, ""))} />
      </div>
    );
  } else {
    control = (
      <input
        id={id}
        className="input"
        type={f.type === "date" ? "date" : f.type === "time" ? "time" : "text"}
        value={value}
        autoComplete="off"
        onChange={(e) => set(f.pattern ? e.target.value.toUpperCase() : e.target.value)}
      />
    );
  }
  const missing = showMissing > 0 && !f.optional && !value;
  return (
    <div
      ref={ref}
      className={`field${f.type === "textarea" || (segmented && opts.length === 3) ? " field-wide" : ""}${error ? " has-error" : ""}${missing ? " has-missing" : ""}`}
      data-stage-part={`claim-field:${f.id}`}
    >
      <label className="field-label" id={`${id}-l`} htmlFor={segmented ? undefined : id}>
        {f.label}
        {f.optional ? <span className="muted"> (optional)</span> : null}
      </label>
      {control}
      {error ? <p className="field-error">{error}</p> : missing ? <p className="field-error">Needed to submit</p> : null}
    </div>
  );
}

function Documents({ type }: { type: ClaimType }) {
  const s = useClaim();
  const docs = documentsFor(type, s.answers);
  return (
    <ul className="doc-list" data-stage-part="doc-list">
      {docs.map((d) => {
        const up = s.uploads[d.id];
        return (
          <li key={d.id} className={`doc-row${up && up.progress >= 100 ? " is-done" : ""}`} data-stage-part={`doc:${d.id}`}>
            <div className="doc-row-main">
              <span className="doc-icon">{up && up.progress >= 100 ? <Check size={16} strokeWidth={3} aria-hidden /> : <Paperclip size={16} aria-hidden />}</span>
              <div className="doc-text">
                <p className="doc-label">
                  {d.label} <span className={`tag ${d.optional ? "tag-opt" : "tag-req"}`}>{d.optional ? "Optional" : "Required"}</span>
                </p>
                {up ? (
                  up.progress < 100 ? (
                    <div className="upload-bar" role="progressbar" aria-valuenow={up.progress} aria-valuemin={0} aria-valuemax={100} aria-label={`Uploading ${up.name}`}>
                      <span style={{ width: `${up.progress}%` }} />
                    </div>
                  ) : (
                    <p className="small doc-file">
                      {up.name} · {fileSize(up.size)}
                    </p>
                  )
                ) : (
                  <p className="small muted">PDF, JPG or PNG, up to 10 MB</p>
                )}
              </div>
            </div>
            <div className="doc-actions">
              {up && up.progress >= 100 ? (
                <button type="button" className="link-btn small danger" onClick={() => removeDocument(d.id)}>
                  <Trash2 size={14} aria-hidden /> Remove
                </button>
              ) : up ? (
                <span className="small muted">Uploading…</span>
              ) : (
                <>
                  <label className="btn btn-ghost btn-sm file-btn">
                    <FileUp size={14} aria-hidden /> Choose file
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,.zip"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadDocument(d.id, { name: file.name, size: file.size });
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <button type="button" className="link-btn small" onClick={() => uploadDocument(d.id, sampleFile(d.id))}>
                    Use sample file
                  </button>
                </>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Review({ type }: { type: ClaimType }) {
  const s = useClaim();
  const navigate = useNavigate();
  const sections = sectionsFor(type).filter((x) => x.id !== "review");
  const missing = claimMissing(s);
  const nMissing = missing.fields.length + missing.documents.length;
  const ready = nMissing === 0 && s.declaration;
  const uploaded = uploadedIds(s);
  const docs = documentsFor(type, s.answers);
  return (
    <div className="review">
      {nMissing ? (
        <div className="review-missing" role="status">
          <p>
            <TriangleAlert size={16} aria-hidden /> <strong>{nMissing} {nMissing === 1 ? "thing" : "things"} still needed</strong> before you can submit:
          </p>
          <ul>
            {missing.fields.map((f) => (
              <li key={f.id}>
                <button type="button" className="link-btn" onClick={() => { openSection(f.section); scrollToSection(f.section); }}>
                  {f.label}
                </button>
              </li>
            ))}
            {missing.documents.map((d) => (
              <li key={d.id}>
                <button type="button" className="link-btn" onClick={() => { openSection("documents"); scrollToSection("documents"); }}>
                  Upload: {d.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="review-ok">
          <Check size={16} strokeWidth={3} aria-hidden /> Every required answer and document is in. Check them once more, then submit.
        </p>
      )}
      <div className="review-grid">
        {sections.map((sec) => {
          const rows =
            sec.id === "documents"
              ? docs.map((d) => ({ k: d.label, v: s.uploads[d.id]?.progress === 100 ? s.uploads[d.id].name : d.optional ? "Not added (optional)" : "" }))
              : visibleFields(type, sec, s.answers).map((f) => ({ k: f.label, v: displayClaimValue(type, f, s.answers[f.id], s.answers) || (f.optional ? "Not given (optional)" : "") }));
          return (
            <div key={sec.id} className="review-block">
              <div className="review-block-head">
                <h3>{sec.title}</h3>
                <button type="button" className="link-btn small" onClick={() => { openSection(sec.id); scrollToSection(sec.id); }}>
                  <Pencil size={13} aria-hidden /> Edit
                </button>
              </div>
              <dl>
                {rows.map((r) => (
                  <div key={r.k}>
                    <dt>{r.k}</dt>
                    <dd className={r.v ? "" : "is-missing"}>{r.v || "Missing"}</dd>
                  </div>
                ))}
              </dl>
            </div>
          );
        })}
      </div>
      <label className={`declaration${s.declaration ? " is-on" : ""}`} data-stage-part="declaration">
        <input type="checkbox" checked={s.declaration} onChange={(e) => setDeclaration(e.target.checked)} />
        <span>{claimForm.review.declaration}</span>
      </label>
      <div className="submit-row">
        <button
          type="button"
          className="btn btn-primary btn-lg"
          disabled={!ready}
          data-stage-part="submit-claim"
          onClick={() => {
            if (submitClaim()) navigate("/claim/submitted");
          }}
        >
          Submit claim
        </button>
        <p className="small muted">
          {nMissing ? "Fill in what’s missing to submit." : s.declaration ? `${uploaded.length} documents attached.` : "Tick the declaration to submit."}
        </p>
      </div>
    </div>
  );
}
