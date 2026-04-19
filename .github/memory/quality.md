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
