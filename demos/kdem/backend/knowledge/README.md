# Aria's knowledge base

What Aria answers from on karnatakadigital.in. This directory is content, not
code: `../knowledge.py` reads it.

## `approved_pages.json`

The list KDEM reviews. It has four parts:

- **`pages`**: every page Aria may answer from, one canonical URL per topic.
  A duplicate or older copy of a page is listed under its canonical page's
  `aliases`, so a link to either one opens the same page. A page with
  `hub_for` is a hub: a new page it links to is added to that section
  automatically.
- **`sections`**: which parts of the site are approved, and which take new
  pages without a person looking first. News and events are added as they are
  published. A new flat page is added only when an approved hub links to it.
  Everything else is held for review.
- **`excluded_patterns`**: test and placeholder pages, form-only pages and
  archives. They are never read.
- **`held_patterns`**: pages that always wait for a person, even when a hub
  links to them.

Only the text a visitor can see is used. Menus, headers, footers, popups,
forms, and anything hidden or placed off-screen are left out. PDFs are not
read: Aria names the document and links to the page that lists it.

## The snapshot

The text of each page is not kept here. It is read from the site into a
snapshot outside the repository (`KDEM_KNOWLEDGE_DIR`), refreshed about once a
day from `wp-sitemap.xml`:

- a page whose `lastmod` changed is read again;
- a new page in an approved section is added;
- a new page anywhere else is recorded for review;
- a page that is no longer in the sitemap, or that now redirects to another
  site or to another page, is dropped;
- a page taken off `pages` is dropped. A page that was added automatically is
  dropped and recorded for review when its section is no longer approved for
  new pages, or when it now matches a held pattern.

The list is applied to the snapshot every time it is loaded, so a page taken
off the list stops being answered from on the next session, before any
refresh.

For an urgent change, refresh by hand on each brains host, against the brain's
own snapshot directory (see `../../README.md`):

```sh
KDEM_KNOWLEDGE_DIR=<the brain's snapshot dir> uv run python demos/kdem/backend/knowledge.py refresh --force https://karnatakadigital.in/policies/
KDEM_KNOWLEDGE_DIR=<the brain's snapshot dir> uv run python demos/kdem/backend/knowledge.py pending
```

To approve a held page, add it to `pages` with its section and title.
