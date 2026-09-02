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
 *   * **Limits are stated as facts**, in their own section, at the same weight as
 *     the features — not softened and not buried.
 *
 * The `id`s below are the wire: the brain's `show_section` names one and the page
 * scrolls to it (`backend/content.py` holds the same seven, and the same order).
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

// ── The seven sections ──────────────────────────────────────────────────────

export const DOC_SECTIONS: DocSection[] = [
  {
    id: "overview",
    title: "A talking head for pipecat agents",
    rail: "Overview",
    body: (
      <>
        <p className="doc-lede">
          Your pipeline already streams speech to the browser. This library draws a face that moves
          with it — lip-synced to the audio, and aware of whether the agent is listening, thinking,
          running a tool, or has just been interrupted.
        </p>
        <p>
          It adds no video track and no second media path. The face rides the RTVI data channel your
          client already has open, at a few hundred bytes a second. There is no per-minute avatar
          vendor between you and the picture.
        </p>
        <Grid
          head={["Package", "What it does"]}
          rows={[
            [
              "voqalize-avatar",
              <>
                One pipecat frame processor. It infers what the agent is doing from frames already
                flowing past it, and aligns mouth shapes to the audio about to be spoken.
              </>,
            ],
            [
              "@voqalize/avatar",
              <>
                One mount call in the browser. It renders the face from the{" "}
                <code>PipecatClient</code> you already connected with.
              </>,
            ],
          ]}
        />
        <p>
          The two are ends of one wire format and publish from the same tag, so the versions cannot
          drift apart. Both are MIT-licensed — use them in closed-source products.
        </p>
        <p className="doc-req">
          Needs pipecat-ai 1.4 or later, Python 3.12+, and Node 20+. Any transport works: nothing in
          either package names one.
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
          Three steps, and neither call takes configuration. This is the whole integration.
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
            That seat is the requirement, not a convention. From there the processor sees the audio
            before it is spoken, at generation speed, which is what the mouth needs.{" "}
            <code>StartFrame</code> supplies the sample rate and the aligner rides inside the wheel,
            so there is nothing to pass in.
          </p>
        </Step>

        <Step n="3">
          <h3>Mount the face where you render the bot</h3>
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
            avatar is an embodiment of your client and reacts to it, so there is no state to read
            back and no avatar to drive.
          </p>
        </Step>

        <Note>
          One optional line: forward your RTVI processor’s <code>on_client_ready</code> event to{" "}
          <code>avatar.on_client_ready()</code>. It re-announces the current state once the
          browser’s data channel exists. Skipping it costs the widget its opening pose and nothing
          more.
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
          Speaking and listening are the easy states. Everything between them is inference, and a
          face that goes blank while a model is mid-response reads as a dropped connection — so idle
          is the wrong answer to most of the silence in a call.
        </p>
        <Grid
          head={["State", "Where it comes from"]}
          rows={[
            [
              "SPEAKING\nLISTENING\nMUTED\nOFFLINE\nDEGRADED",
              <>
                Your <code>PipecatClient</code>, in the browser. No backend involvement, and nothing
                for you to send.
              </>,
            ],
            [
              "THINKING",
              <>
                <code>AvatarProcessor</code>, watching turn and LLM response boundaries. It knows a
                reply is owed.
              </>,
            ],
            [
              "WORKING",
              <>
                You, if your tools run outside the pipeline. The processor sees function-call frames
                when they pass through it and claims this itself; it cannot see a tool running
                inside a service on the far side of a socket.
              </>,
            ],
            ["STRAINING", <>You, when a call you are waiting on has returned nothing at all.</>],
          ]}
        />
        <p>
          Blinking, breathing, gaze aversion and idle sway are never in this table. They belong to
          the renderer and nobody sends them — a server that had to send a blink would be sending it
          late.
        </p>
        <Note>
          The avatar in this page is holding <code>WORKING</code> out loud when you ask it to look
          something up. That claim is coming from the demo’s agent over the same channel described
          below, which is the asymmetry in row three, live.
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
          Beyond the two calls above, a server can say exactly three things to a face. All three
          ride one RTVI <code>server-message</code> under a <code>{'{"type": "avatar"}'}</code>{" "}
          envelope.
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
                A durable candidate state: <code>THINKING</code>, <code>WORKING</code>,{" "}
                <code>STRAINING</code>, or <code>null</code> to clear. Exactly one is in flight, so
                a later claim replaces the earlier one.
              </>,
            ],
            [
              "action",
              <>
                One behaviour that completes on its own and leaves no state behind:{" "}
                <code>ACK_RECEIVE</code>, <code>ACK_NOD</code>, <code>RESPONSE_INTERRUPTED</code>,{" "}
                <code>GESTURE_GREET</code>, <code>GESTURE_GOODBYE</code>,{" "}
                <code>GESTURE_APPROVE</code>, <code>GESTURE_WAIT</code>.
              </>,
            ],
            [
              "cues",
              <>
                Mouth shapes on a timeline. <code>AvatarProcessor</code> sends these for you; see
                the next section.
              </>,
            ],
          ]}
        />
        <p>
          Precedence runs one way, and it is the part to remember. What the browser observes about
          the audio — that the bot started speaking, that the caller did, that the microphone is
          muted — is a fact, and facts win. Your claim sits underneath every fact and retires the
          moment one arrives. You can tell the face what to consider; you cannot tell it what is
          happening.
        </p>
        <p>
          There is no version field. A command the browser does not recognise is ignored, so an
          older page and a newer server still run a call.
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
          A cue is never a play-this-now command. It is a time, a mouth shape, and optionally a
          loudness — and zero on that clock is the first audio sample of the turn, so when a cue
          arrives carries no meaning at all.
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
                Discard the track at and after this offset, then append these cues. An overwrite,
                never a merge.
              </>,
            ],
          ]}
        />
        <p>
          Two legs write that one track. A fast leg predicts shapes from the text the moment there
          is text — about 0.15 ms of work, so it runs on the event loop — and the mouth moves the
          instant audio starts. An accurate leg decodes the rendered audio on a worker thread and
          splices in behind it as it advances. <code>from_ms</code> is the whole correction
          mechanism, and if it is working you never see the second leg arrive.
        </p>
        <Note>
          <code>final: true</code> on a cue message means no more patches for that context. It does
          not mean the audio has finished. <code>BotStoppedSpeaking</code> is the hard stop for the
          mouth.
        </Note>
      </>
    ),
  },

  {
    id: "faces",
    title: "Choose a face, or ship your own",
    rail: "Faces",
    body: (
      <>
        <p className="doc-lede">
          Nine avatars ship: three SVG line-art faces and six painted Canvas2D identities. Each has
          its own entry point, so you pay for the one you import. Swapping one is a remount.
        </p>
        <Code lang="javascript">{`// line art: peep, wren, myna
import { peep } from '@voqalize/avatar/faces/peep';

// painted: arjun, meera, vikram, ishita, kabir, naina
import { createAvatar } from '@voqalize/avatar/avatars/meera';`}</Code>
        <p>
          Under the drawing there are three layers. A mixer resolves layered inputs — idle motion,
          gaze, a gesture clip, the mouth — channel by channel. A rig applies about thirty pose
          numbers. A face consumes them. Layers mix in a fixed order, and while a viseme track is
          playing it owns the mouth outright, so a nod during speech moves the head and nothing
          else.
        </p>
        <p>
          Smoothing is the animation. Every channel chases its target at its own time constant — the
          mouth at 42 ms, the eyelids at 18 ms, the head at 160 ms — so keyframes are not what the
          face does; the smoothing between them is.
        </p>
        <h3>Ship your own avatar</h3>
        <p>
          A different rendering technology is not a face. It is a different{" "}
          <code>createAvatar</code>, published as its own module:
        </p>
        <Code lang="typescript">{`createAvatar({ mount, client, ...yourOptions }) -> { destroy() }`}</Code>
        <p>
          There is no registry, and there is deliberately no renderer interface — the thirty pose
          channels are how our SVG mixer talks to our own faces, not a public seam. What a new
          renderer needs to understand is the wire above. <code>VisemeTrack</code> in{" "}
          <code>@voqalize/avatar/internal</code> turns a cue array and a clock into the shape for
          the current frame; every renderer needs that, and none should write it twice.
        </p>
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
          Four limits worth knowing before you install it, rather than after.
        </p>
        <ul className="doc-limits">
          <li>
            <strong>It is 2-D and vector.</strong> The faces are drawings. If you need photoreal
            video, this is the wrong library.
          </li>
          <li>
            <strong>Alignment is English only.</strong> The aligner’s acoustic model is English. The
            avatar still runs on any language; the mouth shapes are only right for one.
          </li>
          <li>
            <strong>Lipsync wheels cover Linux x86-64, Linux aarch64, and macOS arm64.</strong>{" "}
            Anywhere else, pip installs the sdist, which carries no binary.{" "}
            <code>AvatarProcessor</code> catches it, logs once, and runs the state channel alone.
            The degradation is exactly one thing: the face still listens, thinks, claims the floor
            and yields it, and its mouth does not move while it speaks.
          </li>
          <li>
            <strong>It needs a pipecat pipeline.</strong> There is no standalone player, and no
            client-side lipsync to fall back on.
          </li>
        </ul>
      </>
    ),
  },
];

export const DOC_SECTION_IDS = DOC_SECTIONS.map((s) => s.id);
