# Generalizer Memory

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
