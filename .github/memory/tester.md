# Tester Memory

## Test Suite

- 36 tests across 6 files, all passing (~69s)
- Session-scoped fixtures: `sample_ebsd`, `sample_with_grains`, `variant_graph_result`
- Data file: `data/sdss_ferrite_austenite.ang`

## Coverage Design

- `test_map_properties.py::test_all_non_result_properties` — dynamic iteration over ALL `@map_property` without `requires_result`. Automatically covers new map properties (GROD, Schmid, CSL, GOS, KAM, etc.) without test changes.
- `test_map_properties.py::test_result_properties` — explicit list of 5 result properties. Must be updated when new result properties are added.
- `test_reconstruction.py` — exercises both `variant_graph` and `grain_graph` algorithms end-to-end, including `_refine_or` (optimize_or defaults True) and `vote_fill`.
- `test_sparse_and_detection.py` — sparse/dense grid handling (parametrized), `_primary_symmetry_quats`, `_detect_format` content sniffing.

## Known Bugs

- `_detect_format` HDF5 sniffing is broken: `\x89` byte lost in utf-8 decode→re-encode round-trip. `magic = head[:8].encode()` after `.decode("utf-8", errors="ignore")` drops the leading byte. Test documents this as expected `""` return.

## Decisions

- 2025-04-23: No new tests needed. Dynamic `test_all_non_result_properties` already covers GROD, Schmid Factor, CSL Boundaries. `_refine_or` and `vote_fill` exercised via reconstruction fixtures.
- 2025-04-24: Added `test_sparse_and_detection.py` with 15 new tests: sparse/dense `_to_grid` (1d, nd, property_map, is_sparse), `_primary_symmetry_quats` skip-not-indexed, `_detect_format` parametrized (CTF, ANG×2, HDF5-broken, unknown, missing file). Drag-drop untested (Qt mocking cost > value; simple delegation to `_load_file`).
