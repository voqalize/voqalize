# Fernhollow content

Authored editorial content for the Fernhollow demo store: journal articles, store pages, site copy
and the policy summary the voice agent quotes. The frontend renders the Markdown; the brain reads
`policies.json`. Product facts always come from `../data/catalog.json`, never from here.

```
content/
  journal/<slug>.md   9 articles
  pages/<slug>.md     about, returns, delivery, assembly, care, faq
  policies.json       machine-readable policy summary (returns, delivery, assembly, care)
  site.json           home hero, room and category blurbs, promises, newsletter, footer
  check_content.py    validator; run `python3 -I demos/fernhollow/content/check_content.py`
```

## Journal articles

YAML frontmatter with exactly these keys, in this order:

| key | type | notes |
| --- | --- | --- |
| `title` | string | |
| `slug` | string | kebab-case, equal to the filename without `.md` |
| `dek` | string | one-sentence standfirst |
| `date` | `YYYY-MM-DD` | between 2026-09-01 and 2026-11-01, one article per date |
| `room` | string | one of `living, dining, bedroom, home-office, bath, kitchen, decor` |
| `readMinutes` | int | about words / 200 |
| `hero` | product id | the product whose photo leads the article |
| `products` | list of product ids | 4 to 8, each placed exactly once in the body |

Body: `##` subheads, short paragraphs, and each featured product on a line of its own:

```
::product{id="modular-oak-desk-with-matte-metal-legs"}
```

The renderer turns that line into a product card. 700 to 1,100 words, not counting directive lines.

## Pages

Frontmatter keys `title`, `slug` (= filename), `dek`. Plain Markdown body; tables allowed.

## policies.json

`{returns, delivery, assembly, care}`, each an object of short strings (plus a few numbers:
`delivery.freeThreshold`, `delivery.flatFee`, `assembly.fee`, all USD). Each has `page`, the
`navigate` target (`policy/<topic>`). The pages and this file state the same rules; change both
together:

- Returns: 30 days from delivery, unused items, refund to the original payment method.
- Delivery: free standard delivery on orders over $500, otherwise a flat $49 per order. No delivery
  dates or stock promises.
- Assembly: available for furniture at a flat $79 per item.
- Care: general guidance per material; the product's own label comes first.

## site.json

`hero{headline, subline, cta{label, href}}`, `rooms{<room>: blurb}` for all 7 rooms,
`categories{<slug>: blurb}` for all 32 catalog category slugs, `promises[{title, text}]` (3 to 4),
`newsletter`, `footerTagline`.

## Rules

- **No invented product facts.** About a product, say only what its own catalog title, intro,
  highlights and options say. Never state dimensions, weights, stock, delivery times, warranties or
  performance claims for a product. General design advice is fine and should be practical.
- Fictional brand. No real addresses, phone numbers, people, brands, trademarks or stores. English
  only. Avoid catalog products whose copy names a real place or brand as a selling point.
- Editorial voice: warm, confident, specific. No filler phrases ("elevate your space"), no emoji.
- Every id in `hero`, `products` and `::product` must exist in the catalog.
- `check_content.py` (stdlib only) validates frontmatter keys and order, slugs, dates, rooms, ids,
  placement, word counts, `readMinutes`, banned phrases, and the shape of both JSON files. It must
  pass before committing.
