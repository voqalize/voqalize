# @voqalize/web

Voqalize in the browser. This package will hold the one client library: the
session, and the `<vql-widget>` web component built on top of it.

**Pre-release.** It has not been published to npm, and nothing here is a
stable API yet. Today the package holds:

- **The widget**: `<vql-widget>` and its parts, built with Lit.
- **The launcher**: `<vql-launcher>`, an entry of its own with no
  dependencies, for a page that wants the button before anything else loads.
- **React wrappers and hooks** over the elements and the controllers.
- **The widget configuration**: a JSON Schema, its TypeScript types, and a
  parser that fills in the defaults.
- **The headless controllers** for the mic, captions and placement.
- **An internal session adapter** over `@voqalize/client-transport` and the
  client.

## Entry points

| Import | What it holds |
|---|---|
| `@voqalize/web` | The version. `VoqalizeClient` will be added here. |
| `@voqalize/web/widgets` | The elements and `defineElements()`, the configuration parser, the SiteSettings mapping, and the headless controllers. |
| `@voqalize/web/launcher` | `<vql-launcher>` alone, with no dependencies. |
| `@voqalize/web/react` | The elements as React components, and hooks over the controllers' stores. |
| `@voqalize/web/widget-config.schema.json` | The configuration schema. |
| `@voqalize/web/internal` | The session adapter and instant-start media manager. Not API: these can change in any release. |

## The widget

```html
<script type="module">
  import { defineElements } from "@voqalize/web/widgets";
  defineElements();
</script>
<vql-widget agent="agent_…" key="pk_…" name="Emily" tagline="Ask me about sofas"></vql-widget>
```

The configuration is given either as attributes, for the common fields, or
whole as the `config` property, which takes the same object
`parseWidgetConfig` reads. An attribute wins over the same field in the
property. The attributes are `agent`, `key`, `name`, `character`, `avatar`
(`"false"` for voice only), `avatar-shape`, `anchor`, `placement`, `move`,
`launcher`, `label`, `tagline`, `open-style`, `size`, `collapsed`, `captions`,
`mic-level`, `instant-start`, `brand` and `scheme`; `CONFIG_ATTRIBUTES` maps
each one to its field.

The session is created only when the call starts, and its code is loaded
then, so a page that never opens the widget never downloads the transport. A
page that runs its own session hands it over as the `session` property, or
gives a `sessionSource` that mints the connection.

### States

The widget reflects where it is as two attributes, `view` and `form`:

- **closed**, before a call: `pill`, `face`, `card`, or `none` (the page
  opens it from its own button, or from a `launcher` slot);
- **open**, in a call: `card` (floating), `hero` (filling the window), or
  `card` inside the page when `placement` is `inline`;
- **collapsed**, a call kept running out of the way: `bubble` or `pill`;
- **ended**: the reason, with buttons to call again or close;
- below the mobile breakpoint, the open widget is a `sheet` along the bottom
  of the screen, which a swipe down collapses.

The face is one element from the first state to the last: the widget scales
it between states and never re-mounts it, so the avatar never restarts.

### Methods and events

- `open()` opens the widget, and starts the call if none is running.
  From collapsed it only opens.
- `collapse()` keeps the call and gets out of the way.
- `close()` hangs up if needed and goes back to closed.
- `end()` hangs up and shows the ended state.
- `place(anchor)` or `place({ x, y })` moves a floating widget.
- `setMuted(muted)` mutes or unmutes the mic.

Events bubble and cross the shadow root: `vql-view` (`{ view, form }`),
`vql-open`, `vql-collapse`, `vql-close`, `vql-end` (`{ reason }`), `vql-mic`
(`{ state, hint }`), `vql-agent` (`{ state }`) and `vql-place`
(`{ anchor, point, free }`).

### Placement

A floating widget sits at an anchor and keeps clear of anything matched by
`placement.avoid` or marked `data-vql-avoid`. `move` decides what a visitor
may do: `snap` (drag it, and it settles at the nearest anchor), `free`
(drag it anywhere) or `fixed`. The grip button moves it from the keyboard:
the arrow keys go to the next anchor when snapping, and nudge it when free,
further with Shift. Placement is the `PlacementController` from this
package, so a page drawing its own widget gets the same behaviour.

### The parts

Each part is an element of its own, usable alone or arranged by your page,
and the widget is built from them:

- `<vql-launcher>`: the closed button, in `pill`, `face` or `card` variants.
  It has no dependencies, and loads from `@voqalize/web/launcher`.
- `<vql-face>`: the agent's face. It holds, in order of preference, your
  own content in its slot, the avatar, a still image, or a waveform for voice
  only, over a background that is a colour, a gradient, or an image or video
  URL.
- `<vql-mic>`: the mute button, with a ring or bars that move with your
  voice, and a caret that opens the device menu.
- `<vql-devices>`: the mic and speaker menu, with a level meter.
- `<vql-captions>`: the agent's words, lit as they are spoken.
- `<vql-coach>`: the help shown when the mic is blocked, missing, or waiting
  for permission, worded for the visitor's browser.
- `<vql-status>`: a chip for connecting, listening, thinking, speaking and
  the mic's state, with the call's time.
- `<vql-end>`: the end-call button.

### The avatar

`@voqalize/avatar` is an optional peer dependency. The face loads it only
once there is a character and a live call; if it cannot be loaded, the still
image stays. A page that bundles the avatar says how to load it, once:

```ts
import { setAvatarLoader } from "@voqalize/web/widgets";
setAvatarLoader(() => import("@voqalize/avatar"));
```

## Configuration

