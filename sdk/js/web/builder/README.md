# The widget builder

A page for shaping `<vql-widget>` by hand: a form on the left, the real widget
on a sample page on the right, and a snippet to copy.

```sh
pnpm builder            # prints the URL
PORT=4321 pnpm builder  # a fixed port
```

## What is on the page

- **The form** is read from `widget-config.schema.json`. Each field gets the
  control its schema implies (an enum is a choice, a boolean a switch, a hex
  colour a picker, a bounded number a slider), and `GROUPS` in
  `schema-form.ts` only says where a field goes. A field added to the schema
  that no group names shows up under "More" with no change here.
- **The preview** is the real widget in a desktop frame and a phone frame,
  over a light or a dark sample page, with the real avatar (`@voqalize/avatar`,
  bundled into `preview.js`; its runtime and characters load from the avatar
  CDN). Each state chip replays a recorded agent turn through a fake session
  (`replay.ts`). The turn is real speech: clips the Voqalize speech tier made in
  the voice of the chosen character, with its word timings and the mouth cues a
  call sends (`fixtures/`). `voice.ts` plays them on a real audio track and
  raises the events a call's client raises, so the face moves its lips exactly
  as it does in a call and the captions follow the words as they are said. A
  character with no clips gets the face and the captions, with no voice.
- **Sound.** Browsers keep audio off until the page is clicked, so the first
  click anywhere in the builder turns the sound on; **Sound on / Sound off**
  toggles it, and **Play** replays the turn. Only one frame plays aloud (the
  desktop frame, or the phone frame when it is shown alone); the other moves
  its lips silently.
- **The snippet** carries only what you changed. Fields left at their defaults
  are left out, so the widget's own defaults keep applying. HTML (the script
  tag and the element) and React forms are both offered.
- **Talk to it** opens a real call in the desktop frame through the widget's own
  adapter. It needs an agent id and a publishable key, from any of these:
  - the page's address: `?agent=…&key=pk_…&api=…` (the key is removed from the
    address as soon as the page has read it);
  - `builder/.env.local`, which is gitignored and never committed:

    ```sh
    VQL_BUILDER_AGENT=…
    VQL_BUILDER_KEY=pk_…
    VQL_BUILDER_API=https://…/api/v1   # optional; the production API otherwise
    ```

  - the agent id and key fields in the form.

  The page's origin must be one of the key's allowed origins. On the local
  stack, `http://127.0.0.1:4321` was added to the local travel agent's key for
  this (2026-11-07), so run the builder on that port to call it. The face in a
  call is the Character field, or Emily: the platform does not yet say which
  character an agent has.
- **Apply to my agent** and **Start from my site** are not connected yet. The
  first shows the JSON that will be saved as the agent's widget settings. The
  second explains that it will start you from your site's look: the corner
  other chat widgets leave free, the accent colour, and a character.

The configuration is kept in the page's address (`#c=…`), so a link to the
builder carries it. The publishable key is never put there.

## Remaking the voice

`fixtures/make.mjs` remakes the clips and `voices.json` from the speech tier.
Its header lists what it needs: a key the speech tier trusts (never written
anywhere), ffmpeg, and optionally the voice runtime's cue maker for the mouth
cues. The characters it voices, and the lines, are at its top.

## Moving it to voqalize.com/widget

The builder imports only the package's public entry points (`@voqalize/web`,
`@voqalize/web/widgets` and the schema), so it can move to the marketing site once a release of the package is on npm.
`serve.mjs` is a dev server only. The site would bundle `builder.ts` and
`preview.ts` itself and serve the HTML, CSS, still and `fixtures/` beside them.

## Tests

- `builder.test.ts` (vitest): the form read from the schema, the sparse
  configuration and the snippet.
- `builder.spec.ts` (Playwright, the `builder` project): fields toggled in the
  form change the preview's widget and the snippet.
