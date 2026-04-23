# Quality Agent Memory

## 2026-04-19 — Full codebase review

### Fixed (Critical/High)

1. `_compute_fit_angles` used quaternion L2 distance (`np.sum((c-parent_q)**2) * 180/pi`) instead of actual misorientation angle. Replaced with `misorientation_angle_pair`.
2. `_compute_variants` and `_compute_fit_angles` had O(n²) self-search to find grain index — replaced with `enumerate`.
3. `_compute_parent_orientations` averaged quaternions without hemisphere normalization — anti-podal quaternions would cancel to zero. Added `np.dot` sign flip.
4. MCL `expansion_power` was ignored for non-2 values (both branches of ternary were equivalent). Replaced with unconditional `matrix_power`.
5. `OrientationRelationship.n_variants` had a wrong formula producing 36 for KS (should be 24). Replaced with `len(self.variant_quaternions())`.
6. `_grain_index` O(n) linear scan used in hot loops. Added `_grain_id_to_index` dict builder; used in `build_adjacency_graph` and `vote_fill`.
7. `_compute_neighbors` created a dummy `Grain` object on every iteration as dict `.get()` default. Simplified to explicit `None` check.
8. `start_reconstruction` had no guard against concurrent workers. Added `isRunning()` check.
9. Dead variable `n_pixels` in `ReconstructionEngine.run()` removed.

### Reported (Medium/Low — not fixed)

- `view_menu` and `tools_menu` created but empty (main_window.py)
- `save_action` not connected (main_window.py)
- `highlight_region` is a no-op stub (model_widget.py)
- `_family_from_point_group` always returns CUBIC (ang_io.py)
- Stop button not connected to cancel logic (reconstruction_panel.py)
- `phase_colormap` uses enumerate index instead of actual phase ID (colormap.py)
- `_compute_neighbors` is O(rows*cols) pixel loop — should use grain-level adjacency from labeled_2d

### Open items

- Proper cancellation support for reconstruction worker (QThread.requestInterruption)
- `_grain_index` still used as fallback in `_merge_inclusions` — could use id_map there too

## 2026-04-19 — Focused review of variant graph + new features

### Fixed (Critical)

1. **`__fields__` Pydantic deprecation** — `registered_map_properties` and `compute_map_property` used `dir(cls)`/`dir(self)` which includes `__fields__`, triggering 15 Pydantic v2 deprecation warnings per test run. Replaced with MRO `vars(klass)` iteration — no dunder traversal, faster.
2. **`arccos` RuntimeWarning in `mackenzie_pdf`** — `np.where` evaluates both branches; for theta > 45, arccos args go outside [-1, 1]. Added `np.clip(-1, 1)` on both arccos arguments. Also removed dead `sqrt2` variable.

### Reported (Critical — not fixed, needs design)

3. **`_refine_or` is a no-op** — Both branches (L250-251 reconstruction.py) return `self._or`. The `optimize_or=True` config flag does nothing. Additionally, the cost function computes a quaternion `dq` it never uses, and only applies a scalar angle offset to theoretical misorientations — mathematically wrong. Needs full redesign of the refinement algorithm.

### Reported (Medium — not fixed)

4. **`variant_graph_cluster` cluster labeling** — The loop at graph.py:209 iterates `dim` (grains × variants), but assigns `cluster_labels[grain_idx]` repeatedly — last variant wins. Should aggregate across variant sub-nodes per grain.
5. **`Grain.perimeter`** counts boundary pixels (has-any-exposed-edge), not actual perimeter edge count. Naming is misleading; a pixel with 3 exposed sides counts the same as one with 1.
6. ~~**`_grain_index` dead code**~~ — FIXED 2026-04-23.
7. **`_merge_inclusions` O(n²)** — Inner loop does linear scan of all grains to find neighbor by ID instead of using an id→index map.

## 2026-04-23 — Post-feature quality review

### Fixed (Critical)

