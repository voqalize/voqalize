/**
 * The documentation, which is two-thirds of this page.
 *
 * This page is the link target from the library's README, so a reader who never
 * starts the call still gets the whole library from it. The avatar's spoken
 * answers are a shortcut through the same text.
 *
 * The overview says what the library is and how it works: what runs on the
 * server, what runs in the browser, and where the protocol and the interface are
 * documented. The sections after it are for a developer adding the library to a
 * Pipecat app.
 *
 * How this file is written (2026-09-11):
 *
 *   * Facts only. No marketing language, no filler, no dramatic phrasing.
 *   * Short sentences with a simple structure. One idea per sentence.
 *   * Headings say what the section covers.
 *   * Code comes before the prose that explains it.
 *   * Limits are stated as facts, in their own section.
 *
 * The `id`s below are the wire: the brain's `show_section` names one and the page
 * scrolls to it (`backend/content.py` holds the same nine, and the same order).
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

/** Three columns: a question, the video-avatar answer, and ours. The one table
 *  on the page that compares against something outside the library, because
 *  "how is this different from HeyGen?" is the first question people ask. */
function Compare({
  head,
  rows,
}: {
  head: [string, string, string];
  rows: [string, ReactNode, ReactNode][];
}) {
  return (
    <div className="doc-scroll">
      <table className="doc-grid doc-compare">
        <thead>
          <tr>
            {head.map((label) => (
              <th key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, theirs, ours]) => (
            <tr key={key}>
              <th scope="row">{key}</th>
              <td data-label={head[1]}>{theirs}</td>
              <td data-label={head[2]}>{ours}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The pipecat integration page for each video avatar service in the comparison. */
const VIDEO_SERVICES: [string, string][] = [
  ["HeyGen", "heygen"],
  ["Anam", "anam"],
  ["Protoface", "protoface"],
  ["Simli", "simli"],
  ["Tavus", "tavus"],
];

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

/** Where the overview's terms and claims are defined. */
const REF = {
  viseme: "https://en.wikipedia.org/wiki/Viseme",
  rhubarb: "https://github.com/DanielSWolf/rhubarb-lip-sync",
  rtvi: "https://docs.pipecat.ai/client/rtvi-standard",
  wire: "https://github.com/voqalize/avatar/blob/main/docs/contract-wire.md",
  createAvatar: "https://github.com/voqalize/avatar/blob/main/docs/design-avatar-interface.md",
};

function Ext({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

// ── The nine sections ──────────────────────────────────────────────────────

export const DOC_SECTIONS: DocSection[] = [
  {
    id: "overview",
    title: "Avatars for Pipecat Voice Agents",
    rail: "Overview",
    body: (
      <>
        <p className="doc-lede">
          A lightweight library that provides customizable, lip-synced avatars for your Pipecat
          voice agent. The avatar is animated in the browser. No GPUs or generative video are
          involved.
        </p>
        <p>
          On the server, the library analyses the TTS audio in real time and generates{" "}
          <Ext href={REF.viseme}>visemes</Ext>, using the <Ext href={REF.rhubarb}>Rhubarb</Ext>{" "}
          mouth-shape alphabet. It sends them to the client as standard{" "}
          <Ext href={REF.rtvi}>RTVI</Ext> messages. The visemes are time-synced to the bot audio.
        </p>
        <p>
          On the client, the avatar can be an SVG drawing, a canvas rendering, a Rive animation
          (experimental), or a three.js model made in Blender. It gets the visemes from your <code>PipecatClient</code>
          . Then it animates the face in JavaScript.
        </p>
        <p>
          The <Ext href={REF.wire}>protocol</Ext> between the server and the client is documented.
          The JavaScript interface,{" "}
          <Ext href={REF.createAvatar}>
            <code>createAvatar</code>
          </Ext>
          , is stable.
        </p>
        <p>
          To try it, press <strong>Talk to it</strong>. The avatar answers your questions out loud.
          It scrolls this page to the section it is talking about.
        </p>
        <p>
          The library and nine of its faces are open source, under the MIT licence. Tara, the face
          this page opens on, is a Voqalize premium avatar. Its code and artwork are not open
          source.
        </p>

        <h3>The two packages</h3>
        <Grid
          head={["Package", "What it does"]}
          rows={[
            [
              "voqalize-avatar",
              <>
                A Pipecat frame processor for the server. It goes after the TTS service. It sends the
                avatar’s state and the visemes for each bot reply.
              </>,
            ],
            [
              "@voqalize/avatar",
              <>
                The browser library. You give it your <code>PipecatClient</code>, and it draws the
                avatar.
              </>,
            ],
          ]}
        />
        <p>
          Both packages are released together, from the same version tag. Both use the MIT licence,
          so you can use them in closed-source products.
        </p>
        <p className="doc-req">
          Requirements: pipecat-ai 1.4 or later, Python 3.12 or later, and Node 20 or later. Any
          Pipecat transport works.
        </p>
      </>
    ),
  },

  {
    id: "compare",
    title: "Compared with video avatar services",
    rail: "Compare",
    body: (
      <>
        <p className="doc-lede">
          HeyGen, Anam, Protoface, Simli and Tavus are video avatar services. They send a video of a
          face to the browser. This library sends mouth shapes and states, and the browser draws the
          face.
        </p>
        <p>
          All six go in the same place in a Pipecat pipeline, after the TTS service. A video avatar
          service sends the TTS audio to its own servers. It renders a video of a face saying it.
          Then it sends the video and the audio back through your transport. This library reads the
          same audio inside your pipeline. It works out the mouth shapes and sends them to the
          browser in small RTVI messages.
        </p>
        <Compare
          head={["", "Video avatar services", "voqalize/avatar"]}
          rows={[
            [
              "What the browser receives",
              <>A video track, and the audio that came back with it.</>,
              <>Your TTS audio, and a few hundred bytes a second of avatar messages.</>,
            ],
            [
              "Where the face is rendered",
              <>On the service’s servers.</>,
              <>In the user’s browser.</>,
            ],
            [
              "Extra services",
              <>One hosted service, with its own account and API key.</>,
              <>None. The viseme analysis runs inside your Pipecat pipeline, on its CPU.</>,
            ],
            [
              "Running cost",
              <>The service’s price for the minutes it renders.</>,
              <>Nothing beyond the pipeline you already run.</>,
            ],
            [
              "A new avatar",
              <>Created on the service’s platform, then selected by avatar ID.</>,
              <>
                A new browser module. The server does not change. Voqalize also builds three.js
                avatars in Blender from a single picture.
              </>,
            ],
            [
              "How it looks",
              <>Photoreal video of a person.</>,
              <>A drawn, painted or 2.5-D face, rendered in the browser.</>,
            ],
          ]}
        />
        <p>
          Each service’s Pipecat integration:{" "}
          {VIDEO_SERVICES.map(([name, slug], i) => (
            <span key={slug}>
              {i > 0 ? ", " : null}
              <a
                href={`https://docs.pipecat.ai/api-reference/server/services/video/${slug}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                {name}
              </a>
            </span>
          ))}
          .
        </p>
        <Note>
          Use a video avatar service if the face must look like real video. Use this library if a
          drawn or modelled face is enough and you want no extra service in the audio path.
        </Note>
      </>
    ),
  },

  {
    id: "quickstart",
    title: "Add it to a Pipecat app",
    rail: "Quickstart",
    body: (
      <>
        <p className="doc-lede">There are three steps. Neither call takes any configuration.</p>

        <Step n="1">
          <h3>Install both packages</h3>
          <Code lang="shell">{`pip install voqalize-avatar     # the server package
npm install @voqalize/avatar    # the browser package`}</Code>
        </Step>

        <Step n="2">
          <h3>Add the processor after the TTS service</h3>
          <Code lang="python">{`from voqalize_avatar import AvatarProcessor

pipeline = Pipeline([
    ..., tts, AvatarProcessor(), transport.output(),
])`}</Code>
          <p>
            The processor must sit between the TTS service and the transport output. There it sees
            the audio before the transport sends it. It reads the sample rate from{" "}
            <code>StartFrame</code>. The aligner is included in the wheel, so there is nothing to
            pass in.
          </p>
        </Step>

        <Step n="3">
          <h3>Mount the avatar in the browser</h3>
          <Code lang="javascript">{`import { createAvatar } from '@voqalize/avatar';

const avatar = createAvatar({ mount: el, client: pipecatClient });
// call avatar.destroy() when the element unmounts`}</Code>
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
            <code>createAvatar</code> returns an object with one method, <code>destroy()</code>. The
            avatar listens to your client’s events. There is no avatar state to read or set.
          </p>
        </Step>

        <Note>
          Optional: forward your RTVI processor’s <code>on_client_ready</code> event to{" "}
          <code>avatar.on_client_ready()</code>. It resends the current state once the browser’s
          data channel is open. Without it, the avatar misses its opening pose.
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
          The avatar shows one state at a time. Speaking and listening come from the audio. The
          states between turns are inferred. If the face goes idle while the agent is still working,
          users can think the call has dropped.
        </p>
        <Grid
          head={["State", "Where it comes from"]}
          rows={[
            [
              "SPEAKING\nLISTENING\nMUTED\nOFFLINE\nDEGRADED",
              <>
                Your <code>PipecatClient</code>, in the browser. The server sends nothing for these.
              </>,
            ],
            [
              "THINKING",
              <>
                <code>AvatarProcessor</code>. It sees the user’s turn end and the LLM response
                start, so it knows a reply is due.
              </>,
            ],
            [
              "WORKING",
              <>
                <code>AvatarProcessor</code>, for function calls that pass through the pipeline. For
                tools that run elsewhere, your code sends it.
              </>,
            ],
            ["STRAINING", <>Your code, when something you are waiting on has not responded.</>],
          ]}
        />
        <p>
          Blinking, breathing, gaze and idle movement are not states. The browser generates them.
          The server does not send them.
        </p>
        <Note>
          This demo’s agent sends <code>WORKING</code> when you ask it to look something up. It uses
          the message described in the next section.
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
          A server can send three commands to the avatar. Each one is an RTVI{" "}
          <code>server-message</code> with the envelope <code>{'{"type": "avatar"}'}</code>.
        </p>
        <Code lang="python">{`say = rtvi.send_server_message

# a gesture that ends on its own
await say({"type": "avatar", "cmd": "action", "id": "GESTURE_GREET"})

# a state, held until you clear it or an observed event replaces it
await say({"type": "avatar", "cmd": "claim", "state": "WORKING"})
await say({"type": "avatar", "cmd": "claim", "state": None})`}</Code>
        <Grid
          head={["Command", "Meaning"]}
          rows={[
            [
              "claim",
              <>
                Sets a state: <code>THINKING</code>, <code>WORKING</code>, <code>STRAINING</code>,
                or <code>null</code> to clear it. A new claim replaces the previous one.
              </>,
            ],
            [
              "action",
              <>
                Plays one gesture that ends on its own: <code>ACK_RECEIVE</code>,{" "}
                <code>ACK_NOD</code>, <code>RESPONSE_INTERRUPTED</code>, <code>GESTURE_GREET</code>,{" "}
                <code>GESTURE_GOODBYE</code>, <code>GESTURE_APPROVE</code>,{" "}
                <code>GESTURE_WAIT</code>.
              </>,
            ],
            [
              "cues",
              <>
                Mouth shapes on a timeline. <code>AvatarProcessor</code> sends these. See the next
                section.
              </>,
            ],
          ]}
        />
        <p>
          Observed events take priority over claims. The browser observes when the bot starts
          speaking, when the user starts speaking, and when the microphone is muted. When one of
          these happens, that state is shown and the claim is dropped.
        </p>
        <p>
          Messages have no version field. The browser ignores commands it does not recognise, so an
          older page still works with a newer server.
        </p>
        <p>
          The full protocol is in <Ext href={REF.wire}>contract-wire.md</Ext>.
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
          Each cue has a time, a mouth shape and an optional loudness. Time zero is the first sample
          of the bot’s reply audio. So a cue can arrive before or after the audio it describes.
        </p>
        <Code lang="json">{`{ "type": "avatar", "cmd": "cues", "ctx": "tts-41", "from_ms": 0,
  "cues": [ { "t": 0,   "v": "X" },
            { "t": 60,  "v": "B" },
            { "t": 140, "v": "E", "i": 0.8 } ] }`}</Code>
        <Grid
          head={["Field", "Meaning"]}
          rows={[
            ["t", <>Milliseconds from the first sample of the reply audio.</>],
            [
              "v",
              <>
                A Rhubarb mouth shape, <code>A</code> to <code>H</code>, or <code>X</code> for
                closed.
              </>,
            ],
            ["i", <>Loudness, from 0 to 1. Optional.</>],
            [
              "from_ms",
              <>
                Delete the cues from this time onward, then add these. Cues are replaced, never
                merged.
              </>,
            ],
          ]}
        />
        <p>
          The server writes the cues in two passes. The first pass estimates mouth shapes from the
          text, as soon as the text exists. It takes about 0.15 ms, so it runs on the event loop and
          the mouth can move when the audio starts. The second pass analyses the audio on a worker
          thread. It replaces the first pass’s cues, using <code>from_ms</code>.
        </p>
        <Note>
          <code>final: true</code> means no more cues will be sent for that reply. It does not mean
          the audio has ended. The mouth stops on <code>BotStoppedSpeaking</code>.
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
          The library ships nine faces: three SVG line drawings and six painted Canvas2D faces. Each
          face has its own entry point, so you load only the one you import. To switch faces,
          remount the avatar.
        </p>
        <p>
          Tara, the face this page opens on, is a three.js avatar built in Blender. It is a
          Voqalize premium avatar. It uses the same mixer and the same protocol as the open-source
          faces. Its code and artwork are not part of the open-source library.
        </p>
        <p>
          In this demo, each face is paired with one of two recorded voices. So you choose the face,
          and with it the voice, before the call starts. The choice is locked during the call.
        </p>
        <Code lang="javascript">{`// line art: peep, wren, myna
import { peep } from '@voqalize/avatar/faces/peep';

// painted: arjun, meera, vikram, ishita, kabir, naina
import { createAvatar } from '@voqalize/avatar/avatars/meera';`}</Code>
        <p>
          Each face has three layers. The mixer combines idle movement, gaze, gestures and the
          mouth. The rig turns the result into about thirty pose values. The face draws those
          values. During speech, only the mouth track moves the mouth. A nod during speech moves the
          head and nothing else.
        </p>
        <p>
          Each pose value moves toward its target at its own rate. The mouth takes 42 ms, the
          eyelids 18 ms, and the head 160 ms.
        </p>
        <p>
          To change a face’s colours, pass <code>theme</code>. Each face defines its own keys. The
          defaults are in its <code>THEME</code> export.
        </p>
      </>
    ),
  },

  {
    id: "custom",
    title: "Build your own avatar",
    rail: "Your own",
    body: (
      <>
        <p className="doc-lede">
          There are three ways to make your own avatar. You can draw a new face on the shipped rig,
          write a new renderer, or publish a module of your own.
        </p>

        <h3>Draw a new face on the shipped rig</h3>
        <p>
          You write one module. It creates an SVG and writes pose values into it. The protocol,
          mixer, smoothing, gestures and lipsync stay the same.
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
          You draw 22 of the 30 pose channels: the mouth, the eyes and the brows. The head,
          breathing, shoulders and torso come from a table of constants.
        </p>
        <p>
          Your module has no animation code: no timers, no <code>requestAnimationFrame</code>, no
          easing, and no state between frames. About sixty times a second it receives one object of
          about thirty numbers. The values are already mixed, clamped and smoothed. Your module
          writes them to the DOM.
        </p>

        <h3>Replace the renderer</h3>
        <p>
          To draw with something other than SVG, pass <code>rig</code> instead of{" "}
          <code>face</code>. A rig is a function that returns <code>apply(frame)</code> and{" "}
          <code>destroy()</code>. It can draw with Canvas2D, WebGL, WebGPU, Rive (experimental)
          or another renderer. The six painted faces in this demo are Canvas2D rigs.
        </p>
        <Code lang="javascript">{`createAvatar({
  mount: el,
  client: pipecatClient,
  rig: createMyRig,        // (opts) => { apply(frame), destroy() }
  rigOptions: { … },       // passed through unchanged
});`}</Code>
        <p>
          <code>VisemeTrack</code> in <code>@voqalize/avatar/internal</code> gives the mouth shape
          for the current frame, from a cue array and a clock.
        </p>

        <h3>Publish it</h3>
        <p>
          An avatar is any module that exports <code>createAvatar</code> with the signature below.
          There is no registry. Publish it under your own name and import it like any other package.
          The interface is described in{" "}
          <Ext href={REF.createAvatar}>design-avatar-interface.md</Ext>.
        </p>
        <Code lang="typescript">{`createAvatar({ mount, client, ...yourOptions }) -> { destroy() }`}</Code>
        <Note>
          The thirty pose channels are internal to the library and can change. A new renderer
          should depend on the protocol, which is stable.
        </Note>
      </>
    ),
  },

  {
    id: "limits",
    title: "Limits",
    rail: "Limits",
    body: (
      <>
        <p className="doc-lede">Read these before you install it.</p>
        <ul className="doc-limits">
          <li>
            <strong>The faces are not photoreal.</strong> They are drawn, painted, or modelled in
            2.5-D. For photoreal video, use a video avatar service.
          </li>
          <li>
            <strong>Mouth shapes are accurate only for English.</strong> The aligner’s acoustic
            model is English. The avatar works with any language, but the mouth shapes are less
            accurate.
          </li>
          <li>
            <strong>Lipsync wheels are built for Linux x86-64, Linux aarch64 and macOS arm64.</strong>{" "}
            On other platforms, pip installs the source distribution, which has no aligner binary.{" "}
            <code>AvatarProcessor</code> logs a warning and sends states only. The avatar still
            listens, thinks and takes turns. Its mouth does not move while it speaks.
          </li>
          <li>
            <strong>It needs a Pipecat pipeline.</strong> There is no standalone player and no
            browser-only lipsync.
          </li>
        </ul>
      </>
    ),
  },
];

export const DOC_SECTION_IDS = DOC_SECTIONS.map((s) => s.id);