A widget takes one configuration object. Every field is optional, and an
empty object gives the defaults. The schema in
`src/config/widget-config.schema.json` is the reference: it lists each field
with its default and the values it accepts.

```ts
import { parseWidgetConfig } from "@voqalize/web/widgets";

const config = parseWidgetConfig({
  agent: "agent_…",
  key: "pk_…",
  placement: { anchor: "bottom-left", avoid: ["#cookie-banner"] },
  theme: { brand: "#0f766e" },
});
```

`parseWidgetConfig` never throws:

- An unknown field is ignored. All of them are named together in a single
  console warning.
- An invalid value is replaced by its default, with a warning that names the
  field.
- A configuration given as JSON text, as an HTML attribute carries it, is
  read the same way.

`widgetConfigFromSiteSettings` maps a Site Agent's saved settings onto this
configuration. It covers position, colours, avatar, the assistant's name, and
the greeting, which is returned alongside the configuration because the
greeting is session data, not presentation.

## Going beyond the defaults

The defaults are meant to cover most pages. Past them, there is a fixed
order of tools, and each step is public and stable. Take the first one that
does the job:

- **Configuration**: every field in the schema.
- **Theme tokens**: `--vql-*` custom properties, set on the element or on any
  ancestor.
- **Parts**: `::part(card)`, `::part(face)`, `::part(controls)`,
  `::part(captions)` and the rest, for CSS the tokens do not cover.
- **Slots**: your own content in named places (`side`, `controls-start`,
  `controls-end`, `launcher`, `notice`, `end`).
- **Composition**: arrange the parts yourself (`<vql-face>`, `<vql-mic>`,
  `<vql-captions>`, `<vql-status>` and the rest), all bound to one session.
- **Headless behaviours**: the controllers in this package, attached to your
  own markup:
  - placement: anchors, snap, avoid, remember;
  - caption timing;
  - mic state and level.
- **Events and actions**: `open()`, `collapse()`, `place()`, and an event for
  each change of state.

Reaching into the shadow root, `!important`, and forking the widget are ruled
out. If you need one of them, a step is missing from the library, and we will
add it.

### Theme tokens

Set these on the widget or on any ancestor; `TOKENS` lists them:
`--vql-brand`, `--vql-on-brand`, `--vql-surface`, `--vql-ink`, `--vql-muted`,
`--vql-line`, `--vql-live`, `--vql-danger`, `--vql-radius`, `--vql-font`,
`--vql-shadow`, `--vql-caption-size`, `--vql-face-background`, `--vql-z`,
`--vql-listening`, `--vql-thinking` and `--vql-speaking`.

A token set by the page wins over the same colour in the configuration. The
widget follows the visitor's light or dark setting, unless `theme.scheme` (or
the `scheme` attribute) says `light` or `dark`. A brand colour without
readable text on it gets black or white text, chosen for contrast.

### Parts

The widget exposes `dock`, `card`, `stage`, `frame`, `face`, `status`,
`grip`, `body`, `captions`, `controls`, `mic`, `minimise`, `end`, `devices`,
`side`, `notice`, `coach`, `launcher`, `expand`, `badge`, `hint`,
`sheet-handle`, `end-card`, `end-reason`, `again` and `close`. The `card`
part also carries the form's name, so `::part(card bubble)` styles only the
bubble. Each element exposes its own parts as well, listed in its source.

### Slots

- `side`: a panel beside the open card, such as the product being discussed.
- `controls-start` and `controls-end`: your own buttons in the control row.
- `launcher`: your own closed button, which opens the widget when pressed.
- `notice`: a line above the controls, such as a recording notice.
- `end`: content on the ended card, such as a survey link.

### Accessibility

Focus moves into the widget when it opens (to the mic) and back to the
launcher when it closes. Every button has a label. Escape closes the device
menu, then collapses the widget. Finished sentences are read out through a
polite live region; the word-by-word captions are hidden from screen
readers, so nothing is read twice. Motion stops under
`prefers-reduced-motion`.

### Strict CSP

The elements work under `script-src 'self'; style-src 'self'`, with no
`unsafe-inline` and no `unsafe-eval`. Styles are constructed stylesheets;
the few values set at run time (the dock's position, the meter's level) are
set through the CSSOM, never as a `style` attribute; and no script is
loaded from a `data:` URL. The component page under `test/pages` is served
with such a policy and fails on any violation.

## React

```tsx
import { VoqalizeWidget, useMicState } from "@voqalize/web/react";

<VoqalizeWidget config={{ agent, key, name: "Emily" }} onEnd={(e) => console.log(e.detail.reason)} />;
```

React 18 sets every prop on a custom element as an attribute, so these
wrappers set props as properties instead, and turn `onX` props into
listeners for the `vql-x` event. They work the same on React 18 and 19, and
rendering one registers the elements. `VoqalizeLauncher`, `VoqalizeFace`,
`VoqalizeMic`, `VoqalizeDevices`, `VoqalizeCaptions`, `VoqalizeCoach`,
`VoqalizeStatus` and `VoqalizeEnd` wrap the parts.

The hooks read the controllers' stores with `useSyncExternalStore`:
`useSessionState`, `useMicState`, `useCaptions`, `usePlacement`, and
`useVoqalizeStore` for any store.

## Development

```sh
pnpm typecheck
pnpm test          # unit tests, in happy-dom
pnpm build
pnpm size          # the launcher's and the elements' size, gzipped
pnpm test:pages    # every state in Chromium, under a strict CSP
```

`pnpm test:pages` saves a screenshot of each state to `test-results/shots`,
or to `SHOTS_DIR` when it is set. The launcher's budget is 20 KB minified,
which `pnpm size` checks.

MIT licensed.