1. **Missing `QShortcut` import** — main_window.py used `QShortcut(QKeySequence(...), self)` at line 303 but never imported it. Would crash at runtime when the window opens. Added to `PySide6.QtGui` import.

### Fixed (Major)

2. **Rodrigues rotation formula duplicated** — reconstruction.py `_refine_or` had the axis-angle→rotation matrix formula (K-matrix Rodrigues) copy-pasted in both `cost()` and post-optimization. Extracted to module-level `_axis_angle_to_rotation(ax_vec)`.
3. **Dead function `_grain_index`** — graph.py contained unused O(n) linear scan function superseded by `_grain_id_to_index`. Removed.
4. **Unused imports `QGuiApplication`, `QImage`** — map_viewer.py. Removed.

### Reported (Minor — not fixed)

5. `_classify_csl` final `return None` (ebsd_map.py ~L420) is unreachable dead code — all angle ranges are already handled.
6. `highlight_region` is still a no-op stub (model_widget.py).
7. `_on_pixel_click` and `_on_image_click` both do O(n) grain scan — acceptable for user clicks but could use pixel→grain index.
8. `_DARK_BG`, `_DARK_FG`, `_GRID_COLOR` defined in both stats_panel.py and pole_figure.py — should be in theme.py.
9. Stop button (`_stop_btn`) still not connected to cancellation logic in reconstruction_panel.py.
10. `_refine_or` previously reported as no-op has been rewritten with proper OR optimization via Nelder-Mead, but cost function creates Orientation objects in tight loop — could be slow for large datasets.

## 2026-04-23 — Post-refactoring quality review (second pass)

### Fixed (Critical)

1. **Mutable default `neighbor_ids: list[int] = []`** in Grain Pydantic model — classic shared-mutable-default risk. Changed to `Field(default_factory=list)`.
2. **`_merge_similar` lacked transitive closure** — if labels A→B and B→C merged, C was not merged with A. Implemented union-find with path compression.

### Fixed (Major)

3. **Dead function `_grain_id_to_index`** in graph.py — wrapper around `grain_index_map` from array_ops, never called. Removed.
4. **Dead standalone functions** in math_ops.py — `misorientation_angle_pair`, `misorientation_angle_neighbors`, `misorientation_axis_angle_pair` superseded by `MisorientationOps` class. Removed.
5. **Dead assignment** in main_window.py `_save_file` — `parent_euler = np.zeros(...)` immediately overwritten.
6. **Signal connection leak** in update_bar.py `show_update` — `_download_btn.clicked` accumulated connections on repeated calls. Added disconnect-before-connect.
7. **`release.yml` used `uv pip install pyinstaller`** — redundant since pyinstaller already in dev group. Changed to direct `uv run pyinstaller`.

### Fixed (Minor)

8. **Hardcoded magic numbers** — MCL attractor threshold (`0.01`), prune threshold (`1e-5`), variant convergence threshold (`1e-6`) moved to `ClusteringDefaults` in constants.py.
9. **CSL boundary thresholds** — low-angle (`2.0°`) and high-angle (`15.0°`) hardcoded in `_classify_csl` moved to `CSLParams` in constants.py.

### Open items (not fixed)

- `_compute_neighbors` still O(rows*cols) pixel loop — should use grain-level adjacency from labeled_2d.
- `_DARK_BG`, `_DARK_FG`, `_GRID_COLOR` duplicated in stats_panel.py and pole_figure.py.
- Stop button still not connected to cancellation logic.
- `highlight_region` still a no-op stub.

### Open items from previous reviews (still open)

- Proper cancellation support for reconstruction worker (QThread.requestInterruption)
- `_family_from_point_group` always returns CUBIC (ang_io.py)
- `phase_colormap` uses enumerate index instead of actual phase ID (colormap.py)
- `_compute_neighbors` is O(rows*cols) pixel loop — should use grain-level adjacency
- `_merge_inclusions` O(n²) — uses linear scan for neighbor ID lookup
