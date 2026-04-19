# Developer Memory — PAGB Reconstruction

## Project Setup

- uv + hatchling, src layout at `src/pagb_reconstruction/`
- Entry point: `uv run pagb` → `pagb_reconstruction.app:main`
- Dependencies: orix, numpy, scipy, h5py, matplotlib, PySide6, qdarktheme, pyqtgraph, numba, networkx, scikit-learn, superqt, pydantic

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

## Open Issues

- Theoretical misorientations not mapped into fundamental zone (returns 90-180° range)
- OR optimization (Nyyssönen iterative) not yet implemented
- Grain boundary neighbor computation is O(rows\*cols) — could be faster with ndimage
- ANG loader stores orix Symmetry repr as point_group string (cosmetic issue in to_dict_display)

## Recent Changes

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
