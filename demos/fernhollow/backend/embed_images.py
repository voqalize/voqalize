"""Offline: one CLIP image embedding per catalog product, cached outside the repo.

Run once, by hand, on a machine holding the source images (one ``0.png`` per
product, under ``<images>/<sourceHandle>/``)::

    cd demos && uv run --with open_clip_torch --with pillow \\
        python fernhollow/backend/embed_images.py --images ~/Desktop/voqalize/havenly-data/images \\
        --out ~/Desktop/voqalize/havenly-data/fernhollow-clip.json

The model is the open-source OpenCLIP ViT-B-32 (LAION-2B weights), run on the
CPU. Neither the model, the images nor the raw vectors are committed: the
vectors feed :mod:`build_index`, which commits only the small neighbour and
similarity lists derived from them. A similarity is used to *rank* — two pieces
that look alike sit together — and is never said to the shopper as a fact.

The heavy imports are made by name at run time, so nothing here is a dependency
of the brains image and the type checker reads them as opaque.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "data" / "catalog.json"
MODEL = ("ViT-B-32", "laion2b_s34b_b79k")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()

    torch: Any = importlib.import_module("torch")
    open_clip: Any = importlib.import_module("open_clip")
    pil: Any = importlib.import_module("PIL.Image")

    catalog = json.loads(CATALOG.read_text())
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL[0], pretrained=MODEL[1])
    model.eval()
    torch.set_num_threads(os.cpu_count() or 1)

    items: list[tuple[str, Path]] = []
    for product in catalog["products"]:
        path = Path(args.images).expanduser() / product["sourceHandle"] / "0.png"
        if path.is_file():
            items.append((product["id"], path))
        else:
            print(f"no image for {product['id']}")

    vectors: dict[str, list[float]] = {}
    with torch.no_grad():
        for start in range(0, len(items), args.batch):
            chunk = items[start : start + args.batch]
            batch = torch.stack([preprocess(pil.open(p).convert("RGB")) for _, p in chunk])
            feats = model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            for (pid, _), vec in zip(chunk, feats.tolist(), strict=True):
                vectors[pid] = [round(x, 5) for x in vec]
            print(f"{start + len(chunk)}/{len(items)}", flush=True)

    out = Path(args.out).expanduser()
    out.write_text(json.dumps({"model": "/".join(MODEL), "vectors": vectors}))
    print(f"wrote {len(vectors)} vectors to {out}")


if __name__ == "__main__":
    main()
