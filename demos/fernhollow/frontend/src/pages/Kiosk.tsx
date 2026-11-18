/**
 * /kiosk — the same store as a portrait showroom totem (designed at
 * 1080×1920; on a landscape screen the portrait frame is centred and scaled,
 * every size in container units). Attract screen → room → feel → spend →
 * three picks with reasons and a QR code that opens them on the phone. The
 * picks come from backend/data/edits.json, the list the agent reads. Works by
 * tap; the agent answers the same tiles with `kiosk.answer`. Ninety seconds
 * untouched on the picks, it goes back to the attract screen.
 */
import { ArrowLeft, ChevronRight, Mic, RotateCcw, Smartphone } from "lucide-react";
import qrcode from "qrcode-generator";
import { useEffect, useMemo } from "react";
import { Wordmark } from "../components/Header";
import { Photo } from "../components/bits";
import { type RoomId, getProduct, getVariant, money, productsIn, roomCover } from "../data/catalog";
import { KIOSK, type KioskScreen, kioskKey, kioskOption, useEdits, useKiosk } from "../frontdesk/edits";
import { persona } from "../persona";
import { useVoiceClient } from "../stage/client";
import { voiceReady } from "../voice/VoiceDock";
import { useTitle } from "./usePage";

const IDLE_MS = 90_000;
const STEPS: ("room" | "feel" | "budget")[] = ["room", "feel", "budget"];

/** The URL the QR code carries: the three picks, on this store, on the phone. */
export function picksUrl(ids: string[]): string {
  return `${window.location.origin}${import.meta.env.BASE_URL}my-picks?ids=${ids.join(",")}&from=kiosk`;
}

export function Kiosk() {
  useTitle("Showroom");
  const screen = useKiosk((s) => s.screen);

  // Untouched on the picks for a while: back to the attract screen.
  useEffect(() => {
    if (screen !== "picks") return;
    let t = window.setTimeout(() => useKiosk.getState().restart(), IDLE_MS);
    const touched = () => {
      window.clearTimeout(t);
      t = window.setTimeout(() => useKiosk.getState().restart(), IDLE_MS);
    };
    window.addEventListener("pointerdown", touched);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("pointerdown", touched);
    };
  }, [screen]);

  return (
    <div className="kiosk-stage">
      <div className={`kiosk-frame is-${screen}`}>
        <header className="kiosk-bar">
          <Wordmark still />
          <span className="kiosk-where">Showroom</span>
          {screen !== "attract" ? (
            <button type="button" className="kiosk-restart" data-stage-part="kiosk:restart" onClick={() => useKiosk.getState().restart()}>
              <RotateCcw aria-hidden /> Start over
            </button>
          ) : null}
        </header>
        <main className="kiosk-main">
          {screen === "attract" ? <Attract /> : screen === "picks" ? <Picks /> : <Ask step={screen} />}
        </main>
      </div>
    </div>
  );
}

function Attract() {
  const covers = useMemo(() => (["living", "bedroom", "dining", "home-office"] as RoomId[]).map((r) => roomCover(r)), []);
  const begin = useVoiceClient((s) => s.begin);
  const live = useVoiceClient((s) => s.live);
  return (
    <button type="button" className="kiosk-attract" data-stage-part="kiosk:start" onClick={() => useKiosk.getState().start()} aria-label="Touch to start">
      <span className="kiosk-collage" aria-hidden>
        {covers.map((p, i) => (
          <span key={p.id} className={`kiosk-tile t${i}`}>
            <Photo file={p.images[0]} alt="" size={1000} sizes="50vw" eager />
          </span>
        ))}
      </span>
      <span className="kiosk-attract-copy">
        <span className="kiosk-kicker">Fernhollow showroom</span>
        <span className="kiosk-headline">{KIOSK.headline}</span>
        <span className="kiosk-sub">Three questions, three pieces picked for you, and a code to take them home on your phone.</span>
        <span className="kiosk-touch">
          {KIOSK.attract} <ChevronRight aria-hidden />
        </span>
        {voiceReady() && begin && !live ? (
          <span
            role="button"
            tabIndex={0}
            className="kiosk-talk"
            onClick={(e) => {
              e.stopPropagation();
              useKiosk.getState().start();
              begin();
            }}
          >
            <Mic aria-hidden /> Talk to {persona.name}
          </span>
        ) : null}
      </span>
    </button>
  );
}

const FEEL_SWATCH: Record<string, string[]> = {
  warm_wood: ["#9a6a43", "#c8955f", "#5e3d25"],
  soft_neutrals: ["#efe7da", "#d9cbb6", "#b9a88e"],
  clean_lines: ["#1d2520", "#f4f4f2", "#8b918c"],
  natural_texture: ["#d7cbb2", "#a99a7a", "#efe9dc"],
};

