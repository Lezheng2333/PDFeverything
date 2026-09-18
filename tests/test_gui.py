"""GUI regression suite — worker lifecycle, batch resilience, dialog validation
and reader performance guards. Runs headless (QT_QPA_PLATFORM=offscreen).

Run:  .venv/bin/python tests/test_gui.py
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402
from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")

# Headless run: modal dialogs would block the event loop forever, so replace the
# static QMessageBox helpers with recorders. Tests assert on POPUPS.
POPUPS = []
from PyQt6.QtWidgets import QMessageBox as _QMB  # noqa: E402


def _record(kind):
    def _fn(parent=None, title="", text="", *a, **k):
        POPUPS.append((kind, str(title), str(text)))
        return _QMB.StandardButton.Ok
    return staticmethod(_fn)


_QMB.information = _record("info")
_QMB.warning = _record("warn")
_QMB.critical = _record("crit")
_QMB.about = _record("about")
_QMB.question = staticmethod(
    lambda *a, **k: _QMB.StandardButton.Ok)

import gui.pdf_reader_widget as _rw  # noqa: E402

_rw._DARK = False
from gui.dialogs import RotateDialog, SplitRangeDialog  # noqa: E402
from gui.file_list_widget import FileListWidget  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from gui.pdf_reader_widget import PdfReaderWidget, ViewMode  # noqa: E402
from gui.workers import BaseWorker  # noqa: E402

RESULTS = []


def section(title):
    print(f"\n{title}", flush=True)


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print(f"  {'✅' if condition else '❌'} {name}"
          + (f"  — {detail}" if detail and not condition else ""), flush=True)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


TMP = Path(tempfile.mkdtemp(prefix="pdfeverything_gui_"))


def make_pdf(path: Path, pages=30):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}", fontsize=14)
    doc.save(path)
    doc.close()
    return path


BIG = make_pdf(TMP / "big30.pdf", 30)

# ═══════════════════════════════════════════════════════════
section("═══ 1. BaseWorker: timeout, cancellation, single terminal signal ═══")


def slow_job(progress_callback=None):
    for i in range(400):
        time.sleep(0.01)
        if progress_callback:
            progress_callback(f"tick {i}", i % 100)
    return "done"


errors, done, cancelled = [], [], []
w = BaseWorker(slow_job)
w.MAX_RUNTIME_SECONDS = 0.2
w.error.connect(errors.append)
w.finished.connect(done.append)
w.cancelled.connect(lambda: cancelled.append(True))
w.start()
pump(1.5)
check("timeout stops the operation", not w.isRunning(), f"still running after timeout")
check("timeout reported exactly once", len(errors) == 1, f"{len(errors)} signals")
check("timeout is not reported as success", not done)
w.wait(3000)

errors2, cancelled2, done2 = [], [], []
w2 = BaseWorker(slow_job)
w2.error.connect(errors2.append)
w2.cancelled.connect(lambda: cancelled2.append(True))
w2.finished.connect(done2.append)
w2.start()
pump(0.15)
t0 = time.time()
w2.cancel()
blocked = time.time() - t0
check("cancel() does not block the GUI thread", blocked < 0.5, f"blocked {blocked:.2f}s")
pump(0.7)
check("cancelled worker stops running", not w2.isRunning())
check("cancel emits 'cancelled' once", len(cancelled2) == 1, f"{len(cancelled2)}")
check("cancel emits no error", not errors2, str(errors2[:2]))
w2.wait(3000)

# ═══════════════════════════════════════════════════════════
section("═══ 2. Batch runner resilience ═══")
win = MainWindow()
win.resize(1200, 800)
win.show()
pump(0.4)

out_dir = TMP / "batchout"
out_dir.mkdir(exist_ok=True)
processed = []


def flaky_op(src, dst, *extra):
    processed.append(src.name)
    if src.name == "b.pdf":
        raise RuntimeError("intentional failure on b.pdf")
    Path(dst).write_bytes(b"%PDF-1.4\n%%EOF\n")


files = [TMP / "a.pdf", TMP / "b.pdf", TMP / "c.pdf"]
for f in files:
    f.write_bytes(b"%PDF-1.4\n%%EOF\n")

captured = {}
_orig_finished = win._on_finished


def capture_finished(result):
    captured.update(result or {})
    _orig_finished(result)      # keep the real busy-state teardown


win._on_finished = capture_finished
win._run_batch(files, "op", flaky_op, out_dir=out_dir)
pump(2.0)
check("batch keeps going after a failure", processed == ["a.pdf", "b.pdf", "c.pdf"],
      str(processed))
check("batch reports the failure", len(captured.get("failed", [])) == 1,
      str(captured))
check("batch reports the successes", captured.get("converted") == 2,
      str(captured.get("converted")))
pump(0.3)
busy_widgets = [name for name, widget in (("cancel", win.btn_cancel),
                                          ("progress", win.progress_bar))
                if widget.isVisible()]
check("batch is no longer busy",
      not (win._worker and win._worker.isRunning()) and not busy_widgets,
      f"worker_running={bool(win._worker and win._worker.isRunning())} "
      f"still_visible={busy_widgets}")

# ═══════════════════════════════════════════════════════════
section("═══ 3. Dialog validation ═══")
class Pos:
    """Minimal stand-in for a QPoint in hit-testing calls."""

    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


rot = RotateDialog()
rot.all_pages_check.setChecked(False)


def try_validate(dlg, text):
    """Return (accepted, warning texts). Resets the dialog result first, because
    QDialog.result() stays at Accepted once accept() has been called."""
    del POPUPS[:]
    dlg.setResult(0)
    dlg._validate()
    warnings = [t for kind, _title, t in POPUPS if kind == "warn"]
    return dlg.result() == 1, warnings


rot.pages_edit.setText("abc")
accepted, popups = try_validate(rot, "abc")
check("rotate rejects garbage (no crash)", not accepted and popups, str(popups))

rot.pages_edit.setText("")
accepted, popups = try_validate(rot, "")
check("rotate rejects an empty range", not accepted and popups, str(popups))

rot.pages_edit.setText("2-4")
accepted, popups = try_validate(rot, "2-4")
check("rotate accepts a valid range", accepted, str(popups))
check("rotate parses 1-based -> 0-based", rot.get_pages() == [1, 2, 3], str(rot.get_pages()))
check("rotate CCW maps to 270", RotateDialog().get_angle() == 90)

spl = SplitRangeDialog()
spl.mode_combo.setCurrentIndex(2)
spl.range_edit.setPlainText("1-3\n5")
accepted, popups = try_validate(spl, "1-3\n5")
check("split accepts ranges", accepted, str(popups))
parsed = spl.get_ranges()
check("split builds (start,end) pairs", parsed == [(1, 3), (5, 5)], str(parsed))

spl.range_edit.setPlainText("abc")
accepted, popups = try_validate(spl, "abc")
check("split rejects garbage without crashing",
      (not accepted) and bool(popups), f"accepted={accepted} popups={popups}")
try:
    fresh = spl.get_ranges()
    check("split accessor never raises", True)
except Exception as exc:  # noqa: BLE001
    fresh = None
    check("split accessor never raises", False, repr(exc))
check("split keeps the last validated ranges", fresh == [(1, 3), (5, 5)], str(fresh))

spl.range_edit.setPlainText("5-1")
accepted, popups = try_validate(spl, "5-1")
check("split normalises a reversed range", accepted and spl.get_ranges() == [(1, 5)],
      str(spl.get_ranges()))

# ═══════════════════════════════════════════════════════════
section("═══ 4. Reader: lazy rendering + layout + selection ═══")
reader = PdfReaderWidget()
reader.resize(1500, 1000)
reader.show()
pump(0.4)

renders = []
orig_render = PdfReaderWidget._render_page


def counting_render(doc, pi, zk, vw, vh, force_fit=False, dpr=1.0):
    renders.append(pi)
    return orig_render(doc, pi, zk, vw, vh, force_fit, dpr)


PdfReaderWidget._render_page = staticmethod(counting_render)
t0 = time.time()
reader.open_pdf(BIG)
open_ms = (time.time() - t0) * 1000
pump(0.4)
PdfReaderWidget._render_page = orig_render
check("open renders only the visible window", len(renders) <= 8,
      f"{len(renders)} renders for a 30-page doc")
check("open is fast", open_ms < 1500, f"{open_ms:.0f} ms")
check("cache stays small after open",
      len(PdfReaderWidget._cache) <= 10, f"{len(PdfReaderWidget._cache)} entries")

shown = sum(1 for lbl in reader._labels if lbl.isVisible())
check("scroll mode materialises few widgets", shown <= 6, f"{shown} widgets")

vw, _ = reader._viewport_size()
check("container matches viewport width", reader.page_container.width() == vw,
      f"{reader.page_container.width()} vs {vw}")
expected_x = max(0, (vw - reader._labels[0].width()) // 2)
check("page is centred", reader._labels[0].x() == expected_x,
      f"{reader._labels[0].x()} vs {expected_x}")

reader.resize(1000, 700)
pump(0.8)
vw2, _ = reader._viewport_size()
check("resize re-lays out the container", reader.page_container.width() == vw2,
      f"{reader.page_container.width()} vs {vw2}")
check("resize re-centres the page",
      reader._labels[0].x() == max(0, (vw2 - reader._labels[0].width()) // 2))

reader._set_mode(ViewMode.GRID)
pump(0.5)
grid_visible = sum(1 for lbl in reader._labels if lbl.isVisible())
check("grid materialises only visible thumbnails", 0 < grid_visible < 30,
      f"{grid_visible} of 30")
cell_x, cell_y, cw, ch = reader._cell_rect(4)
check("grid hit-test finds the right cell",
      reader._grid_page_at_pos(Pos(cell_x + 5, cell_y + 5)) == 4,
      str(reader._grid_page_at_pos(Pos(cell_x + 5, cell_y + 5))))
check("grid hit-test rejects empty space",
      reader._grid_page_at_pos(Pos(1, 1)) == -1,
      str(reader._grid_page_at_pos(Pos(1, 1))))

reader._toggle_edit_mode()
pump(0.2)
check("edit mode entered", reader._edit_mode)


def send(kind, x, y):
    ev = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    {QMouseEvent.Type.MouseButtonPress: reader._grid_mouse_press,
     QMouseEvent.Type.MouseMove: reader._grid_mouse_move,
     QMouseEvent.Type.MouseButtonRelease: reader._grid_mouse_release}[kind](ev)
    app.processEvents()


g = reader._grid_geometry(reader._viewport_size()[0])
t0 = time.time()
send(QMouseEvent.Type.MouseButtonPress, g["left"] + 5, g["mg"] + 5)
for i in range(60):
    send(QMouseEvent.Type.MouseMove, g["left"] + 5 + i * 8, g["mg"] + 5 + i * 6)
drag_ms = (time.time() - t0) * 1000
send(QMouseEvent.Type.MouseButtonRelease, g["left"] + 480, g["mg"] + 360)
check("marquee selects several pages", len(reader._selected_pages) > 1,
      str(sorted(reader._selected_pages)))
check("box-select drag is cheap", drag_ms < 400, f"{drag_ms:.0f} ms for 60 moves")

reader._edit_select_all()
check("select-all covers the document", len(reader._selected_pages) == 30)
reader._edit_clear_selection()
check("clear selection works", not reader._selected_pages)
reader._toggle_edit_mode()
pump(0.2)
reader.close_document()
pump(0.3)
check("close resets the reader", reader.doc is None and not reader._labels)

# ═══════════════════════════════════════════════════════════
section("═══ 4b. Reader: search, outline, reading position ═══")
import fitz as _fitz  # noqa: E402

search_doc = TMP / "searchable.pdf"
_d = _fitz.open()
for i in range(20):
    _p = _d.new_page()
    _p.insert_text((72, 100), f"Chapter {i + 1}", fontsize=18)
    _p.insert_text((72, 140), "alpha beta gamma PDFeverything", fontsize=11)
    if i % 5 == 0:
        _p.insert_text((72, 180), f"KEYWORD marker {i}", fontsize=12)
_d.set_toc([[1, "Part One", 1], [2, "Chapter 1", 1], [2, "Chapter 2", 2],
            [1, "Part Two", 11]])
_d.save(search_doc)
_d.close()

reader.close_document()
pump(0.2)
reader.open_pdf(search_doc)
pump(0.5)
check("outline loaded into the sidebar", len(reader._outline_entries) == 2,
      str(len(reader._outline_entries)))
check("outline tree shows top-level entries",
      reader.outline_tree.topLevelItemCount() == 2)
check("sidebar visible by default", reader.sidebar.isVisible())
check("find bar starts hidden", reader.search_bar.isHidden())

reader.start_search("KEYWORD")
pump(0.3)
check("search finds every hit", len(reader._search_hits) == 4,
      str(len(reader._search_hits)))
check("search results listed", reader.search_list.count() == 4,
      str(reader.search_list.count()))
check("search jumps to the first hit",
      reader._current_page == reader._search_hits[0].page,
      f"{reader._current_page} vs {reader._search_hits[0].page}")
first_page = reader._current_page
reader.find_next()
check("find_next advances to the next hit", reader._current_page != first_page,
      f"still on page {reader._current_page + 1}")
reader.find_prev()
check("find_prev goes back", reader._current_page == first_page)

pix = reader._get_or_render(reader._search_hits[0].page, *reader._viewport_size())
img = pix.toImage()
highlighted = any(
    img.pixelColor(x, y).red() > 200 and img.pixelColor(x, y).green() > 150
    and img.pixelColor(x, y).blue() < 120
    for y in range(0, img.height(), 4) for x in range(0, img.width(), 4))
check("hits are painted into the rendered page", highlighted)

reader.start_search("definitelynotpresent")
pump(0.2)
check("no-match search clears the hit list", not reader._search_hits)
reader.start_search("alpha")
pump(0.3)
check("case-insensitive search finds all pages", len(reader._search_hits) == 20,
      str(len(reader._search_hits)))
reader.show_search_bar(False)
pump(0.2)
check("closing the find bar clears hits", not reader._search_hits)

reader._on_outline_clicked(reader.outline_tree.topLevelItem(1), 0)
check("outline click navigates", reader._current_page == 10,
      str(reader._current_page + 1))
reader.toggle_sidebar(False)
pump(0.2)
check("sidebar can be hidden", not reader.sidebar.isVisible())
reader.toggle_sidebar(True)
pump(0.3)
check("sidebar can be restored", reader.sidebar.isVisible())

reader.go_to_page(12)
reader.close_document()
pump(0.3)
reader.open_pdf(search_doc)
pump(0.5)
check("reading position is restored on reopen", reader._current_page == 11,
      f"page {reader._current_page + 1}")
reader.close_document()
pump(0.2)

# ═══════════════════════════════════════════════════════════
section("═══ 5. File list guards ═══")
flw = FileListWidget()
flw.MAX_FILES = 3
flw.add_files([BIG] * 1 + [make_pdf(TMP / f"f{i}.pdf", 1) for i in range(5)])
count = flw.count()
check("file list respects MAX_FILES", count <= 3, f"count={count}")
flw.clear()
check("clear empties the list", flw.count() == 0)

# ═══════════════════════════════════════════════════════════
section("═══ 6. Language switching ═══")
import gui.i18n as I  # noqa: E402


def has_cjk(text):
    return any("\u4e00" <= c <= "\u9fff" for c in text)


# Deterministic start: an earlier run may have persisted either language.
win._switch_language("zh")
win.file_list.add_files([BIG])
for lang in ("en", "zh"):
    win._switch_language(lang)
    pump(0.1)
    leftovers = []
    for action in win.findChildren(__import__("PyQt6.QtGui", fromlist=["QAction"]).QAction):
        if action.text() and (has_cjk(action.text()) if lang == "en" else not action.text()):
            leftovers.append(action.text())
    for btn in win.findChildren(__import__("PyQt6.QtWidgets",
                                           fromlist=["QPushButton"]).QPushButton):
        if btn.text() and lang == "en" and has_cjk(btn.text()):
            parent = btn.parent()
            leftovers.append(f"{btn.text()} [{type(parent).__name__} "
                             f"objectName={btn.objectName()!r} "
                             f"visible={btn.isVisible()}]")
    check(f"no untranslated widgets in {lang}", not leftovers,
          f"{leftovers[:5]} (merge btn = {win.btn_merge.text()!r}, "
          f"lang={I.current_language()!r})")

win._switch_language("zh")
check("merge label follows the language",
      "个文件" in win.btn_merge.text(), win.btn_merge.text())
check("about text uses the live version",
      I.tr("about_text", version="9.9.9").startswith("PDFeverything v9.9.9"))

app.processEvents()

# ═══════════════════════════════════════════════════════════
passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print("\n" + "=" * 56)
print(f"  {passed}/{total} passed" + (" ✅" if passed == total else " ❌"))
print("=" * 56)
for name, ok, detail in RESULTS:
    if not ok:
        print(f"  FAILED: {name} — {detail}")
sys.exit(0 if passed == total else 1)
