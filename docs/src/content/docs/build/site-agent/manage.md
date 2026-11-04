---
title: Site Agent rollback, roles and the console
description: Running a Site Agent day to day. Going back to an earlier version, replacing a lost key, who in your tenant may do what, and which steps the console takes that MCP does not.
---

The site is live, kept current and set up the way you want
([Settings](/build/site-agent/settings/)). This page is what you reach for
afterwards: going back when a version turns out wrong, replacing the key, who
on your team may do each step, and where each step can be taken.

## Roll back

Publish an earlier `superseded` version with `publish_site_version`. It needs
no new approval, and goes through the same `confirm` step as any publish
([Publish in full](/build/site-agent/refresh/#publish-in-full)). A rollback to
a `partial` version needs `publish_anyway` again. A `starter` version cannot
be rolled back to.

Visitors get the earlier version on their next page load. The version you
rolled back from becomes `superseded` in turn, so you can publish it again
later.

## Replace the key

The snippet's live key is shown once, when the site is added; the console then
lists only its prefix. If you lose it, **Rotate key** on the console's Install
page makes a new key and a new snippet. The previous key keeps working for 24
hours while you update your pages. Rotating is console-only.

## Who may do what

| Role | May |
|---|---|
| Owner or admin | Everything: add a site, edit, add notes, review, publish, change settings and goals, pause, rotate the key, manage invites, try a site tool live, and agree to the robots notice. |
| Member | Read sites, versions and the member parts of the [knowledge](/build/site-agent/knowledge/#what-a-version-holds), and preview a site in their own browser. |

Voqalize staff may act on a site as an admin does, except that only your
owner or admin can agree to the robots notice for your site
([robots.txt](/build/site-agent/security/#robotstxt)).

## Console and MCP

Every step in this section can be taken in the console. A coding agent
connected to the [MCP server](/reference/mcp/#site-agent-tools) can add a site,
read and edit knowledge, run a self study, review, publish, change settings
and manage client invites. These are in the console only:

- rotating the live key;
- starting a study Voqalize runs (**Refresh**) or re-checking chosen site
  tools;
- previewing in your own browser (a member invite);
- notes that correct what the assistant knows;
- the site's goals;
- turning the robots agreement off or on;
- pausing and resuming the site, and renaming it;
- **Try it live**, running one proven site tool on your site.
