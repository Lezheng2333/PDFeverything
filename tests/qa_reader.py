"""QA: systematic crash + feature test for PdfReaderWidget."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
import fitz

app = QApplication(sys.argv)
from gui.pdf_reader_widget import PdfReaderWidget, ViewMode

results = []
def test(name, cond):
    results.append((name, cond))
    print(f"  {'✅' if cond else '❌'} {name}")

# ── helpers ──
def make_pdf(pages, path):
    d = fitz.open()
    for i in range(pages):
        p = d.new_page()
        p.insert_text(fitz.Point(72,72), f"Page {i+1}", fontsize=14)
        p.draw_rect(fitz.Rect(72,200,400,300), color=(1,i%2,0), fill=(1,i%2,0))
    d.save(str(path)); d.close()

make_pdf(3, "/tmp/qa_3p.pdf")
make_pdf(1, "/tmp/qa_1p.pdf")

# ═══════════ QA1: No document state ═══════════
print("\n═══ QA1: Empty reader guards ═══")
reader = PdfReaderWidget()
reader.resize(900, 700)
reader.show()
app.processEvents()
# Let _try_show_welcome timer fire (200ms retry)
time.sleep(0.5)
app.processEvents()
# Manually trigger if timer didn't work (headless timing issue)
if not reader._welcome:
    reader._try_show_welcome()
time.sleep(0.1)
app.processEvents()
test("welcome visible after show", reader._welcome is not None and reader._welcome.isVisible())
test("has_document = False", not reader.has_document())

# Click all buttons — must not crash
try:
    reader.btn_zoom_out.click()
    reader.btn_zoom_in.click()
    reader._on_fit_width()
    reader._on_fit_height()
    reader._adjust_zoom(5)
    reader._on_zoom_edit()
    test("scale_all no-op on empty labels", True)
except Exception as e:
    test(f"zoom buttons: {e}", False)

try:
    reader._set_zoom_pct(150)
    test("set_zoom_pct no-op on no doc", True)
except Exception as e:
    test(f"set_zoom_pct: {e}", False)

try:
    reader._on_scrollbar_changed(500)
    test("scrollbar no-op on no doc", True)
except Exception as e:
    test(f"scrollbar: {e}", False)

# ═══════════ QA2: Open + Scroll + Close ═══════════
print("\n═══ QA2: Open 3p → scroll → close → re-open ═══")
reader.open_pdf(Path("/tmp/qa_3p.pdf"))
app.processEvents(); time.sleep(0.5)
test("3 pages loaded", reader._total_pages == 3)
test("scroll labels visible", len(reader._labels) == 3 and reader._labels[0].isVisible())

# Go to page 3 via go_to_page
reader.go_to_page(3)
test("go_to_page(3)", reader._current_page == 2)

# Next page (should clamp)
reader.next_page()
test("next_page clamps at last", reader._current_page == 2)

# Prev page
reader.prev_page()
test("prev_page", reader._current_page == 1)

# Close
reader.close_document()
app.processEvents(); time.sleep(0.3)
test("close_document: doc=None", reader.doc is None)
test("close_document: labels=[]", len(reader._labels) == 0)
test("close_document: welcome shown", reader._welcome is not None)

# Re-open
reader.open_pdf(Path("/tmp/qa_3p.pdf"))
app.processEvents(); time.sleep(0.3)
test("re-open works", reader._total_pages == 3)

# ═══════════ QA3: Zoom pipe ═══════════
print("\n═══ QA3: Two-pass zoom ═══")
reader._set_zoom_pct(100)
app.processEvents()
test("zoom 100% text set", reader.zoom_edit.text() == "100")

reader._set_zoom_pct(200)
app.processEvents()
test("zoom 200% text set", reader.zoom_edit.text() == "200")

reader._set_zoom_pct(100)
app.processEvents()
test("zoom back to 100%", reader.zoom_edit.text() == "100")

# Fit buttons
reader._on_fit_width()
test("fit_width active", reader.btn_fit_width.isChecked())

reader._on_fit_height()
test("fit_height active", reader.btn_fit_height.isChecked())

# Zoom via edit
reader.zoom_edit.setText("75")
reader._on_zoom_edit()
test("edit zoom 75%", reader.zoom_edit.text() == "75")

reader.zoom_edit.setText("")
reader._on_zoom_edit()
test("empty input restored", reader.zoom_edit.text() != "")

reader.zoom_edit.setText("abc")
reader._on_zoom_edit()
test("invalid input restored", reader.zoom_edit.text() != "abc")

reader.zoom_edit.setText("999")
reader._on_zoom_edit()
test(">300 clamped to 300", reader.zoom_edit.text() == "300")

# ═══════════ QA4: View modes ═══════════
print("\n═══ QA4: View modes ═══")
reader._set_mode(ViewMode.GRID)
app.processEvents()
test("grid mode active", reader.btn_grid.isChecked())
test("grid shows all 3", all(l.isVisible() for l in reader._labels))

reader._set_mode(ViewMode.SCROLL)
app.processEvents()
test("scroll mode active", reader.btn_scroll.isChecked())

# ═══════════ QA5: Grid dbl-click → scroll ═══════════
print("\n═══ QA5: Grid dbl-click ═══")
make_pdf(6, "/tmp/qa_6p.pdf")
reader.close_document()
app.processEvents(); time.sleep(0.2)
reader.open_pdf(Path("/tmp/qa_6p.pdf"))
app.processEvents(); time.sleep(0.3)
reader._set_mode(ViewMode.GRID)
app.processEvents()
test("grid 6 pages visible", reader._view_mode == ViewMode.GRID)
# Simulate dbl-click on page 3
reader._on_grid_dbl_click(2)
app.processEvents()
test("dbl-click switches to scroll", reader._view_mode == ViewMode.SCROLL)
test("dbl-click jump to page 3", reader._current_page == 2)
test("dbl-click fit_height", reader._zoom_mode == "fit_height")

# ═══════════ QA6: Single-page PDF edge case ═══════════
print("\n═══ QA6: 1-page PDF ═══")
reader.close_document()
app.processEvents(); time.sleep(0.2)
reader.open_pdf(Path("/tmp/qa_1p.pdf"))
app.processEvents(); time.sleep(0.2)
test("1p: total=1", reader._total_pages == 1)
test("1p: prev disabled", not reader.btn_prev.isEnabled())
test("1p: next disabled", not reader.btn_next.isEnabled())
reader._set_mode(ViewMode.GRID)
app.processEvents()
reader._on_grid_dbl_click(0)
app.processEvents()
test("1p grid dbl-click no crash", reader._view_mode == ViewMode.SCROLL)

# ═══════════ QA7: Close → welcome → re-click ═══════════
print("\n═══ QA7: Close + welcome stability ═══")
reader.close_document()
app.processEvents(); time.sleep(0.3)
test("welcome shown after close", reader._welcome is not None and reader._welcome.isVisible())
# Close again (should not crash)
reader.close_document()
app.processEvents()
test("double close no crash", True)
# Re-open
reader.open_pdf(Path("/tmp/qa_3p.pdf"))
app.processEvents(); time.sleep(0.2)
test("re-open after double close", reader._total_pages == 3)
reader.close_document()
app.processEvents(); time.sleep(0.2)

# ═══════════ QA8: _sharp_render with no doc = no crash ═══════════
print("\n═══ QA8: Deferred timer safety ═══")
reader._pending_zoom_pct = 150
reader._sharp_render()  # no doc — must not crash
test("sharp_render with no doc", True)

app.quit()

# ── summary ──
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"\n{'='*50}")
print(f"  {passed}/{total} passed" + (" ✅" if passed==total else " ❌"))
print(f"{'='*50}")
sys.exit(0 if passed == total else 1)
