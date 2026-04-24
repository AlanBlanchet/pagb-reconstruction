# Developer Memory — PAGB Reconstruction

## Project Setup

- uv + hatchling + hatch-vcs, src layout at `src/pagb_reconstruction/`
- Dynamic versioning via hatch-vcs (git tags), fallback "0.0.0"
- Entry point: `uv run pagb` → `pagb_reconstruction.app:main`
- Dependencies: orix, numpy, scipy, h5py, matplotlib, PySide6, qdarktheme, pyqtgraph, numba, networkx, scikit-learn, superqt, pydantic, packaging
- Dev deps: pytest>=8.0, pyinstaller>=6.0 in [dependency-groups] dev
- Tests: `uv run pytest tests/ -v` — 21 tests, all pass
- Task runner: `just install`, `just test`, `just run`, `just build`

## Key Decisions

- orix `crystal_map.orientations` fails on multi-phase data — use `crystal_map.rotations` (phase-agnostic) for quaternion access
- reconstruction.py: all symmetry access now uses `self._map._primary_symmetry_quats()` (3 call sites fixed — \_detect_grains, \_build_graph, \_merge_similar)
- IPF coloring for multi-phase: iterate `phases_in_data`, build `Orientation` per phase with its own symmetry, color with `IPFColorKeyTSL` per phase, combine into single RGB array
- `_primary_symmetry_quats()` helper returns symmetry quats from first phase in data — used by KAM, grain detection, grain boundaries
- Euler angles: `crystal_map.rotations.to_euler()` works regardless of phase count

- orix Symmetry API: use `from orix.quaternion.symmetry import get_point_group` with space group NUMBER (not string)
- CrystalMap construction requires `PhaseList` object, not raw list
- `_POINT_GROUP_TO_SPACE_GROUP` dict in crystal.py maps point group string → space group int for orix lookup
- Numba `@njit(cache=True)` for math bottlenecks, `parallel=True` for batch ops
- Markov clustering implemented from scratch (no external MCL library)
- OR variant_quaternions uses all parent symmetry ops applied to the OR rotation

## Architecture

- `core/base.py` — Displayable, SpatialRegion, CrystallographicEntity, SpatialMap, map_property decorator
- `core/crystal.py` — CrystalFamily enum, LatticeParams, \_POINT_GROUP_TO_SPACE_GROUP dict (CrystalSystem deleted)
- `core/phase.py` — PhaseConfig(CrystallographicEntity)
- `core/grain.py` — Grain(SpatialRegion)
- `core/orientation.py` — OrientationData(Displayable)
- `core/ebsd_map.py` — EBSDMap(SpatialMap) with 11 @map_property methods, set_result() for result-dependent props
- `core/orientation_relationship.py` — OR(Displayable) with \_register decorator, \_presets ClassVar, OR_PRESETS alias
- `core/reconstruction.py` — ReconstructionConfig/Result(Displayable)
- `core/variant.py` — VariantAnalyzer(Displayable)
- io/ — loader registry pattern with auto-format detection
- ui/ — PySide6 + pyqtgraph + qdarktheme, QThread worker for reconstruction
- utils/ — numba-accelerated math, IPF coloring

## Class Hierarchy

- Displayable → to_widget(), to_dict_display(), \_ui_title ClassVar
- SpatialRegion(Displayable) → pixel_indices, mask(), highlight_on()
- CrystallographicEntity(Displayable) → family, point_group, lattice, symmetry prop, n_symmetry_ops
- SpatialMap(Displayable) → registered_map_properties(), compute_map_property()
- map_property decorator tags methods with name + requires_result
- EBSDMap: 15 @map_property methods total (11 original + Parent IPF, Parent + Boundaries, GOS, Misorientation)
- GrainMetrics in core/grain_metrics.py: intercept + area methods → GrainSizeResult
- Grain class: added equivalent_diameter, aspect_ratio, perimeter properties + map_width field
- ReconstructionEngine.run() now sets self.\_map.grains after grain detection (required for GOS map)
- \_boundary_from_ids helper on EBSDMap: detects boundaries from integer ID maps (used by Parent IPF, Parent + Boundaries)

