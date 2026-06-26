"""Clean PDF reader — 3 viewing modes, bottom toolbar, touchpad smooth scroll & pinch-zoom."""

from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent, QWheelEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QGridLayout,
)


class ViewMode(Enum):
    SCROLL = "scroll"     # continuous vertical scroll (default)
    SINGLE = "single"     # one page at a time, prev/next to flip
    GRID = "grid"         # 2×3 thumbnail grid, scrollable


RENDER_SCALE = 2  # always render at 2x for retina-sharp display


class PdfReaderWidget(QWidget):
    """Immersive PDF reader. Bottom toolbar, 3 view modes, touchpad support."""

    document_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Optional = None
        self._path: Optional[Path] = None
        self._current_page = 0          # 0-based (used in SINGLE mode)
        self._total_pages = 0
        self._view_mode = ViewMode.SCROLL  # default: continuous scroll
        self._zoom_mode = "fit_width"
        self._custom_zoom = 1.0
        self._init_ui()

    # ═══════════════════════════════════════════════════
    #  UI Construction
    # ═══════════════════════════════════════════════════

    def _init_ui(self):
        self.setStyleSheet("background-color: #2c2c2c;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Page display area (takes all space) ──
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
        # Enable gesture-based scrolling (pinch-zoom)
        self.scroll_area.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.page_container = QWidget()
        self.page_container.setStyleSheet("background: transparent;")
        # Persistent layout — never deleted, only cleared+repopulated
        self._container_layout = QVBoxLayout(self.page_container)
        self._container_layout.setContentsMargins(0, 20, 0, 20)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setWidget(self.page_container)

        main_layout.addWidget(self.scroll_area, 1)

        # ── Bottom toolbar ──
        self.toolbar = QWidget()
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
        self.toolbar.setObjectName("reader_toolbar")
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(10, 6, 10, 6)
        tb.setSpacing(10)

        # View mode buttons (toggle group)
        self.btn_scroll = QPushButton("Scroll")
        self.btn_scroll.setCheckable(True)
        self.btn_scroll.setChecked(True)
        self.btn_scroll.setToolTip("Continuous vertical scroll (default)")
        self.btn_scroll.clicked.connect(lambda: self._set_mode(ViewMode.SCROLL))

        self.btn_single = QPushButton("Single")
        self.btn_single.setCheckable(True)
        self.btn_single.setToolTip("One page at a time with previous/next")
        self.btn_single.clicked.connect(lambda: self._set_mode(ViewMode.SINGLE))

        self.btn_grid = QPushButton("Grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setToolTip("2x3 thumbnail grid, scrollable")
        self.btn_grid.clicked.connect(lambda: self._set_mode(ViewMode.GRID))

        tb.addWidget(self.btn_scroll)
        tb.addWidget(self.btn_single)
        tb.addWidget(self.btn_grid)

        tb.addSpacing(20)

        # Navigation (only relevant in SINGLE mode, hidden in scroll/grid)
        self.nav_widget = QWidget()
        nav_layout = QHBoxLayout(self.nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(36)
        self.btn_prev.clicked.connect(self.prev_page)

        self.page_input = QLineEdit("1")
        self.page_input.setFixedWidth(48)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self._on_page_input)

        self.label_total = QLabel("/ 1")

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(36)
        self.btn_next.clicked.connect(self.next_page)

        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.page_input)
        nav_layout.addWidget(self.label_total)
        nav_layout.addWidget(self.btn_next)

        tb.addWidget(self.nav_widget)

        tb.addStretch()

        # Zoom controls
        self.btn_fit_width = QPushButton("Fit Width")
        self.btn_fit_width.clicked.connect(self.zoom_fit_width)

        self.btn_fit_page = QPushButton("Fit Page")
        self.btn_fit_page.clicked.connect(self.zoom_fit_page)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["100%", "150%", "200%", "300%"])
        self.zoom_combo.setCurrentIndex(-1)
        self.zoom_combo.setToolTip("Zoom level")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_combo)

        tb.addWidget(self.btn_fit_width)
        tb.addWidget(self.btn_fit_page)
        tb.addWidget(self.zoom_combo)

        tb.addStretch()

        self.label_filename = QLabel("")
        self.label_filename.setStyleSheet("color: #777;")
        tb.addWidget(self.label_filename)

        main_layout.addWidget(self.toolbar)

        # ── Show welcome ──
        self._show_welcome()

        # Keyboard + touch
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        # ── Pinch-zoom state ──
        self._pinch_scale = 1.0
        self._pinch_active = False

    # ═══════════════════════════════════════════════════
    #  View Mode Switching
    # ═══════════════════════════════════════════════════

    def _set_mode(self, mode: ViewMode):
        self._view_mode = mode
        self.btn_scroll.setChecked(mode == ViewMode.SCROLL)
        self.btn_single.setChecked(mode == ViewMode.SINGLE)
        self.btn_grid.setChecked(mode == ViewMode.GRID)
        # Show nav widget only in SINGLE mode
        self.nav_widget.setVisible(mode == ViewMode.SINGLE)
        if self.doc:
            self._render_current()

    # ═══════════════════════════════════════════════════
    #  Public API
    # ═══════════════════════════════════════════════════

    def open_pdf(self, path: Path) -> None:
        import fitz
        try:
            self.doc = fitz.open(path)
        except Exception as e:
            self._show_welcome(f"Cannot open: {e}")
            return
        if self.doc.is_encrypted:
            if not self.doc.authenticate(""):
                self.doc.close()
                self.doc = None
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
            self.doc.close()
            self.doc = None
        self._path = None
        self._total_pages = 0
        self._current_page = 0
        self._clear_container()
        self._update_nav_ui()
        self.label_filename.clear()
        self._show_welcome()

    def go_to_page(self, num: int):
        if not self.doc:
            return
        num = max(1, min(num, self._total_pages))
        if num - 1 != self._current_page or self._view_mode == ViewMode.SCROLL:
            self._current_page = num - 1
            self._render_current()
            self._update_nav_ui()

    def next_page(self):
        if self.doc and self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._render_current()
            self._update_nav_ui()

    def prev_page(self):
        if self.doc and self._current_page > 0:
            self._current_page -= 1
            self._render_current()
            self._update_nav_ui()

    def first_page(self):
        self.go_to_page(1)

    def last_page(self):
        self.go_to_page(self._total_pages)

    # ═══════════════════════════════════════════════════
    #  Zoom
    # ═══════════════════════════════════════════════════

    def zoom_fit_width(self):
        self._zoom_mode = "fit_width"
        self.zoom_combo.setCurrentIndex(-1)
        if self.doc:
            self._render_current()

    def zoom_fit_page(self):
        self._zoom_mode = "fit_page"
        self.zoom_combo.setCurrentIndex(-1)
        if self.doc:
            self._render_current()

    def set_zoom(self, factor: float):
        self._zoom_mode = factor
        text = f"{int(factor*100)}%"
        idx = self.zoom_combo.findText(text)
        self.zoom_combo.setCurrentIndex(idx if idx >= 0 else -1)
        if self.doc:
            self._render_current()

    # ═══════════════════════════════════════════════════
    #  Rendering (3 modes)
    # ═══════════════════════════════════════════════════

    def _render_current(self):
        if not self.doc:
            return
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

    def _render_scroll(self):
        """Render all pages stacked vertically for continuous scrolling."""
        vw, vh = self._viewport_size()
        self._clear_container()

        layout = self._container_layout
        layout.setSpacing(10)
        layout.setContentsMargins(0, 20, 0, 20)

        for pi in range(self._total_pages):
            pix = self._render_pixmap(pi, vw, vh)
            label = QLabel()
            label.setPixmap(pix)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("QLabel { background: white; }")
            layout.addWidget(label)
        self._update_nav_ui()

    def _render_single(self):
        """Render one page at a time."""
        vw, vh = self._viewport_size()
        self._clear_container()

        layout = self._container_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        pix = self._render_pixmap(self._current_page, vw, vh)
        label = QLabel()
        label.setPixmap(pix)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("QLabel { background: white; }")
        layout.addWidget(label)

    def _render_grid(self):
        """Render thumbnails in a 2-column grid inside the persistent layout."""
        vw, vh = self._viewport_size()
        self._clear_container()

        layout = self._container_layout
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        COLS = 2
        thumb_w = (vw - 40 - (COLS - 1) * 12) // COLS
        thumb_h = int(thumb_w * 1.414)

        current_row_widget = None
        for pi in range(self._total_pages):
            pix = self._render_pixmap(pi, thumb_w, thumb_h, force_fit=True)
            label = QLabel()
            label.setPixmap(pix)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedSize(thumb_w, thumb_h)
            label.setScaledContents(False)
            label.setStyleSheet("QLabel { background: white; border: 1px solid #555; }")
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.setToolTip(f"Page {pi + 1}")

            pidx = pi  # capture
            label.mousePressEvent = lambda ev, p=pidx: self._on_grid_thumb_click(p)

            # Every 2 items = a new row
            if pi % COLS == 0:
                current_row_widget = QWidget()
                row_layout = QHBoxLayout(current_row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(12)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                layout.addWidget(current_row_widget)

            # Find the row layout and add the label
            row_layout = current_row_widget.layout()
            row_layout.addWidget(label)
            # Add stretch to keep centering
            if pi % COLS == COLS - 1 or pi == self._total_pages - 1:
                row_layout.addStretch()

    def _render_pixmap(self, page_idx: int, max_w: int, max_h: int = 9999, force_fit: bool = False) -> QPixmap:
        """Render a single page to QPixmap at retina quality, scaled to fit max_w × max_h."""
        import fitz
        from PyQt6.QtCore import Qt as QtCore
        page = self.doc[page_idx]
        pw, ph = page.rect.width, page.rect.height

        if force_fit:
            zoom = min(max_w / pw, max_h / ph)
        elif self._zoom_mode == "fit_width":
            zoom = max_w / pw
        elif self._zoom_mode == "fit_page":
            zoom = min(max_w / pw, max_h / ph)
        else:
            zoom = self._zoom_mode  # float

        # Render at 2x resolution for retina displays
        zoom_2x = zoom * RENDER_SCALE
        mat = fitz.Matrix(zoom_2x, zoom_2x)
        pix = page.get_pixmap(matrix=mat)

        # PyMuPDF produces RGB byte order.
        qimg = QImage(pix.samples, pix.width, pix.height,
                      pix.stride, QImage.Format.Format_RGB888)

        target_w = int(pix.width / RENDER_SCALE)
        target_h = int(pix.height / RENDER_SCALE)
        pixmap = QPixmap.fromImage(qimg).scaled(
            target_w, target_h,
            QtCore.AspectRatioMode.IgnoreAspectRatio,
            QtCore.TransformationMode.SmoothTransformation,
        )
        return pixmap

    def _clear_container(self):
        """Remove all child widgets from the container's persistent layout."""
        layout = self.page_container.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
            # Also clean up nested layouts
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw:
                        sw.setParent(None)
                        sw.deleteLater()
                import sip
                sip.delete(sub)

    def _show_welcome(self, text: str = "Open a PDF to start reading"):
        self._clear_container()
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("QLabel { color: #888; font-size: 20px; background: transparent; }")
        self._container_layout.addWidget(label)

    # ═══════════════════════════════════════════════════
    #  Slots
    # ═══════════════════════════════════════════════════

    def _on_page_input(self):
        try:
            num = int(self.page_input.text())
            self.go_to_page(num)
        except ValueError:
            self._update_nav_ui()

    def _on_zoom_combo(self, text: str):
        factor = {"100%": 1.0, "150%": 1.5, "200%": 2.0, "300%": 3.0}.get(text)
        if factor:
            self.set_zoom(factor)

    def _on_grid_thumb_click(self, page_idx: int):
        """Click a thumbnail → switch to SINGLE mode at that page."""
        self._current_page = page_idx
        self._set_mode(ViewMode.SINGLE)

    def _update_nav_ui(self):
        self.page_input.setText(str(self._current_page + 1))
        self.label_total.setText(f"/ {self._total_pages}")
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < self._total_pages - 1)
        self.page_input.setEnabled(self._total_pages > 0)

    # ═══════════════════════════════════════════════════
    #  Keyboard
    # ═══════════════════════════════════════════════════

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            if self._view_mode == ViewMode.SINGLE:
                self.prev_page()
            else:
                super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Right:
            if self._view_mode == ViewMode.SINGLE:
                self.next_page()
            else:
                super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Home:
            self.first_page()
        elif event.key() == Qt.Key.Key_End:
            self.last_page()
        else:
            super().keyPressEvent(event)

    # ═══════════════════════════════════════════════════
    #  Mouse / Touchpad (smooth scroll + pinch-zoom)
    # ═══════════════════════════════════════════════════

    def wheelEvent(self, event: QWheelEvent):
        """Ctrl+scroll = pinch-zoom simulation on mouse.
        Native touchpad pinch-to-zoom is handled by macOS gesture → wheelEvent
        with pixel deltas and ControlModifier."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # macOS touchpad pinch sends Ctrl+wheel with pixelDelta
            delta = event.angleDelta().y()
            current = self._zoom_mode if isinstance(self._zoom_mode, float) else 1.0
            new_zoom = current * (1.0 + delta / 1200.0)  # smooth, 1200 = sensitivity
            new_zoom = max(0.25, min(4.0, new_zoom))
            self.set_zoom(new_zoom)
        else:
            # Normal scroll — let QScrollArea handle it smoothly
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.doc and self._zoom_mode in ("fit_width", "fit_page"):
            self._render_current()
        elif self.doc and self._view_mode == ViewMode.GRID:
            self._render_current()

    # ═══════════════════════════════════════════════════
    #  Public helpers for MainWindow
    # ═══════════════════════════════════════════════════

    def has_document(self) -> bool:
        return self.doc is not None

    def current_path(self) -> Optional[Path]:
        return self._path

    def retranslate_ui(self):
        pass
