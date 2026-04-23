# PAGB Reconstruction — Project Instructions

## Overview

Prior Austenite Grain Boundary reconstruction from EBSD data. PySide6 desktop app with orix-backed crystallographic engine.

## Run / Build

- `uv run pagb` or `uv run python -m pagb_reconstruction.app`
- `uv` for dependency management (never `uv pip`)
- src layout: `src/pagb_reconstruction/`

## Package Structure

- `core/` — Pydantic data models, grain detection, graph clustering, reconstruction engine. No Qt imports at module level.
- `io/` — File loaders (ANG, CTF, HDF5) via `EBSDLoader` ABC + registry pattern with `register_loader`.
- `ui/` — PySide6 + pyqtgraph + qdarktheme. QThread for reconstruction. Dock widgets tabified by area.
- `utils/` — Numba-accelerated quaternion math, IPF coloring helpers.

## Class Hierarchy

- `CrystalSystem` (family + point_group + lattice) → `PhaseConfig` (name, color, space_group)
- `OrientationRelationship` — OR definition with classmethod presets (KS, NW, GT, Pitsch, Bain) in `OR_PRESETS` dict
- `EBSDMap` wraps orix `CrystalMap` + phases + grains + parent_map
- `Grain` — pixel indices, mean quaternion, neighbors
- `ReconstructionConfig` / `ReconstructionEngine` / `ReconstructionResult` — pipeline config, execution, output
- `VariantAnalyzer` — variant/packet/Bain group assignment
- `OrientationData` — quaternion array + symmetry, wraps orix `Orientation`

## Planned Hierarchy (not yet implemented)

- `Displayable` base model in `core/base.py` with lazy-import `.to_widget()`
- `SpatialRegion`, `CrystallographicEntity`, `SpatialMap` derived from `Displayable`
- `@map_property` decorator for auto-registering visualization properties on maps
- `ModelFormWidget` in `ui/model_widget.py` — auto-generate Qt forms from Pydantic field introspection

## Patterns

- OR presets: classmethod factories on `OrientationRelationship`, registered in `OR_PRESETS` class-level dict. Adding new OR = add classmethod + dict entry.
- IO loaders: subclass `EBSDLoader`, declare `supported_extensions`, call `register_loader` at import. `load_ebsd(path)` dispatches by extension.
- orix API: `CrystalMap` for spatial data, `Orientation`/`Symmetry` for crystallography, `get_point_group(space_group_number)` for symmetry lookup.
- Numba: `@njit(cache=True)` for scalar math, `parallel=True` for batch quaternion ops. All in `utils/math_ops.py`.
- Qt constraint: `core/` never imports Qt at module level. Lazy imports inside method bodies only.
- Markov clustering: implemented from scratch in `core/graph.py`, no external MCL library.
- `_POINT_GROUP_TO_SPACE_GROUP` in `crystal.py` maps point group string → space group int for orix lookup.

## Dependencies

orix, numpy, scipy, h5py, matplotlib, PySide6, qdarktheme, pyqtgraph, numba, networkx, scikit-learn, superqt, pydantic
