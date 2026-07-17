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
- Martensite (334k px) reconstruction ≈ 18.5 MIN (variant clustering ~5min + merge inclusions ~3min; progress bar frozen mid-step → looks hung but isn't). Parent IPF on-demand compute ~2min. Detect done via green progress pixel srgb(166,227,161), not CPU (never drops below ~100%).
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