function Ask({ step }: { step: KioskScreen }) {
  const q = KIOSK.questions.find((x) => x.id === step)!;
  const answers = useKiosk((s) => s.answers);
  const changed = useKiosk((s) => s.changed);
  const n = STEPS.indexOf(step as (typeof STEPS)[number]);
  const back = () => useKiosk.getState().go(n === 0 ? "attract" : STEPS[n - 1]);
  return (
    <section className="kiosk-ask" aria-labelledby="kq">
      <div className="kiosk-progress" aria-label={`Question ${n + 1} of 3`}>
        {STEPS.map((s, i) => (
          <span key={s} className={i < n ? "is-done" : i === n ? "is-now" : ""} />
        ))}
      </div>
      <p className="kiosk-step">Question {n + 1} of 3</p>
      <h1 className="kiosk-q" id="kq">
        {q.label}
      </h1>
      <div className={`kiosk-tiles q-${q.id}`}>
        {q.options.map((o) => {
          const on = answers[q.id] === o.value;
          const agent = on && changed?.by === "emily" && changed.question === q.id;
          return (
            <button
              key={o.value}
              type="button"
              className={`kiosk-opt${on ? " is-on" : ""}`}
              aria-pressed={on}
              data-stage-part={`kiosk:${q.id}:${o.value}`}
              onClick={() => useKiosk.getState().answer(q.id, o.value)}
            >
              {q.id === "room" ? (
                <span className="kiosk-opt-photo" aria-hidden>
                  <Photo file={roomCover(o.value as RoomId).images[0]} alt="" sizes="40vw" />
                </span>
              ) : q.id === "feel" ? (
                <span className="kiosk-opt-swatch" aria-hidden>
                  {(FEEL_SWATCH[o.value] ?? []).map((c) => (
                    <span key={c} style={{ background: c }} />
                  ))}
                </span>
              ) : (
                <span className="kiosk-opt-num" aria-hidden>
                  {o.max ? money(o.max) : "∞"}
                </span>
              )}
              <span className="kiosk-opt-label">{o.label}</span>
              {q.id === "room" ? <span className="kiosk-opt-sub">{productsIn(o.value as RoomId).length} pieces</span> : null}
              {agent ? <span className="kiosk-agent">{persona.name}</span> : null}
            </button>
          );
        })}
      </div>
      <button type="button" className="kiosk-back" onClick={back}>
        <ArrowLeft aria-hidden /> Back
      </button>
    </section>
  );
}

function Picks() {
  const answers = useKiosk((s) => s.answers);
  const edits = useEdits();
  const picks = edits?.kiosk[kioskKey(answers.room ?? "", answers.feel ?? "", answers.budget ?? "")] ?? [];
  const room = kioskOption("room", answers.room)?.label ?? "";
  const feel = kioskOption("feel", answers.feel)?.label ?? "";
  const budget = kioskOption("budget", answers.budget)?.label ?? "";
  const url = picksUrl(picks.map((p) => p.product_id));
  return (
    <section className="kiosk-picks" aria-labelledby="kp">
      <p className="kiosk-step">
        {room} · {feel} · {budget}
      </p>
      <h1 className="kiosk-q" id="kp">
        Your three
      </h1>
      <ol className="kiosk-pick-list">
        {picks.map((pick, i) => {
          const p = getProduct(pick.product_id);
          if (!p) return null;
          const v = getVariant(p, pick.variant_id);
          return (
            <li key={p.id} className="kiosk-pick" data-fh-thing={`product:${p.id}`} data-stage-part={`kiosk:pick:${p.id}`}>
              <span className="kiosk-pick-photo">
                <Photo file={p.images[0]} alt="" size={1000} sizes="40vw" />
                <span className="kiosk-pick-n">{i + 1}</span>
              </span>
              <span className="kiosk-pick-body">
                <span className="kiosk-pick-cat">{p.category}</span>
                <span className="kiosk-pick-title">{p.title}</span>
                <span className="kiosk-pick-price">
                  {money(v.price)}
                  {v.compareAtPrice && v.compareAtPrice > v.price ? <s>{money(v.compareAtPrice)}</s> : null}
                </span>
                <span className="kiosk-pick-why">{pick.reason}</span>
              </span>
            </li>
          );
        })}
      </ol>
      {picks.length ? (
        <div className="kiosk-take" data-stage-thing="kiosk:qr">
          <QrCode text={url} />
          <div>
            <p className="kiosk-take-h">
              <Smartphone aria-hidden /> Take them with you
            </p>
            <p className="kiosk-take-p">Scan with your phone camera to open these three on fernhollow, ready to save or buy.</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}

/** A QR code as one SVG path (qrcode-generator does the encoding). */
export function QrCode({ text }: { text: string }) {
  const { d, n } = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    const count = qr.getModuleCount();
    let path = "";
    for (let r = 0; r < count; r++) for (let c = 0; c < count; c++) if (qr.isDark(r, c)) path += `M${c + 4} ${r + 4}h1v1h-1z`;
    return { d: path, n: count + 8 };
  }, [text]);
  return (
    <svg className="kiosk-qr" viewBox={`0 0 ${n} ${n}`} role="img" aria-label="QR code that opens your three picks on your phone" data-url={text} shapeRendering="crispEdges">
      <rect width={n} height={n} fill="#fff" />
      <path d={d} fill="#1d2520" />
    </svg>
  );
}
