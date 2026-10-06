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
  site, is dropped.

For an urgent change, refresh by hand:

```sh
uv run python demos/kdem/backend/knowledge.py refresh --force https://karnatakadigital.in/policies/
uv run python demos/kdem/backend/knowledge.py pending    # pages waiting for review
```

To approve a held page, add it to `pages` with its section and title.
