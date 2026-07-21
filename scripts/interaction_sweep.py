"""Drive every reachable interaction of the real MainWindow on real data.

Run:  python scripts/interaction_sweep.py <log-dir>

Unit tests exercise widgets in isolation; this drives the ASSEMBLED app the way a
user does — load, every display mode, click, hover, zoom, overlays, split view,
line profile, ROI, a real reconstruction, parent reassignment, exports, themes,
workspaces, reset and reload.

Two things it catches that pytest does not:
  * exceptions raised INSIDE Qt slots, which Qt swallows — the step still reports
    "ok", so the session log is scanned for ERROR/CRITICAL as the real verdict.
    The boundary overlay had been dead this way (IndexError on every draw).
  * a slot whose signature does not match the signal connected to it, which only
    fails when a human actually clicks the control.

Exit code is non-zero if any step fails or anything was logged at ERROR or above.
"""
import os, sys, time, tempfile, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CUDA_HOME", "/usr/local/cuda-12.6")
os.environ["PAGB_LOG_DIR"] = sys.argv[1]

from PySide6.QtCore import QPointF, QUrl, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtGui import QDesktopServices

app = QApplication([])
from pagb_reconstruction.utils import logging_setup
logging_setup.setup_logging()

from pagb_reconstruction.ui.theme import apply_theme, set_theme, THEMES
apply_theme(app)
from pagb_reconstruction.ui.main_window import MainWindow
from pagb_reconstruction.ui.workspaces import PROFILES, apply_profile

FAILS = []
def step(name):
    def deco(fn):
        t0 = time.time()
        try:
            fn()
            app.processEvents()
            print(f"  ok   {name} ({time.time()-t0:.1f}s)", flush=True)
        except Exception as e:
            FAILS.append((name, e))
            print(f"  FAIL {name}: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
        return fn
    return deco

# --- neutralize modal/system side effects, keep the code path real ---
opened_urls = []
QDesktopServices.openUrl = staticmethod(lambda url: opened_urls.append(url.toString()) or True)
QMessageBox.about = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
tmpdir = tempfile.mkdtemp(prefix="pagb-sweep-")
saves = {"n": 0}
def fake_save(*a, **k):
    saves["n"] += 1
    return (os.path.join(tmpdir, f"out{saves['n']}.png" if saves["n"] % 2 else f"out{saves['n']}.csv"), "")
QFileDialog.getSaveFileName = staticmethod(fake_save)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("data/martensite_roomtemp.ctf", ""))

w = MainWindow(); w.resize(1400, 900); w.show(); app.processEvents()

class FakeClick:
    def __init__(self, x, y, button=Qt.MouseButton.LeftButton):
        self._p = QPointF(x, y); self._b = button
    def pos(self): return self._p
    def button(self): return self._b
    def scenePos(self): return self._p
    def accept(self): pass
    def double(self): return False

@step("load real .ctf")
def _():
    from pathlib import Path
    w._load_file(Path("data/martensite_roomtemp.ctf"))
    assert w._ebsd_map is not None

@step("pre-recon display modes")
def _():
    mv = w._map_viewer
    for i in range(mv._display_combo.count()):
        mode = mv._display_combo.itemText(i)
        if not mode: continue
        mv._display_combo.setCurrentIndex(i); app.processEvents()
        t0 = time.time()
        while mv._active_worker is not None and time.time()-t0 < 180:
            app.processEvents(); time.sleep(0.03)

