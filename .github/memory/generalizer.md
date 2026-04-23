# Generalizer Memory

## 2026-04-23: Third pass — hardcoded colors, redundant model_config, Grain.row_col

### Changes made

1. **theme.py expanded** — Added `SURFACE_DIM`, `TEXT_MUTED`, `TEXT_DISABLED` constants for remaining Catppuccin colors. `apply_theme()` now references constants instead of hardcoded strings.

2. **map_viewer.py fully themed** — All 8 hardcoded color literals replaced with theme constants via imports+f-strings: `ACCENT` for crosshairs/overlay, `EDGE_COLOR`+`ACCENT` for computing overlay, `SURFACE_DIM`+`TEXT_MUTED` for status strip, `DARK_FG`+`GRID_COLOR` for grain overlay, `TEXT_DISABLED`+`GRID_COLOR` for placeholder.

3. **reconstruction_panel.py** — Progress bar gradient now uses `ACCENT` constant.

4. **Removed 6 redundant `model_config = ConfigDict(arbitrary_types_allowed=True)`** — on `OrientationData`, `VariantAnalyzer`, `EBSDMap`, `OrientationRelationship`, `Grain`, `ReconstructionResult`. All inherit from `Displayable` which already declares it. Cleaned up unused `ConfigDict` imports from 4 files.

5. **`Grain.row_col` property** — Extracted repeated `pixel_indices // cols, pixel_indices % cols` pattern (4× in grain.py + ebsd_map.py) into single `row_col` property on Grain. Used in `aspect_ratio`, `perimeter`, `grain_id_map`, `gos_map`.

### Occurrence counts after

- Hardcoded theme colors outside theme.py: 0 in Python code (was 8 in map_viewer, 1 in reconstruction_panel)
- `model_config = ConfigDict(arbitrary_types_allowed=True)`: 2 (base.py definition + constants.py SlipSystems — non-Displayable)
- `pixel_indices // cols` + `pixel_indices % cols`: 1 occurrence (grod_map per-pixel loop — different pattern)

### Files changed

- `ui/theme.py`: +3 lines (3 new constants), ~6 lines changed (apply_theme)
- `ui/widgets/map_viewer.py`: +8 import lines, ~0 net (f-string replacements)
- `ui/widgets/reconstruction_panel.py`: +1 import, 1 line changed
- `core/grain.py`: +4 lines (row_col property), −3 lines (simplified aspect_ratio/perimeter)
- `core/ebsd_map.py`: −5 lines (removed cols variable + manual r/c calc, removed ConfigDict import)
- `core/orientation.py`: −2 lines (removed ConfigDict import + model_config)
- `core/variant.py`: −2 lines (removed ConfigDict import + model_config)
- `core/orientation_relationship.py`: −2 lines (removed ConfigDict import + model_config)
- `core/reconstruction.py`: −2 lines (removed ConfigDict import + model_config)

**Net: ~10 lines removed, 8 hardcoded color violations fixed, 6 redundant declarations removed**

### Open items (unchanged)

- `_primary_symmetry_quats` called 14× (8 in ebsd_map, 6 via `self._map._primary_symmetry_quats()` in reconstruction) — single-owner accessor pattern, acceptable.
- `_setup_ui` 7× — method name convention, not logic duplication.
- `setContentsMargins(4, 4, 4, 4)` 9× — Qt layout boilerplate, not worth extracting.
- Colors inside theme.py CSS string — these ARE the single source of truth for Qt stylesheet; not extractable further without template engine.

## 2026-04-23: Second pass — theme dedup + rich map metadata

### Changes made

1. **Theme constants consolidated** — `_DARK_BG`, `_DARK_FG`, `_GRID_COLOR` were defined in both `stats_panel.py` and `pole_figure.py`. Moved to `ui/theme.py` as `DARK_BG`, `DARK_FG`, `GRID_COLOR`. Added `ACCENT` and `EDGE_COLOR` for other repeated color values.

2. **`create_dark_figure()` helper** — Extracted repeated `Figure(figsize=...) + set_facecolor(DARK_BG) + FigureCanvasQTAgg()` pattern (4× across stats_panel + pole_figure) into single `create_dark_figure()` in `theme.py`.

