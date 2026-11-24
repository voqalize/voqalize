import { describe, expect, it } from "vitest";
import { PERSONA, jobFor, roleFor } from "./persona";
import { withSlash } from "./state/nav";

describe("the dock's role label follows the page's job (the brain's mode_for)", () => {
  it("maps /welcome to onboarding, / and /help to support, the rest to coach", () => {
    expect(jobFor("/welcome")).toBe("onboarding");
    expect(jobFor("/")).toBe("support");
    expect(jobFor("")).toBe("support");
    expect(jobFor("/help")).toBe("support");
    expect(jobFor("/help/")).toBe("support");
    expect(jobFor("/reimbursements")).toBe("coach");
    expect(jobFor("/tax/regime/BB-1007?x=1")).toBe("coach");
    expect(roleFor("/welcome")).toBe(PERSONA.roles.onboarding);
    expect(roleFor("/leave")).toBe(PERSONA.roles.coach);
  });
});

describe("the app's home keeps its slash (A2)", () => {
  it("adds the slash to the bare base only", () => {
    expect(withSlash("/demos/payroll_app", "/demos/payroll_app")).toBe("/demos/payroll_app/");
    expect(withSlash("/demos/payroll_app/", "/demos/payroll_app")).toBeNull();
    expect(withSlash("/demos/payroll_app/leave", "/demos/payroll_app")).toBeNull();
  });
});