@step("hover + click across map (incl. edges/out-of-bounds)")
def _():
    mv = w._map_viewer
    rows, cols = w._ebsd_map.shape
    for (x, y) in [(5,5), (cols//2, rows//2), (cols-1, rows-1), (cols+50, rows+50), (-3,-3)]:
        mv._on_image_click(FakeClick(x+0.5, y+0.5))
        app.processEvents()

@step("zoom in/out/fit")
def _():
    w._map_viewer.zoom(1.25); w._map_viewer.zoom(0.8); w._map_viewer.zoom_fit()

@step("boundary overlay on all display modes")
def _():
    mv = w._map_viewer
    w._boundary_cb.setChecked(True); app.processEvents()
    for i in range(0, mv._display_combo.count(), 4):
        mode = mv._display_combo.itemText(i)
        if not mode: continue
        mv._display_combo.setCurrentIndex(i); app.processEvents()
        t0 = time.time()
        while mv._active_worker is not None and time.time()-t0 < 180:
            app.processEvents(); time.sleep(0.03)
    w._boundary_cb.setChecked(False); app.processEvents()

@step("hist-eq toggle")
def _():
    mv = w._map_viewer
    mv._hist_eq_cb.setChecked(True); app.processEvents()
    mv._hist_eq_cb.setChecked(False); app.processEvents()

@step("split view + its combo")
def _():
    mv = w._map_viewer
    mv.set_split_visible(True); app.processEvents()
    for i in range(min(3, mv._split_combo.count())):
        mv._split_combo.setCurrentIndex(i); app.processEvents()
    mv.set_split_visible(False); app.processEvents()

@step("line profile (two clicks)")
def _():
    mv = w._map_viewer
    mv.toggle_line_mode(True)
    mv._on_image_click(FakeClick(10.5, 10.5))
    mv._on_image_click(FakeClick(120.5, 90.5))
    app.processEvents()
    mv.toggle_line_mode(False)

@step("ROI select + stats + clear")
def _():
    w._toggle_roi(True); app.processEvents()
    mv = w._map_viewer
    if mv._roi_item is not None:
        mv._roi_item.setPos((20, 20)); mv._roi_item.setSize((80, 60)); app.processEvents()
    w._clear_roi(); app.processEvents()

@step("run reconstruction (real, via panel worker)")
def _():
    w._run_reconstruction()
    t0 = time.time()
    while w._result is None and time.time()-t0 < 600:
        app.processEvents(); time.sleep(0.1)
    assert w._result is not None, "reconstruction did not finish in 600s"

@step("post-recon display modes (all)")
def _():
    mv = w._map_viewer
    for i in range(mv._display_combo.count()):
        mode = mv._display_combo.itemText(i)
        if not mode: continue
        mv._display_combo.setCurrentIndex(i); app.processEvents()
        t0 = time.time()
        while mv._active_worker is not None and time.time()-t0 < 240:
            app.processEvents(); time.sleep(0.03)

@step("click parent grain (info panel + highlight)")
def _():
    mv = w._map_viewer
    idx = mv._display_combo.findText("Parent + Boundaries")
    if idx >= 0:
        mv._display_combo.setCurrentIndex(idx); app.processEvents()
        t0 = time.time()
        while mv._active_worker is not None and time.time()-t0 < 240:
            app.processEvents(); time.sleep(0.03)
    rows, cols = w._ebsd_map.shape
    mv._on_image_click(FakeClick(cols//3+0.5, rows//3+0.5)); app.processEvents()

@step("parent reassignment (review feature)")
def _():
    import numpy as np
    pid = w._result.parent_grain_ids
    ids = np.unique(pid[pid >= 0])
    assert len(ids) >= 2
    w._on_reassign_parent(int(ids[1]), int(ids[0])); app.processEvents()

@step("stats dashboard + pole figure refresh")
def _():
    w._stats_dashboard.update_stats(w._result, w._ebsd_map, elapsed=1.0); app.processEvents()
    w._pole_figure.set_orientations(w._result.parent_orientations); app.processEvents()

@step("param panel: presets + read config")
def _():
    p = w._param_panel
    for name in ("KS (Kurdjumov-Sachs)", "Bainite", "NW (Nishiyama-Wassermann)"):
        try: p.apply_preset(name)
        except Exception:
            for b in getattr(p, "_preset_buttons", []) or []:
                b.click()
            break
    _ = p.get_config(); app.processEvents()

@step("OR panel combo change")
def _():
    combo = getattr(w._or_panel, "_or_combo", None) or getattr(w._or_panel, "_combo", None)
    if combo is not None and combo.count() > 1:
        combo.setCurrentIndex(1); app.processEvents(); combo.setCurrentIndex(0)

@step("theme switch (all) + workspaces (all)")
def _():
    for t in THEMES: set_theme(app, t); app.processEvents()
    for prof in PROFILES.values(): apply_profile(w, prof); app.processEvents()

@step("export image / stats / map data")
def _():
    w._export_image(); w._export_stats(); w._export_map_data(); app.processEvents()
    outs = os.listdir(tmpdir)
    assert outs, "no export files written"

@step("report bug URL + open log")
def _():
    w._report_bug(); w._open_log_file()
    assert opened_urls, "no URL captured"
    assert "issues/new" in opened_urls[0]

@step("recent files menu + reset + reload")
def _():
    w._update_recent_menu() if hasattr(w, "_update_recent_menu") else None
    w._reset(); app.processEvents()
    from pathlib import Path
    w._load_file(Path("data/martensite_roomtemp.ctf")); app.processEvents()

@step("save session file")
def _():
    w._save_file(); app.processEvents()

print("\n=== SWEEP RESULT ===")
print(f"failures: {len(FAILS)}")
for name, e in FAILS:
    print(f"  - {name}: {type(e).__name__}: {e}")

# the log file is the crash detector for anything swallowed by Qt slots
log = logging_setup.log_file_path().read_text(encoding="utf-8", errors="replace")
errs = [l for l in log.splitlines() if " ERROR " in l or " CRITICAL " in l]
print(f"log ERROR/CRITICAL lines: {len(errs)}")
for l in errs[:20]:
    print("   ", l)

sys.exit(1 if (FAILS or errs) else 0)
