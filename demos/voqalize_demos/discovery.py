"""Find the co-located demo backends and collect their routers.

Each demo is a folder ``demos/<name>/`` with its ``backend/`` beside its
``frontend/``. A backend is a small Python package exporting three names from its
``routes.py`` (re-exported by its ``__init__``):

- ``NAME``    — the URL segment (``travel``), which must equal the folder name.
- ``build``   — ``(GeminiProvider) -> Brain``, the per-session brain factory.
- ``router``  — the FastAPI ``APIRouter`` for ``/{NAME}/s/{session_id}``.

There is no central registry to keep in sync (the old ``manifest.py`` +
``check_wiring`` is gone): dropping a ``demos/<name>/backend/`` folder in *is* the
registration. The umbrella includes every discovered router; ``build`` is exposed
too so tests can drive a demo's brain directly.

The demo backends are not installed packages — they are loaded from source, in
place, so ``import`` never depends on packaging each folder. That works because
the shared ``voqalize_demos`` package is installed editable (a uv workspace
member), so this file resolves the repo's ``demos/`` root from its own location.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from fastapi import APIRouter

from voqalize_demos.session import BrainFactory


@dataclass(frozen=True)
class DiscoveredDemo:
    """One co-located demo backend, loaded from ``demos/<name>/backend/``."""

    name: str
    router: APIRouter
    build: BrainFactory


def _demos_root() -> Path:
    """The repo's ``demos/`` directory — the parent of this shared package.

    Overridable with ``VOQALIZE_DEMOS_ROOT`` for unusual layouts; the default
    (``…/demos/voqalize_demos/discovery.py`` → ``…/demos``) is correct whenever the
    package is imported from source, which the editable workspace install ensures."""
    override = os.environ.get("VOQALIZE_DEMOS_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[1]


def _load_backend_package(name: str, backend_dir: Path) -> ModuleType:
    """Import ``demos/<name>/backend/`` as a package under a synthetic name so its
    relative imports (``from .brain import …``, ``from .content import …``) resolve
    against the folder in place — no installation, no ``sys.path`` surgery."""
    pkg = f"voqalize_demos._loaded.{name}"
    spec = importlib.util.spec_from_file_location(
        pkg,
        backend_dir / "__init__.py",
        submodule_search_locations=[str(backend_dir)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover — a malformed backend
        raise RuntimeError(f"demos: cannot load backend package for {name!r} at {backend_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[pkg] = module
    spec.loader.exec_module(module)
    return module


def discover() -> list[DiscoveredDemo]:
    """Load every ``demos/<name>/backend/`` (alphabetical) into a list of demos.

    A folder with a ``backend/routes.py`` is a demo; anything else under ``demos/``
    (``voqalize_demos``, ``frontend`` scaffolding, ``dist``) is skipped. Raises if a
    backend is missing ``NAME`` / ``build`` / ``router``, or if ``NAME`` disagrees
    with the folder — a wiring bug that should fail startup, not a live session."""
    root = _demos_root()
    demos: list[DiscoveredDemo] = []
    for backend_dir in sorted(root.glob("*/backend")):
        if not (backend_dir / "routes.py").is_file():
            continue
        folder = backend_dir.parent.name
        module = _load_backend_package(folder, backend_dir)
        try:
            name = module.NAME
            router = module.router
            build = module.build
        except AttributeError as exc:
            raise RuntimeError(
                f"demos: backend {folder!r} must export NAME, router, build from routes.py"
            ) from exc
        if name != folder:
            raise RuntimeError(f"demos: backend folder {folder!r} declares NAME={name!r}")
        demos.append(DiscoveredDemo(name=name, router=router, build=build))
    return demos


def build_for(name: str) -> BrainFactory:
    """The brain factory for one demo by name (for tests that drive a brain)."""
    for demo in discover():
        if demo.name == name:
            return demo.build
    raise KeyError(f"no demo backend discovered for {name!r}")
