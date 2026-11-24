/**
 * The dock's role label follows the page's job, by the brain's own rule
 * (`job_of` in backend/brain.py), and every job has a label in persona.json.
 */
import { describe, expect, it } from "vitest";
import { jobOf, PERSONA, roleFor } from "./persona";

describe("role label", () => {
  it("takes the job the brain takes on each page", () => {
    expect(jobOf("/")).toBe("sdr");
    expect(jobOf("/modules/declarations")).toBe("sdr");
    expect(jobOf("/tax")).toBe("sdr");
    expect(jobOf("/customers")).toBe("sdr");
    expect(jobOf("/pricing")).toBe("pricing");
    expect(jobOf("/book-demo")).toBe("booker");
    expect(jobOf("/demos/payroll_site/book-demo")).toBe("booker");
  });
  it("reads every job's label from persona.json", () => {
    for (const job of ["sdr", "pricing", "booker"] as const) expect(PERSONA.roles[job]).toBeTruthy();
    expect(roleFor("/pricing")).toBe(PERSONA.roles.pricing);
  });
});
