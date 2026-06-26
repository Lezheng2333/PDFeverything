"""Clean single-page PDF reader widget — minimal UI, maximum page real estate."""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

ZOOM_MODES = {
    "fit_width": 0,
    "fit_page": 1,
    "100%": 1.0,
    "150%": 1.5,
    "200%": 2.0,
    "300%": 3.0,
}

# DPI base — 72 is PDF-native. Higher = sharper but slower render.
BASE_DPI = 72


class PdfReaderWidget(QWidget):
    """A clean PDF reader. Embed as a tab in any QTabWidget."""

    document_changed = pyqtSignal(str)  # emits filename

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Optional = None       # fitz.Document
        self._path: Optional[Path] = None
        self._current_page = 0          # 0-based
        self._total_pages = 0
        self._zoom_mode = "fit_width"   # str key or float multiplier
        self._custom_zoom = 1.0
        self._base_dpi = 144            # 144 DPI = sharp on retina screens
        self._toolbar_visible = True
        self._init_ui()

    # ── UI Construction ───────────────────────────────

    def _init_ui(self):
        self.setStyleSheet("background-color: #2c2c2c;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Toolbar ──
        self.toolbar = QWidget()
        self.toolbar.setStyleSheet(
            "QWidget { background: #1e1e1e; border-bottom: 1px solid #3a3a3a; }"
            "QPushButton { color: #ccc; background: #333; border: 1px solid #555; "
            "border-radius: 4px; padding: 4px 10px; font-size: 13px; }"
            "QPushButton:hover { background: #444; }"
            "QPushButton:pressed { background: #555; }"
            "QPushButton:disabled { color: #555; }"
            "QLineEdit { color: #fff; background: #2a2a2a; border: 1px solid #555; "
            "border-radius: 4px; padding: 3px 6px; font-size: 13px; max-width: 50px; }"
            "QComboBox { color: #ccc; background: #333; border: 1px solid #555; "
            "border-radius: 4px; padding: 3px 8px; font-size: 13px; }"
            "QComboBox:hover { background: #444; }"
            "QLabel { color: #999; font-size: 13px; }"
        )
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(8, 6, 8, 6)
        tb_layout.setSpacing(8)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(36)
        self.btn_prev.setToolTip("Previous page (←)")
        self.btn_prev.clicked.connect(self.prev_page)
        tb_layout.addWidget(self.btn_prev)

        self.page_input = QLineEdit("1")
        self.page_input.setFixedWidth(48)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self._on_page_input)
        tb_layout.addWidget(self.page_input)

        self.label_total = QLabel("/ 1")
        tb_layout.addWidget(self.label_total)

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(36)
        self.btn_next.setToolTip("Next page (→)")
        self.btn_next.clicked.connect(self.next_page)
        tb_layout.addWidget(self.btn_next)

        tb_layout.addSpacing(16)

        self.btn_fit_width = QPushButton("Fit Width")
        self.btn_fit_width.setToolTip("Fit page width to viewport")
        self.btn_fit_width.clicked.connect(self.zoom_fit_width)
        tb_layout.addWidget(self.btn_fit_width)

        self.btn_fit_page = QPushButton("Fit Page")
        self.btn_fit_page.setToolTip("Fit entire page in viewport")
        self.btn_fit_page.clicked.connect(self.zoom_fit_page)
        tb_layout.addWidget(self.btn_fit_page)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["100%", "150%", "200%", "300%"])
        self.zoom_combo.setCurrentIndex(-1)
        self.zoom_combo.setToolTip("Zoom level")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_combo)
        tb_layout.addWidget(self.zoom_combo)

        tb_layout.addStretch()

        self.label_filename = QLabel("")
        self.label_filename.setStyleSheet("color: #888;")
        tb_layout.addWidget(self.label_filename)

        main_layout.addWidget(self.toolbar)

        # ── Page display ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: #2c2c2c; border: none; }"
            "QScrollBar:vertical { background: #1e1e1e; width: 10px; }"
            "QScrollBar::handle:vertical { background: #555; border-radius: 4px; "
            "min-height: 30px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar:horizontal { background: #1e1e1e; height: 10px; }"
            "QScrollBar::handle:horizontal { background: #555; border-radius: 4px; "
            "min-width: 30px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )
        self.scroll_area.setWidgetResizable(False)

        self.page_label = QLabel("")
        self.page_label.setStyleSheet(
            "QLabel { background: white; border: none; }")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.page_label)

        main_layout.addWidget(self.scroll_area, 1)

        # ── Welcome placeholder ──
        self._show_placeholder()

        # Keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    # ── Public API ────────────────────────────────────

    def open_pdf(self, path: Path) -> None:
        """Open a PDF file and display its first page."""
        import fitz
        try:
            self.doc = fitz.open(path)
        except Exception as e:
            self._show_placeholder(f"Cannot open: {e}")
            return

        # Handle encrypted PDFs
        if self.doc.is_encrypted:
            # Try empty password first
            if not self.doc.authenticate(""):
                self.doc.close()
                self.doc = None
                self._show_placeholder("This PDF is password-protected.")
                return

        self._path = path
        self._total_pages = len(self.doc)
        self._current_page = 0
        self._zoom_mode = "fit_width"
        self._update_nav_ui()
        self._render_current()
        self.label_filename.setText(path.name)
        self.document_changed.emit(str(path))
        self.setFocus()

    def close_document(self) -> None:
        """Close the current document."""
        if self.doc:
            self.doc.close()
            self.doc = None
        self._path = None
        self._total_pages = 0
        self._current_page = 0
        self.page_label.clear()
        self.label_filename.clear()
        self._update_nav_ui()
        self._show_placeholder()

    def go_to_page(self, num: int) -> None:
        """Go to a specific page (1-based)."""
        if not self.doc:
            return
        num = max(1, min(num, self._total_pages))
        if num - 1 != self._current_page:
            self._current_page = num - 1
            self._render_current()
            self._update_nav_ui()

    def next_page(self) -> None:
        if self.doc and self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._render_current()
            self._update_nav_ui()

    def prev_page(self) -> None:
        if self.doc and self._current_page > 0:
            self._current_page -= 1
            self._render_current()
            self._update_nav_ui()

    def first_page(self) -> None:
        self.go_to_page(1)

    def last_page(self) -> None:
        self.go_to_page(self._total_pages)

    # ── Zoom ──────────────────────────────────────────

    def zoom_fit_width(self) -> None:
        self._zoom_mode = "fit_width"
        self.zoom_combo.setCurrentIndex(-1)
        self._render_current()

    def zoom_fit_page(self) -> None:
        self._zoom_mode = "fit_page"
        self.zoom_combo.setCurrentIndex(-1)
        self._render_current()

    def set_zoom(self, factor: float) -> None:
        """Set fixed zoom (e.g. 1.5 = 150%)."""
        self._zoom_mode = factor
        text = f"{int(factor*100)}%"
        idx = self.zoom_combo.findText(text)
        self.zoom_combo.setCurrentIndex(idx if idx >= 0 else -1)
        self._render_current()

    # ── Internal rendering ────────────────────────────

    def _render_current(self) -> None:
        """Render the current page at the current zoom and update display."""
        if not self.doc or self._current_page < 0:
            return

        import fitz
        page = self.doc[self._current_page]
        viewport_w = self.scroll_area.viewport().width() - 4
        viewport_h = self.scroll_area.viewport().height() - 4

        if viewport_w <= 0:
            viewport_w = 800
        if viewport_h <= 0:
            viewport_h = 600

        page_rect = page.rect
        pw, ph = page_rect.width, page_rect.height

        if self._zoom_mode == "fit_width":
            zoom = viewport_w / pw
        elif self._zoom_mode == "fit_page":
            zoom = min(viewport_w / pw, viewport_h / ph)
        else:
            zoom = self._zoom_mode  # fixed float

        # Render at scaled DPI
        render_dpi = BASE_DPI * zoom
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, dpi=BASE_DPI)

        # Convert to QPixmap
        qimg = QImage(pix.samples, pix.width, pix.height,
                      pix.stride, QImage.Format.Format_RGB888)

        # QImage from PyMuPDF samples is typically RGB, but may need BGR swap
        # PyMuPDF pix.samples are in RGB order, but QImage.Format_RGB888 expects
        # the native byte order. On little-endian, QImage stores RGB as BGR.
        # We swap to avoid blue-tinted pages.
        qimg = qimg.rgbSwapped()

        pixmap = QPixmap.fromImage(qimg)
        self.page_label.setPixmap(pixmap)
        self.page_label.resize(pixmap.size())

    def _show_placeholder(self, text: str = "Open a PDF to start reading") -> None:
        """Show a centered placeholder label instead of a page."""
        self.page_label.setPixmap(QPixmap())
        self.page_label.setText(text)
        self.page_label.setStyleSheet(
            "QLabel { color: #888; font-size: 20px; background: transparent; }")
        self.page_label.resize(self.scroll_area.viewport().size())

    def _update_nav_ui(self) -> None:
        """Sync navigation UI with current state."""
        self.page_input.setText(str(self._current_page + 1))
        self.label_total.setText(f"/ {self._total_pages}")
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < self._total_pages - 1)
        self.page_input.setEnabled(self._total_pages > 0)

    # ── Slots ─────────────────────────────────────────

    def _on_page_input(self) -> None:
        """User typed a page number and pressed Enter."""
        try:
            num = int(self.page_input.text())
            self.go_to_page(num)
        except ValueError:
            self._update_nav_ui()  # reset to current

    def _on_zoom_combo(self, text: str) -> None:
        if text in ZOOM_MODES and isinstance(ZOOM_MODES[text], float):
            self.set_zoom(ZOOM_MODES[text])

    # ── Keyboard / Mouse ──────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_Up:
            self.prev_page()
        elif event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_Down:
            self.next_page()
        elif event.key() == Qt.Key.Key_Home:
            self.first_page()
        elif event.key() == Qt.Key.Key_End:
            self.last_page()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.set_zoom(min(4.0, (self._zoom_mode if isinstance(self._zoom_mode, float) else 1.0) + 0.25))
            else:
                self.set_zoom(max(0.25, (self._zoom_mode if isinstance(self._zoom_mode, float) else 1.0) - 0.25))
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event) -> None:
        """Re-render on window resize when in fit_width/fit_page mode."""
        super().resizeEvent(event)
        if self.doc and self._zoom_mode in ("fit_width", "fit_page"):
            self._render_current()

    # ── Public helpers for MainWindow integration ─────

    def has_document(self) -> bool:
        return self.doc is not None

    def current_path(self) -> Optional[Path]:
        return self._path

    def retranslate_ui(self) -> None:
        """Called by MainWindow when language changes."""
        # Under glass: minimal UI text changes with i18n — tr() calls are
        # done by MainWindow._retranslate_ui() which sets tooltips and alt text.
        pass
