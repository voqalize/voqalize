---
title: Site Agent previews and invites
description: Trying an unpublished Site Agent version on your live site before visitors get it, and letting others try it. Client and member invites, the Voqalize Preview extension, minutes, revoking, and the console's Try it live.
---

Every version so far reached visitors only once it was published
([Refreshes and review](/build/site-agent/refresh/)). A **preview** lets a
person try a version on your live site first: before it is published, and
before the snippet is on any page. There is no sign-in.

A preview always shows the site's `preview_version`: the newest version that
is waiting for review, approved or published
([Published, preview and latest](/build/site-agent/refresh/#published-preview-and-latest)).

```text
  owner or admin                     the person invited               your live site
  ──────────────                     ──────────────────               ──────────────
  create an invite ── …/p/<code> ──▶ opens the link
                                     installs Voqalize Preview
                                     opens the site ────────────────▶ button with a
                                                                      Voqalize Preview badge,
                                                                      speaking the preview version
```

## Share a preview

An owner or admin creates a **client invite**, in the console or with
`create_site_invite` over [MCP](/reference/mcp/#site-agent-tools):

- a label saying who it is for;
- how many days it works;
- how many voice minutes it may use.

The answer carries the link, `…/p/<code>`. It is shown once. The site must have
a version to preview. `list_site_invites` lists a site's invites and
`revoke_site_invite` ends one.

## Preview it yourself

Any member of the tenant can use **Preview in my browser** in the console. That
**member invite** lasts 30 days and has no minute budget. It is console-only.

## Opening the link

The link shows how to install the **Voqalize Preview** extension for Chrome,
then opens the site.

- **The extension is downloaded from the console and loaded unpacked**:
  `chrome://extensions`, **Developer mode**, **Load unpacked**. It is not in
  the Chrome Web Store.
- **It asks Chrome for access to the site's own origins only.**
- **On the page** the button carries a **Voqalize Preview** badge and follows
  the same rules as the installed snippet
  ([where the button shows](/build/site-agent/settings/#where-the-button-shows)).
  A page that already runs the snippet is left alone.

## Minutes, keys and revoking

- **Voice minutes are checked when a call starts.** A call that crosses the
  budget is not cut.
- **Each person's key lasts 24 hours** and is refreshed from the invite until
  the invite ends.
- **Revoking an invite also revokes every key made from it**, so the next call
  from that browser is refused.
- **A paused site still previews.** Pausing stops the live key, not previews
  ([Pause](/build/site-agent/settings/#pause-the-assistant)).

## Try a site tool live

In the console, an owner or admin can run one proven site tool on the real
site with **Try it live**, to watch it work. It runs in the Voqalize Preview
extension, on the preview version, with the arguments from the tool's own
passing proof. Each try uses a single-use token that lasts 10 minutes.

- **A tool that only looks or opens a page** runs at once.
- **A tool that changes the page**, with a proven undo, needs your
  confirmation first.
- **A tool that sends a form, or does anything that cannot be undone**, cannot
  be tried.
