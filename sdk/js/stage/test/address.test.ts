import { afterEach, describe, expect, it } from "vitest";

import { clipPath, PATH_MAX, pageAddress } from "../src/address";
import { attachStage, type StageClient } from "../src/attach";
import { arrived, type Carried } from "../src/moves";

const SECRET = "https://user:pw@shop.test/orders/KT1001?key=tok_secret&email=jane%40example.com#jane@example.com";

function fakeClient() {
  const sent: { event: string; payload: unknown }[] = [];
  const client: StageClient = {
    on: () => client,
    off: () => client,
    sendUIEvent: (event, payload) => void sent.push({ event, payload }),
  };
  return { client, sent };
}

afterEach(() => {
  history.replaceState(null, "", "/");
  document.title = "";
});

describe("pageAddress", () => {
  it("keeps the origin and path, and drops the userinfo, query and fragment", () => {
    expect(pageAddress(SECRET)).toBe("https://shop.test/orders/KT1001");
    expect(pageAddress("http://localhost:5173/?a=1")).toBe("http://localhost:5173/");
  });

  it("cuts a long path, and returns nothing for what is not a URL", () => {
    const long = `https://shop.test/${"x".repeat(400)}`;
    const got = pageAddress(long);
    expect(got.length).toBe("https://shop.test".length + PATH_MAX);
    expect(got.endsWith("…")).toBe(true);
    expect(clipPath("/rooms")).toBe("/rooms");
    expect(pageAddress("not a url")).toBe("");
  });
});

describe("hello", () => {
  it("says the page's origin and path, with no query, fragment or title", () => {
    history.replaceState(null, "", "/orders/KT1001?key=tok_secret#jane@example.com");
    document.title = "Order #KT1001 — Jane";
    const f = fakeClient();
    attachStage(f.client, { onMove: () => {} }).hello();
    expect(f.sent).toHaveLength(1);
    const { event, payload } = f.sent[0]!;
    expect(event).toBe("stage_hello");
    expect(payload).toEqual({ runtime: "@voqalize/stage", contract: 1, url: `${location.origin}/orders/KT1001` });
    const text = JSON.stringify(payload);
    for (const leak of ["tok_secret", "jane@", "Jane", "KT1001 —", "title", "?", "#"]) expect(text).not.toContain(leak);
  });

  it("sends more only when the page sends its own hello", () => {
    const f = fakeClient();
    const a = attachStage(f.client, { onMove: () => {} });
    a.send({ runtime: "@voqalize/stage", contract: 1, url: "https://shop.test/a?b=c", title: "Mine" });
    expect(f.sent[0]!.payload).toMatchObject({ url: "https://shop.test/a?b=c", title: "Mine" });
  });
});

describe("arrived", () => {
  const c = (expect?: string): Carried => ({ call_ref: "k1", move: "page.open", expect }) as Carried;

  it("names hosts and paths only, never a query or a fragment", () => {
    const details = [
      arrived(c(), SECRET).detail,
      arrived(c("/orders/KT1001?key=other"), SECRET).detail,
      arrived(c("https://shop.test/cart?coupon=X#y"), SECRET).detail,
      arrived(c("http://[bad"), SECRET).detail,
    ];
    expect(details).toEqual([
      "the page loaded /orders/KT1001",
      "opened /orders/KT1001",
      "asked for shop.test/cart; the page that came up is shop.test/orders/KT1001",
      "opened /orders/KT1001",
    ]);
    for (const d of details) for (const leak of ["tok_secret", "jane", "coupon", "user", "pw", "?", "#"]) expect(d).not.toContain(leak);
  });

  it("cuts a long path in its detail", () => {
    const d = arrived(c(), `https://shop.test/${"t".repeat(500)}`).detail!;
    expect(d.length).toBeLessThan(PATH_MAX + 20);
  });
});