## Open Issues

- Theoretical misorientations not mapped into fundamental zone (returns 90-180° range)
- OR optimization (Nyyssönen iterative) not yet implemented
- Grain boundary neighbor computation is O(rows\*cols) — could be faster with ndimage
- ANG loader stores orix Symmetry repr as point_group string (cosmetic issue in to_dict_display)
- Pydantic deprecation warning: `__fields__` used by `SpatialMap.compute_map_property` via `dir(self)` triggering getattr on class (15 warnings in test_map_properties)
- Unlabeled pixels get parent_grain_id=-1 (small grains below min_grain_size threshold)

## UI Interactive Features (added)

- MapViewer: `pixel_clicked` signal + `_on_image_click` handler shows grain info overlay (pixel coords, phase, Euler angles, grain ID, parent ID, variant ID, fit angle)
- MapViewer: `_grain_overlay` QLabel with dark semi-transparent background for info display
- StatsPanel: GrainMetrics `to_widget()` form + Measure button for interactive grain size measurement
- StatsPanel: 2x2 subplot layout — size distribution, fit quality, misorientation histogram (with Mackenzie cubic PDF overlay), variant distribution bar chart
- StatsPanel: `mackenzie_pdf()` module-level function for cubic Mackenzie distribution
- ORPanel: `or_changed` Signal(str) emitted on combo change, connected to MainWindow.\_on_or_changed

## Recent Changes

- Added `build_variant_graph()` and `variant_graph_cluster()` to `core/graph.py`
  - variant graph: builds sparse matrix over (grain × variant) space with Gaussian-weighted misorientation edges
  - clustering: MCL-style expand/inflate on variant graph, scores per-grain variant by row sum, picks argmax
- Modified `ReconstructionConfig.algorithm` to `Literal["grain_graph", "variant_graph"]` (default: "variant_graph")
- Split `ReconstructionEngine.run()` into `_run_variant_graph()` and `_run_grain_graph()` code paths
- Added `_aggregate_parent_quats()` — groups per-grain parent orientations by cluster label, averages with hemisphere alignment, remaps labels to sequential
- Added `_refine_or()` — Nelder-Mead optimization of OR axis-angle adjustment (called when `config.optimize_or=True`)
- Moved `misorientation_angle_pair` import to module level in reconstruction.py, removed 2 local imports
- Variant graph results: 72 parent grains, mean fit 1.21° on sample data (vs 78 parents, 20.55° for grain_graph)

