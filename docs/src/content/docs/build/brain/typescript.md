---
title: TypeScript types
description: Your Action and AppEvent classes already describe every payload. `voqalize types` turns both into TypeScript unions so the browser half of each direction is derived rather than copied — and adding one becomes a compile error until it is handled.
---

An [action](/build/brain/actions/) is already a complete description of a
payload: field names, types, defaults, docstrings. So is an [app
event](/build/brain/context/), in the other direction. Writing either description
a second time in TypeScript is not typing work, it is copying — and the copy has
no way to fail.

```bash
uv run voqalize types backend/brain.py -o frontend/src/actions.gen.ts
```

Out comes one file covering both directions: an interface per action and per
event, an interface per nested model, a union over `command` and a union over
`event`. Check it in, and regenerate it the way you regenerate a lockfile.

## What the copy costs

Two failures, and neither of them says anything at the time.

**Rename a field in Python** and the hand-written interface goes on compiling.
The browser reads `cmd.mealType`, gets `undefined`, coerces it to `''`, and draws
a row with a blank cell. Nothing throws. The bug surfaces as a screenshot in a bug
report a week later.

**Add an action** and the page's `switch` drops it on `default: break`. The brain
dispatches, the wire carries it, the reducer ignores it, and the screen simply
does not move — while the transcript reads perfectly, because the agent said the
right sentence either way.

Generated types turn both into build failures. That is the entire pitch: not
better editor completions, but a compiler that notices.

## What it emits

For a brain declaring `LogMeal`, with a nested `MealItem`:

```ts
// Generated from backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types backend/brain.py -o frontend/src/actions.gen.ts

export interface LogMeal {
  /** Which meal of the day this is. */
  meal_type: 'breakfast' | 'lunch' | 'snack' | 'dinner' | 'other';

  /** The foods with quantities and your calorie estimates. */
  items: MealItem[];

  /** Optional one-line note, e.g. 'ate out — office canteen'. */
  note: string;
}

export interface MealItem {
  name: string;
  quantity: string;
  calories: number;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'log_meal'; payload: LogMeal }
  | { command: 'highlight'; payload: Highlight };

export function asUiAction(command: string, payload: unknown): UiAction | null;
export function unhandledUiAction(action: never): never;
```

And for the same brain declaring the `QuantitySet` event:

```ts
export interface QuantitySet {
  item_id: string;

  quantity: number;
}

/** Everything the person can do on screen, discriminated by `event`. */
export type AppEvent =
  | { event: 'quantity_set'; payload: QuantitySet };

export const APP_EVENT_NAMES: readonly AppEventName[];
export function sendAppEvent(
  send: ((event: string, payload?: unknown) => void) | null | undefined,
  event: AppEvent,
): void;
```

`sendAppEvent` takes a pipecat client's `sendUIEvent` — or `null` before the call
connects, which drops the gesture, correctly: there is no brain that missed it.

```tsx
sendAppEvent(client?.sendUIEvent.bind(client), {
  event: 'quantity_set',
  payload: { item_id: 'li3', quantity: 5 },
});
```

Docstrings and `Field(description=...)` carry across as JSDoc, so the hint your
model reads is the hint your editor shows. A `Literal` or an `Enum` becomes a
string-literal union — narrower than the `// breakfast | lunch | ...` comment a
hand-written file usually settles for.

## Reading it in the browser

`asUiAction` narrows a raw `ui-command` and returns `null` for a command this file
does not declare, because a page and a brain ship separately and an older page
meeting a newer action should ignore it rather than throw. `unhandledUiAction`
goes in the `default` arm, where its `never` parameter is what fails the build:

```tsx
useRTVIClientEvent(
  RTVIEvent.UICommand,
  useCallback(({ command, payload }: UICommandData) => {
    const action = asUiAction(command, payload ?? {});
    if (!action) return;
    switch (action.command) {
      case 'log_meal':
        // `action.payload` is LogMeal here.
        return store.logMeal(action.payload);
      case 'highlight':
        return store.highlight(action.payload.section);
      default:
        return unhandledUiAction(action);
    }
  }, [store]),
);
```

Add `ShowSummary` to the brain, regenerate, and the build stops on that last line:

```
error TS2345: Argument of type '{ command: "show_summary"; payload: ShowSummary; }'
  is not assignable to parameter of type 'never'.
```

## No action field is optional, and that is on purpose

A Python field with a default is absent from the schema's `required` list, and
the generated *action* interface still declares it as present. That is not a bug
in the reading of `required` — it is the guarantee `Action` makes: **every
declared field is emitted, `None` included, as JSON `null`.** The wire shape is a
function of the class, not of which fields happened to be set on one instance.

So `note: str = ""` becomes `note: string`, and `caption: str | None = None`
becomes `caption: string | null` — always there, sometimes null. Marking either
one `?` would force every reader to handle an absence that cannot occur.

The same guarantee is why nothing here emits zod or any other validator.
Narrowing on `command` is sound on its own: the brain that minted the message is
the brain these types were generated from.

**Events go the other way, so `required` is the truth there.** Your browser builds
the object and pydantic fills the defaults on arrival, so `question: str = ""`
generates `question?: string` — a field the page may leave out. A nested model
both halves reference is generated whole, which is the stricter read and always
valid to send.

## Pointing it at your module

The argument is the module that *declares* your actions — usually the brain
itself, sometimes a separate `actions.py` that both the brain and your tests
import:

```bash
voqalize types backend/brain.py -o frontend/src/actions.gen.ts   # a file path
voqalize types myapp.brain.actions -o src/actions.gen.ts          # or a dotted module
```

A file path is imported under its real package name, so a brain that does
`from .content import FACTS` loads here exactly as it does when it runs.

**What it reads is that module's namespace**, not every `Action` or `AppEvent`
subclass alive in the process. Importing one brain drags in whatever that brain
imports, and a process-wide registry cannot say which app speaks what. Anything
the module names — declared there or imported into it — is in; nothing else is.
That is the same scoping `AppEvents` uses at runtime, for the same reason.

Three flags, and that is the whole surface:

| | |
|---|---|
| `-o`, `--out` | file to write; stdout when omitted |
| `--union-name` | name of the action union, `UiAction` by default |
| `--event-union-name` | name of the event union, `AppEvent` by default |

Rename a union when one frontend talks to two brains: everything derived from it
follows, so `--union-name DeskAction` gives you `DeskAction`,
`DESK_ACTION_COMMANDS`, `asDeskAction` and `unhandledDeskAction`.

## Keeping it honest

The output is byte-identical run to run — no timestamp, no set iteration — so the
check is one line in CI:

```bash
voqalize types backend/brain.py -o frontend/src/actions.gen.ts
git diff --exit-code frontend/src/actions.gen.ts
```

A brain whose types were not regenerated fails there rather than in a browser.

Keep the generated file to itself and import from it. Client-only fields — a
`fresh?: boolean` your reducer sets, an `id` you mint on arrival — belong in your
own view models, which can extend the generated ones. Editing the generated file
works exactly until the next regeneration.

## Read next

- [Actions](/build/brain/actions/) — declaring the payloads this generates from.
- [Context and history](/build/brain/context/) — the inbound half these events serve.
