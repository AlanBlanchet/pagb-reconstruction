# Git Agent Memory

## Repository State
- Mode: relaxed (explicit in task)
- Remote: `origin` → `git@github.com:AlanBlanchet/pagb-reconstruction.git`
- Latest tag: `v0.2.1` on `2e8e9c0`

## Recent Commits (main)
- `b2aca14` — fix: grain detection crash, sparse grid support, drag-and-drop, extensionless loading
- `2e8e9c0` — Merge branch 'main' (tag: v0.2.1)
- `64d3c35` — fix: switch to pyqtdarktheme-fork to fix Windows crash
- `5b6580e` — fix: collect_all for orix .pyi stubs + silence disconnect warning (tag: v0.2.0)
- `3b5c99d` — fix: use collect_submodules for PyInstaller hidden imports

## Tags
- `v0.2.1` — on `2e8e9c0`
- `v0.2.0` — on `5b6580e`

## Notes
- `.venv` is in `.gitignore`. No secrets found in source scan.
- `data/` contains sample EBSD file (1.1M) and documentation screenshots (~700KB total).
- CI/CD workflows in `.github/workflows/` (ci.yml, release.yml).
- `pagb-onefile.spec` added for single-exe Windows builds, now tracked in repo.
- distpath conflict: PyInstaller onefile and folder builds both wrote to `dist/`, causing the `.exe` copy step to fail. Fixed by using `--distpath dist-onefile` for the onefile build.
- b2aca14: 8 files changed, 493 insertions, 96 deletions — sparse grid support, drag-and-drop, extensionless file loading, phase crash fixes, requires_result auto-guard, new tests.
