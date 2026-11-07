// Makes the voice the builder's preview speaks in: the replayed turn's lines,
// spoken by the Voqalize speech tier in the voice each offered character
// speaks in, with the speech tier's own word timings and the mouth cues the
// voice runtime would send for that audio.
//
//   VQL_SPEECH_KEY=/path/to/runtime-signing-key.pem \
//   VQL_CUES="/path/to/cue-maker -language en -voice" \
//   node builder/fixtures/make.mjs
//
// - VQL_SPEECH_KEY (required): a private key the speech tier trusts. The token
//   minted from it is never printed or written anywhere.
// - VQL_SPEECH_URL: the speech tier's TTS socket, wss://speech.dev.voqalize.com by default.
// - VQL_CATALOG: the control plane's public catalogue, which says which voice
//   each character speaks in (the first of its suggested voices).
// - VQL_CUES: the voice runtime's own cue maker, as a command line that takes
//   the voice id as its last argument, reads the speech tier's
//   `phoneme_timestamps` messages on stdin and writes the mouth track a call
//   sends. Without it the clips carry no cues, and the face follows the
//   audio's loudness alone.
//
// Writes, beside this file: `<voice>-<context>.webm` (Opus) and `voices.json`.
// Needs ffmpeg on the PATH.

import { spawnSync } from "node:child_process";
import { createSign, randomBytes } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));

/** The characters the builder offers by name. The builder's list is read from what this writes. */
const CHARACTERS = ["emily", "tara", "ananya", "javier", "tess", "tanya", "tanvi", "tushar"];

/** What the agent says in the replayed turn, by TTS context: one context per reply, as a call has. */
const LINES = {
  open: ["Hi there! This is how I'd look and sound on your site.", "What would you like to know?"],
  reply: ["Of course. Tell me roughly how many people will use it."],
};

const LANGUAGE = "en";
const SAMPLE_RATE = 24000;
const SPEECH_URL = process.env.VQL_SPEECH_URL ?? "wss://speech.dev.voqalize.com";
const CATALOG = process.env.VQL_CATALOG ?? "https://app.dev.voqalize.com/api/v1/catalog.get";

function fail(msg) {
  console.error(`make: ${msg}`);
  process.exit(2);
}

const b64url = (b) => Buffer.from(b).toString("base64url");

/** The speech tier's token: RS256, the claims the voice runtime mints. */
async function token() {
  const path = process.env.VQL_SPEECH_KEY;
  if (!path) fail("VQL_SPEECH_KEY must name a private key the speech tier trusts");
  const key = await readFile(path, "utf8");
  const now = Math.floor(Date.now() / 1000);
  const head = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const body = b64url(JSON.stringify({ iss: "pygato", aud: "vql-speech", sub: "vql-builder-fixtures", iat: now, exp: now + 600 }));
  const sig = createSign("RSA-SHA256").update(`${head}.${body}`).sign(key);
  return `${head}.${body}.${b64url(sig)}`;
}

/** One context spoken: its audio, its words and the raw phone messages, as the socket sent them. */
function speak(jwt, voice, ctx, sentences) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`${SPEECH_URL}/tts/websocket?api_key=${jwt}&cartesia_version=2025-11-04`);
    const pcm = [];
    const words = [];
    const phones = [];
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error(`${voice} ${ctx}: no answer in time`));
    }, 60_000);
    ws.onopen = () => {
      sentences.forEach((transcript, i) => {
        const msg = { transcript, continue: true, context_id: ctx };
        if (i === 0) {
          Object.assign(msg, {
            model_id: "sonic-2",
            voice: { mode: "id", id: `omnivoice/${voice}` },
            language: LANGUAGE,
            output_format: { container: "raw", encoding: "pcm_s16le", sample_rate: SAMPLE_RATE },
            add_timestamps: true,
            add_phoneme_timestamps: true,
            use_normalized_timestamps: false,
            max_buffer_delay_ms: 0,
          });
        }
        ws.send(JSON.stringify(msg));
      });
      ws.send(JSON.stringify({ transcript: "", continue: false, context_id: ctx }));
    };
    ws.onmessage = (ev) => {
      const raw = String(ev.data);
      const m = JSON.parse(raw);
      if (m.type === "chunk" && m.data) pcm.push(Buffer.from(m.data, "base64"));
      else if (m.type === "timestamps") {
        const w = m.word_timestamps;
        w.words.forEach((text, i) => words.push({ text, start: w.start[i], end: w.end[i] }));
      } else if (m.type === "phoneme_timestamps") phones.push(raw);
      else if (m.type === "error") {
        clearTimeout(timer);
        ws.close();
        reject(new Error(`${voice} ${ctx}: ${m.error ?? m.message ?? "error"}`));
      } else if (m.type === "done") {
        clearTimeout(timer);
        ws.close(1000);
        resolve({ pcm: Buffer.concat(pcm), words, phones });
      }
    };
    ws.onerror = () => {
      clearTimeout(timer);
      reject(new Error(`${voice} ${ctx}: the socket failed`));
    };
  });
}

