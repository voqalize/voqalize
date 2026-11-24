import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { landingOf, persona, roleFor } from "./persona";

describe("persona", () => {
  it("labels the dock by the page's job, from persona.json roles", () => {
    expect(landingOf("/app/transactions")).toBe("banking");
    expect(landingOf("/loans/home")).toBe("loans");
    expect(landingOf("/cards/apply?card=daily")).toBe("cards");
    expect(landingOf("/open-account")).toBe("account");
    expect(landingOf("/")).toBe("home");
    expect(roleFor("/loans/car")).toBe(persona.roles.loans);
    expect(roleFor("/app")).toBe(persona.roles.banking);
  });

  it("has a still photo for the character the idle dock shows", () => {
    expect(existsSync(resolve(__dirname, "characters", `${persona.character}.webp`))).toBe(true);
  });
});
