---
name: stage-move
description: Add or change a Stage move (something the voice agent does on a page) in an app's Stage Spec, then regenerate and check it. Use when a site or app needs a new on-screen action, a cue verb, a change to a move's class or arguments, or claims and objects for the promise guard.
---

# Adding a Stage move

A move is declared once, in the app's `scene.json` (the Stage Spec), and generated for
the brain and the page. Never declare a move in Python or TypeScript by hand. The build
contract is `design/stage.md`; read it if anything here is unclear.

## 1. Choose the class: it decides everything else

Ask, in order, and stop at the first yes:

1. Does it change something the person owns (cart, booking, form data, an account)?
   → `confirmed`. A tool only, never a cue, sent after a clear yes in a later turn.
   Paying, submitting personal data, consent, captchas and ID numbers are not moves at
   all: the person presses that button.
2. Does it change the page's state in a way that can be undone (filter, sort, search,
   pick a variant, open a calendar)? → `reversible`.
3. Does it open another page or item? → `navigate`.
4. It only changes what is in view (scroll to, ring, open a tab or a question) → `look`.

Never lower a class to make a move cueable. When unsure, choose the higher class.

## 2. Cue or tool

- A `look`, `navigate` or `reversible` move with at most four plain word arguments may
  have a `verb`: one lowercase word, 2–12 letters, never `name function tool call args
  arguments action parameters`. The model writes it as `{verb: A | B}` at the start of
  the sentence it belongs to, and the page makes it as the voice reaches those words.
- Everything else has no verb and is sent by a brain tool (`stage.send(move_id, args)`).
  A tool-only move takes at most twelve arguments.

## 3. Write it

```json
{
  "id": "listing.filter",
  "verb": "filter",
  "class": "reversible",
  "args": [{ "name": "facet" }, { "name": "value", "optional": true }],
  "say": "{filter: Facet | Option} as you name a filter of the listing in front.",
  "claims": ["filtering by", "filtro por"],
  "objects": ["filter", "filtro"],
  "doc": "Apply one filter of the listing in front with the listing's own control.",
  "notes": ["Dev call 1a2b: why this is as it is."]
}
```

- `id`: `area.verb_or_noun`, unique. A kit's moves are named `<kit>.…`; check
  `sdk/python/src/voqalize/sdk/stage/kits/` before writing one a kit already has, and take
  it with `"kits": [{"id": "commerce", "major": 1, "moves": [...]}]` instead.
- `args`: `string` (default), `integer`, `number`, `boolean`, or `array`; `enum` for a
  closed set; `optional` (absent or null) or a `default`. Arguments name things the
  visitor sees (a heading, an option label), never selectors or ids the model would invent.
- `say`: the one line that teaches the cue, written with its own verb. It goes into every
  request, so keep it short.
- `claims` / `objects` (any move that changes the page): the phrases and nouns that, said
  in a reply, promise this move. A turn that promises it and never sends it is caught and
  made to send it. Write `claims` as announcements ("opening the * calendar"; `*` is up
  to a few words), and `objects` in the singular, in every language the app speaks.
- `doc` for whoever writes the performer; `notes` for the call that taught it.

## 4. Regenerate, check, perform

```sh
uv run voqalize stage gen <app>/scene.json --py <brain>/stage_gen.py --ts <page>/scene.gen.ts
uv run voqalize stage check <app>/scene.json          # errors fail; warnings are advice
```

Then write the performer on the page. Register it through the scene so the class and
argument types come from the spec, and a move left out does not compile:

```ts
scene.registerAll(moves, {
  "listing.filter": async ({ facet, value }, c) => {
    const pill = findPill(facet, value) ?? c.refuse("value", `no ${facet} ${value}`, offered(facet));
    await c.scrollTo(pill);
    await c.ring(pill, `${facet}: ${value}`); // ring before acting, always
    await c.beat();
    press(pill);
    return `${facet} ${value} applied`;     // one short detail the model can repeat
  },
  // …every other move
});
```

Rules a performer keeps: ring before anything on the page changes; refuse with the options
the page offers rather than guessing; report as soon as the visible effect lands
(`c.done(...)`), and ring what it points at afterwards with `c.after(...)`.

## 5. Prove it

- `uv run --directory sdk/python pytest -q tests/unit/stage` and the app's own tests.
- A page test with `@voqalize/stage/conformance`: `checkRegistry(scene, moves)` and
  `conformance(scene, moves, [{ move, args, setup }])` must find no errors.
- For a demo, `cd demos && uv run pytest tests/test_stage_specs.py` (generated files current,
  no check errors), then a call on dev.
