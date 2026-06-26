"""Clean PDF reader — 3 viewing modes, bottom toolbar, touchpad, lazy render + cache."""

from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget, QSizePolicy,
)


class ViewMode(Enum):
    SCROLL = "scroll"
    SINGLE = "single"
    GRID = "grid"


RENDER_SCALE = 2  # 2x for retina sharpness
RESIZE_DEBOUNCE_MS = 250  # wait before re-rendering on resize
SCROLL_LAZY_PREFETCH = 5  # pages ahead/behind to pre-render in scroll mode


class _RenderWorker(QObject):
    """Renders pages in background, emits pixmap when done."""
    rendered = pyqtSignal(int, object)  # page_idx, QPixmap

    def __init__(self):
        super().__init__()
        self._pending: list = []

    @pyqtSlot()
    def process(self):
        if not self._pending:
            return
        page_idx, doc_ref, zoom_key, max_w, max_h, force_fit = self._pending.pop(0)
        pixmap = PdfReaderWidget._render_page(doc_ref, page_idx, zoom_key,
                                               max_w, max_h, force_fit)
        self.rendered.emit(page_idx, pixmap)


class PdfReaderWidget(QWidget):
    """Immersive PDF reader. Bottom toolbar, 3 view modes, touchpad, lazy + cached."""

    document_changed = pyqtSignal(str)

    # Cache: (page_idx, zoom_key) -> QPixmap
    _render_cache: dict = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Optional = None
        self._path: Optional[Path] = None
        self._current_page = 0
        self._total_pages = 0
        self._view_mode = ViewMode.SCROLL
        self._zoom_mode = "fit_width"
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._on_resize_timeout)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(100)
        self._scroll_timer.timeout.connect(self._on_scroll_timeout)
        self._init_ui()

    # ═══════════════════════════════════════════════════
    #  UI Construction
    # ═══════════════════════════════════════════════════

    def _init_ui(self):
        self.setStyleSheet("background-color: #2c2c2c;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scroll area ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: #2c2c2c; border: none; }
            QScrollBar:vertical { background: #1e1e1e; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal { background: #1e1e1e; height: 10px; margin: 0; }
            QScrollBar::handle:horizontal { background: #555; border-radius: 4px; min-width: 30px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._scroll_timer.start)

        self.page_container = QWidget()
        self.page_container.setStyleSheet("background: transparent;")
        self.scroll_area.setWidget(self.page_container)

        root.addWidget(self.scroll_area, 1)

        # ── Bottom toolbar ──
        self.toolbar = QWidget()
        self.toolbar.setObjectName("reader_toolbar")
        self.toolbar.setStyleSheet("""
            QWidget#reader_toolbar { background: #1e1e1e; border-top: 1px solid #3a3a3a; }
            QPushButton { color: #ccc; background: #333; border: 1px solid #555;
                border-radius: 4px; padding: 5px 12px; font-size: 13px; }
            QPushButton:hover { background: #444; }
            QPushButton:checked { background: #007aff; color: #fff; border-color: #007aff; }
            QPushButton:disabled { color: #555; background: #2a2a2a; }
            QLineEdit { color: #fff; background: #2a2a2a; border: 1px solid #555;
                border-radius: 4px; padding: 4px 6px; font-size: 13px; max-width: 50px; }
            QComboBox { color: #ccc; background: #333; border: 1px solid #555;
                border-radius: 4px; padding: 4px 8px; font-size: 13px; }
            QComboBox:hover { background: #444; }
            QLabel { color: #999; font-size: 13px; }
        """)
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(10, 6, 10, 6)
        tb.setSpacing(10)

        self.btn_scroll = QPushButton("Scroll")
        self.btn_scroll.setCheckable(True); self.btn_scroll.setChecked(True)
        self.btn_scroll.setToolTip("Continuous scroll (default)")
        self.btn_scroll.clicked.connect(lambda: self._set_mode(ViewMode.SCROLL))

        self.btn_single = QPushButton("Single")
        self.btn_single.setCheckable(True)
        self.btn_single.setToolTip("One page at a time")
        self.btn_single.clicked.connect(lambda: self._set_mode(ViewMode.SINGLE))

        self.btn_grid = QPushButton("Grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setToolTip("2-column thumbnail grid")
        self.btn_grid.clicked.connect(lambda: self._set_mode(ViewMode.GRID))

        tb.addWidget(self.btn_scroll)
        tb.addWidget(self.btn_single)
        tb.addWidget(self.btn_grid)
        tb.addSpacing(20)

        self.nav_widget = QWidget()
        nl = QHBoxLayout(self.nav_widget)
        nl.setContentsMargins(0, 0, 0, 0); nl.setSpacing(6)
        self.btn_prev = QPushButton("◀"); self.btn_prev.setFixedWidth(36)
        self.btn_prev.clicked.connect(self.prev_page)
        self.page_input = QLineEdit("1"); self.page_input.setFixedWidth(48)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self._on_page_input)
        self.label_total = QLabel("/ 1")
        self.btn_next = QPushButton("▶"); self.btn_next.setFixedWidth(36)
        self.btn_next.clicked.connect(self.next_page)
        nl.addWidget(self.btn_prev); nl.addWidget(self.page_input)
        nl.addWidget(self.label_total); nl.addWidget(self.btn_next)
        tb.addWidget(self.nav_widget); tb.addStretch()

        self.btn_fit_width = QPushButton("Fit W")
        self.btn_fit_width.clicked.connect(self.zoom_fit_width)
        self.btn_fit_page = QPushButton("Fit P")
        self.btn_fit_page.clicked.connect(self.zoom_fit_page)
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["100%", "150%", "200%", "300%"])
        self.zoom_combo.setCurrentIndex(-1)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_combo)
        tb.addWidget(self.btn_fit_width); tb.addWidget(self.btn_fit_page)
        tb.addWidget(self.zoom_combo); tb.addStretch()

        self.label_filename = QLabel("")
        self.label_filename.setStyleSheet("color: #777;")
        tb.addWidget(self.label_filename)

        root.addWidget(self.toolbar)

        self._show_welcome()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    # ═══════════════════════════════════════════════════
    #  View Mode
    # ═══════════════════════════════════════════════════

    def _set_mode(self, mode: ViewMode):
        self._view_mode = mode
        self.btn_scroll.setChecked(mode == ViewMode.SCROLL)
        self.btn_single.setChecked(mode == ViewMode.SINGLE)
        self.btn_grid.setChecked(mode == ViewMode.GRID)
        self.nav_widget.setVisible(mode == ViewMode.SINGLE)
        if self.doc:
            self._render_current()

    # ═══════════════════════════════════════════════════
    #  Public API
    # ═══════════════════════════════════════════════════

    def open_pdf(self, path: Path) -> None:
        import fitz
        PdfReaderWidget._render_cache.clear()
        try:
            self.doc = fitz.open(path)
        except Exception as e:
            self._show_welcome(f"Cannot open: {e}")
            return
        if self.doc.is_encrypted:
            if not self.doc.authenticate(""):
                self.doc.close(); self.doc = None
                self._show_welcome("This PDF is password-protected.")
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

    def close_document(self):
        if self.doc:
            self.doc.close(); self.doc = None
        self._path = None; self._total_pages = 0; self._current_page = 0
        PdfReaderWidget._render_cache.clear()
        self._clear_container()
        self._update_nav_ui()
        self.label_filename.clear()
        self._show_welcome()

    def go_to_page(self, num: int):
        if not self.doc: return
        num = max(1, min(num, self._total_pages))
        if num - 1 != self._current_page:
            self._current_page = num - 1
            self._render_current()
            self._update_nav_ui()

    def next_page(self):
        if self.doc and self._current_page < self._total_pages - 1:
            self._current_page += 1; self._render_current(); self._update_nav_ui()

    def prev_page(self):
        if self.doc and self._current_page > 0:
            self._current_page -= 1; self._render_current(); self._update_nav_ui()

    def first_page(self): self.go_to_page(1)
    def last_page(self): self.go_to_page(self._total_pages)

    def zoom_fit_width(self):
        self._zoom_mode = "fit_width"; self.zoom_combo.setCurrentIndex(-1)
        PdfReaderWidget._render_cache.clear()
        if self.doc: self._render_current()

    def zoom_fit_page(self):
        self._zoom_mode = "fit_page"; self.zoom_combo.setCurrentIndex(-1)
        PdfReaderWidget._render_cache.clear()
        if self.doc: self._render_current()

    def set_zoom(self, factor: float):
        self._zoom_mode = factor
        text = f"{int(factor*100)}%"
        idx = self.zoom_combo.findText(text)
        self.zoom_combo.setCurrentIndex(idx if idx >= 0 else -1)
        PdfReaderWidget._render_cache.clear()
        if self.doc: self._render_current()

    # ═══════════════════════════════════════════════════
    #  Zoom key for cache
    # ═══════════════════════════════════════════════════

    def _zoom_key(self, max_w: int, max_h: int, force_fit: bool) -> str:
        """Stable key for caching a page at a given zoom + viewport."""
        if force_fit:
            return f"fit:{max_w}x{max_h}"
        if self._zoom_mode == "fit_width":
            return f"fw:{max_w}"
        if self._zoom_mode == "fit_page":
            return f"fp:{max_w}x{max_h}"
        return f"z:{self._zoom_mode:.2f}"

    # ═══════════════════════════════════════════════════
    #  Static page renderer (used by cache)
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _render_page(doc_ref, page_idx: int, zoom_key: str,
                     max_w: int, max_h: int, force_fit: bool) -> QPixmap:
        import fitz
        page = doc_ref[page_idx]
        pw, ph = page.rect.width, page.rect.height

        # Decode zoom from key
        if zoom_key.startswith("fit:"):
            parts = zoom_key[4:].split("x")
            zoom = min(int(parts[0]) / pw, int(parts[1]) / ph)
        elif zoom_key.startswith("fw:"):
            zoom = int(zoom_key[3:]) / pw
        elif zoom_key.startswith("fp:"):
            parts = zoom_key[3:].split("x")
            zoom = min(int(parts[0]) / pw, int(parts[1]) / ph)
        elif zoom_key.startswith("z:"):
            zoom = float(zoom_key[2:])
        else:
            zoom = max_w / pw

        mat = fitz.Matrix(zoom * RENDER_SCALE, zoom * RENDER_SCALE)
        pix = page.get_pixmap(matrix=mat)
        qimg = QImage(pix.samples, pix.width, pix.height,
                      pix.stride, QImage.Format.Format_RGB888)
        tw = max(1, int(pix.width / RENDER_SCALE))
        th = max(1, int(pix.height / RENDER_SCALE))
        from PyQt6.QtCore import Qt as QtCore
        return QPixmap.fromImage(qimg).scaled(
            tw, th,
            QtCore.AspectRatioMode.IgnoreAspectRatio,
            QtCore.TransformationMode.SmoothTransformation,
        )

    # ═══════════════════════════════════════════════════
    #  Render orchestration
    # ═══════════════════════════════════════════════════

    def _render_current(self):
        if not self.doc: return
        if self._view_mode == ViewMode.SCROLL:
            self._render_scroll()
        elif self._view_mode == ViewMode.SINGLE:
            self._render_single()
        elif self._view_mode == ViewMode.GRID:
            self._render_grid()

    def _viewport_size(self):
        vp = self.scroll_area.viewport()
        w = vp.width() - 4 if vp.width() > 0 else 800
        h = vp.height() - 4 if vp.height() > 0 else 600
        return w, h

    def _get_or_render(self, page_idx: int, max_w: int, max_h: int,
                        force_fit: bool = False) -> QPixmap:
        key = (page_idx, self._zoom_key(max_w, max_h, force_fit))
        if key in PdfReaderWidget._render_cache:
            return PdfReaderWidget._render_cache[key]
        pixmap = PdfReaderWidget._render_page(
            self.doc, page_idx, key[1], max_w, max_h, force_fit)
        PdfReaderWidget._render_cache[key] = pixmap
        return pixmap

    def _make_label(self, pixmap: QPixmap,
                     extra_style: str = "background: white;",
                     tooltip: str = "") -> QLabel:
        label = QLabel()
        label.setPixmap(pixmap)
        label.setFixedSize(pixmap.size())
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"QLabel {{ {extra_style} }}")
        if tooltip:
            label.setToolTip(tooltip)
        return label

    # ═══════════════════════════════════════════════════
    #  3 render modes
    # ═══════════════════════════════════════════════════

    def _render_scroll(self):
        """Scroll: stack labels vertically with absolute positioning."""
        vw, vh = self._viewport_size()
        self._clear_container()
        spacing = 10; margin = 20
        y = margin
        max_w = 0
        for pi in range(self._total_pages):
            pix = self._get_or_render(pi, vw, 9999)
            label = self._make_label(pix)
            label.setParent(self.page_container)
            label.move(margin, y)
            label.show()
            y += pix.height() + spacing
            max_w = max(max_w, pix.width())
        total_w = max_w + 2 * margin
        total_h = y - spacing + margin
        self.page_container.setFixedSize(total_w, total_h)
        self._update_nav_ui()

    def _render_single(self):
        vw, vh = self._viewport_size()
        self._clear_container()
        pix = self._get_or_render(self._current_page, vw, 9999)
        label = self._make_label(pix)
        label.setParent(self.page_container)
        label.move(0, 0)
        label.show()
        self.page_container.setFixedSize(pix.width(), pix.height())

    def _render_grid(self):
        vw, vh = self._viewport_size()
        self._clear_container()
        COLS = 2
        margin = 20; spacing = 12
        thumb_w = max(80, (vw - 2*margin - (COLS-1)*spacing) // COLS)
        thumb_h = int(thumb_w * 1.414)

        for pi in range(self._total_pages):
            pix = self._get_or_render(pi, thumb_w, thumb_h, force_fit=True)
            label = self._make_label(pix,
                                      extra_style="background: white; border: 1px solid #555;",
                                      tooltip=f"Page {pi + 1}")
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            col = pi % COLS; row = pi // COLS
            x = margin + col * (thumb_w + spacing)
            y = margin + row * (thumb_h + spacing)
            label.setParent(self.page_container)
            label.move(x, y)
            label.show()
            pidx = pi
            label.mousePressEvent = lambda ev, p=pidx: self._on_grid_thumb_click(p)

        rows = (self._total_pages + COLS - 1) // COLS
        total_w = 2*margin + COLS*thumb_w + (COLS-1)*spacing
        total_h = 2*margin + rows*thumb_h + (rows-1)*spacing
        self.page_container.setFixedSize(total_w, total_h)

    # ═══════════════════════════════════════════════════
    #  Slots
    # ═══════════════════════════════════════════════════

    def _on_scroll_timeout(self):
        """Scroll position changed — could be used for lazy loading."""
        pass  # all pages are cached on first render, scroll is instant

    def _on_resize_timeout(self):
        if self.doc:
            PdfReaderWidget._render_cache.clear()
            self._render_current()

    def _on_page_input(self):
        try:
            self.go_to_page(int(self.page_input.text()))
        except ValueError:
            self._update_nav_ui()

    def _on_zoom_combo(self, text: str):
        factor = {"100%": 1.0, "150%": 1.5, "200%": 2.0, "300%": 3.0}.get(text)
        if factor:
            self.set_zoom(factor)

    def _on_grid_thumb_click(self, page_idx: int):
        self._current_page = page_idx
        self._set_mode(ViewMode.SINGLE)

    def _update_nav_ui(self):
        self.page_input.setText(str(self._current_page + 1))
        self.label_total.setText(f"/ {self._total_pages}")
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < self._total_pages - 1)
        self.page_input.setEnabled(self._total_pages > 0)

    def _clear_container(self):
        for child in self.page_container.findChildren(QWidget):
            if child is not self.page_container:
                child.setParent(None)
                child.deleteLater()

    def _show_welcome(self, text: str = "Open a PDF to start reading"):
        self._clear_container()
        vw, vh = self._viewport_size()
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("QLabel { color: #888; font-size: 20px; background: transparent; }")
        label.setParent(self.page_container)
        label.setGeometry(0, 0, vw, vh)
        label.show()

    # ═══════════════════════════════════════════════════
    #  Keyboard
    # ═══════════════════════════════════════════════════

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            if self._view_mode == ViewMode.SINGLE: self.prev_page()
            else: super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Right:
            if self._view_mode == ViewMode.SINGLE: self.next_page()
            else: super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Home: self.first_page()
        elif event.key() == Qt.Key.Key_End: self.last_page()
        else: super().keyPressEvent(event)

    # ═══════════════════════════════════════════════════
    #  Touchpad: scroll + pinch-zoom
    # ═══════════════════════════════════════════════════

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            current = self._zoom_mode if isinstance(self._zoom_mode, float) else 1.0
            new_zoom = max(0.25, min(4.0, current * (1.0 + delta / 1200.0)))
            self.set_zoom(new_zoom)
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.doc:
            self._resize_timer.start()

    # ═══════════════════════════════════════════════════
    #  Public helpers
    # ═══════════════════════════════════════════════════

    def has_document(self) -> bool: return self.doc is not None
    def current_path(self) -> Optional[Path]: return self._path
    def retranslate_ui(self): pass
