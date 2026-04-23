# Git Agent Memory

## Repository State
- Mode: relaxed (explicit in task)
- Remote: `origin` → `git@github.com:AlanBlanchet/pagb-reconstruction.git`
- Current tag: `v0.1.0` on main (`9d53526`)

## Recent Commits (main)
- `9d53526` — fix: add pagb-onefile.spec to repo (was untracked)
- `5089fdc` — fix: separate onefile distpath to avoid PyInstaller build conflict
- `ed1bdbb` — fix/release-exe-artifact merge
- `a8c4482` — fix/release-workflow merge
- `8178695` — refactor/kernel-classes-and-release-infra merge
- `bfa8ebc` — refactor/base-hierarchy-and-multi-phase merge
- `a7e6118` — initial empty commit

## Tags
- `v0.1.0` — on `9d53526` (re-tagged fourth time to include pagb-onefile.spec)

## Notes
- `.venv` is in `.gitignore`. No secrets found in source scan.
- `data/` contains sample EBSD file (1.1M) and documentation screenshots (~700KB total).
- CI/CD workflows in `.github/workflows/` (ci.yml, release.yml).
- Tag delete+recreate pattern used multiple times to retrigger release workflow on same version.
- `pagb-onefile.spec` added for single-exe Windows builds, now tracked in repo.
- distpath conflict: PyInstaller onefile and folder builds both wrote to `dist/`, causing the `.exe` copy step to fail. Fixed by using `--distpath dist-onefile` for the onefile build.