3. **`style_ax()` moved to theme** — `_style_ax()` was local to `stats_panel.py` but implements the standard dark-mode matplotlib axes styling. Moved to `theme.py` as `style_ax()`.

4. **Rich `_MapPropertyMeta`** — Expanded from 2 slots (`name`, `requires_result`) to 7: `dtype` (Literal["scalar", "rgb", "discrete"]), `colormap`, `value_range`, `unit`, `category`. Updated `map_property()` decorator to accept all kwargs.

5. **All `@map_property` decorators enriched** — 18 map properties in `ebsd_map.py` now declare `dtype`, `colormap`, `unit`, `category` etc. MapViewer uses `meta.dtype` to decide RGB vs colorbar behavior instead of `ndim == 3` heuristic. Also uses `meta.colormap` for property-specific colormaps.

### Occurrence counts after

- `_DARK_BG` / `_DARK_FG` / `_GRID_COLOR`: 0 in source (was 2 files each)
- `DARK_BG` definition: 1 file (theme.py)
- `Figure(figsize=...) + set_facecolor`: 0 raw (was 4×) — now `create_dark_figure()`
- `_style_ax`: 0 (was 1 definition + 4 calls) — replaced with `style_ax` from theme
- `"#313244"` in non-CSS source: 0 (was 4× in stats_panel histograms) — now `EDGE_COLOR`
- `"#89b4fa"` in scatter/hist: 0 (was 3×) — now `ACCENT`
- `"#45475a"` in pole_figure: 0 (was 1 hardcoded) — now `GRID_COLOR`

### Files changed

- `ui/theme.py`: +24 lines (added constants + 2 helpers)
- `ui/widgets/stats_panel.py`: −23 lines (removed constants, _style_ax, Figure boilerplate)
- `ui/widgets/pole_figure.py`: −6 lines (removed constants, Figure boilerplate)
- `ui/widgets/map_viewer.py`: +12 lines (meta.dtype lookup, meta.colormap usage)
- `core/base.py`: +22 lines (expanded _MapPropertyMeta, richer decorator)
- `core/ebsd_map.py`: +18 lines (metadata on all 18 map_property decorators)

**Net: ~27 lines added** (metadata enrichment is additive by nature — new capabilities, not just dedup)

### Open items (unchanged from first pass)

- `_primary_symmetry_quats` called 6× — single-owner pattern, acceptable.
- `_setup_ui` 7× — method name convention, not logic duplication.
- `model_config = ConfigDict(arbitrary_types_allowed=True)` 5× — pydantic boilerplate, base already has it; subclasses redeclare for type checker.
- `setContentsMargins(4, 4, 4, 4)` 9× — Qt layout boilerplate, not worth extracting.

## 2026-04-19: First pass

### Changes made

1. **Loader collapse** — `load()`/`save()` moved to `EBSDLoader` base in `io/base.py`. `ANGLoader`, `CTFLoader`, `HDF5Loader` are now data-only (declare `supported_extensions` only). `_extract_phases` + helpers moved from `ang_io.py` to `io/base.py` as `extract_phases`.

2. **OR_PRESETS canonical** — Renamed `_presets` ClassVar → `OR_PRESETS` directly. Removed monkey-patch alias at module bottom. Added `_default_parent()`/`_default_child()` classmethods to DRY the 5× repeated `parent or PhaseConfig.austenite()` / `child or PhaseConfig.martensite()` pattern.

3. **IPF coloring consolidated** — `IPFColorKeyTSL` usage now lives exclusively in `utils/colormap.py`. Both `EBSDMap._ipf_map` and `OrientationData.ipf_color` delegate to `colormap.ipf_colors`. `DEFAULT_IPF_DIRECTION` constant replaces 4× `Vector3d.zvector()` default pattern.

### Net line reduction

**Total: ~64 lines removed**

### Open items

- `_primary_symmetry_quats` is called 6× (3 in ebsd_map, 3 in reconstruction). All go through one method on EBSDMap — acceptable single-owner pattern.
- `_setup_ui` appears 7× in Qt widgets — method name convention, not duplicated logic.
- `model_config = ConfigDict(arbitrary_types_allowed=True)` appears 5× — pydantic boilerplate, cannot DRY without metaclass.
