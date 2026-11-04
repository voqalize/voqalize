---
title: The Site Agent
description: A voice assistant for a website you already run, built by Voqalize from the site's public pages. The whole path in order, from adding the site to a visitor's first call, with the rest of the section in reading order.
---

The Site Agent is a voice assistant for a website you already run. You give
Voqalize the site's address. Voqalize reads its public pages, writes down what
the assistant knows and what it may do on each kind of page, and a person on
your side reviews that before visitors hear it. Visitors reach it through one
script tag. You write no brain and run no server.

A voice agent you build yourself, with your own brain, needs none of this;
start at [How Voqalize works](/build/session/) instead.

```text
  you                              Voqalize                           a visitor
  ───                              ────────                           ─────────
  add the site ──────────────────▶ quick first read
                                     └─▶ starter version, published ─▶ "still learning"
                                   full study
                                     └─▶ new version, waiting
  review it, publish it ─────────▶ that version is published ───────▶ the assistant
  paste site.js on your pages ──────────────────────────────────────▶ clicks, talks
```

This page follows that path once, from adding the site to a visitor's first
call. Each later page in this section picks the story up where the one before
left it, and adds what comes after the first call.

## Add the site

A tenant owner or admin adds the site in the console's **Add a site**, or a
coding agent does it with `create_site` over [MCP](/reference/mcp/#site-agent-tools).
Both take the site's home page, an `https://` address on one public host, and
the languages the assistant speaks; English when you choose none. The origin of
that address is the site's **primary origin**, and a tenant has one site per
primary origin.

The answer carries the **snippet**: the script tag for your pages, with the
site's live key in it. It is shown once. Keep it; you paste it in a later step.

Adding the site also asks you to agree that Voqalize may read pages your
`robots.txt` asks crawlers to skip. In the console, adding the site is the
agreement; over MCP it is a separate argument.
[Bot protection and robots.txt](/build/site-agent/security/#robotstxt) has the
words and how to turn it off.

## The quick first read

Within minutes of adding the site, Voqalize reads its home page and up to 10 key pages (about, pricing, contact, FAQ, policies)
and publishes what it found as the site's first **version**.

A version is one complete, numbered copy of what the assistant knows and may do
on the site. A version is never changed after it is stored; every change makes a
new one. The site **publishes** one version at a time, and that is the one
visitors are served.

This first version is the **starter**. It answers on every page carrying the
snippet and tells visitors it is still learning the site. It is published
without review, it cannot be edited, and once a studied version replaces it, it
is never published again.

## The full study

At the same time Voqalize starts the site's first **study**: it reads the site
in depth and writes a new version from it. A study writes:

- what the assistant always knows, in every call;
- the deeper topics it reads when a question needs one;
- every fact, with the page it came from and the quote on that page;
- a map of the site's kinds of page and how to reach them;
- the **site tools**: actions the assistant may run on your pages, such as
  adding an item to the cart or filling a form, each proven by a run on your
  site before it is kept.

Before the version is stored, Voqalize **checks** it: every fact's quote is on
its page, the page map reads the pages it claims to, and every site tool passed
its proof. A version that passes waits for review with the status
`ready_for_review`. Nothing visitors hear changes yet.

If your site's bot protection turns the reader away, the version is `blocked`
instead; [Bot protection and robots.txt](/build/site-agent/security/#if-your-site-blocks-automated-visitors)
says how to let it in.

## Review and publish the first version

A tenant owner or admin reads the new version and decides. In the console this
is the site's review; over MCP it is `get_site_version` and
`read_site_knowledge` to read, then:

- **Approve it.** `review_site_version` with `decision` `approve`. Where the
  study found two facts that disagree, approving needs a choice between them.
  Approving changes nothing visitors get.
- **Publish it.** `publish_site_version`. Without `confirm: true` it publishes
  nothing and answers with what would change against the live version; show
  that to the person, then call again with `confirm: true`.

The published version is now the studied one, and the starter's "still
learning" greeting is gone. This first publish of a studied version also
applies the assistant name, greeting, colours and corner the study chose,
unless a person has already saved their own
([Settings](/build/site-agent/settings/)).

## Paste the tag

Paste the snippet just before `</body>` on every page where the assistant may
appear:

```html
<script async src="https://cdn.voqalize.com/sites/site.js" data-key="pk_live_…"></script>
```

- **It is the same script for every website.** Only the key is yours.
- **The key works only on the site's own origins**, so it need not be kept
  secret.
- **The URL never changes.** Publishing a new version needs no change on your
  pages; visitors get it on their next page load.
- **You can paste it at any point.** Until a version is published the script
  shows nothing.

If your site sends a `Content-Security-Policy`, it needs the sources in
[CSP](/build/site-agent/security/#if-your-site-sets-a-content-security-policy)
before the button can load.

## A visitor talks to it

The script reads the site's settings and shows a button in a corner of the
page. A visitor clicks it and talks. The assistant answers from the published
version and follows the page as the visitor moves through the site: it can
open pages, search, show a section, point at things and, through the site tools
the reviewed version holds, act on the page. It never places an order or
presses a payment control.

Each call is a session in your tenant, read back like any other in
[Operate](/operate/) and kept for 30 days.
[What is sent](/build/site-agent/security/#what-is-sent) lists exactly what
crosses during a call.

## What comes next

The site is live. The rest of this section, in reading order:

- [Refreshes and review](/build/site-agent/refresh/): keeping it current,
  which refreshes publish themselves, and every state a version can be in.
- [Edit the knowledge](/build/site-agent/knowledge/): changing what the
  assistant knows and may do yourself, through a checked draft.
- [Self studies](/build/site-agent/self-study/): running a study with your own
  coding agent over MCP, and the upload it sends.
- [Previews and invites](/build/site-agent/preview/): trying an unpublished
  version on your live site, and letting others try it.
- [Settings](/build/site-agent/settings/): the assistant, avatar, languages,
  look, where the button shows, and what the assistant may do.
- [CSP, bot protection and data](/build/site-agent/security/): what your site
  must allow, and what is sent.
- [Roll back, roles and the console](/build/site-agent/manage/): going back to
  an earlier version, who may do what, and what only the console does.
- [Limits](/build/site-agent/limits/): every bound in one table.
