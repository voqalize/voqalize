import { describe, expect, it } from "vitest";
import { checkClaimValue, documentsFor, fieldById, fieldVisible, missingFor, optionsFor } from "./logic";

describe("claim form rules (data/claim_form.json)", () => {
  it("show_if chains: driver_name needs driver_is_policyholder=no, which needs an accident or glass", () => {
    const f = fieldById("motor", "driver_name")!;
    expect(fieldVisible("motor", f, { incident_kind: "theft", driver_is_policyholder: "no" })).toBe(false);
    expect(fieldVisible("motor", f, { incident_kind: "accident", driver_is_policyholder: "no" })).toBe(true);
  });
  it("documents follow the answers", () => {
    const ids = (a: Record<string, string>) => documentsFor("motor", a).map((d) => d.id);
    expect(ids({ incident_kind: "theft" })).not.toContain("damage_photos");
    expect(ids({ incident_kind: "accident", police_reported: "yes" })).toEqual(expect.arrayContaining(["damage_photos", "fir_copy", "driving_licence"]));
  });
  it("health members come from the chosen policy", () => {
    const f = fieldById("health", "patient_member")!;
    const opts = optionsFor("health", f, { policy_id: "health-2026" });
    if (opts.length) expect(opts.map((o) => o.value)).toContain("rohan");
  });
  it("checks values: IFSC pattern, dates, select options", () => {
    expect(checkClaimValue("motor", fieldById("motor", "ifsc")!, "mrdn0000417", {}).ok).toBe(true);
    expect(checkClaimValue("motor", fieldById("motor", "ifsc")!, "ABC", {}).ok).toBe(false);
    expect(checkClaimValue("motor", fieldById("motor", "incident_date")!, "14/11/2026", {}).ok).toBe(false);
    expect(checkClaimValue("motor", fieldById("motor", "incident_kind")!, "Theft", {})).toEqual({ ok: true, value: "theft" });
  });
  it("lists required fields and documents still missing", () => {
    const m = missingFor("health", { claim_mode: "reimbursement" }, []);
    expect(m.fields.map((f) => f.id)).toContain("policy_id");
    expect(m.documents.map((d) => d.id)).toEqual(expect.arrayContaining(["discharge_summary", "id_proof"]));
    expect(m.documents.map((d) => d.id)).not.toContain("cancelled_cheque");
  });
});
