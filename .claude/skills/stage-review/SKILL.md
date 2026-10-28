---
name: stage-review
description: Review a diff that touches Stage (a Stage Spec, a kit, a performer, a brain using voqalize.sdk.stage, or @voqalize/stage itself) against Stage's rules. Use before committing or when asked to review Stage changes.
---

# Reviewing a Stage change

Read the diff, then check each item. Report only what is wrong, with the file and line,
and why it fails in a call. `design/stage.md` is the contract.

## The spec

- [ ] Every move's **class** matches what it does, and was not lowered to make it a cue.
      A move that changes what the person owns is `confirmed`; paying, consent, personal
      data submission and IDs are not moves at all.
- [ ] A **verb** only on `look`, `navigate` or `reversible`, at most four word arguments;
      the verb is one lowercase word and not a call word.
- [ ] **Arguments** name what the visitor sees, or are enums; nothing the model would have
      to invent (selectors, internal ids).
- [ ] Every move that changes the page has **claims or objects**, in every language the app
      speaks.
- [ ] A cue's **say** line writes its own verb and no undeclared one.
- [ ] **Slices** allowlist their fields; anything personal is `private`; event **notes** are
      verb phrases that print no values beyond the change.
- [ ] A kit move changed: a minor version only adds; a lowered class or a rename is a major.
- [ ] `uv run voqalize stage check` has no errors, and the generated files were regenerated
      (`stage_gen.py`, `scene.gen.ts`, any `--json`) in the same commit.

## The page

- [ ] Every performer **rings before it acts**; nothing on the page changes first.
- [ ] A performer **refuses** with the options the page offers instead of guessing.
- [ ] It reports one short detail; it calls `c.done()` when the visible effect has landed,
      and only rings afterwards in `c.after()`.
- [ ] No pipecat client is constructed, wrapped or re-exported.
- [ ] No state is pushed whole; changes go as the spec's events, through `scene.event()`.
- [ ] Registration goes through the scene (`registerAll`), never `moves.register` with a
      hand-written class.
- [ ] A plugin is declared in the spec, and requests only its `egress` origins.

## The brain

- [ ] The brain's moves come from `stage_gen`, never hand-declared.
- [ ] Replies pass through `stage.cued(...)`; results and events through `stage.handle(...)`.
- [ ] No written line blames the site, store or page for being slow; holding lines are
      neutral ("Still working on it, one moment.").
- [ ] Tools return within the tool budget; a read answers from the mirror.
- [ ] The brain sends no acknowledgement of its own: the runtime acknowledges.

## Prose (this repo is public)

- [ ] No internal service names, tenant or agent ids, secrets or node addresses.
- [ ] A new term is in `design/lexicon.yaml` before it appears in docs.
- [ ] The agent is called "the agent", not a persona's name, in docs.
