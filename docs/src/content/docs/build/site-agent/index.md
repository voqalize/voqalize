---
title: The Site Agent
description: A voice assistant for an existing website that Voqalize builds from the site's public pages. What a site, a version, a study and a review are, who may do what, and where each step happens.
---

The Site Agent is a voice assistant for a website you already run. Voqalize
reads the site's public pages, writes down what the assistant knows and what it
may do on each kind of page, and serves that to visitors through one script tag.
You write no brain and run no server. A person on your side reviews what was
learnt before visitors hear it.

A voice agent you build yourself, with your own brain, does not need any of
this; start at [How Voqalize works](/build/session/) instead.

## How a site goes live

- **Add the site.** In the console, or with `create_site` over
  [MCP](/reference/mcp/#site-agent-tools). You get the snippet with the site's
  live key, shown once.
- **A quick first read is live within minutes.** It reads about 15 of your
  pages, answers on every page carrying the snippet, and tells visitors it is
  still learning the site.
- **A full study runs.** Voqalize reads the site in depth and stores a new
  version that waits for review.
- **A person reviews and publishes it.** Visitors get the new version on their
  next page load.
- **You keep it current.** Refresh the study, edit the knowledge, or run a
  study yourself with your coding agent. Each makes a new version, reviewed the
  same way.

## Concepts

**Site.** One website, named by its primary origin (the `https://` origin of
its home page). A tenant has one site per primary origin. A site holds its
settings, its versions, its preview invites and its live key.

**Version.** One complete, numbered copy of what the assistant knows and may do
on the site. Versions are never changed after they are stored; a change is a new
version. Each has a `status`:

| `status` | Means |
|---|---|
| `ready_for_review` | Passed its checks; waiting for a person. |
| `partial` | Stored, but some checks failed; `partial_failures` lists them. Publishing it needs every one named. |
| `approved` | A person approved it. Visitors do not get it until it is published. |
| `published` | What visitors are served now. |
| `superseded` | Was published, then replaced. Publishing it again is a rollback. |
| `rejected` | A person rejected it. |
| `invalid` | The bundle failed validation. |
| `blocked` | The site blocked our reader; see [If your site blocks automated visitors](/build/site-agent/install/#if-your-site-blocks-automated-visitors). |

Each version also records its `origin`: `starter` (the quick first read),
`managed_study` (a study Voqalize ran), `knowledge_edit` (a draft someone
submitted) or `self_study` (a study your own coding agent ran).

**Published, preview and latest.** A site points at a published, a preview and a latest version.
`published_version` is what visitors are served. `preview_version` is what a
preview invite and the console's preview show, normally the newest version
waiting for review; rejecting it sends the preview back to the published one.
`latest_version` is the newest stored, whatever its status.

**Study.** Reading the site and writing a version from it. A `managed_study` is
run by Voqalize on our servers; you start one with **Refresh** in the console.
A self study is the same work done by your coding agent on your machine, with
your own model account. The first study of a site is `initial`; any later one
is a `refresh`, compared against the published version. See
[Studies and self studies](/build/site-agent/study/).

**Knowledge.** What a version holds, read part by part with
`read_site_knowledge`:

| Part | Holds | Who may read |
|---|---|---|
| `l1` | What the assistant always knows: it is in every call. | Any member |
| `l2` | The menu of deeper topics, each with when to read it. | Any member |
| `l2:<topic>` | One topic in full. | Any member |
| `report` | The study's report. | Any member |
| `facts` | Each fact, with the page it came from and the quote on that page. | Owner or admin |
| `page_map` | The kinds of page on the site and how to reach them. | Owner or admin |
| `questions` | The questions the study tested the knowledge against. | Owner or admin |
| `stage` | The site's Stage moves: what the assistant can show on screen. | Owner or admin |

**Site tools.** The actions the assistant may run on your pages, such as adding
an item to the cart or filling a form, each proven by a check before it is
served. A new or changed site tool is always shown to a reviewer.

**Checks.** What a version is tested against before it can be stored: every
fact's quote is on its page, the page map reads the pages it claims to, and
every site tool passed its proof. A version that fails checks is `partial` or
`invalid`; a draft that fails them cannot be submitted.

**Review.** A person approves or rejects a version, choosing between
conflicting facts where the study found two. Approving does not change what
visitors get; publishing does. See [Review and publish](/build/site-agent/publish/).

**Preview invite.** A link that lets someone try a version that is not yet
published, on your live site, in their own browser, with no snippet installed.
See [Try it before you install](/build/site-agent/install/#try-it-before-you-install).

## Who may do what

| Role | May |
|---|---|
| Owner or admin | Everything: add a site, edit, review, publish, change settings, manage invites, and agree to the robots notice. |
| Member | Read sites, versions and the member parts of the knowledge, and preview a site in their own browser. |

Voqalize staff may act on a site as an admin does, except that only an owner or
admin can agree to the robots notice for their site.

## Console and MCP

Every step above can be taken in the console. A coding agent connected to the
[MCP server](/reference/mcp/#site-agent-tools) can add a site, read and edit
knowledge, run a self study, review, publish, change settings and manage client
invites. These are in the console only:

- rotating the live key;
- starting a managed study (**Refresh**) or re-checking chosen actions;
- previewing in your own browser (a member invite);
- notes that correct or add to what the assistant knows;
- the site's goals;
- turning the robots notice off.

## Pages in this section

- [Install the snippet](/build/site-agent/install/): the tag, its options, CSP,
  bot blocking, previews, and what is sent.
- [Studies and self studies](/build/site-agent/study/): how a site is read,
  and how your coding agent runs a study over MCP.
- [Edit the knowledge](/build/site-agent/knowledge/): drafts, operations and
  checks.
- [Review and publish](/build/site-agent/publish/): approving, publishing and
  rolling back.
- [Settings](/build/site-agent/settings/): the assistant, avatar, languages and
  look.
- [Limits](/build/site-agent/limits/): every bound in one table.
