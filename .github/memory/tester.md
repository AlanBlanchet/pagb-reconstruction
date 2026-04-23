# Tester Memory

## Test Suite

- 21 tests across 5 files, all passing (~65s)
- Session-scoped fixtures: `sample_ebsd`, `sample_with_grains`, `variant_graph_result`
- Data file: `data/sdss_ferrite_austenite.ang`

## Coverage Design

- `test_map_properties.py::test_all_non_result_properties` — dynamic iteration over ALL `@map_property` without `requires_result`. Automatically covers new map properties (GROD, Schmid, CSL, GOS, KAM, etc.) without test changes.
- `test_map_properties.py::test_result_properties` — explicit list of 5 result properties. Must be updated when new result properties are added.
- `test_reconstruction.py` — exercises both `variant_graph` and `grain_graph` algorithms end-to-end, including `_refine_or` (optimize_or defaults True) and `vote_fill`.

## Decisions

- 2025-04-23: No new tests needed. Dynamic `test_all_non_result_properties` already covers GROD, Schmid Factor, CSL Boundaries. `_refine_or` and `vote_fill` exercised via reconstruction fixtures.
