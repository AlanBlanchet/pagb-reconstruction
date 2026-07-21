# Rust migration for the PAGB EBSD app — evidence

Researched 2026-07-21. Question: migrate to Rust (whole app? windowing? kernels?).
Verdict: **stay on Python/PySide6/orix**; Rust is defensible only for isolated,
swappable numeric hot paths — and measurement says that is not where our time goes.

## 1. Crystallography / EBSD core — NO Rust equivalent exists

No crate combines point-group symmetry + orientation/misorientation with symmetry
reduction + IPF colouring + .ang/.ctf/HDF5 readers. Searched crates.io, lib.rs,
docs.rs, GitHub topics, Zenodo/arXiv.

- Closest: `moyo` (spglib org, v0.15.0, 2026-07-13, ~47k downloads) — but it derives
  space groups FROM atomic structure (DFT), not orientation analysis of MEASURED
  data. No Orientation object, no IPF, no EBSD parsers.
- `pdbtbx`, `crystals` — protein PDB/CIF, unmaintained since Oct 2024.
- Generic quaternion crates (nalgebra, cgmath, quaternion-core) — rotation maths
  only, zero crystal-symmetry knowledge.

**Replacing orix = ~5-10k LOC greenfield with zero head start.** This is the
single decisive fact against migration.

## 2. PyO3 + maturin — mature

PyO3 v0.29.0 (212M downloads, stable API since 0.23, abi3 supported), maturin
v1.14.1, rust-numpy zero-copy interop. Shipped at scale by Polars, Ruff,
pydantic-core, orjson, tokenizers, cryptography.

Gap: PyO3-inside-PyInstaller is under-documented — not known-broken, just unproven.
Risk is packaging (binary discovery, per-platform CI, Windows signing), not PyO3.

## 3. GUI — nothing is a drop-in Qt replacement

| | state | blocker for us |
|---|---|---|
| egui 0.35 | pre-1.0, breaks each release | churn; a11y gaps. Closest precedent: Rerun |
| iced 0.14 | pre-1.0, ~15mo between releases | no docking, no accessibility |
| Slint 1.17 | most API-stable (1.0 since 2023) | docking "not on roadmap" |
| Tauri 2.11 | best packaging/signing | webview — UI becomes HTML/CSS/JS |
| Dioxus 0.7 | pre-1.0 | weakest verified production record |

None matches Qt's AT-SPI/NSAccessibility/MSAA breadth. None has EBSD/materials
precedent. We rely on docked panels, which only egui has (via `egui_dock`).

## 4. Plotting — a hard, disqualifying gap

**No Rust plotting crate renders LaTeX-style maths labels.** plotters (stale ~19mo),
charming (no PDF, no colourbar), Kuva (breaks past ~850k points) — none.

That is fatal for this domain: EBSD figures need Miller indices ({111}), Greek
letters and sub/superscripts (θ, γ→α'). matplotlib does this natively.

Interactive large image: `egui_plot` 0.36 is GPU-backed (wgpu) and the only real
candidate, but has no per-pixel colormap LUT — live contrast/colormap changes would
mean CPU recompute + re-upload, where pyqtgraph re-applies a GPU LUT cheaply.
Unproven at 10^7 pixels.

## 5. Large data — ndarray fits; MCL is the one real gap

`ndarray` v0.17 is a clean numpy analogue. polars/arrow are columnar — wrong shape
for a dense pixel grid. `sprs` covers sparse.

**No Rust crate implements Markov Clustering.** Either FFI-bind the C reference
(micans/mcl) or reimplement on sprs. Bounded, unlike the crystallography gap.

Out-of-core is over-engineering here: an EBSD channel is 40-80 MB, a full map well
under 1 GB — fits RAM on any workstation.

## 6. Would Rust have caught OUR bugs? 1.5 of 4

| bug | Rust? |
|---|---|
| float array used as boolean index | **YES** — compile error (E0054); no numeric↔bool coercion, and `Array1<f64>`/`Array1<bool>` are distinct types |
| running QThread dropped | **HALF** — `thread::scope` (1.63) makes the memory-unsafe half a lifetime error, and deterministic Drop removes the GC-timing crash. But `JoinHandle` is NOT `#[must_use]` (rust-lang/rust#48820 still open), so a silently detached thread compiles clean |
| Qt `toggled(bool)` → zero-arg slot | **NOT a Rust win per se** — C++ Qt5 already catches this; PySide6 loses it because the Python slot is untyped. Fixed by leaving Qt's dynamic layer, not by Rust |
| integer ID clamped to a 256-entry LUT | **NO** — `as` truncates silently by design (`300u32 as u8 == 44`). Pure domain-logic bug. Only opt-in `clippy::pedantic` + newtype/`TryFrom` discipline helps, equally available in Python |

Note the one that actually hurt Eloïse (the 256-clamp, which blanked her parent
maps) is the one Rust does **not** catch.

## Bottom line

Full migration re-implements orix from scratch, loses LaTeX labels with no
replacement, and accepts either API churn or no docking in the GUI. Not supported
by the 2026 ecosystem. Partial migration is technically sound but, per profiling,
aimed at 0.2 s of an 18.9 s reconstruction.
