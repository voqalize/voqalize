# Fernhollow catalog data

`catalog.json` is a subset of mock.shop's public `home-large-catalog` (published there as "Havenly Nest"),
renamed for a fictional store: 792 products, all 32 categories, 20–25 varied products per category
(price spread plus least-similar picks; extreme price outliers dropped).

- Built by `build_catalog.py` from the subset file produced by the `havenly-data` scripts
  (`~/Desktop/voqalize/havenly-data/`: `fetch_catalog.py`, `select_subset.py`).
- Only reshaped and renamed. One real trademark ("Eames") and one French handle were renamed.
  No dimensions, stock or delivery data exist in the source, and none are added.
- `intro` and `highlights` come from the source HTML (paragraph + bullet list).
- Images are referenced by their original mock.shop CDN `src`; the frontend downloads and converts them
  to WebP at build time (`frontend/scripts/images.mjs`), served from our own origin.
