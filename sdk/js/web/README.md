# @voqalize/web

Voqalize in the browser. This package will hold the one client library: the
session, and the `<vq-widget>` web component built on top of it.

**Pre-release.** It has not been published to npm, and nothing here is a
stable API yet. Today the package holds the widget's core, without any markup:

- **The widget configuration**: a JSON Schema, its TypeScript types, and a
  parser that fills in the defaults.
- **The headless controllers** for the mic, captions and placement.
- **An internal session adapter** over `@voqalize/client-transport` and the
  client.

## Entry points

| Import | What it holds |
|---|---|
| `@voqalize/web` | The version. `VoqalizeClient` will be added here. |
| `@voqalize/web/widgets` | The configuration parser, the SiteSettings mapping, and the headless controllers. |
| `@voqalize/web/widget-config.schema.json` | The configuration schema. |
| `@voqalize/web/internal` | The session adapter and instant-start media manager. Not API: these can change in any release. |

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
- **Theme tokens**: `--vq-*` custom properties, set on the element or on any
  ancestor.
- **Parts**: `::part(card)`, `::part(face)`, `::part(controls)`,
  `::part(captions)` and the rest, for CSS the tokens do not cover.
- **Slots**: your own content in named places (`side`, `controls-start`,
  `controls-end`, `launcher`, `notice`, `end`).
- **Composition**: arrange the parts yourself (`<vq-avatar>`, `<vq-controls>`,
  `<vq-captions>`, `<vq-status>`), all bound to one session.
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

This package has only the configuration and the headless behaviours so far.
The element, its parts and its slots come next.

## Development

```sh
pnpm typecheck
pnpm test
pnpm build
```

MIT licensed.