- Created ui/model_widget.py with ModelFormWidget (auto-generates Qt forms from Pydantic models), \_apply_constraints, \_read_widget_value, \_make_color_button, highlight_region stub
- ParamPanel simplified: uses ReconstructionConfig().to_widget() instead of manual spinbox construction
- ORPanel simplified: combo populated from OrientationRelationship.preset_names(), detail from from_preset().description
- MapViewer simplified: combo populated from EBSDMap.registered_map_properties(), display via compute_map_property()
- MapViewer.set_reconstruction_result now calls ebsd_map.set_result() so result-dependent properties work
- MapViewer.\_populate_combo filters out requires_result properties when no result available
- PhasePanel.\_show_detail uses phase.to_dict_display() instead of manual string formatting
- Deleted property_selector.py (unused)
- Removed PropertySelector from ui/widgets/**init**.py exports
- Fixed Pydantic deprecation: access model_fields from class (type(self).model_fields) not instance

## Comprehensive Enhancement Pass (latest)

### Bug Fixes

- `_refine_or()`: Rewrote from no-op → proper Nelder-Mead optimization using Rodrigues rotation perturbation of base rotation matrix, cost = mean parent misorientation across grain neighbor pairs
- `variant_graph_cluster()`: Fixed "last variant per grain wins" → majority voting with weighted accumulation across variant nodes per grain

### Quality Fixes (2026-04-23)

- Added missing `QShortcut` import to `ui/main_window.py` (was in QtGui, not QtWidgets)
- Extracted `_axis_angle_to_rotation()` helper in `core/reconstruction.py` — Rodrigues formula was duplicated in `_refine_or` cost() and post-minimize block
- Deleted dead `_grain_index()` from `core/graph.py` — superseded by `_grain_id_to_index` dict lookup
- `QGuiApplication`/`QImage` unused imports in map_viewer.py were already removed in prior pass
- `_merge_inclusions()`: Replaced O(n²) linear scan with dict lookup (`grain_id_to_idx`)

### New Core Features

- `misorientation_axis_angle_pair()` in math_ops.py: returns both angle and axis (for CSL detection)
- `_misori_axis_angle_with_symmetry()` njit function backing it
- `ReconstructionConfig` fields: all now have `Field(description="...")` for tooltip generation
- EBSDMap: 3 new `@map_property` methods: GROD, Schmid Factor, CSL Boundaries
- CSL boundary detection: Σ3 (60° <111>) = red, Σ9 (38.9° <110>) = blue, HAGB = black, LAGB = gray

### UI Enhancements

- theme.py: Catppuccin-inspired colors, comprehensive CUSTOM_STYLESHEET for QGroupBox, QTabWidget, QPushButton, QProgressBar, QToolBar, QStatusBar, QDockWidget, QComboBox, QSpinBox
- main_window.py: Keyboard shortcuts (Ctrl+O/R/S, Escape stop, 1-9 map modes), file info in status bar, QShortcut imports
- map_viewer.py: Status strip (monospace info bar at bottom), histogram equalization checkbox, linked cursor crosshairs, `select_display_index()`, improved welcome placeholder, right-click context menu
- stats_panel.py: 3-tab layout (Grain Size / Misorientation / Variants), cumulative distribution checkbox, phase filter dropdown, dark theme matplotlib styling with `_style_ax()` helper
- pole_figure.py: Contour mode with KDE, dark theme matplotlib, crystal direction annotations
- reconstruction_panel.py: Step timing via `step_timed` signal, colored progress bar, step counter ("Step 3/13"), Results Summary QGroupBox with parent count + mean fit + timing breakdown
- or_panel.py: Rich details box showing rotation axis/angle, Miller indices for both phases, variant count
- phase_panel.py: Volume fraction percentages, QPixmap color swatches, crystal family name
- param_panel.py: Presets dropdown (Default/Fine/Coarse), tooltips from Field descriptions

### Tests

anel.py: Volume fraction percentages, QPixmap color swatches, crystal family name

- param_panel.py: Presets dropdown (Default/Fine/Coarse), tooltips from Field descriptions

### Tests

- All 21 tests pass after changes

## Major Restructuring Pass (2026-04-23)

### Part A: Numba kernel classes (math_ops.py)

- Added QuaternionOps, MisorientationOps, MathOps wrapper classes
- @njit functions remain module-level (Numba requirement), classes expose via staticmethod()
- Convenience methods: MisorientationOps.pair(), .neighbors(), .axis_angle_pair()
- All callers updated: graph.py, reconstruction.py, ebsd_map.py, grain.py, utils/**init**.py
- grain.py: moved misorientation import from function-level to module-level

### Part B: Constants extraction (core/constants.py)

- BoundaryThresholds: grain_angle_deg=5.0
- CSLParams: sigma3/sigma9 angles, tolerances, axes, dot_threshold
- SlipSystems: BCC/FCC planes and directions as numpy arrays
- ClusteringDefaults: inflation, expansion, convergence, min_edge_weight, variant params
- Used in: ebsd_map.py (boundary, CSL, Schmid), graph.py (clustering params)

### Part C: Async map computation

- ComputeWorker(QThread) in ui/widgets/compute_worker.py
- MapViewer.\_update_display() now async: shows overlay, runs in worker, handles cancel via generation counter
- \_on_compute_done / \_on_compute_error callbacks with stale-result filtering
- base.py compute_map_property: added try/except + logging on error

### Part D: Deduplication (utils/array_ops.py)

- remap_labels(): used in graph.py (2 places), reconstruction.py
- boundaries_from_2d(): used in ebsd_map.py (\_boundary_from_ids, parent maps)
- align_hemisphere(): used in reconstruction.py (\_aggregate_parent_quats, \_compute_parent_orientations)
- grain_index_map(): used in graph.py, reconstruction.py

### Part E: Bug fixes

- io/base.py: \_family_from_point_group now uses \_POINT_GROUP_FAMILIES dict (was always CUBIC)
- reconstruction.py \_compute_variants: packet_ids = variant // max(n_variants//4, 1), bain_ids = variant % min(n_variants, 3)
- variant.py bain_group_ids: uses min(n_variants, 3) instead of hardcoded 3

### Part F: Build/Release infrastructure

- pyproject.toml: dynamic version via hatch-vcs, added packaging + pyinstaller deps
- **init**.py: **version** from importlib.metadata
- Justfile: install, run, test, build, clean tasks
- pagb.spec: PyInstaller spec
- .github/workflows/ci.yml: test on push/PR, Python 3.10-3.12 matrix
- .github/workflows/release.yml: build + release on tag push
- packaging/: build-appimage.sh, .desktop file

### Part G: Auto-update checker

- core/updater.py: UpdateChecker(QThread), checks GitHub API, compares versions via packaging.Version
- ui/widgets/update_bar.py: dismissable banner with download button
- main_window.py: QTimer.singleShot(3000, \_check_updates), UpdateBar in central widget layout

### Part H: README.md — features, install, dev, build, release, architecture

### Part I: .gitignore — added \_version.py, _.AppImage,_.spec.bak

### Lessons

- Numba @njit cannot decorate class methods directly — must stay module-level, wrap via staticmethod()
- Generation counter pattern handles stale async results cleanly (no thread cancellation needed)
- grain.py had function-level import of math_ops — no circular dep, moved to module level

## Release Workflow Fixes (2026-04-23)

- release.yml: Added appimagetool install step (downloaded to /usr/local/bin with sudo)
- release.yml: AppImage build uses `uv run bash` so python3 resolves to venv Python; `APPIMAGE_EXTRACT_AND_RUN=1` env for FUSE-less CI
- release.yml: Archives (tar.gz, zip) now built in build jobs, not release job — avoids artifact path flattening issues
- release.yml: Release job uses `download-artifact` with `merge-multiple: true` to flatten all artifacts into one dir
- build-appimage.sh: Replaced ImageMagick `convert` with Pillow (PIL) one-liner for icon generation; added icon copy to AppDir root for AppImage spec compliance
- pagb.spec: Added `copy_metadata('pagb-reconstruction')` to datas for `importlib.metadata.version()` to work in frozen builds
- pagb.spec: Added hidden imports: networkx, pydantic, packaging, matplotlib (+ backends), orix.quaternion.symmetry

## Bug Fix Pass — GitHub Issue #2 (2026-04-24)

### Bug 1: \_primary_symmetry_quats() not_indexed phase crash

- `phases_in_data.ids` can include -1 (not_indexed); `point_group` is None for those
- Fixed: loop over ids, skip pid < 0 or None point_group, raise ValueError if no valid phase
- Also fixed: `_ipf_map()`, `schmid_factor_map()`, `parent_ipf_map()` loops now skip pid < 0

### Bug 2: Sparse grid reshape crash

- Hex grid ANG files: `xmap.size != prod(xmap.shape)` — e.g. 250664 vs 501327
- Added `is_sparse` property, `_grid_indices()` (row/col from coordinates), `_to_grid(data, fill)` scatter method
- Replaced ALL `.reshape(self.shape)` calls with `_to_grid()` (property_map, phase_map, \_ipf_map, euler_angle_map, band_contrast_map, schmid_factor_map, all result maps)
- Grid-neighbor methods (KAM, misorientation, grain_boundary, CSL boundaries): return zeros for sparse — needs fundamentally different neighbor computation
- GROD map: sparse-aware via `_grid_indices()` lookup dict for pixel → (row, col) mapping
- `run_grain_detection()`: raises NotImplementedError for sparse maps
- `schmid_factor_map`: fixed `n_pixels = self.crystal_map.size` (was `rows * cols`)

### Bug 3: Drag-and-drop file loading

- Added `self.setAcceptDrops(True)` in MainWindow.**init**
- Added `dragEnterEvent()` + `dropEvent()` — accepts URL drops, loads first file

### Bug 4: Extensionless file loading cleanup

- Removed unused `_EXT_MAP` dict from io/base.py
- Replaced `hasattr(phase, "structure")` with `getattr()` chain
- Replaced `hasattr(phase, "color")` with `getattr(phase, "color", None) or "#808080"`
- `extract_phases()` now skips phase_id < 0 (not_indexed)

### Known Remaining Issues

- orix auto-renames phases on ANG load ("Ferrite" → "Fe") — cosmetic issue

## PixelTopology Refactor (2026-04-24)

### What changed
- Added `PixelTopology` Pydantic model in `core/ebsd_map.py`: computes neighbor pairs via cKDTree, works for any grid geometry (square, hex, sparse)
- NN radius: uses median of actual nearest-neighbor distances × 1.01 (not `max(dx,dy)` — hex grids have NN dist = 2×dx which is larger than dy)
- `EBSDMap.topology` lazy property replaces `_grid_indices()` and `_grid_cache`
- `_to_grid()` uses `topology.pixel_to_rc` instead of separate `_grid_indices()` method
- `pixel_index_at(row, col)` → reverse lookup from grid position to pixel index
- Added `MisorientationOps.pairs()` static method + `_misori_pairs` numba kernel in math_ops.py
- Rewrote `kam_map`, `misorientation_map`, `grain_boundary_map`, `csl_boundary_map` using topology pairs — no more `is_sparse` guards returning zeros
- Rewrote `gos_map`, `grod_map`, `grain_id_map` to work on flat pixel arrays + `_to_grid()` instead of `g.row_col`
- Rewrote `detect_grains()` in grain.py: accepts `topology` param, uses scipy sparse connected_components instead of ndimage.label
- Updated `_compute_neighbors()` to use pair array instead of grid iteration
- Updated `reconstruction.py._detect_grains()` to pass `topology`
- Updated `main_window.py` hover/click to use `pixel_index_at()` — works for sparse maps now
- Removed `_grid_cache`, `_grid_indices()`, `NotImplementedError` for sparse grain detection

### Files changed
- `src/pagb_reconstruction/core/ebsd_map.py` — PixelTopology class, EBSDMap rewrite
- `src/pagb_reconstruction/core/grain.py` — detect_grains topology-based, _compute_neighbors pair-based
- `src/pagb_reconstruction/utils/math_ops.py` — _misori_pairs kernel, MisorientationOps.pairs()
- `src/pagb_reconstruction/core/reconstruction.py` — _detect_grains passes topology
- `src/pagb_reconstruction/core/__init__.py` — exports PixelTopology
- `src/pagb_reconstruction/ui/main_window.py` — hover/click use pixel_index_at

### Lessons
- Hex grid: dx=0.1, dy=0.17321 (dx×√3) but actual NN distance = 2×dx = 0.2 — radius must come from actual data, not step sizes
- cKDTree.query_pairs with `output_type='ndarray'` gives (E, 2) directly — no set conversion needed
- scipy connected_components on sparse matrix is cleaner than ndimage.label for non-rectangular domains
