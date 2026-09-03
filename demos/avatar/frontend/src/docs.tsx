/**
 * The documentation, which is two-thirds of this page.
 *
 * This page is the link target from the library's own README, so it has to work
 * for a reader who never says a word: everything the avatar can tell you out
 * loud is written here first, and the voice is a fast path through it rather
 * than the only way in.
 *
 * Written to the Google developer documentation style guide and the plain-language
 * principles of ISO 24495-1, for one reader — an engineer who already runs a
 * pipecat pipeline:
 *
 *   * **Headings name a task**, in sentence case, in the words the reader would
 *     use ("Add it to a pipecat app", not "Integration").
 *   * **Code comes before the prose about it.** The reader is scanning for the
 *     line to paste; the paragraph explains the line they have already found.
 *   * **Second person, present tense, active voice.** You install, you mount, it
 *     sends.
 *   * **One idea per sentence, in the shortest words that are still exact.** A
 *     sentence that needs two commas to hold itself up is two sentences.
 *   * **Limits are stated as facts**, in their own section, at the same weight as
 *     the features — not softened and not buried.
 *
 * The `id`s below are the wire: the brain's `show_section` names one and the page
 * scrolls to it (`backend/content.py` holds the same eight, and the same order).
 * Adding a section here means adding it there, and the `SectionId` literal in the
 * brain is what makes the mismatch a type error rather than a dead scroll.
 */

import type { ReactNode } from "react";

/** One documentation section. `title` is the heading the reader sees and the
 *  one the avatar says out loud, so the two never drift. */
export interface DocSection {
  id: string;
  title: string;
  /** Shown in the section rail, where there is room for two or three words. */
  rail: string;
  body: ReactNode;
}

// ── Prose primitives ────────────────────────────────────────────────────────
//
// Deliberately four, and none of them is a card. The documentation is set on the
// page itself; a border around a paragraph would be decoration, whereas a code
// block's field and a limit's rule both mark a genuine change of register.

function Code({ lang, children }: { lang: string; children: string }) {
  return (
    <figure className="doc-code">
      <figcaption>{lang}</figcaption>
      <pre>
        <code>{children}</code>
      </pre>
    </figure>
  );
}

/** A short table. Used only where the content really is rows and columns —
 *  which state comes from where, and which package owns what. */
