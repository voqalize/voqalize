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
  Everything else is held for review. A section with `read_pdfs` has the PDFs
  its approved pages link to read as well (see below).
- **`excluded_patterns`**: test and placeholder pages, form-only pages and
  archives. They are never read.
- **`held_patterns`**: pages that always wait for a person, even when a hub
  links to them.

Only the text a visitor can see is used. Menus, headers, footers, popups,
forms, and anything hidden or placed off-screen are left out.

## PDFs

Policies, guidelines, reports and newsletters are mostly PDFs, and the sitemap
does not list them. They are found from the links in the visible text of the
approved pages in a section with `read_pdfs` (today `policies-resources` and
`focus-areas-programmes`):

- only PDFs on karnatakadigital.in are read; a link to a PDF on another site is
  ignored. The excluded and held patterns apply to them as to pages, so a PDF
  whose path matches a held pattern waits for review;
- a PDF is named by its link text. When the link says nothing ("View More",
  "Download Now", an icon), it is named by the heading of its own card, then
  by the title inside the file, then by its file name;
- its text is read page by page, so Aria can say "the Startup Policy, page 12"
  and offer the PDF itself as the link;
- a PDF that is encrypted, damaged, larger than 25 MB, or made of scanned
  images with no text layer is not answered from. There is no OCR: a scanned
  policy needs a text version on the site before Aria can read it. These are
  listed by `pending`, with the reason;
- a PDF that no approved page links to any more is dropped.

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
  new pages, or when it now matches a held pattern;
- each linked PDF is asked for with the ETag and Last-Modified it had last
  time, and read again only when it changed. At most 40 PDFs not seen before
  are read per run; the rest follow on the next run.

The list is applied to the snapshot every time it is loaded, so a page taken
off the list stops being answered from on the next session, before any
refresh.

For an urgent change, refresh by hand on each brains host, against the brain's
own snapshot directory (see `../../README.md`):

```sh
KDEM_KNOWLEDGE_DIR=<the brain's snapshot dir> uv run python demos/kdem/backend/knowledge.py refresh --force https://karnatakadigital.in/policies/
KDEM_KNOWLEDGE_DIR=<the brain's snapshot dir> uv run python demos/kdem/backend/knowledge.py refresh --force https://karnatakadigital.in/wp-content/uploads/2026/01/policy.pdf
KDEM_KNOWLEDGE_DIR=<the brain's snapshot dir> uv run python demos/kdem/backend/knowledge.py pending
```

`--force` with a PDF's URL downloads and reads it again even if the server
says it has not changed. A PDF is only read while an approved page links to
it, so to add one, link it from such a page on the site.

To approve a held page, add it to `pages` with its section and title.
