# Git Agent Memory

## Repository State
- Mode: strict (no `.github/git-mode` file — defaulted)
- Remote: `origin` → `git@github.com:AlanBlanchet/pagb-reconstruction.git`
- Current tag: `v0.1.0` on main (`8178695`)

## Branches (merged)
- `refactor/base-hierarchy-and-multi-phase` — merged to main at `bfa8ebc`. 3 commits (base hierarchy, variant graph, UI overhaul).
- `refactor/kernel-classes-and-release-infra` — merged to main at `8178695`. 1 commit: kernel classes, config extraction, async compute, release infra (34 files, 1096 insertions).

## Tags
- `v0.1.0` — first release. Pushed to origin.

## History
- `a7e6118` — initial empty commit
- `bfa8ebc` — merge of base-hierarchy branch
- `8178695` — merge of kernel-classes branch, tagged v0.1.0

## Notes
- `.venv` is in `.gitignore`. No secrets found in source scan.
- `data/` contains sample EBSD file (1.1M) and documentation screenshots (~700KB total).
- CI/CD workflows added in `.github/workflows/` (ci.yml, release.yml).
- PyInstaller spec and Justfile added for release builds.
