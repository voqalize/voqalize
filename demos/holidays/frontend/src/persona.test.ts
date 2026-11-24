import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { PERSONA, pageOf, roleFor } from "./persona";

describe("persona", () => {
  it("labels the dock by the page's job, from persona.json roles", () => {
    expect(pageOf("/")).toBe("home");
    expect(pageOf("/plan")).toBe("plan");
    expect(pageOf("/checkout/")).toBe("checkout");
    expect(pageOf("/booked?ref=1")).toBe("booked");
    expect(roleFor("/plan")).toBe(PERSONA.roles.plan);
    expect(roleFor("/")).toBe(PERSONA.roles.home);
  });

  it("has a still photo for the character the idle dock shows", () => {
    expect(existsSync(resolve(__dirname, "characters", `${PERSONA.character}.webp`))).toBe(true);
  });
});