/** The mouth track the voice runtime would send for these phones, from its own code. */
function cues(voice, phones) {
  const cmd = process.env.VQL_CUES;
  if (!cmd) return undefined;
  const r = spawnSync(`${cmd} omnivoice/${voice}`, {
    shell: true,
    input: phones.join("\n") + "\n",
    encoding: "utf8",
  });
  if (r.status !== 0) fail(`the cue maker for ${voice}: ${r.stderr}`);
  return JSON.parse(r.stdout);
}

function opus(pcm, out) {
  const r = spawnSync(
    "ffmpeg",
    ["-hide_banner", "-loglevel", "error", "-y", "-f", "s16le", "-ar", String(SAMPLE_RATE), "-ac", "1", "-i", "-",
      "-c:a", "libopus", "-b:a", "24k", "-application", "voip", out],
    { input: pcm },
  );
  if (r.status !== 0) fail(`ffmpeg: ${r.stderr}`);
}

/** The words of each sentence, with when each starts in ms from the context's first sample. */
function sentencesOf(sentences, words) {
  const out = [];
  let k = 0;
  for (const text of sentences) {
    const n = text.split(/\s+/).filter(Boolean).length;
    const mine = words.slice(k, k + n);
    k += n;
    out.push({ text, words: mine.map((w) => ({ text: w.text, at: Math.round(w.start * 1000) })) });
  }
  if (k !== words.length) fail(`the speech tier timed ${words.length} words where the lines have ${k}`);
  return out;
}

const catalog = await fetch(CATALOG).then((r) => (r.ok ? r.json() : fail(`${CATALOG}: ${r.status}`)));
const characters = {};
for (const name of CHARACTERS) {
  const c = catalog.characters?.find((x) => x.name === name);
  const voice = c?.suggested_voices?.[0];
  if (!voice?.startsWith("omnivoice/")) fail(`the catalogue has no omnivoice voice for ${name}`);
  characters[name] = voice.slice("omnivoice/".length);
}

const jwt = await token();
const voices = {};
for (const voice of [...new Set(Object.values(characters))]) {
  voices[voice] = {};
  for (const [ctx, sentences] of Object.entries(LINES)) {
    const said = await speak(jwt, voice, `${ctx}-${randomBytes(4).toString("hex")}`, sentences);
    const file = `${voice}-${ctx}.webm`;
    opus(said.pcm, join(here, file));
    const track = cues(voice, said.phones);
    voices[voice][ctx] = {
      audio: file,
      ms: Math.round((said.pcm.length / 2 / SAMPLE_RATE) * 1000),
      sentences: sentencesOf(sentences, said.words),
      ...(track ? { cues: track } : {}),
    };
    console.log(`${file}: ${voices[voice][ctx].ms} ms, ${track ? "with" : "without"} cues`);
  }
}

await writeFile(join(here, "voices.json"), `${JSON.stringify({ language: LANGUAGE, characters, voices })}\n`);
console.log("voices.json written");
