/**
 * The policy document on screen: which one, which section, and the clause the
 * agent marked (one at a time). `policy.viewed` goes to the brain on open and
 * on a section change.
 */
import { create } from "zustand";
import { emit } from "../stage/events";

export type Verdict = "covered" | "not_covered" | "covered_with_limits" | "depends";

export const VERDICT_LABEL: Record<Verdict, string> = {
  covered: "Covered",
  not_covered: "Not covered",
  covered_with_limits: "Covered with limits",
  depends: "Depends",
};

interface PolicyViewState {
  policyId: string | null;
  section: string | null;
  mark: { policyId: string; clauseId: string; verdict: Verdict; n: number } | null;
}

export const usePolicyView = create<PolicyViewState>(() => ({ policyId: null, section: null, mark: null }));

export function viewPolicy(policyId: string, section: string | null = null) {
  const s = usePolicyView.getState();
  if (s.policyId === policyId && s.section === section) return;
  usePolicyView.setState({
    policyId,
    section,
    mark: s.mark && s.mark.policyId === policyId ? s.mark : null,
  });
  emit("policy.viewed", { policy_id: policyId, section });
}

let n = 0;
export function markClause(policyId: string, clauseId: string, verdict: Verdict) {
  usePolicyView.setState({ mark: { policyId, clauseId, verdict, n: ++n } });
}

export function clearMark() {
  usePolicyView.setState({ mark: null });
}

export function leavePolicy() {
  usePolicyView.setState({ policyId: null, section: null, mark: null });
}
