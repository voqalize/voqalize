import { CheckCircle2, Phone } from "lucide-react";
import { Link } from "react-router-dom";
import { claimsGuide, policyById } from "../data";
import { HELPLINE } from "../components/Header";
import { fmtDate } from "../lib/format";
import { useClaim } from "../state/claim";

const FALLBACK = {
  motor: {
    next_steps: [
      "A surveyor will call you to arrange an inspection of the vehicle.",
      "Once the estimate is approved, the garage can begin repairs.",
      "We settle with the network garage directly, or pay the approved amount to your bank account.",
    ],
    turnaround: "We will be in touch within one working day.",
  },
  health: {
    next_steps: ["Our medical team reviews your claim and may ask for more documents.", "We settle the approved amount with the hospital or to your bank account."],
    turnaround: "We will be in touch within one working day.",
  },
};

export function ClaimSubmitted() {
  const submitted = useClaim((s) => s.submitted);
  if (!submitted) {
    return (
      <div className="wrap page narrow">
        <h1 className="h1">No claim submitted yet</h1>
        <p className="muted">Start a claim and we’ll show its reference here once you submit it.</p>
        <Link to="/claim" className="btn btn-primary">Make a claim</Link>
      </div>
    );
  }
  const pol = policyById(submitted.policy_id);
  const mode = submitted.mode === "reimbursement" ? "reimbursement" : "cashless";
  const guide =
    submitted.type === "motor"
      ? (claimsGuide?.motor ?? FALLBACK.motor)
      : (claimsGuide?.health?.[mode] ?? FALLBACK.health);
  const steps = guide.next_steps ?? [];
  return (
    <div className="wrap page narrow submitted">
      <div className="submitted-card">
        <CheckCircle2 size={44} className="ok-icon" aria-hidden />
        <p className="eyebrow">Claim submitted</p>
        <h1 className="h1">Your claim reference is</h1>
        <p className="reference mono" data-stage-part="claim-reference">{submitted.reference}</p>
        <p className="muted">
          {submitted.type === "motor" ? "Motor claim" : `Health claim (${mode})`}
          {pol ? ` on ${pol.plan}, ${pol.policy_number}` : ""} · {fmtDate(submitted.at.slice(0, 10))} · {submitted.documents.length} documents
        </p>
      </div>
      <section className="next-steps" aria-labelledby="next-h">
        <h2 id="next-h" className="h3">What happens next</h2>
        <ol>
          {steps.map((s, i) => (
            <li key={i}>
              <span className="step-n">{i + 1}</span>
              <span>{s}</span>
            </li>
          ))}
        </ol>
        {guide.turnaround ? <p className="turnaround">{guide.turnaround}</p> : null}
        <p className="small muted">
          <Phone size={13} aria-hidden /> Questions? Call the claims helpline on <strong>{HELPLINE}</strong> and quote {submitted.reference}.
        </p>
      </section>
      <p className="hero-ctas">
        <Link to="/my-policies" className="btn btn-primary">Back to my policies</Link>
        <Link to="/" className="btn btn-ghost">Home</Link>
      </p>
    </div>
  );
}
