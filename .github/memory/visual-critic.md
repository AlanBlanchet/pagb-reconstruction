# visual-critic memory — pagb-reconstruction

## 2026-06-18

### Launch / capture
- ~~interact sandbox is BROKEN on this host~~ **STALE — FIXED 2026-06-18 in interact v0.3.5** (issue #33 closed: display-number collision between concurrent servers; verified working live 2026-07-17 with THIS app — `launch_app` + reconstruction + capture all inside the sandbox). **Use interact `launch_app` normally; the manual Xephyr :77 workaround below is OBSOLETE — do not use it.**
- <details><summary>Obsolete manual :77 workaround (kept for archaeology only)</summary> spawn a self-managed, kept-alive Xephyr — `DISPLAY=:0 Xephyr :77 -screen 1400x900 -ac -br -noreset` as a background task so it survives — then launch `setsid bash -lc 'cd <repo> && DISPLAY=:77 LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe QT_QPA_PLATFORM=xcb exec uv run pagb data/sdss_ferrite_austenite.ang --run'`, capture with `DISPLAY=:77 xwd -root -silent | convert xwd:- out.png`, drive with `xdotool` on :77.</details>
- Launch (2026-07-17, interact >0.26): `launch_app(command="uv run pagb data/sdss_ferrite_austenite.ang --run", cwd="<repo>", wait=90)` — `cwd=` is new; shell phrasing `cd <repo> && uv run pagb …` also works now. Numba warm makes the window map late (~30-50s cold): interact no longer advertises the 1x1 `Qt Selection Owner` utility windows, it waits for the real `PAGB Reconstruction` window (raise `wait`, or retry `list_desktop_windows`). Drive/capture with `target="nested:PAGB Reconstruction"`, popups with `target="nested"`.
- Multiple `PAGB Reconstruction` windows collide by title — verify the live PID before trusting any window grab; kill stale PIDs first.

### App behaviour / data truth
- `uv run pagb <file> --run` auto-loads + reconstructs. First run compiles numba then computes ~40-50s (progress bar → 100% green "Done"). Poll CPU to detect settle. App holds ~150% CPU even after Done (overlay/timer — minor, not blocking).
- SDSS sample: 100 rows × 117 cols. austenite = id 1 = RED (228,26,28); ferrite = id 2 = BLUE (55,126,184). It is a DUPLEX scan (no prior-austenite structure) — see project memory [[reconstruction-correctness]].
- Engine render == GUI render: can use `m.compute_map_property("Parent IPF"|"IPF-Z"|...)` for clean comparison crops.

### Selectors (1400x900)
- Display-mode combo ~x965 y50 (Qt centers popup on current item → re-screenshot the open list before clicking). Right tabs y~447 (Phases/OR/Params/Info). Bottom tabs y~849 (Reconstruction/Statistics/Poles/Log). Toolbar overflow `»` (far right) reveals Line Profile/ROI/Clear ROI/Reset.
- Qt QComboBox popup does NOT composite into nested capture — click to focus then keyboard, or screenshot the open list separately.

### Verified fixed (2026-06-18, commit bbe0d8c) — 11/11 core PASS
ASTM now log10 (8.9, physical); result auto-switches to Parent+Boundaries; colorbar reads real data range; toolbar labelled (Run findable); Line Profile on toolbar; display list grouped; Info-tab trap gone; map dominant at normal width; phase label consistent; results quality verdict; scale bar µm.

### Still OPEN (confirmed on pixels, ranked)
- P1 no IPF colour-key triangle on orientation maps (uninterpretable). `ipfz_map.png`.
- P1 categorical maps (Packet/Block/Variant) use a CONTINUOUS colorbar — need discrete swatch legend + categorical colormap. `packet_colorbar.png`.
- P2 cold-state Save/Export enabled with no data (misleading affordance).
- P3 pixel readout triplicated (status strip + in-map box + Info dock); chart axes lack units; "Detected vs Parent" counts unlabeled.
- Responsive defect: at ≤900px the display-mode combo falls into toolbar overflow (primary control hidden) and the 380px dock eats ~42% width.
- P4 OR dock content clips at bottom at default height; CPU not idle post-compute.

## 2026-06-18 (later) — legend verification pass
- Launch that works in this harness: the `run_in_background:true` Bash tool with `exec env DISPLAY=:77 LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe QT_QPA_PLATFORM=xcb uv run pagb <abs-path>` — the task IS the app and survives (nohup/& dies). Kept-alive Xephyr :77 same way.
- Combo: popup renders BLACK in xwd + type-ahead unreliable. Open combo, find override-redirect popup (`xwininfo -root -children | grep '"pagb"'`, width<300 height>200, geom moves +919+33 pre-recon → +919+0 post), mousemove over it, Home + N Down (arrows skip separators). Post-recon order: Phase0 IPF-Z1 IPF-X2 IPF-Y3 Euler4 GrainID5 CSL6 BandContrast7 KAM8 GOS9 GAM10 Misor11 GROD12 ParentGrainID13 VariantID14 FitQuality15 FitAngle16 Packet17 Block18 ParentIPF19.
- Fixture truth: SDSS .ang duplex → Variant/Packet/Block ~97% id=0 (uniform blue is CORRECT, not a bug). Use data/martensite_roomtemp.ctf to see real categorical + parent structure. tab20 id0 = rgb(31,119,180).
- ~~Martensite (334k px) reconstruction ≈ 18.5 MIN~~ **STALE — superseded 2026-07-21: now ~12s** (see the 2026-07-21 entry). Parent IPF on-demand compute ~2min. Detect done via green progress pixel srgb(166,227,161), not CPU (never drops below ~100%).
- VERIFIED PASS: IPF key triangle present + LABELLED ([001]/[101]/[111]/m-3m) for IPF-X/Y/Z + Parent IPF, hidden for Phase/KAM/Fit Angle; categorical maps distinct per-id colours, no continuous colorbar. IPF key now width 110 + "IPF ∥ axis" caption (was stealing ~10% map width).
- STILL OPEN: categorical discrete SWATCH legend (colour→id number) — map_viewer.py comment; reconstruction performance on large maps (18.5min); CPU idle leak.

## 2026-07-17 — redesign verification pass (interact sandbox WORKING again)
- Standard interact `launch_app` + `target="nested:PAGB Reconstruction"` works now — Xephyr workaround no longer needed this host.
- `launch_app size=` sets the Xephyr canvas, NOT the app window: PAGB opens at its own fixed default **1200x800** regardless. To truly resize: `xdotool windowsize <wid> W H` on the inner DISPLAY (wid via `xwininfo -root -children | grep -i pagb`), and launch the canvas LARGER than the target first or the screenshot crops instead of the app resizing (a cropped screenshot mimics "panel clipped, no scrollbar" — false FAIL).
- Redesign verdicts (Carbon default): left-stripe subtraction PASS, Phosphor icons PASS, panels/buttons PASS, theme-switch integrity PASS across Carbon/Latte/Nord (map canvas staying black across themes = deliberate).
- Bugs found: Tasks overlay painted with NO background during a run (QWidget subclass + QSS type selector needs WA_StyledBackground — fixed same turn); toolbar rendered ONE row despite two QToolBars (stale QSettings window_state re-docked them — fixed by insertToolBarBreak after restoreState).
- Programmatic (offscreen, computed) checks after fixes: main y=29 / view y=78 (two rows), TaskManager bg pixel #141414 alpha=255 (opaque); OR/Stats QScrollArea vsb ranges 655/402 at 300x250 (scroll engages).

## 2026-07-17 — Statistics-scroll FAIL was a critic coordinate error (RESOLVED)
- The "Statistics dock has no scrollbar" FAIL (reported twice) was WRONG: with the default layout the bottom dock is ~796px wide (right dock takes the right ~380 at full height), so its vertical scrollbar sits at x≈790. The critic checked x≈818 — ~28px PAST the dock edge, in the gap — and missed it. A zoomed crop of the real rendered PNG at x 760-796 shows the recessed track + grey rounded handle plainly; drag scrolls the content. Offscreen vsb_max/vis were CORRECT; the earlier "don't trust the offscreen vsb line" note was itself the error. Lesson: derive a dock's true right-edge x from its measured width before sampling for a scrollbar — don't assume full window width.

## 2026-07-17 — map pixelation fix (issue #8) PASS
- SmoothPixmapTransform + autoDownsample (map_viewer.py) confirmed clean: no cross-hatch across 5 window sizes incl. non-integer ratios (1247x833 vs 501x667 source) + aggressive downscale (700x550), on IPF-Z/Phase/Band Contrast. VLM + pixel checkerboard test (adjacent-sign-alt 0.29-0.38; true aliasing would be ~0.8-1.0) both clean.
- RESIDUAL UNVERIFIED: sandbox is 1:1 DPI — cannot reproduce fractional-OS-scaling (user's Windows 125/150%) compounding with app-window fractional scale. Flag if user reports recurrence.
- Ergonomic: IPF-key triangle floats in ~40% dead black canvas at wide windows (worst issue); Equalize/Boundaries checkboxes + colormap selector unlabeled until hover; 10µm scale bar tiny.
- Resize technique for this app: `xdotool search --name 'PAGB Reconstruction'` then `xdotool windowsize <wid> W H` on DISPLAY=:99.

## 2026-07-17 — reconstruction param controls (Eloïse papers) PASS
- min_parent_size_um "Min. parent grain size (µm)" slider (Post-processing) + Bainite preset (Default/Fine/Coarse/Bainite) both PASS: clicking Bainite visibly changes params (threshold 2.5→3.5, min parent size 0→5 etc.); slider ranges 0–50µm. Panel legible at 1600x1300, all cards expand cleanly.
- Ergonomic: FOUR size controls scattered across 3 cards (min child grain / min cluster / merge islands / min parent size) — hard to tell which answers a size request. Fixed labels with units this turn; grouping them still open. Raw snake_case→Title labels read badly ("Um" not µm) — always set pydantic Field(title=...) for UI labels.
- interact gotchas (reconfirmed): set final window size at launch_app time, NOT via post-launch xrandr/xdotool (later resize → cropped screenshot). Mouse-wheel over the side panel routes to the map canvas underneath (zooms map) — collapse cards instead of scrolling; interaction bug worth a ticket.

## 2026-07-17 — Compare approaches dialog PASS (5/5) + 2 defects fixed
- "Compare…" button (Reconstruction dock, Ctrl+2 reveals dock) → CompareDialog: preset checkboxes (Default/Bainite pre-checked), one-field Sweep, 150px fast-preview, ranked results table (Map/Approach/Parents/%recon/Size µm AW/Mean fit) best-fit-first, Apply. All PASS.
- FIXED this turn: (a) ParamPanel.set_config didn't sync the preset segmented tab → applying a Compare winner left "Default" highlighted, a click silently reset values (param_panel.py set_current + match). (b) enabled outline QPushButton used $border ≈ disabled $surface → read as disabled; bumped default border to $border_strong, bg $elevated.
- OPEN/UNCONFIRMED: one Compare run (Fine+Bainite, 150px crop) made the whole sandboxed app window vanish near 95% during the Bainite stage; immediate retry completed clean, empty stderr. Not reproduced, no stack trace. If seen again, launch app with `> app.log 2>&1` to capture. Resurface on any crash report near reconstruction end.
- interact recipe reconfirmed: launch_app(command="bash -lc 'cd <repo> && exec env LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe QT_QPA_PLATFORM=xcb .venv/bin/python -m pagb_reconstruction.app data/martensite_roomtemp.ctf'", size="1600x1200"); window opens fixed 1200x800. Compare on 150px crop ~2-4 min/config. Dialogs are QDialog with no title bar in WM-less sandbox — capture target="nested". Poll with run_actions chained sleep(≤30s)+screenshot, not Bash sleep.

## 2026-07-21 — full ergonomic audit (verdict FAIL) + OR panel delta verdict

### Environment / harness
- Reconstruction on `data/martensite_roomtemp.ctf` now completes in **~12s**
  (978 parents, 93.4% recon, mean fit 5.79°) — supersedes the stale ~18.5min note above.
- The **OR tab loads its data without running a reconstruction** — an OR-only check can skip the run.
- `QSettings` persists geometry + theme inconsistently across launches — always screenshot after launch, never assume size or theme.
- Preset-combo `click + Down + Return` sometimes needs a **second Return** to commit. Verify by screenshot, not the action log.
- **interact gotcha (filed as interact #82)**: mouse-wheel `scroll` can resize the whole app WINDOW rather than scroll the target widget (1600x1200 → 1600x2000 observed). Avoid `scroll` for this app; use `xdotool windowsize` for exact sizes.

### Confirmed-open defects, ranked
- **Docks are non-resizable** — splitter drags produce zero pixel movement in either axis. Root cause of the map's ~27%-width letterboxing: the user cannot trade empty dock space for map area.
- **Map viewer wastes ~70% of its width** to fixed-aspect letterboxing while sitting beside equally empty docks; the two compound.
- **Right-dock tab strip shows only 2 of 4 tabs** (Phases/OR/Params/Info) at ~315px; switching can permanently hide a previously-visible tab with **no scroll affordance** — only recovery is the View-menu checkbox toggle.
- **Equalize corrupts categorical maps** — on "Phase" it turns 2 colours into banded rainbow noise. Should be disabled for non-continuous channels.
- ~~**Fullscreen-fit toolbar button** toggles with zero effect~~ **NOT REPRODUCED 2026-07-21** — `zoom_fit()` was measured headless against a zoomed-in viewbox and correctly restores the full image range, producing the identical result to `autoRange(padding=0)`. The "no effect" reading is what a working Fit button looks like when the view is ALREADY fitted. Do not re-file without first zooming in, then clicking Fit. No fix applied — patching a working control on an unreproduced symptom would have been a speculative change.
- **Line-profile toolbar toggle appears to do nothing**: it arms a mode that needs two subsequent clicks ON THE MAP to draw a profile, but gives no cursor change, hint, or armed-state feedback. Still open — the defect is the missing affordance, not a dead control (`toggle_line_mode` is covered by test_map_viewer.py).
- **Statistics dock**: ~35% permanently blank right of the stat cards. **Params panel**: 10+ fields, only ~3 visible before clipping.

### Poles-blank / Parents-empty — do NOT re-file as dead features
Both were observed blank in the audit session, but each was verified to work when given data: the pole figure renders 2476 scatter points from real quaternions, and `worst_fit_parents` returns 200 rows on the real map (`parent_orientations` = 334167 finite quats, 978 parents). The same session saw the **result silently reset to "Idle"** after an Escape keypress plus a drag near the dock splitter (window also jumped size). Escape is bound to Stop. Both symptoms are almost certainly **downstream of that reset** — re-check whether the result is still live before diagnosing either panel. The reset itself is the real open bug and needs a dedicated repro pass.

### OR panel — Misorientation Distribution plot
- **`minimumHeight` is NOT enforced** by the enclosing `QScrollArea` in the real dock: it **clips silently rather than scrolling**. Measured 178px at a 1080px window and ~20px (invisible) at 900px, against a 220px floor. **Headless/offscreen does NOT reproduce this** — the scroll area behaves correctly there (484px, scrollbar appears), so this defect is live-dock-only. Floor lowered to 160px, which the dock can honour.
- Legend naming verified correct ("Measured misorientations" / "Theoretical &lt;preset&gt; peaks"), exactly 2 entries, no stacking across KS→NW→GT→Pitsch→Bain. But the swatch **overlaps the tall measured spike**.
- **Linear y-axis made the plot scientifically useless**: one ~450k spike near 0° flattens the 40–90° OR peaks (&lt;15k) the panel exists to show. Log-y enabled.
- Mouse-wheel over the OR panel routes to the map canvas underneath, so a user cannot scroll to reveal clipped content.

## 2026-07-21 (3rd pass) — misorientation dock relocation CONFIRMED FIXED

- **Misorientation dock: 5/5 PASS.** Axis box 1342px wide × 103px tall, identical at 900px and 1080px window heights. Full x-axis 0–180°, log y (1/10²/10⁴), curve and 2-entry legend all render cold. This is the regression that FAILED twice while it lived in the OR sidebar — relocating it out of the shared scroll area was the fix, not any `minimumHeight` value.
- **Right-dock/map splitter now genuinely resizable** — dragged 1076→850→1250px map width, bidirectional. Previously literally zero pixel movement (`setMaximumWidth(380)` against a 320 default).
- **Splitter handle technique**: it is a precise `(63,64,66)` 4px-wide column and it MOVES between layouts — locate it by pixel scan each time; a drag 1-4px off the real handle silently no-ops and looks identical before/after. The horizontal (map/bottom-dock) handle sat at y ≈ window_height × 0.645 in a 1080px window.
- **Bottom dock group barely grows with the window**: +14px of dock height for +180px of window height, because nearly all of it goes to the map/right-dock row. Workable for a single-widget tab (Misorientation), proven inadequate for any multi-widget tab.
- **Statistics 1x4 relayout FAILED** — and the diagnosis is the valuable part: the stat-card row (~66px) + Grain Size Measurement groupbox (~200px) alone exceed the ~230px dock ceiling *before the chart row is reached*, so the charts were 100% below the fold at both 900px and 1080px cold. 1x4 vs 2x2 was the wrong axis; a 1x1 grid would fail identically. Charts themselves ARE readable at quarter-width (axis box 234px tall, 270-330px wide, all labels legible) once scrolled into view — width was never the bottleneck, height budget above them is.
  → Acted on: chart row moved OUT of the scroll area onto the outer layout with stretch 1; header (cards + measurement) capped at `setMaximumHeight(180)`. Re-verification pending.
- Reconstruction via the toolbar Run icon, ~11-20s; wait 20s then screenshot.

## 2026-07-21 (4th pass) — Summary/Statistics split verdict: FAIL, 3 real defects

### Harness (persist — cost ~15 min to rediscover)
- **WAYLAND_DISPLAY leaks into the sandbox.** `launch_app` inherits the host's `WAYLAND_DISPLAY`, so Qt renders onto the REAL compositor instead of Xephyr: event loop alive, GPU busy, zero errors, and NO window ever appears in the sandbox. Always launch with `env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=xcb GDK_BACKEND=x11` on this host. Filed interact#85.
- **QSettings masks first-run defaults**: `~/.config/PAGB/pagb-reconstruction.conf` holds a `window_state` blob restoring dock sizes verbatim. DELETE it to test genuine cold behaviour — otherwise a layout bug looks fixed (or a fix looks broken) purely from cache.
- Bottom-dock height via x=5 pixel scan: splitter handle `(63,64,66)`, section separators `(51,51,51)`.

### Verdicts
- Statistics charts-only: **PASS** (4 charts, no scroll, legible at 1:1 at both 900px and 1080px).
- Stop disabled at rest / enabled during run: **PASS** (grey 85,85,85 → 225,225,225 → grey).
- Failed run keeps previous result: **PASS** — status bar reads "Reconstruction failed — previous result kept", Parents + Summary unchanged.
- Line-profile banner arm/disarm: **PASS**; the two-click-draws-a-line behaviour was INCONCLUSIVE (synthetic clicks may not reach the pyqtgraph scene — a harness limit, not a proven app bug). Still open to confirm.
- **Wheel guard: FAIL, and a REGRESSION** — unfocused wheel over the spinboxes CHANGED values (50→45, 1000→0). Root cause found after: Qt's default `WheelFocus` lets the very scroll being guarded give the control focus, so the `hasFocus()` check passes and the value changes. → fixed with `StrongFocus` + forwarding the event to the enclosing QScrollArea so the panel scrolls instead of going dead.
- **Summary / Misorientation / Parents hidden at cold entry: FAIL** — confirmed on 2 independent fresh installs. Root cause: `restoreState()` only positions docks its saved blob knows about, so ANY dock shipped in a later release stays hidden forever for existing users, View menu the only recovery. → fixed by persisting `dock_names` beside `window_state` and revealing (tabified onto an area sibling) any dock absent from the saved set.
- **Dock ceiling fix ineffective: FAIL** — 355px @900 vs 356px @1080, same symptom as the pre-fix 384/384, while manual splitter drags worked fine. Root cause: Qt only ever SHRINKS a dock to its `maximumHeight`, never expands it, so raising the ceiling left the assigned height untouched and gave every extra pixel to the map. → fixed by scaling the bottom-dock height by the window's own resize ratio (preserves a user's manual split rather than re-imposing a default).

## 2026-07-21 (5th pass) — verdict + root causes found afterwards

- **Wheel guard: PASS.** Unfocused wheel leaves Method/Test lines/Step size unchanged and scrolls the panel; focused wheel still adjusts (50→52). The `WheelFocus`→`StrongFocus` fix holds.
- **Hidden tabs: FAIL — real root cause was NOT the restore path.** `apply_profile()` sets visibility from a hard-coded name tuple, and the "Analyze" profile (auto-applied when a reconstruction finishes) never listed Summary / Misorientation / Parents — so completing a run HID exactly those three. Same hard-coded-list bug class as `_cap_bottom_docks`. Fixed by adding them to Analyze, plus a test asserting every dock appears in at least one profile, and `test_profiles_reference_real_docks` now derives the dock set from the live window instead of a hand-written literal (the literal passed while three real docks were missing).
- **Line-profile disarm: FAIL — cause was ORDERING.** `_show_misorientation_profile` opens a QDialog; disarming after it meant the crosshair, banner and pressed button stayed up for as long as the dialog was. Disarm now runs BEFORE the dialog, with a test asserting that order.
- **Dock height: auto-scaling REVERTED.** It made the dock grow but destroyed a manual splitter drag on any resize. Investigating further: Qt reflows dock heights on window resize regardless — measured 381→279→299 across 1080/900/1080 with NO app-side scaling at all — so manual drags never survived a resize; the scaling only made the reset land on the default. Kept the recomputed ceiling (removes the stale cap that blocked growth), dropped the scaling (removes the regression). `test_manual_split_survives_a_window_resize` is xfail-with-reason, not deleted, so the limitation stays visible. Proper fix = persist the chosen height and reapply after layout settles.
- Harness: a `drag` with identical from/to coords reaches the pyqtgraph scene as a click; a plain `click` does NOT. Use drag-as-click for any map interaction test here.
- Bottom-dock x=5 scan: `(51,51,51)` marks both the outer handle and the status-bar boundary, and `(63,64,66)` appears at several y's — read the FULL column profile, not the first match.

## 2026-07-21 (6th pass) — profile fix PASS, new line-render defect found

- **Hidden tabs: PASS.** Cold `--run` on a fresh install shows all 7 bottom tabs without touching View, and Summary / Misorientation / Parents each render real data. Root cause had been `apply_profile()`'s hard-coded name tuple in the "Analyze" profile, not the restore path. No profile leaves a dock unrecoverable (View checkboxes stay live).
- **Line-profile disarm ordering: PASS.** Banner gone and toolbar button unpressed at the moment the dialog opens, dialog carries genuine data.
- **NEW defect found and fixed: the drawn line never rendered.** 0/250 samples matched the warning colour along the exact computed path (endpoints derived from the app's own live pixel readout), in every theme, dialog open and closed. Cause: `_line_item` was left at the default z=0 while boundary is 10 and highlight 11, so it painted UNDER the map image. The profile dialog showing correct data is what made this look like a coordinate bug — it never was. Fixed with `setZValue(12)` plus a test asserting the line sits above every overlay.
- **Dock height: PASS on behaviour.** No auto-grow on resize; a manual drag holds at rest; max draggable now ≈490px @1080 (was 355-384) and ≈415px @900. Statistics' 4 charts fit comfortably at both; Summary's Measure-results line still clips at 415px but has its own scrollbar (reachable, not lost).
- **Standing structural critique (not yet acted on):** every dock-height fix so far — ceiling calc, ratio scaling, reverted scaling, recomputed ceiling — shuffles the SAME fixed pixel pool, because the map row is never allowed to shrink below its current floor. Each fix only raises how much of the map's space the dock may take, never the floor itself. The next data-dense tab will hit the same wall. Real fix = a user/preset-adjustable map minimum, or a one-click maximize-dock / 25-50-75 split preset.

### Harness
- `size="1400x1300"` at launch, then `xdotool windowsize $(xdotool search --name "PAGB Reconstruction") W H` on `DISPLAY=:99` resizes reliably without cropping.
- Escape sent to `target="nested:Misorientation Profile"` closes only that dialog — it does NOT fire the main window's Stop shortcut, so it is safe for dismissing dialogs without losing the result.
- Horizontal map/bottom-dock splitter: scan x=5 for a `(63,64,66)` 4px band; its y moves with window height and after every drag — rescan, never reuse a stale y.

## 2026-07-21 (7th pass) — line render STILL FAIL, real cause was a signal loop

- Critic reproduced 0/753 colour samples across 3 armed runs, full-canvas scan included, endpoint circles absent too. Crucially it noted the **identical code renders correctly HEADLESS** (`headless_export3.png`, z=12 confirmed) — which is what pointed away from z-order.
- **Real cause: a re-entrant signal loop introduced by the toolbar-sync fix two passes earlier.** `_disarm_line_mode(keep_line=True)` emits `line_mode_changed(False)` → unchecks the toolbar QAction → its `toggled(False)` calls `toggle_line_mode(False)` → `_disarm_line_mode()` with `keep_line` defaulting to **False** → `_clear_line()` erases the line the user just measured. Fixed with a `_disarming` re-entrance guard.
- **Why every test missed it:** a `MapViewer`-only test has nothing connected to `line_mode_changed`, so the loop never closes and the line survives. It only reproduces when armed through the TOOLBAR ACTION from a real `MainWindow` — arming via `viewer.toggle_line_mode(True)` leaves the action unchecked, so `setChecked(False)` emits nothing. New test `test_line_survives_the_toolbar_sync_roundtrip` arms the way a user does.
- The earlier `setZValue(12)` fix is still correct and kept (the item genuinely had no z while boundary=10, highlight=11) — it just was not the whole story. A test asserting `.zValue()` numerically can never catch a non-painting item; it does not render or export the scene.
- **Boundary overlay + grain highlight: PASS, no z-order regression traded in** (grain boundaries render; `highlight_parent()` pixel-diffed to a real 68px grain, 33x273px changed region, max delta 88).

### Ergonomic findings from operating it end to end
- Line-Profile toggle has no durable pressed-state cue across dock/tab switches — the critic mis-toggled it twice itself. A first-time user will arm/disarm silently and conclude the tool does nothing.
- Parents-tab copy says "select one to locate it" but selecting only tints in place — no pan/zoom-to-grain — so a worst-fit grain under ~100px is practically invisible despite the highlight rendering correctly.
- Toolbar Line Profile icon at x≈478,y≈106 (2nd row, chart-line icon); click by coordinate, cached element refs go stale across dock-tab switches.

## 2026-07-21 (8th pass) — line render CONFIRMED FIXED

- **PASS.** 536/800 hits on the exact computed path, **800/800 within ±4px**, both endpoint circle markers render, and the line SURVIVES closing the profile dialog (766 hits, identical bbox before/after) — that survival was the exact thing the re-entrant signal loop was destroying. Full-canvas scan: zero stray warning-colour pixels outside the line bbox.
- Root cause recap: the toolbar-sync signal loop (`_disarm_line_mode` → `line_mode_changed` → action `setChecked(False)` → `toggled` → `_disarm_line_mode()` with `keep_line=False` → `_clear_line()`), NOT the z-order. The `setZValue(12)` fix was correct but insufficient alone.
- **Scan gotcha**: a full-window scan for the warning hue false-positives against the Misorientation-histogram chart (same hue) below y≈930. Mask that out or restrict to the map canvas box (x45–1035, y145–900) before counting.
- **Operator verdict on ergonomic priority** (better reasoned than the main thread's): fix the toggle pressed-state affordance BEFORE the Parents locate-zoom. The toolbar-toggle pattern is the shared entry gate to Line Profile / ROI / Clear ROI, so an unreadable armed state causes mis-operation across the whole family, not one workflow; it already caused repeat error in the most experienced operator of the tool. Parents-locate is real but narrower blast radius and needs new interaction machinery. Both are now built.

## 2026-07-21 (10th pass) — rebuilt main_window.py: ALL 7 PASS

Re-verified after `main_window.py` was rebuilt from HEAD (a bad scripted slice had left 40 duplicated methods in one class, second copy shadowing the first, with the whole suite still green).

- Cold launch, all 7 bottom tabs with real data, Parents locate-zoom, Info-panel-follows-selection, armed-state cue surviving tab switches, line render **239/240 (99.6%) ±4px at non-default zoom**, Stop lifecycle incl. "previous result kept" — **all PASS**.
- **Summary now fits unscrolled at full drag at BOTH 900 and 1080**, ~90-160px headroom. That was the point of raising the ceiling.
- Map at full drag: ~245px @1080, ~195px @900 — not distorted, boundaries and scale bar still legible. Critic's read: acceptable as a user-CHOSEN trade-off, not as a forced default. A 50-68px worst-fit grain would be hard to spot at that scale.

### Two defects found, both fixed same pass
- **Stale Info fields** (trust bug): selecting a Parents row filled the parent fields but left Grain ID / Phase / Eq. Diameter / Aspect Ratio / Neighbors from the last map CLICK sitting beside them, reading as though they belonged to the parent. Now blanked on parent selection.
- **The dock-height formula was claiming something false.** Implementer's `ceiling = height - 220` predicted 680/860; the app enforced ~493-501 regardless of window height. Cause: the bottom docks span the full width (both bottom corners assigned to them), so the central row's floor is the **RIGHT dock's minimum height (200px)**, not the map's 88px. The ceiling is only a SAFETY cap — Qt's layout binds first. Right-dock height floor lowered 200 → 120 (those panels all scroll), lifting max reach at 1080 from 645 to 674. Comment now says the cap is a backstop, and the test asserts REACHABLE height (≥480, the empirically sufficient value) instead of the formula.

### Method notes
- **Fresh launch per window size is mandatory** before judging dock height — a manual drag carried over from a prior resize gives false-FAIL readings (known Qt limitation; xfail test exists).
- Standing structural gap (not yet built): the dock/map split is a zero-sum pool with no memory. A metallurgist bouncing Parents (wants map) ↔ Summary (wants dock) drags the splitter every session. Fix = persist the chosen dock height, and/or a one-click 25/50/75 preset.

## 2026-07-21 (11th pass) — split presets REMOVED after a live FAIL

- **Verdict FAIL, feature deleted.** `apply_split_preset`'s pin-min/max-then-restore trick reached its 22% target HEADLESS but never live: only the GROW direction took effect, SHRINK clamped at ~383px — the original bug. Cause: these docks are tabified, so the group cannot shrink past the tallest tab's `sizeHint` (Poles ~555, Statistics ~523), and pinning the bounds around the resize does not defeat that in the real app.
- **Why it was removed rather than patched again:** cold launch already sits at ~383px, so clicking "Map" was a SILENT no-op — harder to notice than the visible clamp it replaced. Shipping a button that does nothing is the same defect class this whole session removed from the app (dead toolbar buttons, an armed mode that stayed armed, Save with nothing to save, an invisible line profile). Also the reused `ph.arrows-out` icon was pixel-identical to the Zoom Fit button two icons away.
- **THIRD recurrence of headless-passes / live-fails in this widget.** Any future dock-resize work must be verified LIVE; the offscreen suite structurally cannot see this class of failure. A re-attempt has to lower the tallest tab's `sizeHint` first.
- **Right-dock floor revert (160 → 120): PASS, no regression.** Phases/OR/Params/Info identical; max dock reach 737px @1080; 4 Statistics charts still fit unscrolled. Params still clips to ~1 field at minimum right-dock height — pre-existing and inherent to the user having maximised the bottom dock, not a floor value to tune (two attempts proved the floor never binds; the central row bottoms at ~233px from the MAP viewer's own 159px minimum).
- **Persistence still owed, still unbuilt.** Confirmed needed (a second launch after Panel returns map-dominant; Qt's `restoreState` does not carry it). Both attempts segfaulted: `resizeDocks()` during `showEvent` re-enters Qt's running layout, and a `QTimer` defer let the callback outlive the window. Moot for now — the presets it would persist are gone.
- Method: move the mouse OFF the splitter handle before colour-sampling it, or a resting cursor leaves it hover-blue and reads as "stuck".

## 2026-07-21 (12th pass) — dock persistence FAIL, fixed at the shared layer

- **Reproduced live and precisely**: drag dock to 763px → File→Quit (real `closeEvent`) → relaunch `--run`. Layout restored CORRECTLY (splitter y=517 mid-reconstruction), then snapped to y=787-790 — byte-identical to a true cold default — the instant the run finished.
- **Root cause: I guarded one of three `resizeDocks` callers.** `_fit_layout_to_map_aspect` got `_layout_restored`; `apply_profile` (workspaces.py) did not, so `_on_reconstruction_done` → `apply_profile(PROFILES["Analyze"])` → `resizeDocks([dock],[480])` stomped the restored height on every completed run.
- **Fixed at the shared layer**: a profile owns WHICH docks are visible and which is raised; it owns their SIZE only as a fallback, skipped entirely when `_layout_restored`. Audited all six `resizeDocks` call sites — two are construction defaults (pre-restore), one is `reset_layout` (user explicitly asked for defaults), one is `showEvent`'s first-run-only branch, one is the guarded fit, two are the now-guarded profile.
- **Critic's structural verdict, worth heeding**: there is no single source of truth for dock geometry, which is what produced 11 passes of whack-a-mole. Any future dock work must audit EVERY `resizeDocks` caller, not the one that happens to be in view.
- **Test-design note**: a pixel assertion here passes VACUOUSLY offscreen — Qt clamps the dock at the tallest tab's sizeHint so neither the user resize nor the override moves it. The observable contract offscreen is that the geometry CALL is not made; verified by reverting the fix and watching the test fail.
- Critic's "would you ship this?" answer on the broken version: **no** — "claiming persistence is fixed when it reverts on the single most common action (load data, hit Run) is worse than no fix: it looks fixed at a glance, then betrays the user the first time they reconstruct."

## 2026-07-22 — workflow rail: keeper (4/5 PASS), cue made bidirectional

- User unfroze the design direction (removed "precision instrument" from decisions.md himself). His mandate: "both the functionalities AND something good". DREAM3D-NX explicitly rejected as a VISUAL reference ("looks horrible") — its workflow-skeleton idea only. No 3D features exist or are planned; "3D" is that product's name.
- **Rail verdict: "not a removal candidate."** Renders native to the app's language ("built-in, not bolted-on"), all six stage routings PASS, map canvas md5-identical across stage clicks, cost 90px, no overflow at 1200px. Its real value per the critic: it imposes a canonical ORDER over ~11 previously unordered tabs.
- **PARTIAL FAIL fixed same turn**: the current-stage cue was click-driven only — manually raising a dock tab left the rail claiming the last rail-clicked stage, and "Load" stayed current forever. Now: every dock's `visibilityChanged` maps back to its stage (`_DOCK_STAGE`), stageless tabs (Statistics/Summary/Poles/Log) CLEAR the cue rather than lie, and Load restores the previous stage after its dialog (an action, not a destination). QButtonGroup made non-exclusive because an exclusive group forbids clearing.
- Rail width 90px; boundary scan via PIL at x=0-150 mid-height row is fast and reliable for width/overflow checks. Rail accent = app-wide `rgb(79,140,255)`.
- Session work committed: `b5d256989` (ergonomics: "controls must not lie"), `2a072fd` (decisions). Both by explicit pathspec.

## 2026-07-22 — rail cue sync CONFIRMED live (4/4 PASS), item closed

- Bidirectional cue verified on pixels: manual Parents click moved cue to Review unprompted; Params click moved it; Statistics CLEARED it (zero checked buttons on a full-rail pixel scan); Load → Cancel restored the prior stage. Startup + Reset Layout land sane; forward routing intact. No visibilityChanged storm misbehaviour observed.
- **Read-the-rail method note**: move the mouse OFF the rail before reading its state — `:hover` (#232323) and `:checked` (#2c2c2c) are 9 levels apart on the dark theme, and a resting cursor mimics the checked look at a glance (the critic briefly false-read this itself).
- **Advisory, not owed now** (critic's own framing: "if this recurs as a real user complaint"): (a) the common post-run landing (Statistics, stageless) lights zero rail buttons — truthful, but a first glance can read as "broken" for a second; consider whether stageless tabs should map to the nearest stage instead. (b) strengthen hover/checked separation if misreads recur.

## 2026-07-22 — parent-boundary overlay + scale bar (Eloïse reference match)

- Launch recipe (reconfirmed): `env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=xcb GDK_BACKEND=x11 uv run pagb data/martensite_roomtemp.ctf --run` via `launch_app(cwd=repo, size="1400x1300")`, `target="nested:PAGB Reconstruction"`, wait ~30s. Recon ~12s (978 parents, 93.4%, fit 5.79°); auto-lands on IPF-Z + Parent boundaries checked. Drop `--run` for a cold map (scale bar + key show on load, no compute) — much faster for non-reconstruction checks.
- **PASS**: parent boundaries as bold black polygon lines over the child IPF map (not tab20 fills); "Parent boundaries" checkbox toggles them; overlay composes over Phase/IPF-X too (base-map independent). IPF key labelled with phase names ("Iron bcc/fcc"). Axis indicator "X →"/"Y ↓" top-left.
- **Scale-bar number-clipping bug + fix**: stock `pg.ScaleBar` grows LEFTWARD (rect [-w,0]), label at -w/2 → anchored bottom-left the numeral clips off-screen, only "µm" survives. Fix = `_ScaleBar` subclass growing RIGHTWARD (rect [0,w]), label +w/2, bold 11pt white on a dark chip. CONFIRMED fixed: reads "20 µm", chip bg ≈(8,8,8), ~20:1 contrast, bar 20px inside the left edge, no clip. Read-the-scale-bar method: pixel-scan a row through the chip/bar y-band, don't rely on a screenshot VLM query.
- **Standing ergonomic (pre-existing, NOT introduced here, since 2026-07-17)**: ~120-150px black dead-zone between the map's right edge and the Info dock, hosting only the small floating IPF key. Candidate follow-up: move the key into a map corner inset and widen the map. Tracked, not fixed this turn (orthogonal to the reference-match task; needs its own composition pass).

## 2026-07-22 — hover lag fix + thin borders + FPS counter (all 3 PASS)

- **Hover lag** (user: "very very slow"): PASS. FPS while sweeping the map = 1294/1118/901/1086/1083 (was ~3-6). Root cause: hover converted ALL orientations to Euler every move (~170ms) in BOTH `map_viewer._on_mouse_move` AND `main_window._on_pixel_hover`, and `crystal_map.rotations` rebuilds the whole object (~55ms) per access. Fix in ebsd_map.py: `pixel_euler` (single cached rotation), memoized `band_contrast_map`, O(1) `pixel_index_at`. 245ms->2ms/hover.
- **Border weight** (user: "too big"): PASS. Pen 2px->1px cosmetic; measured median 1-2px, crisp even in dense clusters, zoom-stable.
- **FPS counter**: PASS. Toggle in the View toolbar ("FPS" button) -> live "N fps" readout top-right of the map.
- **"Black lines everywhere" (density, NOT thickness)**: the martensite map reconstructs to 978 parents, median ECD 2-4um (long tail of small parents) but area-weighted-mean ~11um — a few large grains + many tiny ones. Filtering the overlay to parents >5um ECD (314 of 978) renders as clean as Eloise's reference. Lever is reconstruction min-grain-size/merge OR a display filter — a data-visibility decision, surfaced to the user, not baked in.
- **P3 duplicate hover readout (critic-flagged, recurring since 2026-06-18)**: the SAME `(x,y)|Phase|phi|IQ` string renders TWICE — `MapViewer._status_strip` (above bottom dock tabs) AND the real `MainWindow` QStatusBar, ~380px apart. Fix = delete `_status_strip`, keep the QStatusBar. Still open; needs actual deletion, not another observation.
