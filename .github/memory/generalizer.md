# Generalizer Memory

## 2026-04-19: First pass

### Changes made

1. **Loader collapse** — `load()`/`save()` moved to `EBSDLoader` base in `io/base.py`. `ANGLoader`, `CTFLoader`, `HDF5Loader` are now data-only (declare `supported_extensions` only). `_extract_phases` + helpers moved from `ang_io.py` to `io/base.py` as `extract_phases`.

2. **OR_PRESETS canonical** — Renamed `_presets` ClassVar → `OR_PRESETS` directly. Removed monkey-patch alias at module bottom. Added `_default_parent()`/`_default_child()` classmethods to DRY the 5× repeated `parent or PhaseConfig.austenite()` / `child or PhaseConfig.martensite()` pattern.

3. **IPF coloring consolidated** — `IPFColorKeyTSL` usage now lives exclusively in `utils/colormap.py`. Both `EBSDMap._ipf_map` and `OrientationData.ipf_color` delegate to `colormap.ipf_colors`. `DEFAULT_IPF_DIRECTION` constant replaces 4× `Vector3d.zvector()` default pattern.

### Occurrence counts after

- `IPFColorKeyTSL` import: 1 file (was 3)
- `Vector3d.zvector()`: 2 (was 4) — one is the constant definition, one is the specific IPF-Z map
- `_extract_phases` / phase extraction logic: 1 location (was duplicated via cross-import)
- `orix_load(str(path))`: 1 (was 3)
- `orix_save(str(path), ...)`: 1 (was 3)
- `parent or PhaseConfig.austenite()`: 0 literal (replaced with `cls._default_parent()`)

### Net line reduction

- `ang_io.py`: 82 → 8 (−74)
- `ctf_io.py`: 26 → 8 (−18)
- `hdf5_io.py`: 26 → 8 (−18)
- `io/base.py`: 38 → 95 (+57) — absorbed shared logic
- `orientation_relationship.py`: ~235 → ~232 (−3) — removed alias hack, added 2 helper methods
- `ebsd_map.py`: removed 1 import, simplified _ipf_map (−3)
- `orientation.py`: simplified ipf_color (−4)
- `colormap.py`: added constant, simplified (−1)

**Total: ~64 lines removed**

### Open items

- `_primary_symmetry_quats` is called 6× (3 in ebsd_map, 3 in reconstruction). All go through one method on EBSDMap — acceptable single-owner pattern.
- `_setup_ui` appears 7× in Qt widgets — method name convention, not duplicated logic.
- `model_config = ConfigDict(arbitrary_types_allowed=True)` appears 5× — pydantic boilerplate, cannot DRY without metaclass.
