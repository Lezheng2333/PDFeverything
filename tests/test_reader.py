"""Comprehensive reader tests — run with: python tests/test_reader.py"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
import fitz

app = QApplication(sys.argv)

from gui.pdf_reader_widget import PdfReaderWidget, ViewMode

passed, failed = 0, 0

def test(assertion, name, detail=""):
    global passed, failed
    if assertion:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}" + (f": {detail}" if detail else ""))

# ── Helpers ─────────────────────────────────────────────

def make_test_pdf(pages: int, with_colors: bool = True) -> Path:
    doc = fitz.open()
    colors = [(1, 0, 0), (0, 0, 1), (0, 1, 0), (1, 0, 1), (0, 0, 0),
              (1, 1, 0), (0, 1, 1), (0.5, 0.5, 0.5)]
    for i in range(pages):
        page = doc.new_page()
        text = f"Page {i+1} — Test"
        page.insert_text(fitz.Point(72, 72), text, fontsize=18, fontname="Helvetica")
        if with_colors and i < len(colors):
            r, g, b = colors[i]
            page.draw_rect(fitz.Rect(72, 120, 400, 200),
                           color=(r, g, b), fill=(r, g, b))
    out = Path(f"/tmp/test_reader_{pages}p.pdf")
    doc.save(str(out))
    doc.close()
    return out


# ═══════════ Test 1: Open & Render ═══════════
print("\n═══ Test 1: Open & Render ═══")
pdf_3p = make_test_pdf(3)
w = PdfReaderWidget()
w.resize(1200, 900)
w.show()
app.processEvents()

w.open_pdf(pdf_3p)
app.processEvents(); time.sleep(0.3)

test(w._total_pages == 3, "3-page PDF opens with correct page count")
test(w.has_document(), "has_document() returns True")
test(w.current_path() == pdf_3p, "current_path() returns correct path")
test(w.label_filename.text() == "test_reader_3p.pdf", "filename displayed in toolbar")
test(w._zoom_mode == 1.0, f"default zoom is 100% (got {w._zoom_mode})")
test(w.zoom_edit.text() == "100", f"zoom_edit shows 100 (got {w.zoom_edit.text()})")
test(len(w._labels) == 3, f"3 labels created (got {len(w._labels)})")
test(w._labels[0].isVisible(), "first label is visible (Scroll mode)")
test(w._labels[0].pixmap() is not None and not w._labels[0].pixmap().isNull(),
     "first page has valid pixmap")

# Color check: page 1 should have red rect
img0 = w._labels[0].pixmap().toImage()
red_pixel = img0.pixelColor(200, 150)
test(red_pixel.red() > 120 and red_pixel.green() < 50 and red_pixel.blue() < 50,
     f"Red rect is actually red (R{red_pixel.red()} G{red_pixel.green()} B{red_pixel.blue()})")

# ═══════════ Test 2: View Mode Switching ═══════════
print("\n═══ Test 2: View Mode Switching ═══")

# Switch to Grid
w._set_mode(ViewMode.GRID)
app.processEvents()
test(w._view_mode == ViewMode.GRID, "Switch to GRID mode")
test(w.btn_grid.isChecked(), "Grid button is checked")
test(not w.btn_scroll.isChecked(), "Scroll button unchecked")

# Switch back to Scroll
w._set_mode(ViewMode.SCROLL)
app.processEvents()
test(w._view_mode == ViewMode.SCROLL, "Switch back to SCROLL mode")
test(w.btn_scroll.isChecked(), "Scroll button is checked")
test(not w.btn_grid.isChecked(), "Grid button unchecked")

# ═══════════ Test 3: Navigation (Scroll mode) ═══════════
print("\n═══ Test 3: Navigation ═══")

w.go_to_page(1)
test(w._current_page == 0, "go_to_page(1) → current_page=0")

w.next_page()
test(w._current_page == 1, "next_page() → page 2")

w.next_page()
test(w._current_page == 2, "next_page() → page 3")

w.next_page()  # should clamp
test(w._current_page == 2, "next_page() at last page clamps")

w.prev_page()
test(w._current_page == 1, "prev_page() → page 2")

w.first_page()
test(w._current_page == 0, "first_page() → page 1")

w.last_page()
test(w._current_page == 2, "last_page() → page 3")

# Go beyond bounds
w.go_to_page(999)
test(w._current_page == 2, "go_to_page(999) clamps to last page")
w.go_to_page(-5)
test(w._current_page == 0, "go_to_page(-5) clamps to first page")

# ═══════════ Test 4: Zoom ═══════════
print("\n═══ Test 4: Zoom ═══")

w._set_zoom_pct(150)
app.processEvents()
test(w._zoom_mode == 1.5, f"set_zoom 150% → _zoom_mode={w._zoom_mode}")
test(w.zoom_edit.text() == "150", f"zoom_edit shows 150 (got {w.zoom_edit.text()})")
test(not w.btn_fit_width.isChecked(), "Fit W unchecked after manual zoom")
test(not w.btn_fit_height.isChecked(), "Fit H unchecked after manual zoom")

w._set_zoom_pct(200)
test(w._zoom_mode == 2.0, "set_zoom 200%")
test(w.zoom_edit.text() == "200", "zoom_edit shows 200")

# Fit Width
w._on_fit_width()
app.processEvents()
test(w._zoom_mode == "fit_width", "fit_width mode active")
test(w.btn_fit_width.isChecked(), "Fit W button checked")

# Fit Height
w._on_fit_height()
app.processEvents()
test(w._zoom_mode == "fit_height", "fit_height mode active")
test(w.btn_fit_height.isChecked(), "Fit H button checked")

# Adjust zoom via buttons
w._adjust_zoom(+5)
test(w._zoom_mode != "fit_height", "_adjust_zoom exits fit mode")

# Zoom via edit field
w._set_zoom_pct(100)
w.zoom_edit.setText("75")
w._on_zoom_edit()
test(w.zoom_edit.text() == "75", "edit zoom 75%")

w.zoom_edit.setText("")
w._on_zoom_edit()
test(w.zoom_edit.text() != "", "empty input restores previous value")

w.zoom_edit.setText("abc")
w._on_zoom_edit()
test(w.zoom_edit.text() != "abc", "invalid input restores value")

w.zoom_edit.setText("999")
w._on_zoom_edit()
test(w.zoom_edit.text() == "300", ">300 clamped to 300")

# ═══════════ Test 5: Grid Grid dbl-click ═══════════
print("\n═══ Test 5: Grid dbl-click → Scroll ═══")
pdf_6p = make_test_pdf(6)
w.close_document()
app.processEvents(); time.sleep(0.2)
w.open_pdf(pdf_6p)
app.processEvents(); time.sleep(0.3)

w._set_mode(ViewMode.GRID)
app.processEvents()
test(w._view_mode == ViewMode.GRID, "Grid mode with 6 pages")

# Double-click page 3 → switch to Scroll + Fit Height + jump
w._on_grid_dbl_click(2)  # 0-based = page 3
app.processEvents()
test(w._view_mode == ViewMode.SCROLL, "dbl-click switches to Scroll mode")
test(w._current_page == 2, "dbl-click jumps to page 3")
test(w._zoom_mode == "fit_height", "dbl-click activates fit_height")

# ═══════════ Test 6: Close & Reopen ═══════════
print("\n═══ Test 6: Close & Reopen ═══")
w.close_document()
app.processEvents(); time.sleep(0.3)
test(w.doc is None, "close_document() clears doc")
test(not w.has_document(), "has_document() → False after close")
test(w._total_pages == 0, "total_pages → 0 after close")
test(len(w._labels) == 0, "labels cleared after close")
test(w._welcome is not None and w._welcome.isVisible(), "welcome screen shown after close")

# Reopen
w.open_pdf(pdf_3p)
app.processEvents(); time.sleep(0.3)
test(w.has_document(), "re-open works")
test(w._total_pages == 3, "page count restored after reopen")

# ═══════════ Test 7: Single-page PDF edge cases ═══════════
print("\n═══ Test 7: Single-page PDF ═══")
pdf_1p = make_test_pdf(1)
w.close_document()
app.processEvents(); time.sleep(0.2)
w.open_pdf(pdf_1p)
app.processEvents(); time.sleep(0.2)

test(w._total_pages == 1, "1-page PDF opens")
test(not w.btn_prev.isEnabled(), "Prev disabled on page 1/1")
test(not w.btn_next.isEnabled(), "Next disabled on page 1/1")
test(w.page_label.text() == "1 / 1", f"page_label shows 1/1 (got {w.page_label.text()})")

# Grid mode with 1 page
w._set_mode(ViewMode.GRID)
app.processEvents()
test(True, "Grid mode with 1 page does not crash")

# Double close should not crash
w.close_document()
app.processEvents()
w.close_document()
app.processEvents()
test(True, "Double close_document() does not crash")

# ═══════════ Test 8: Deferred timer safety ═══════════
print("\n═══ Test 8: Deferred timer safety ═══")
# _sharp_render with no doc must not crash
w._pending_zoom_pct = 150
w._sharp_render()
test(True, "_sharp_render with no doc does not crash")

# _cancel_deferred_renders with no doc
w._cancel_deferred_renders()
test(True, "_cancel_deferred_renders does not crash")

# ═══════════ Test 9: Cache LRU ═══════════
print("\n═══ Test 9: LRU Cache ═══")
w.open_pdf(pdf_3p)
app.processEvents(); time.sleep(0.3)

from gui.pdf_reader_widget import PdfReaderWidget as PRW
# After open, 100% base should be cached for all pages
base_hit = all(PRW._cache_get((pi, "z:1.000")) is not None for pi in range(3))
test(base_hit, "100% base cached for all pages after open")

# Zoom to 150% — deferred render should populate cache
w._set_zoom_pct(150)
app.processEvents(); time.sleep(0.5)  # wait for _sharp_render (40ms timer)
# After sharp render, zoom:1.500 should be cached for visible pages (±1)
zhits = sum(1 for pi in range(3) if PRW._cache_get((pi, "z:1.500")) is not None)
test(zhits >= 1, f"zoom 150% cached for at least 1 page (got {zhits} cached)")

# Memory tracking is working
test(PRW._cache_memory_bytes > 0, f"cache memory tracking active ({PRW._cache_memory_bytes} bytes)")

# ═══════════ Test 10: i18n keys ═══════════
print("\n═══ Test 10: i18n ═══")
from gui.i18n import tr
expected_keys = [
    "tab_reader", "reader_scroll", "reader_grid",
    "reader_scroll_tip", "reader_grid_tip",
    "reader_prev", "reader_next",
    "reader_fit_width", "reader_fit_height",
    "reader_fit_width_tip", "reader_fit_height_tip",
    "reader_zoom_out", "reader_zoom_in", "reader_zoom_edit",
    "reader_drop_here", "reader_load_file", "reader_close",
    "reader_open_pdf", "reader_file_filter",
    "reader_encrypted", "reader_cannot_open",
]
for k in expected_keys:
    en = tr(k, lang="en")
    zh = tr(k, lang="zh")
    test(en != k and zh != k, f"i18n key '{k}'", f"EN='{en}', ZH='{zh}'")

w.close_document()
app.quit()

# ── Results ──────────────────────────────────────────────
total = passed + failed
print(f"\n{'='*50}")
print(f"  {passed}/{total} passed" + (" ✅" if passed == total else " ❌"))
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
