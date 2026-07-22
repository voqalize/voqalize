/**
 * The demos landing page — a directory of every demo, read straight from the
 * shared manifest (`demos/manifest.json`). Each card links to `/{name}`, the
 * demo's own entrypoint. Keeping this manifest-driven means adding a demo never
 * touches this file.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import manifest from "../../../manifest.json";

interface DemoEntry {
  name: string;
  title: string;
  tagline: string;
}

const DEMOS = (manifest as { demos: DemoEntry[] }).demos;

const VERMILION = "#E24E2A";
const ACTION = "#C23F1E";

function Landing() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#FAF6F0",
        color: "#1A1613",
        fontFamily: "'Inter',system-ui,-apple-system,sans-serif",
        padding: "64px 24px",
      }}
    >
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span style={{ width: 12, height: 12, borderRadius: "50%", background: VERMILION }} />
          <span style={{ fontWeight: 800, fontSize: 20, letterSpacing: "-.02em" }}>Voqalize demos</span>
        </div>
        <p style={{ color: "#6E665C", fontSize: 15, lineHeight: 1.5, margin: "0 0 40px" }}>
          Runnable voice apps — each one is example code, a live demo, and an integration
          test. You bring the brain, we bring the voice.
        </p>

        <div style={{ display: "grid", gap: 14 }}>
          {DEMOS.map((d) => (
            <a
              key={d.name}
              href={`/${d.name}`}
              style={{
                display: "block",
                padding: "20px 22px",
                background: "#FFFDFA",
                border: "1px solid #E3DACD",
                borderRadius: 14,
                textDecoration: "none",
                color: "inherit",
              }}
            >
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
                <span style={{ fontWeight: 700, fontSize: 16 }}>{d.title}</span>
                <span style={{ color: ACTION, fontSize: 13, fontWeight: 600 }}>Open →</span>
              </div>
              <p style={{ margin: "6px 0 0", color: "#6E665C", fontSize: 13.5, lineHeight: 1.45 }}>
                {d.tagline}
              </p>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Landing />
  </StrictMode>,
);
