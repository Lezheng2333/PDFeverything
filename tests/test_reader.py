"""Comprehensive reader tests — run with: python tests/test_reader.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
import fitz

app = QApplication(sys.argv)

from gui.pdf_reader_widget import PdfReaderWidget, ViewMode

# ── Helpers ─────────────────────────────────────────────

def make_test_pdf(pages: int, with_colors: bool = True) -> Path:
    """Create test PDF with N pages."""
    doc = fitz.open()
    colors = [(1, 0, 0), (0, 0, 1), (0, 1, 0), (1, 0, 1), (0, 0, 0),
              (1, 1, 0), (0, 1, 1), (0.5, 0.5, 0.5)]
    for i in range(pages):
        page = doc.new_page()
        text = f"Page {i+1}" if not with_colors else f"Page {i+1} — Test"
        page.insert_text(fitz.Point(72, 72), text, fontsize=18, fontname="Helvetica")
        if with_colors and i < len(colors):
            r, g, b = colors[i]
            page.draw_rect(fitz.Rect(72, 120, 400, 200),
                           color=(r, g, b), fill=(r, g, b))
            page.insert_text(fitz.Point(80, 160),
                           f"Color ({r},{g},{b})", fontsize=12)
    out = Path(f"/tmp/test_{pages}p.pdf")
    doc.save(str(out))
    doc.close()
    return out

def run_test(name: str, assertion: bool, detail: str = ""):
    mark = "✅" if assertion else "❌"
    print(f"  {mark} {name}" + (f": {detail}" if detail and not assertion else ""))

# ── Test Suite ──────────────────────────────────────────

passed, failed = 0, 0

def test(assertion, name, detail=""):
    global passed, failed
    if assertion:
        passed += 1
    else:
        failed += 1
    run_test(name, assertion, detail)

# ── Test 1: Open & Render ─────────────────────────────────
print("\n═══ Test 1: Open & Render ═══")
pdf_3p = make_test_pdf(3)
w = PdfReaderWidget()
w.resize(1200, 900)

w.open_pdf(pdf_3p)
test(w._total_pages == 3, "3-page PDF opens with correct page count")
test(w.has_document(), "has_document() returns True")
test(w.current_path() == pdf_3p, "current_path() returns correct path")
test(w.label_filename.text() == "test_3p.pdf", "filename displayed in toolbar")

# Check that pages were rendered (scroll mode = default)
layout = w.page_container.layout()
test(layout.count() == 3, f"Scroll mode renders all pages (got {layout.count()})")

# Check first page pixmap is valid
label0 = layout.itemAt(0).widget()
pix0 = label0.pixmap()
test(pix0 is not None and not pix0.isNull(), "First page pixmap is valid")
test(pix0.width() > 200 and pix0.height() > 200, f"Pixmap has reasonable dimensions ({pix0.width()}x{pix0.height()})")

# Check color: page 1 should have red rect
img = pix0.toImage()
red_pixel = img.pixelColor(200, 150)
test(red_pixel.red() > 120 and red_pixel.green() < 50 and red_pixel.blue() < 50,
     f"Red rect is actually red (R{red_pixel.red()} G{red_pixel.green()} B{red_pixel.blue()})")

# ── Test 2: View Mode Switching ─────────────────────────
print("\n═══ Test 2: View Mode Switching ═══")
# Switch to Single
w._set_mode(ViewMode.SINGLE)
test(w._view_mode == ViewMode.SINGLE, "Switch to SINGLE mode")
layout = w.page_container.layout()
test(layout.count() == 1, f"Single mode: 1 page widget (got {layout.count()})")
test(w.btn_single.isChecked(), "Single button is checked")
test(w.nav_widget.isVisible(), "Nav widget visible in Single mode")

# Switch to Grid
w._set_mode(ViewMode.GRID)
test(w._view_mode == ViewMode.GRID, "Switch to GRID mode")
test(w.btn_grid.isChecked(), "Grid button is checked")
test(not w.nav_widget.isVisible(), "Nav widget hidden in Grid mode")

# Switch back to Scroll
w._set_mode(ViewMode.SCROLL)
test(w._view_mode == ViewMode.SCROLL, "Switch back to SCROLL mode")
test(w.btn_scroll.isChecked(), "Scroll button is checked")
test(not w.nav_widget.isVisible(), "Nav widget hidden in Scroll mode")

# ── Test 3: Navigation (Single mode) ────────────────────
print("\n═══ Test 3: Navigation (Single mode) ═══")
w._set_mode(ViewMode.SINGLE)

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

# ── Test 4: Zoom ────────────────────────────────────────
print("\n═══ Test 4: Zoom ═══")
w.zoom_fit_width()
test(w._zoom_mode == "fit_width", "zoom_fit_width() mode set")

w.set_zoom(2.0)
test(w._zoom_mode == 2.0, f"set_zoom(2.0) → {w._zoom_mode}")
test(w.zoom_combo.currentText() == "200%", f"Zoom combo shows 200% (got {w.zoom_combo.currentText()})")

w.set_zoom(1.5)
test(w._zoom_mode == 1.5, "set_zoom(1.5)")
test(w.zoom_combo.currentText() == "150%", f"Zoom combo shows 150% (got {w.zoom_combo.currentText()})")

w.zoom_fit_page()
test(w._zoom_mode == "fit_page", "zoom_fit_page() mode set")

# ── Test 5: Close & Reopen ──────────────────────────────
print("\n═══ Test 5: Close & Reopen ═══")
w.close_document()
test(w.doc is None, "close_document() clears doc")
test(not w.has_document(), "has_document() → False after close")
test(w._total_pages == 0, "total_pages → 0 after close")

# Reopen
w.open_pdf(pdf_3p)
test(w.has_document(), "re-open works")
test(w._total_pages == 3, "page count restored after reopen")

# ── Test 6: Edge Cases ──────────────────────────────────
print("\n═══ Test 6: Edge Cases ═══")

# Single page PDF
pdf_1p = make_test_pdf(1)
w.open_pdf(pdf_1p)
test(w._total_pages == 1, "1-page PDF opens")
w._set_mode(ViewMode.SINGLE)
test(w.btn_prev.isEnabled() == False, "Prev disabled on page 1")
test(w.btn_next.isEnabled() == False, "Next disabled on page 1")

# Empty close when no doc open
w.close_document()
w.close_document()  # double close should not crash
test(True, "Double close_document() does not crash", "always true sanity check")

# ── Test 7: Large PDF (performance) ─────────────────────
print("\n═══ Test 7: Large PDF (20 pages) ═══")
pdf_20p = make_test_pdf(20, with_colors=False)
import time
t0 = time.time()
w.open_pdf(pdf_20p)
elapsed = time.time() - t0
test(w._total_pages == 20, f"20-page PDF opens ({elapsed:.2f}s)")

# Grid mode with 20 pages
w._set_mode(ViewMode.GRID)
test(True, "Grid mode with 20 pages does not crash")

# Scroll mode with 20 pages
w._set_mode(ViewMode.SCROLL)
test(True, "Scroll mode with 20 pages does not crash")

# ── Test 8: I18n keys exist ──────────────────────────────
print("\n═══ Test 8: i18n ═══")
from gui.i18n import tr
expected_keys = [
    "tab_reader", "reader_scroll", "reader_single", "reader_grid",
    "reader_scroll_tip", "reader_single_tip", "reader_grid_tip",
    "reader_prev", "reader_next", "reader_fit_width", "reader_fit_page",
    "reader_zoom_tip", "reader_welcome", "reader_open_pdf", "reader_file_filter",
    "reader_encrypted", "reader_cannot_open",
]
for k in expected_keys:
    en = tr(k, lang="en")
    zh = tr(k, lang="zh")
    test(en != k and zh != k, f"i18n key '{k}'", f"EN='{en}', ZH='{zh}'")

# ── Results ──────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"  {passed} passed, {failed} failed, {passed+failed} total")
print(f"{'='*40}")
sys.exit(0 if failed == 0 else 1)
