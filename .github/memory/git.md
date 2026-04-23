# Git Agent Memory

## Repository State
- Mode: strict (no `.github/git-mode` file — defaulted)
- Initial empty commit on `main`: `a7e6118`

## Branches
- `refactor/base-hierarchy-and-multi-phase` — active branch. Two commits:
  1. `f40715b` — base class hierarchy, multi-phase support, loader consolidation (54 files, 16756 insertions)
  2. `7c67dac` — variant graph reconstruction, OR refinement, grain metrics, map properties (29 files, 958 insertions). Not pushed.

## Notes
- `.venv` is in `.gitignore`. No secrets found in source scan.
- `data/` contains sample EBSD file (1.1M) and documentation screenshots (~700KB total).
- Screenshots added in `7c67dac`: parent_ipf, parent_ipf2, recon, stats, variant_id.
