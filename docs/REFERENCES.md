# References — parent-grain reconstruction

The reconstruction methods, parameters, and quality metrics in this app follow
the published prior-austenite / parent-grain reconstruction literature. The goal
is to **support the concepts these papers describe generically** (selectable ORs,
tunable tolerances, multiple grouping strategies, fit metrics) rather than hard-
code any single method. Each entry notes where it informs the app.

1. **Cayron, Artaud & Briottet (2006)** — "Reconstruction of parent grains from
   EBSD data." *Materials Characterization* 57, 386–401.
   doi:10.1016/j.matchar.2006.03.008
   — Groupoid nucleation-and-growth grouping; the misfit angle **Δδ_r** and the
   `M_min` mis-indexation / small-island tolerance. Informs the noise-island
   removal (`min_parent_size_um`) and the OR-operator matching idea.

2. **Hielscher, Nyyssönen, Niessen & Gazder (2022)** — "The variant graph approach
   to improved parent grain reconstruction." *Materialia* 22, 101399.
   doi:10.1016/j.mtla.2022.101399  (MTEX 5.8)
   — The **variant-graph + Markov-clustering** method this app's `variant_graph`
   algorithm implements. Source of the inflation α (≈1.05–1.1), edge threshold /
   tolerance, and the efficiency levers (variant merging 24→12, early stopping).

3. **Niessen, Nyyssönen, Gazder & Hielscher (2022)** — "Parent grain reconstruction
   from partially or fully transformed microstructures in MTEX." *J. Appl. Cryst.*
   55, 180–194. doi:10.1107/S1600576721011560
   — Growth (retained-parent seeded), nucleation, and graph strategies; the
   disorientation **fit** metric and revert-by-fit / revert-by-cluster-size
   (`min_cluster_size`); OR presets incl. Bain & Burgers; iterative OR refinement.

4. **Taylor, Smith, Donoghue, Burnett & Pickering (2024)** — "In-situ heating-stage
   EBSD validation of algorithms for prior-austenite grain reconstruction in steel."
   *Scripta Materialia* 242, 115924. doi:10.1016/j.scriptamat.2023.115924
   — Validates reconstructions against in-situ ground truth. Source of the
   **area-weighted equivalent-circle-diameter** grain-size metric (the headline
   "closeness to reality" number), OR mean-angular-deviation, and the recommendation
   to fill non-indexed pixels before reconstruction. KS most reliable for both
   martensite and bainite.

5. **Wang, Wang, Liu, Xie & Shang (2025)** — "In-situ high-temperature EBSD study of
   austenite reversion from martensite, bainite and pearlite in a high-strength
   steel." *J. Mater. Sci. Technol.* 217, 268–280. doi:10.1016/j.jmst.2024.08.027
   — **Bainite** specifics: weak variant selection → wider lath spread → looser
   grouping tolerances (LAGB 5–15°). Informs the Bainite parameter preset.

6. **Sun, Zhou, Zhang, Yang, Liu, Guo & Gu (2023)** — "Novel reconstruction
   approaches of austenitic annealing twin boundaries and grain boundaries of
   ultrafine grained prior austenite." *Materials & Design* 227, 111692.
   doi:10.1016/j.matdes.2023.111692
   — Σ3 (60°⟨111⟩) **annealing-twin-aware** reconstruction; twin handling as an
   option (roadmap), area-weighted fit error.

7. **Bachmann, Müller, Britz et al. (2022)** — "Efficient reconstruction of prior
   austenite grains in steel from etched light optical micrographs using deep
   learning..." *Frontiers in Materials* 9, 1033505. doi:10.3389/fmats.2022.1033505
   — Grain-size-distribution fit metrics and OR-tolerance merging; a
   deep-learning-from-micrograph alternative (out of scope for EBSD input, noted
   for completeness).

## Roadmap the literature supports

Done:

- Compare approaches side by side, scored on shared fit metrics (Taylor 2024) —
  the Compare… dialog: presets + one-field sweep, ranked best-fit-first, apply
  the winner's parameters.
- Variant merging 24→12 for large-map performance (Hielscher 2022 §5.4) —
  `merge_variants_deg` (12° pairs the KS 10.53° block variants; matching per
  Bain-group cycle, variant precision restored after clustering).

Not yet implemented:

- Retained-austenite seeded growth for partially transformed maps (Niessen 2022).
- Σ3 annealing-twin detection/merging toggle (Sun 2023; Hielscher 2022).
- Pole-figure back-calculated-variant overlay + per-OR mean angular deviation
  (Hielscher 2022; Taylor 2024).
- Pre-reconstruction non-indexed-pixel fill toggle (Taylor 2024) — display-side
  fill exists; reconstruction-time fill still open.
