import { describe, expect, it } from "vitest";
import { PERSONA, jobFor, roleFor } from "../data/persona";
import { stillUrl } from "./Face";

describe("the agent's widget", () => {
  it("labels the dock by the job on the page, as the brain picks it", () => {
    expect(jobFor("/")).toBe("shopping");
    expect(jobFor("/shop/women/kurtas")).toBe("shopping");
    expect(jobFor("/compare")).toBe("shopping");
    expect(jobFor("/bag")).toBe("shopping");
    expect(jobFor("/p/7412")).toBe("fit");
    expect(jobFor("/p/")).toBe("fit");
    expect(jobFor("/gifts")).toBe("gifts");
    expect(jobFor("/orders")).toBe("orders");
    expect(jobFor("/returns")).toBe("returns");
    expect(jobFor("/kiosk")).toBe("kiosk");
    expect(roleFor("/p/7412")).toBe(PERSONA.roles.fit);
    expect(roleFor("/wishlist")).toBe(PERSONA.roles.shopping);
  });

  it("has a still photo for the persona's character", () => {
    expect(stillUrl).toBeTruthy();
    expect(stillUrl).toContain(PERSONA.character);
  });
});