function Grid({ head, rows }: { head: [string, string]; rows: [string, ReactNode][] }) {
  return (
    <table className="doc-grid">
      <thead>
        <tr>
          <th>{head[0]}</th>
          <th>{head[1]}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([key, value]) => (
          <tr key={key}>
            <th scope="row">{key}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="doc-note">{children}</p>;
}

function Step({ n, children }: { n: string; children: ReactNode }) {
  // The one numbered thing on the page, because installing, wiring and mounting
  // genuinely happen in that order and the reader is following along.
  return (
    <div className="doc-step">
      <span className="doc-step-n" aria-hidden>
        {n}
      </span>
      <div className="doc-step-body">{children}</div>
    </div>
  );
}

// ── The eight sections ──────────────────────────────────────────────────────

export const DOC_SECTIONS: DocSection[] = [
  {
    id: "overview",
    title: "A talking head for pipecat agents",
    rail: "Overview",
    body: (
      <>
        <p className="doc-lede">
          Your pipeline already streams speech to the browser. This library draws a face that moves
          with it. The mouth follows the audio, and the expression follows what the agent is doing:
          listening, thinking, running a tool, or being interrupted.
        </p>
        <p>
          There is no video track. The face rides the RTVI data channel your client already has
          open, at a few hundred bytes a second. Nothing renders on a server, so there is no
          per-minute avatar vendor between you and the picture.
        </p>
        <Grid
          head={["Package", "What it does"]}
          rows={[
            [
              "voqalize-avatar",
              <>
                One pipecat frame processor. It reads the frames already flowing past it to work out
                what the agent is doing, and it lines up mouth shapes with the audio about to play.
              </>,
            ],
            [
              "@voqalize/avatar",
              <>
                One mount call in the browser. It draws the face from the <code>PipecatClient</code>{" "}
                you already connected with.
              </>,
            ],
          ]}
        />
        <p>
          The two packages are ends of one wire format. They publish from the same tag, so their
          versions cannot drift apart. Both are MIT-licensed, so you can use them in a closed-source
          product.
        </p>
        <p className="doc-req">
          Needs pipecat-ai 1.4 or later, Python 3.12+, and Node 20+. Any transport works: neither
          package names one.
        </p>
      </>
    ),
  },

  {
    id: "quickstart",
    title: "Add it to a pipecat app",
    rail: "Quickstart",
    body: (
      <>
        <p className="doc-lede">
          Three steps. Neither call takes configuration, and this is the whole integration.
        </p>

        <Step n="1">
          <h3>Install both halves</h3>
          <Code lang="shell">{`pip install voqalize-avatar     # the pipeline half
npm install @voqalize/avatar    # the browser half`}</Code>
        </Step>

        <Step n="2">
          <h3>Put the processor between TTS and the transport</h3>
          <Code lang="python">{`from voqalize_avatar import AvatarProcessor

pipeline = Pipeline([
    ..., tts, AvatarProcessor(), transport.output(),
])`}</Code>
          <p>
            That position is a requirement, not a convention. From there the processor can see the
            audio before it is played, which is what the mouth needs. It reads the sample rate off{" "}
            <code>StartFrame</code>, and the aligner ships inside the wheel, so there is nothing to
            pass in.
          </p>
        </Step>

        <Step n="3">
          <h3>Mount the face where you draw the bot</h3>
          <Code lang="javascript">{`import { createAvatar } from '@voqalize/avatar';

const avatar = createAvatar({ mount: el, client: pipecatClient });
// avatar.destroy() when the tile unmounts`}</Code>
          <p>In React, with a different face:</p>
          <Code lang="jsx">{`import { Avatar } from '@voqalize/avatar/react';
// peep is the default face
import { wren } from '@voqalize/avatar/faces/wren';

<Avatar
  client={pipecatClient}
  options={{ face: wren }}
  className="call-tile"
/>`}</Code>
          <p>
            <code>createAvatar</code> returns <code>{"{ destroy() }"}</code> and nothing else. The
            avatar watches your client and reacts to it. There is no state to read back, and nothing
            to drive.
          </p>
        </Step>

        <Note>
          One optional line: forward your RTVI processor’s <code>on_client_ready</code> event to{" "}
          <code>avatar.on_client_ready()</code>. It repeats the current state once the browser’s
          data channel exists. Skip it and you lose the opening pose. Nothing else changes.
        </Note>
      </>
    ),
  },

  {
    id: "states",
    title: "What the avatar shows between turns",
    rail: "States",
    body: (
      <>
        <p className="doc-lede">
          Speaking and listening are easy. Everything between them has to be inferred. If the face
          goes blank while the model is still working, people read it as a dropped call — so idle is
          the wrong answer to most of the silence in a conversation.
        </p>
        <Grid
          head={["State", "Where it comes from"]}
          rows={[
            [
              "SPEAKING\nLISTENING\nMUTED\nOFFLINE\nDEGRADED",
              <>
                Your <code>PipecatClient</code>, in the browser. No backend involved, and nothing
                for you to send.
              </>,
            ],
            [
              "THINKING",
              <>
                <code>AvatarProcessor</code>. It watches turn and LLM response boundaries, so it
                knows a reply is owed.
              </>,
            ],
            [
              "WORKING",
              <>
                You, if your tools run outside the pipeline. The processor claims this itself for
                function calls that pass through it. It cannot see a tool running inside a service
                on the far side of a socket.
              </>,
            ],
            ["STRAINING", <>You, when something you are waiting on has returned nothing at all.</>],
          ]}
        />
        <p>
          Blinking, breathing, gaze and idle sway are not in this table. They belong to the
          renderer, and nobody sends them. A server that had to send a blink would be sending it
          late.
        </p>
        <Note>
          The avatar on this page holds <code>WORKING</code> when you ask it to look something up.
          That claim comes from the demo’s agent over the channel described below. It is row three,
          live.
        </Note>
      </>
    ),
  },

  {
    id: "wire",
    title: "Drive the avatar from your own code",
    rail: "The wire",
    body: (
      <>
        <p className="doc-lede">
          Past the two calls above, a server can say exactly three things to a face. All three ride
          one RTVI <code>server-message</code> under a <code>{'{"type": "avatar"}'}</code> envelope.
        </p>
        <Code lang="python">{`say = rtvi.send_server_message

# a self-completing behaviour — a wave, a nod, a wait gesture
await say({"type": "avatar", "cmd": "action", "id": "GESTURE_GREET"})

# a durable state, held until you clear it or a fact retires it
await say({"type": "avatar", "cmd": "claim", "state": "WORKING"})
await say({"type": "avatar", "cmd": "claim", "state": None})`}</Code>
        <Grid
          head={["Command", "Meaning"]}
          rows={[
            [
              "claim",
              <>
                A state you are asking for: <code>THINKING</code>, <code>WORKING</code>,{" "}
                <code>STRAINING</code>, or <code>null</code> to clear it. Only one is in flight at a
                time, so a new claim replaces the old one.
              </>,
            ],
            [
              "action",
              <>
                One behaviour that finishes on its own and leaves no state behind:{" "}
                <code>ACK_RECEIVE</code>, <code>ACK_NOD</code>, <code>RESPONSE_INTERRUPTED</code>,{" "}
                <code>GESTURE_GREET</code>, <code>GESTURE_GOODBYE</code>,{" "}
                <code>GESTURE_APPROVE</code>, <code>GESTURE_WAIT</code>.
              </>,
            ],
            [
              "cues",
              <>
                Mouth shapes on a timeline. <code>AvatarProcessor</code> sends these for you. See
                the next section.
              </>,
            ],
          ]}
        />
        <p>
          Precedence runs one way, and this is the part to remember. What the browser observes about
          the audio is a fact: the bot started speaking, the caller started speaking, the microphone
          is muted. Facts win. Your claim sits underneath them and is dropped as soon as a fact
          arrives. You can tell the face what to consider. You cannot tell it what is happening.
        </p>
        <p>
          There is no version field. The browser ignores a command it does not recognise, so an old
          page and a new server still run a call.
        </p>
      </>
    ),
  },

  {
    id: "lipsync",
    title: "How the mouth stays in sync",
    rail: "Lipsync",
    body: (
      <>
        <p className="doc-lede">
          A cue is not a play-this-now command. It is a time, a mouth shape, and sometimes a
          loudness. Zero on that clock is the first audio sample of the turn, so it does not matter
          when a cue arrives.
        </p>
        <Code lang="json">{`{ "type": "avatar", "cmd": "cues", "ctx": "tts-41", "from_ms": 0,
  "cues": [ { "t": 0,   "v": "X" },
            { "t": 60,  "v": "B" },
            { "t": 140, "v": "E", "i": 0.8 } ] }`}</Code>
        <Grid
          head={["Field", "Meaning"]}
          rows={[
            ["t", <>Milliseconds from the turn’s first audio sample.</>],
            [
              "v",
              <>
                A Rhubarb mouth shape, <code>A</code> to <code>H</code>, or <code>X</code> for
                closed.
              </>,
            ],
            ["i", <>Loudness, 0 to 1. Optional.</>],
            [
              "from_ms",
              <>
                Throw away the track from this offset onward, then add these cues. It overwrites; it
                never merges.
              </>,
            ],
          ]}
        />
        <p>
          Two passes write that one track. A fast pass guesses shapes from the text as soon as there
          is text, so the mouth moves the moment audio starts. It costs about 0.15 ms, which is why
          it can run on the event loop. An accurate pass then decodes the real audio on a worker
          thread and splices its results in behind the first. <code>from_ms</code> is the whole
          correction mechanism. When it works, you never notice the second pass arrive.
        </p>
        <Note>
          <code>final: true</code> on a cue message means no more patches for that context. It does
          not mean the audio has finished. <code>BotStoppedSpeaking</code> is what stops the mouth.
        </Note>
      </>
    ),
  },

  {
    id: "faces",
    title: "Choose a face",
    rail: "Faces",
    body: (
      <>
        <p className="doc-lede">
          Nine avatars ship: three SVG line-art faces and six painted Canvas2D people. Each one has
          its own entry point, so you only pay for the one you import. Swapping is a remount.
        </p>
        <p>
          This demo still asks you to choose before you dial, and that is a speech constraint rather
          than a rendering one. Nine faces share two recorded reference voices, so picking a face
          picks a voice. Changing it halfway through an answer is the one thing a listener always
          notices, so the strip locks once the call is up.
        </p>
        <Code lang="javascript">{`// line art: peep, wren, myna
import { peep } from '@voqalize/avatar/faces/peep';

// painted: arjun, meera, vikram, ishita, kabir, naina
import { createAvatar } from '@voqalize/avatar/avatars/meera';`}</Code>
        <p>
          Under the drawing there are three layers. A mixer combines the things that want to move
          the face — idle motion, gaze, a gesture, the mouth — one channel at a time. A rig turns
          the result into about thirty pose numbers. A face draws them. While a mouth track is
          playing it owns the mouth outright, so a nod during speech moves the head and nothing
          else.
        </p>
        <p>
          Smoothing is what you actually see. Every channel chases its target at its own speed: the
          mouth in 42 ms, the eyelids in 18 ms, the head in 160 ms. Keyframes are not what the face
          does. The smoothing between them is.
        </p>
        <p>
          To recolour a face without redrawing it, pass <code>theme</code>. The keys belong to the
          face; read the defaults off its <code>THEME</code> export.
        </p>
      </>
    ),
  },

  {
    id: "custom",
    title: "Ship your own avatar",
    rail: "Your own",
    body: (
      <>
        <p className="doc-lede">
          There are three ways in, and they cost an hour, an afternoon, and a week. Pick by how much
          of the face you actually want to own.
        </p>

        <h3>Draw a new face on the shipped rig</h3>
        <p>
          This is the common case. You write one module that draws an SVG and writes pose numbers
          into it. Nothing else changes: the wire, the mixer, the smoothing, the gestures and the
          lipsync all stay where they are.
        </p>
        <Code lang="javascript">{`// my-face.js — no build step, no dependencies
export function createFace(mount, theme) {
  mount.innerHTML = buildSvgMarkup(theme);   // generated, not an asset
  const svg = mount.querySelector('svg');
  return {
    svg,
    theme,
    apply(params) { /* write ~30 floats into the DOM, 60x a second */ },
    destroy() { mount.innerHTML = ''; },
  };
}
export const META  = { viewBox: {…}, mouthCrop: {…} };  // the 4:3 camera
export const THEME = { ink: '#1b1b1b', paper: '#ffffff' };
export const myFace = { create: createFace, meta: META };`}</Code>
        <Code lang="javascript">{`import { myFace } from './my-face.js';
createAvatar({ mount: el, client: pipecatClient, face: myFace });`}</Code>
        <p>
          You draw 22 of the 30 channels: the mouth, the eyes and the brows. Head, breath, shoulders
          and torso are done for you from a table of constants, so you write numbers rather than
          code for those.
        </p>
        <p>
          Your module holds no animation. No timer, no <code>requestAnimationFrame</code>, no
          easing, and no state that survives a frame. Roughly sixty times a second you are handed
          one object of about thirty floats, already mixed, clamped and smoothed, and you write it
          into the DOM. That is the whole job.
        </p>

        <h3>Replace the renderer</h3>
        <p>
          If SVG is not what you want to draw in, pass <code>rig</code> instead of <code>face</code>
          . A rig is a factory that returns <code>apply(frame)</code> and <code>destroy()</code>,
          and it can paint with anything — Canvas2D, WebGL, WebGPU, or a third-party renderer. The
          six painted avatars in this demo are exactly this: a Canvas2D rig in front of the same
          mixer.
        </p>
        <Code lang="javascript">{`createAvatar({
  mount: el,
  client: pipecatClient,
  rig: createMyRig,        // (opts) => { apply(frame), destroy() }
  rigOptions: { … },       // passed straight through; opaque to the library
});`}</Code>
        <p>
          <code>VisemeTrack</code> in <code>@voqalize/avatar/internal</code> turns a cue array and a
          clock into the mouth shape for the current frame. Every renderer needs that, and no
          renderer should write it twice.
        </p>

        <h3>Publish it</h3>
        <p>
          An avatar is any module that exports <code>createAvatar</code> with the signature below.
          There is no registry to add yourself to, no name to resolve, and no renderer interface to
          implement. Publish it under your own name and import it like any other package.
        </p>
        <Code lang="typescript">{`createAvatar({ mount, client, ...yourOptions }) -> { destroy() }`}</Code>
        <Note>
          The thirty pose channels are how our mixer talks to our own faces. They are not a public
          seam, and they can change. What a new renderer has to understand is the wire above, which
          does not.
        </Note>
      </>
    ),
  },

  {
    id: "limits",
    title: "What it does not do",
    rail: "Limits",
    body: (
      <>
        <p className="doc-lede">
          Four limits, worth knowing before you install it rather than after.
        </p>
        <ul className="doc-limits">
          <li>
            <strong>It is 2-D and vector.</strong> The faces are drawings. If you need photoreal
            video, this is the wrong library.
          </li>
          <li>
            <strong>Alignment is English only.</strong> The aligner’s acoustic model is English. The
            avatar runs on any language, but the mouth shapes are only right for one.
          </li>
          <li>
            <strong>Lipsync wheels cover Linux x86-64, Linux aarch64, and macOS arm64.</strong>{" "}
            Anywhere else, pip installs the sdist, which carries no binary.{" "}
            <code>AvatarProcessor</code> notices, logs once, and runs the state channel on its own.
            You lose exactly one thing: the face still listens, thinks, takes the floor and gives it
            back, and its mouth does not move while it speaks.
          </li>
          <li>
            <strong>It needs a pipecat pipeline.</strong> There is no standalone player, and no
            browser-side lipsync to fall back on.
          </li>
        </ul>
      </>
    ),
  },
];

export const DOC_SECTION_IDS = DOC_SECTIONS.map((s) => s.id);
