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
  over a light or a dark sample page. Each state chip replays a recorded agent
  turn (its words and voice levels) through a fake session (`replay.ts`). There
  is no call and no network. The face shows a placeholder still, because the
  builder does not bundle the avatar.
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
- **Apply to my agent** and **Start from my site** are not connected yet. The
  first shows the JSON that will be saved as the agent's widget settings. The
  second explains that it will start you from your site's look: the corner
  other chat widgets leave free, the accent colour, and a character.

The configuration is kept in the page's address (`#c=…`), so a link to the
builder carries it. The publishable key is never put there.

## Moving it to voqalize.com/widget

The builder imports only the package's public entry points (`@voqalize/web`,
`@voqalize/web/widgets` and the schema), so it can move to the marketing site once a release of the package is on npm.
`serve.mjs` is a dev server only. The site would bundle `builder.ts` and
`preview.ts` itself and serve the HTML, CSS and still beside them.

## Tests

- `builder.test.ts` (vitest): the form read from the schema, the sparse
  configuration and the snippet.
- `builder.spec.ts` (Playwright, the `builder` project): fields toggled in the
  form change the preview's widget and the snippet.
