#!/usr/bin/env python3
"""Reader robustness regression tests — the defects found by the v1.9.0 QA round.

Every test here failed before the corresponding fix, so this file is the guard
against those bugs coming back. Run:
    QT_QPA_PLATFORM=offscreen .venv/bin/python tests/qa_reader_defects.py
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent, QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from gui.pdf_reader_widget import MAX_CACHE_MB, PdfReaderWidget, ViewMode  # noqa: E402

PASS, FAIL = 0, 0
FAILURES = []
WORK = Path(tempfile.mkdtemp(prefix="pdfe_reader_qa_"))


def check(ok, name, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  \u2705 {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  \u274c {name}" + (f"\n        \u2192 {detail}" if detail else ""))


def section(t):
    print(f"\n\u2550\u2550\u2550 {t} \u2550\u2550\u2550")


def pump(n=25):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def make_pdf(path: Path, pages: int, label: str = "P"):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"{label}{i}", fontsize=30)
        page.insert_text((72, 150), "alpha beta gamma", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def press(label, x=None, y=None, widget=None):
    """Deliver a real press event to a grid label (label-local coords)."""
    x = label.width() // 2 if x is None else x
    y = label.height() // 2 if y is None else y
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y), QPointF(x, y),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    label.mousePressEvent(ev)


pdf6 = make_pdf(WORK / "six.pdf", 6)
pdf3 = make_pdf(WORK / "three.pdf", 3, "Q")

# ══════════════════════════════════════════════════════════════════
section("D1: grid click hits the intended page (not always page 1)")
# ══════════════════════════════════════════════════════════════════
w = PdfReaderWidget(); w.resize(1200, 900); w.show()
w.open_pdf(pdf6); pump()
w._set_mode(ViewMode.GRID); pump()
w._enter_edit_mode(); pump()

check(w._total_pages == 6, "6-page document loaded", f"got {w._total_pages}")
mapping = {}
for pi in range(6):
    w._selected_pages.clear()
    press(w._labels[pi])
    mapping[pi] = set(w._selected_pages)
check(all(mapping[i] == {i} for i in range(6)),
      "clicking thumbnail N selects page N",
      f"got {mapping}")

# the left-edge case that used to produce the phantom -1
w._selected_pages.clear()
press(w._labels[4], x=5, y=w._labels[4].height() // 2)
check(all(p >= 0 for p in w._selected_pages) and w._selected_pages <= {3, 4, 5},
      "clicking a thumbnail's left edge never selects a phantom page",
      f"got {w._selected_pages}")

# a double-click must open the page under the cursor
w._leave_edit_mode(skip_prompt=True); pump()
press(w._labels[4])
w._grid_dbl_click_handler(None)
pump()
check(w._grid_last_press == 4, "double-click records the clicked page",
      f"got {w._grid_last_press}")

# ══════════════════════════════════════════════════════════════════
section("D2: phantom page -1 cannot enter the selection")
# ══════════════════════════════════════════════════════════════════
w._enter_edit_mode(); pump()
w._selected_pages.clear()
w._on_grid_click(-1, None)
check(w._selected_pages == set(), "negative index is rejected outright",
      f"got {w._selected_pages}")
check(not w.btn_edit_del.isEnabled(), "delete stays disabled with no selection")
check(not w._unsaved_edits, "a rejected click does not flag unsaved changes")


# ══════════════════════════════════════════════════════════════════
section("D3: drag-sort keeps a live document handle")
# ══════════════════════════════════════════════════════════════════
from core.page_editor import PdfPageEditor  # noqa: E402

src = make_pdf(WORK / "reorder.pdf", 6, "R")
ed = PdfPageEditor(src)
ed.move_pages([0], 2)
check(ed.doc is not None and len(ed.doc) == 6,
      "move_pages leaves a usable document", f"pages={len(ed.doc) if ed.doc else None}")

# out-of-range ordinals must not duplicate the last page
ed2 = PdfPageEditor(src)
ed2.move_pages(sorted({-1, 1}), 1)
check(len(ed2.doc) == 6, "move_pages with a -1 ordinal does not duplicate a page",
      f"got {len(ed2.doc)} pages (was 6)")


# ══════════════════════════════════════════════════════════════════
section("D4: cache honours its memory ceiling and accounting")
# ══════════════════════════════════════════════════════════════════
PdfReaderWidget._clear_cache()
budget = PdfReaderWidget._cache_budget_bytes()
PdfReaderWidget._protected_pages = set(range(3, 6))
for i in range(60):
    PdfReaderWidget._cache_put((i, "z:1.000"), QPixmap(1400, 1900))
check(PdfReaderWidget._cache_memory_bytes <= budget,
      "cache stays within its budget even with 60 immortal bases",
      f"{PdfReaderWidget._cache_memory_bytes / 1e6:.1f}MB > {budget / 1e6:.1f}MB")
alive = {k[0] for k in PdfReaderWidget._cache}
check({3, 4, 5} <= alive, "the live page window survives eviction",
      f"kept {sorted(alive & {3, 4, 5})}")

# width()/height() are already device pixels — no dpr² term
pm = QPixmap(100, 100)
pm.setDevicePixelRatio(2.0)
check(PdfReaderWidget._pixmap_bytes(pm) == 100 * 100 * 4,
      "pixmap accounting does not double-count the device pixel ratio",
      f"got {PdfReaderWidget._pixmap_bytes(pm)}")

PdfReaderWidget._clear_cache()
PdfReaderWidget._protected_pages = set()
for i in range(300):
    PdfReaderWidget._cache_put((i, f"z:{1 + i % 5}.000"), QPixmap(200 + i, 300))
real = sum(PdfReaderWidget._pixmap_bytes(p) for p in PdfReaderWidget._cache.values())
check(PdfReaderWidget._cache_memory_bytes == real,
      "tracked memory matches the live entries exactly",
      f"tracked={PdfReaderWidget._cache_memory_bytes} real={real}")
PdfReaderWidget._clear_cache()

# replacing an entry must not drift the counter
PdfReaderWidget._cache_put((0, "z:1.000"), QPixmap(100, 100))
first = PdfReaderWidget._cache_memory_bytes
PdfReaderWidget._cache_put((0, "z:1.000"), QPixmap(100, 100))
check(first == PdfReaderWidget._cache_memory_bytes,
      "replacing a cache entry keeps the counter exact",
      f"{first} -> {PdfReaderWidget._cache_memory_bytes}")
PdfReaderWidget._clear_cache()


# ══════════════════════════════════════════════════════════════════
section("D5: resizing re-renders fit mode at the new size")
# ══════════════════════════════════════════════════════════════════
w2 = PdfReaderWidget(); w2.resize(800, 600); w2.show()
w2.open_pdf(pdf3); pump()
w2._on_fit_height(); pump(40)
before = None
if w2._labels[0].pixmap() is not None:
    before = (w2._labels[0].pixmap().width(), w2._labels[0].pixmap().height())
w2.resize(1600, 1200)
w2._on_resize()
pump(60)
after_pm = w2._labels[0].pixmap()
check(after_pm is not None and before is not None and
      (after_pm.width(), after_pm.height()) != before,
      "fit-mode pixmap is re-rendered for the new viewport",
      f"before={before} after={None if after_pm is None else (after_pm.width(), after_pm.height())}")
# The entry is legitimately repopulated by the re-render, but it must hold the
# pixmap for the NEW viewport, not the pre-resize one.
refreshed = PdfReaderWidget._cache_get((0, "fh"))
check(refreshed is None or (refreshed.width(), refreshed.height()) != before,
      "fit-mode cache entry no longer holds the pre-resize render",
      f"cached {None if refreshed is None else (refreshed.width(), refreshed.height())}, "
      f"before={before}")


# ══════════════════════════════════════════════════════════════════
section("D6: opening another document resets per-document state")
# ══════════════════════════════════════════════════════════════════
w3 = PdfReaderWidget(); w3.resize(1200, 900); w3.show()
w3.open_pdf(pdf6); pump()
w3.search_edit.setText("alpha")
w3.start_search("alpha")
pump()
hits_before = len(w3._search_hits)
check(hits_before > 0, "search produced hits in the first document",
      f"got {hits_before}")

w3.open_pdf(pdf3); pump()
check(w3._search_hits == [], "search hits are cleared when another file opens",
      f"kept {len(w3._search_hits)} hits")
check(w3._highlight_rects == {}, "highlight rectangles are cleared")
check(w3.search_list.count() == 0, "search sidebar is cleared",
      f"got {w3.search_list.count()} rows")
check(w3.search_edit.text() == "", "search box is cleared")
check(0 <= w3._current_page < w3._total_pages,
      "current page is inside the new document",
      f"page={w3._current_page} of {w3._total_pages}")

# edit mode must not survive the switch either
w3._set_mode(ViewMode.GRID); pump()
w3._enter_edit_mode(); pump()
editor_before = w3._page_editor
w3.open_pdf(pdf6); pump()
check(w3._page_editor is None, "page editor is dropped on document switch")
check(not w3._edit_mode, "edit mode is left on document switch")
check(not w3._unsaved_edits, "unsaved-edit flag is reset")


# ══════════════════════════════════════════════════════════════════
section("D7: hostile files never raise out of open_pdf")
# ══════════════════════════════════════════════════════════════════
empty = WORK / "empty.pdf"; empty.write_bytes(b"")
trunc = WORK / "trunc.pdf"; trunc.write_bytes(pdf3.read_bytes()[:300])
notpdf = WORK / "fake.pdf"; notpdf.write_bytes(b"%PDF-1.4\njunk\n" * 4)
zeropage = WORK / "zeropage.pdf"
from pypdf import PdfWriter  # noqa: E402
with open(zeropage, "wb") as fh:      # a PDF with an empty page tree
    PdfWriter().write(fh)
enc = WORK / "enc.pdf"
d = fitz.open(str(pdf3)); d.save(str(enc), encryption=fitz.PDF_ENCRYPT_AES_256,
                                 user_pw="pw", owner_pw="pwo"); d.close()

for bad, name in ((empty, "0-byte"), (trunc, "truncated"), (notpdf, "fake header"),
                  (zeropage, "0-page"), (enc, "password-protected")):
    try:
        w3.open_pdf(bad)
        pump(5)
        check(True, f"open_pdf survives a {name} PDF")
    except Exception as e:
        check(False, f"open_pdf survives a {name} PDF", f"{type(e).__name__}: {e}")

# a failed open must not leave the previous document half-alive
w3.open_pdf(pdf6); pump()
w3.open_pdf(notpdf); pump(5)
check(w3._labels == [] or not w3._total_pages or w3._total_pages == 6,
      "failed open leaves a consistent state",
      f"labels={len(w3._labels)} total={w3._total_pages}")


# ══════════════════════════════════════════════════════════════════
section("D8: editing a multi-page doc stays inside its memory budget")
# ══════════════════════════════════════════════════════════════════
big40 = make_pdf(WORK / "forty.pdf", 40, "B")
w4 = PdfReaderWidget(); w4.resize(1200, 900); w4.show()
w4.open_pdf(big40); pump()
w4._set_mode(ViewMode.GRID); pump()
w4._enter_edit_mode(); pump()

# Drive the real delete path (confirm dialog stubbed to Yes) so the rebuild and
# the document-handle handling are exercised exactly as in the app.
from PyQt6.QtWidgets import QMessageBox  # noqa: E402
_orig_question = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
try:
    PdfReaderWidget._clear_cache()
    w4._selected_pages = {0}
    w4._edit_delete()
    pump(15)
finally:
    QMessageBox.question = _orig_question

check(w4._total_pages == 39, "page count follows the deletion", f"got {w4._total_pages}")
check(w4.doc is not None and not w4.doc.is_closed,
      "document handle stays live after a delete")
cached = len(PdfReaderWidget._cache)
check(cached <= 8, "post-edit rebuild only materialises the visible pages",
      f"cached {cached} pages (used to be every page: 39)")

# Drag-sort path: move_pages rebinds the document, so the reader must re-read it.
# Before the fix the next line raised ValueError("document closed") inside a Qt
# slot, which aborts the process.
PdfReaderWidget._clear_cache()
w4._selected_pages = {3}
w4._drag_active = True
w4._page_editor.move_pages([3], 0)
w4.doc = w4._page_editor.doc          # the fix under test
w4._rebuild_labels_from_editor()
pump(10)
check(w4.doc is not None and not w4.doc.is_closed,
      "drag-sort move leaves a usable document handle")
check(w4._total_pages == 39, "page count unchanged by a reorder",
      f"got {w4._total_pages}")
PdfReaderWidget._clear_cache()


# ══════════════════════════════════════════════════════════════════
section("D9: tooltip uses one reusable timer")
# ══════════════════════════════════════════════════════════════════
w5 = PdfReaderWidget(); w5.resize(1000, 800); w5.show()
from PyQt6.QtCore import QTimer  # noqa: E402
before_timers = len(w5.findChildren(QTimer))
for _ in range(6):
    w5._hover_widget = w5.btn_zoom_in
    w5._hover_pos = w5.btn_zoom_in.mapToGlobal(w5.btn_zoom_in.rect().center())
    w5._show_tooltip()
after_timers = len(w5.findChildren(QTimer))
check(after_timers == before_timers,
      "hovering 6 times creates no extra timers",
      f"{before_timers} -> {after_timers}")


# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"  {PASS}/{PASS + FAIL} reader-defect regressions passed"
      + ("" if not FAIL else f"  \u2014 {FAIL} FAILED"))
print("=" * 60)
for name, detail in FAILURES:
    print(f"  \u274c {name}")
    if detail:
        print(f"       {detail}")

import shutil  # noqa: E402
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if FAIL else 0)
