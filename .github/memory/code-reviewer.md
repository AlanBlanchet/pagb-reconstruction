# code-reviewer memory — pagb-reconstruction

## 2026-07-17 — UI theme redesign review

- **Recurring UI pattern to watch:** per-widget inline `setStyleSheet(f"…{palette}…")` baked at construction NEVER re-themes on `set_theme` (the Theme menu does a live switch). Fix = push static styling into `ui/theme/app.scss` via a type/objectName selector + a dynamic property (e.g. `[active="true"]` like `QPushButton[primary]`), so the global QSS re-apply covers already-built widgets. Applied this turn to StatCard, TaskManager/TaskItem, CollapsibleCard, SegmentedControl, UpdateBar, map_viewer overlays.
- **Theme architecture:** `ui/theme/` package — `palette.py` (typed Pydantic `ThemePalette`, `HexColor` = pattern-constrained hex, single colour source), `engine.py` (qtsass compile of `app.scss` with `$vars` from `model_dump()`, live `set_theme`), `icons.py` (semantic Phosphor registry via qtawesome), `app.scss` (authored stylesheet).
- **Theme test gap that hid the bug:** a smoke test asserting `active_theme().name` proves the GLOBAL switched, NOT that a pre-built widget re-themed. The real edge = build widget → switch theme → assert its resolved colour changed (or that it carries no palette-bearing inline stylesheet). Added `test_prebuilt_widget_retheme_on_switch`.
- Only inline styling that legitimately stays per-instance: dynamic run-state (reconstruction progress success-flash, verdict colour). Everything palette-static belongs in SCSS.
