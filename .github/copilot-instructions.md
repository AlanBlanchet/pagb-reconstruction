# PAGB Reconstruction — Project Instructions

## Overview

Prior Austenite Grain Boundary reconstruction from EBSD data. PySide6 desktop app with orix-backed crystallographic engine.

## Run / Build

- `just run` (or `uv run pagb` / `uv run python -m pagb_reconstruction.app`)
- `just test`, `just build`, `just clean` — Justfile as task runner
- `uv` for dependency management (never `uv pip`)
- src layout: `src/pagb_reconstruction/`
- Version: hatch-vcs from git tags → auto-generated `_version.py`. Never edit `_version.py` manually.
- Distribution: PyInstaller via `pagb.spec`, AppImage via `packaging/build-appimage.sh`

## Package Structure

- `core/` — Pydantic data models, grain detection, graph clustering, reconstruction engine, constants. No Qt imports at module level.
- `core/constants.py` — Pydantic models for numeric defaults (BoundaryThresholds, CSLParams, SlipSystems, ClusteringDefaults).
- `core/updater.py` — GitHub release checker (UpdateChecker QThread, UpdateInfo dataclass).
- `io/` — File loaders (ANG, CTF, HDF5) via `EBSDLoader` ABC + registry pattern with `register_loader`.
- `ui/` — PySide6 + pyqtgraph + qdarktheme. Dock widgets tabified by area.
- `ui/widgets/compute_worker.py` — Generic `ComputeWorker(QThread)` for running any callable off-UI-thread.
- `ui/widgets/update_bar.py` — In-app update notification bar.
- `utils/` — Numba-accelerated math, array helpers, IPF coloring.
- `utils/array_ops.py` — Pure-numpy array utilities (label remapping, boundary detection, hemisphere alignment).

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
- Numba: bare `@njit` functions for kernels, wrapped by facade classes (`QuaternionOps`, `MisorientationOps`, `MathOps`) that expose them as `@staticmethod`. Callers use the class API, not raw functions.
- Qt constraint: `core/` never imports Qt at module level. Lazy imports inside method bodies only.
- Async compute: `ComputeWorker(fn, *args)` QThread for any off-thread work. Signals: `finished(object)`, `error(str)`.
- Constants: Pydantic models in `core/constants.py` for numeric defaults — instantiate to get defaults, override fields as needed.
- Markov clustering: implemented from scratch in `core/graph.py`, no external MCL library.
- `_POINT_GROUP_TO_SPACE_GROUP` in `crystal.py` maps point group string → space group int for orix lookup.

## Dependencies

orix, numpy, scipy, h5py, matplotlib, PySide6, qdarktheme, pyqtgraph, numba, networkx, scikit-learn, superqt, pydantic, packaging
