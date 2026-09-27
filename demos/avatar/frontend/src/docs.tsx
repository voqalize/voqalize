/**
 * The documentation, which is two-thirds of this page.
 *
 * This page is the link target from the package's README, so a reader who never
 * starts the call still gets the whole avatar from it. The avatar's spoken
 * answers are a shortcut through the same text.
 *
 * The overview says what the avatar is and how it works: what Voqalize sends,
 * what runs in the browser, and where each part comes from. The sections after
 * it are for a developer adding the avatar to a page that already makes
 * Voqalize calls.
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
 * scrolls to it (`backend/content.py` holds the same ids, in the same order).
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
// Deliberately few, and none of them is a card. The documentation is set on the
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
 *  on the page that compares against something outside the avatar, because
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

/** Where the overview's terms and claims are defined. */
const REF = {
  viseme: "https://en.wikipedia.org/wiki/Viseme",
  rtvi: "https://docs.pipecat.ai/client/rtvi-standard",
  readme: "https://github.com/voqalize/avatar/tree/main/packages/avatar#readme",
  licence: "https://avatar.voqalize.com/LICENSE",
};

/** What a page with a Content-Security-Policy has to allow, as the package's
 *  README states it. */
const CSP = `script-src  https://avatar.voqalize.com
connect-src https://avatar.voqalize.com blob:
img-src     https://avatar.voqalize.com blob:`;

function Ext({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

// ── The sections ───────────────────────────────────────────────────────────


export const DOC_SECTIONS: DocSection[] = [
  {
    id: "overview",
    title: "An avatar for your voice agent",
    rail: "Overview",
    body: (
      <>
        <p className="doc-lede">
          A lip-synced 2.5-D character for a Voqalize voice call. The avatar is animated in the
          user’s browser. No GPUs or generative video are involved.
        </p>
        <p>
          Every Voqalize call already sends what the face needs. It sends the state of the call,
          any gesture your brain plays, and the mouth shapes (<Ext href={REF.viseme}>visemes</Ext>)
          for each reply, timed to the bot audio. They travel as standard{" "}
          <Ext href={REF.rtvi}>RTVI</Ext> messages on the data channel the call already has.
        </p>
        <p>
          In the browser, you give <code>@voqalize/avatar</code> your <code>PipecatClient</code> and
          the name of a character. It fetches the avatar runtime and that character from{" "}
          <code>avatar.voqalize.com</code> and draws the face in the element you give it.
        </p>
        <p>
          To try it, press <strong>Talk to it</strong>. The avatar answers your questions out loud.
          It scrolls this page to the section it is talking about.
        </p>

        <h3>What runs where</h3>
        <Grid
          head={["Part", "What it does"]}
          rows={[
            [
              "Voqalize",
              <>
                Sends the avatar’s state and the mouth shapes for each reply, in every call. There
                is nothing to install or turn on.
              </>,
            ],
            [
              "@voqalize/avatar",
              <>
                The package you install from npm. A small loader: you give it your{" "}
                <code>PipecatClient</code> and a character name, and it mounts the face. MIT.
              </>,
            ],
            [
              "The avatar runtime",
              <>
                The renderer and the characters, fetched from <code>avatar.voqalize.com</code> when
                the face mounts. Each release of the package is pinned to the runtime it was
                released with. Licensed <Ext href={REF.licence}>separately</Ext>, for use with
                Voqalize.
              </>,
            ],
          ]}
        />
        <p className="doc-req">
          Requirements: a page that makes Voqalize calls with <code>@pipecat-ai/client-js</code> 1.4
          or later, and a browser with WebGL 2. React 18 or later is optional.
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
          face to the browser. Voqalize sends mouth shapes and states, and the browser draws the
          face.
        </p>
        <p>
          A video avatar service sits after the TTS service in a Pipecat pipeline. It sends the TTS
          audio to its own servers. It renders a video of a face saying it. Then it sends the video
          and the audio back through your transport. Voqalize already knows the sounds in the audio
          it synthesises. It turns them into mouth shapes and sends them to the browser in small
          RTVI messages.
        </p>
        <Compare
          head={["", "Video avatar services", "The Voqalize avatar"]}
          rows={[
            [
              "What the browser receives",
              <>A video track, and the audio that came back with it.</>,
              <>The call’s audio, and a few hundred bytes a second of avatar messages.</>,
            ],
            [
              "Where the face is rendered",
              <>On the service’s servers.</>,
              <>In the user’s browser.</>,
            ],
            [
              "Extra services",
              <>One hosted service, with its own account and API key.</>,
              <>None. The mouth shapes come from the voice pipeline the call already runs.</>,
            ],
            [
              "Running cost",
              <>The service’s price for the minutes it renders.</>,
              <>Nothing beyond the call.</>,
            ],
            [
              "A different avatar",
              <>Created on the service’s platform, then selected by avatar ID.</>,
              <>A different character name. The server does not change.</>,
            ],
            [
              "How it looks",
              <>Photoreal video of a person.</>,
              <>A 2.5-D character, rendered in the browser.</>,
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
          Use a video avatar service if the face must look like real video. Use this avatar if a
          modelled face is enough and you want no extra service in the audio path.
        </Note>
      </>
    ),
  },

  {
    id: "quickstart",
    title: "Add it to your page",
    rail: "Quickstart",
    body: (
      <>
        <p className="doc-lede">
          The server side is already running. The browser side is one package and one call.
        </p>

        <h3>Install the package</h3>
        <Code lang="shell">{`npm install @voqalize/avatar`}</Code>

        <h3>Mount a character</h3>
        <Code lang="javascript">{`import { createAvatar } from '@voqalize/avatar';

const avatar = createAvatar({ mount: el, client: pipecatClient, character: 'tara' });
// call avatar.destroy() when the element unmounts`}</Code>
        <p>In React:</p>
        <Code lang="jsx">{`import { Avatar } from '@voqalize/avatar/react';

<Avatar client={pipecatClient} character="tara" className="call-tile" />`}</Code>
        <p>
          <code>createAvatar</code> returns at once, with one method, <code>destroy()</code>. The
          face appears when the runtime and the character have arrived. It listens to your client’s
          events, so there is no avatar state to read or set. In React, nothing mounts while{" "}
          <code>client</code> is <code>null</code>, and a new <code>client</code> or{" "}
          <code>character</code> rebuilds the face.
        </p>

        <h3>Allow the avatar host</h3>
        <p>
          If your page sets a Content-Security-Policy, add these sources. The runtime is a module
          from <code>avatar.voqalize.com</code>, the character is fetched from there, and its
          textures are decoded from <code>blob:</code> URLs.
        </p>
        <Code lang="text">{CSP}</Code>
        <p>
          The <Ext href={REF.readme}>package README</Ext> is the reference for the options and the
          policy.
        </p>
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
                Voqalize. It sees the user’s turn end and knows a reply is due.
              </>,
            ],
            [
              "WORKING",
              <>
                Your brain, while a tool runs long enough for the user to notice.
              </>,
            ],
            ["CANT_HEAR", <>Your brain, when something it is waiting on has not responded.</>],
          ]}
        />
        <p>
          Blinking, breathing, gaze and idle movement are not states. The browser generates them.
          The server does not send them.
        </p>
      </>
    ),
  },

  {
    id: "wire",
    title: "Drive the avatar from your brain",
    rail: "Driving it",
    body: (
      <>
        <p className="doc-lede">
          Your brain can tell the avatar what to show. It travels as RTVI server messages on the
          data channel your call already has.
        </p>
        <Grid
          head={["What", "Meaning"]}
          rows={[
            [
              "A state",
              <>
                Held until it is cleared or replaced: thinking, working, or that it cannot hear you.
                A new one replaces the previous one. Voqalize already sends thinking, so state from
                your brain is a race with it.
              </>,
            ],
            [
              "An action",
              <>
                One gesture that ends on its own — a nod, a receipt, a wave. Every character
                has acknowledge, the whole backchannel family in one word, and the reaction to being
                interrupted. Any other gesture belongs to the character that is mounted, and one it
                does not know is ignored rather than an error.
              </>,
            ],
            [
              "Mouth shapes",
              <>A timeline of mouth shapes for each reply. Voqalize sends these. See the next section.</>,
            ],
          ]}
        />
        <p>
          Send actions, and leave state alone. An action composes with whatever the call is doing;
          a state contests it. This demo’s brain does exactly that: when it waves or nods at you, it
          is playing one action from inside a tool call, with no floor and no audio.
        </p>
        <p>
          Observed events take priority. A state the server sends is a candidate; the browser
          observes when the bot starts speaking, when the user starts speaking, and when the
          microphone is muted, and when one of those happens that fact is shown and the candidate
          is dropped.
        </p>
        <p>
          A browser ignores a state or a gesture it does not recognise, so a newer brain does not
          break an older page. It does not show the gesture either, so upgrade the package before
          your brain relies on a gesture that only a newer release has.
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
        <p>
          Voqalize knows which sounds it spoke, and when, for every sentence it synthesises. The
          mouth shapes are made from those. Audio is never held back to wait for them.
        </p>
        <p>
          The mouth follows the reply’s audio as the browser receives it. It moves whenever that
          audio arrives, even if the user has the volume down, which is a sign to check the
          speaker rather than the call.
        </p>
        <Note>
          The last batch for a reply means no more cues are coming. It does not mean the audio
          has ended. The mouth stops when the bot stops speaking.
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
          A character is a name. Pass it as <code>character</code>, and the runtime fetches that
          character when the face mounts. A page downloads only the characters it mounts.
        </p>
        <p>
          The characters are the ones on the strip beside this documentation, and the key you pass
          is the name on the chip, in lower case. A name the runtime does not have logs an error to
          the console and mounts nothing.
        </p>
        <Code lang="jsx">{`<Avatar client={pipecatClient} character="tanvi" />`}</Code>
        <p>
          To switch faces, pass another name. In React the face is rebuilt; with{" "}
          <code>createAvatar</code>, destroy the old one and create a new one.
        </p>
        <p>
          In this demo, each face is paired with its own voice. So you choose the face, and with it
          the voice, before the call starts. The choice is locked during the call.
        </p>
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
            <strong>The faces are not photoreal.</strong> They are modelled in 2.5-D. For photoreal
            video, use a video avatar service.
          </li>
          <li>
            <strong>It needs a Voqalize call.</strong> The mouth shapes and states come from
            Voqalize. There is no standalone player and no browser-only lipsync.
          </li>
          <li>
            <strong>The page must reach <code>avatar.voqalize.com</code>.</strong> The runtime and
            the characters are fetched from there when the face mounts. A strict
            Content-Security-Policy has to allow it.
          </li>
          <li>
            <strong>It needs WebGL 2.</strong> Without it, the tile shows a still photograph of the
            character, like a call where the other side has turned their camera off.
          </li>
        </ul>
      </>
    ),
  },
];

export const DOC_SECTION_IDS = DOC_SECTIONS.map((s) => s.id);
