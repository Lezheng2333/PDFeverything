"""PDF reader — pre-render all, label pool reuse, i18n toolbar, 3s tooltips, pinch-zoom popup."""

from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget, QToolTip, QFrame,
)


class ViewMode(Enum):
    SCROLL = "scroll"
    SINGLE = "single"
    GRID = "grid"


RENDER_SCALE = 2; RESIZE_DEBOUNCE = 300; MAX_CACHE = 2000


class PdfReaderWidget(QWidget):
    document_changed = pyqtSignal(str)
    _cache: dict = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None; self._path = None
        self._current_page = 0; self._total_pages = 0
        self._view_mode = ViewMode.SCROLL; self._zoom_mode = "fit_width"
        self._labels = []  # label pool — reused, not re-created

        self._resize_timer = QTimer(self); self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(RESIZE_DEBOUNCE)
        self._resize_timer.timeout.connect(self._on_resize)

        self._scroll_timer = QTimer(self); self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(80)
        self._scroll_timer.timeout.connect(self._track_scroll_page)

        self._hover_timer = QTimer(self); self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(3000)
        self._hover_timer.timeout.connect(self._show_tooltip)

        self._zoom_popup_timer = QTimer(self); self._zoom_popup_timer.setSingleShot(True)
        self._zoom_popup_timer.setInterval(1200)
        self._zoom_popup_timer.timeout.connect(self._hide_zoom_popup)
        self._zoom_popup = QLabel(self)
        self._zoom_popup.setStyleSheet(
            "QLabel { background: rgba(0,0,0,180); color: #fff; font-size: 18px; "
            "font-weight: bold; border-radius: 10px; padding: 8px 16px; }")
        self._zoom_popup.setAlignment(Qt.AlignmentFlag.AlignCenter); self._zoom_popup.hide()

        self._init_ui()

    # ═══════════════ UI ═══════════════

    def _init_ui(self):
        self.setStyleSheet("background-color: #2c2c2c;")
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        self.scroll_area = QScrollArea(); self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: #2c2c2c; border: none; }
            QScrollBar:vertical { background: #1e1e1e; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background: #1e1e1e; height:10px; margin:0; }
            QScrollBar::handle:horizontal { background: #555; border-radius:4px; min-width:30px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
        """)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._scroll_timer.start)

        self.page_container = QWidget(); self.page_container.setStyleSheet("background: transparent;")
        self.scroll_area.setWidget(self.page_container)

        root.addWidget(self.scroll_area, 1)

        # Toolbar
        self.toolbar = QWidget(); self.toolbar.setObjectName("reader_toolbar")
        self.toolbar.setStyleSheet("""
            QWidget#reader_toolbar { background: #1e1e1e; border-top: 1px solid #3a3a3a; }
            QPushButton { color: #ccc; background: #333; border: 1px solid #555; border-radius:4px; padding:5px 12px; font-size:13px; }
            QPushButton:hover { background: #444; }
            QPushButton:checked { background: #007aff; color:#fff; border-color:#007aff; }
            QPushButton:disabled { color:#555; background:#2a2a2a; }
            QLineEdit { color:#fff; background:#2a2a2a; border:1px solid #555; border-radius:4px; padding:4px 6px; font-size:13px; max-width:50px; }
            QComboBox { color:#ccc; background:#333; border:1px solid #555; border-radius:4px; padding:4px 8px; font-size:13px; }
            QLabel { color:#999; font-size:13px; }
        """)
        tb = QHBoxLayout(self.toolbar); tb.setContentsMargins(10,6,10,6); tb.setSpacing(10)

        self.btn_scroll = QPushButton("Scroll"); self.btn_scroll.setCheckable(True); self.btn_scroll.setChecked(True)
        self.btn_scroll.clicked.connect(lambda: self._set_mode(ViewMode.SCROLL))
        self.btn_single = QPushButton("Single"); self.btn_single.setCheckable(True)
        self.btn_single.clicked.connect(lambda: self._set_mode(ViewMode.SINGLE))
        self.btn_grid = QPushButton("Grid"); self.btn_grid.setCheckable(True)
        self.btn_grid.clicked.connect(lambda: self._set_mode(ViewMode.GRID))
        for b in [self.btn_scroll, self.btn_single, self.btn_grid]:
            self._hover_on(b)
        tb.addWidget(self.btn_scroll); tb.addWidget(self.btn_single); tb.addWidget(self.btn_grid)
        tb.addSpacing(20)

        self.nav_widget = QWidget()
        nl = QHBoxLayout(self.nav_widget); nl.setContentsMargins(0,0,0,0); nl.setSpacing(6)
        self.btn_prev = QPushButton("◀"); self.btn_prev.setFixedWidth(36); self.btn_prev.clicked.connect(self.prev_page)
        self._hover_on(self.btn_prev)
        self.page_input = QLineEdit("1"); self.page_input.setFixedWidth(48)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter); self.page_input.returnPressed.connect(self._on_page_input)
        self.label_total = QLabel("/ 1")
        self.btn_next = QPushButton("▶"); self.btn_next.setFixedWidth(36); self.btn_next.clicked.connect(self.next_page)
        self._hover_on(self.btn_next)
        nl.addWidget(self.btn_prev); nl.addWidget(self.page_input); nl.addWidget(self.label_total); nl.addWidget(self.btn_next)
        tb.addWidget(self.nav_widget); tb.addStretch()

        self.btn_fit_width = QPushButton("Fit Width"); self.btn_fit_width.setCheckable(True); self.btn_fit_width.setChecked(True)
        self.btn_fit_width.clicked.connect(self._on_fit_width); self._hover_on(self.btn_fit_width)
        self.btn_fit_page = QPushButton("Fit Page"); self.btn_fit_page.setCheckable(True)
        self.btn_fit_page.clicked.connect(self._on_fit_page); self._hover_on(self.btn_fit_page)
        self.zoom_combo = QComboBox(); self.zoom_combo.addItems(["100%","150%","200%","300%"])
        self.zoom_combo.setCurrentIndex(-1); self.zoom_combo.currentTextChanged.connect(self._on_zoom_combo)
        tb.addWidget(self.btn_fit_width); tb.addWidget(self.btn_fit_page); tb.addWidget(self.zoom_combo); tb.addStretch()

        self.label_filename = QLabel(""); self.label_filename.setStyleSheet("color: #777;"); tb.addWidget(self.label_filename)
        root.addWidget(self.toolbar)
        self._show_welcome(); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setMouseTracking(True)

    def _hover_on(self, w):
        w._orig_enter = w.enterEvent; w._orig_leave = w.leaveEvent
        def enter(e):
            self._hover_widget = w; self._hover_timer.start(3000)
            if w._orig_enter: w._orig_enter(e)
        def leave(e):
            self._hover_timer.stop(); QToolTip.hideText()
            if w._orig_leave: w._orig_leave(e)
        w.enterEvent = enter; w.leaveEvent = leave
        if hasattr(w, 'mouseMoveEvent'):
            w._orig_move = w.mouseMoveEvent
            def move(e):
                if getattr(self,'_hover_widget',None) is w: self._hover_pos = e.globalPosition().toPoint(); self._hover_timer.start(3000)
                if w._orig_move: w._orig_move(e)
            w.mouseMoveEvent = move

    def _show_tooltip(self):
        w = getattr(self,'_hover_widget',None)
        if w and hasattr(self,'_hover_pos'):
            t = w.toolTip()
            if t: QToolTip.showText(self._hover_pos, t, self)

    # ═══════════════ Mode ═══════════════

    def _set_mode(self, mode: ViewMode):
        self._view_mode = mode
        self.btn_scroll.setChecked(mode == ViewMode.SCROLL)
        self.btn_single.setChecked(mode == ViewMode.SINGLE)
        self.btn_grid.setChecked(mode == ViewMode.GRID)
        self.nav_widget.setVisible(mode == ViewMode.SINGLE)
        if self.doc:
            self._layout_labels()

    # ═══════════════ Public ═══════════════

    def open_pdf(self, path: Path) -> None:
        import fitz
        PdfReaderWidget._cache.clear(); self._destroy_labels()
        try: self.doc = fitz.open(path)
        except Exception as e: self._show_welcome(f"Cannot open: {e}"); return
        if self.doc.is_encrypted:
            if not self.doc.authenticate(""): self.doc.close(); self.doc = None; self._show_welcome("This PDF is password-protected."); return
        self._path = path; self._total_pages = len(self.doc); self._current_page = 0
        self._zoom_mode = "fit_width"
        self.btn_fit_width.setChecked(True); self.btn_fit_page.setChecked(False); self.zoom_combo.setCurrentIndex(-1)
        self._build_labels()
        self._pre_render_all()
        self._layout_labels()
        self._update_nav_ui(); self.label_filename.setText(path.name)
        self.document_changed.emit(str(path)); self.setFocus()

    def close_document(self):
        if self.doc: self.doc.close(); self.doc = None
        self._path = None; self._total_pages = 0; self._current_page = 0
        PdfReaderWidget._cache.clear(); self._destroy_labels()
        self._update_nav_ui(); self.label_filename.clear(); self._show_welcome()

    def go_to_page(self, num: int):
        if not self.doc: return
        num = max(1, min(num, self._total_pages))
        if num - 1 != self._current_page:
            self._current_page = num - 1
            if self._view_mode == ViewMode.SCROLL: self._scroll_to_current()
            else: self._layout_labels()
            self._update_nav_ui()

    def next_page(self):
        if self.doc and self._current_page < self._total_pages - 1:
            self._current_page += 1; self._layout_labels(); self._update_nav_ui()

    def prev_page(self):
        if self.doc and self._current_page > 0:
            self._current_page -= 1; self._layout_labels(); self._update_nav_ui()

    def first_page(self): self.go_to_page(1)
    def last_page(self): self.go_to_page(self._total_pages)

    def zoom_fit_width(self):
        if self._zoom_mode == "fit_width": return
        self._zoom_mode = "fit_width"
        self.btn_fit_width.setChecked(True); self.btn_fit_page.setChecked(False); self.zoom_combo.setCurrentIndex(-1)
        PdfReaderWidget._cache.clear()
        if self.doc: self._update_label_pixmaps(); self._layout_labels(); self._pre_render_all()

    def zoom_fit_page(self):
        if self._zoom_mode == "fit_page": return
        self._zoom_mode = "fit_page"
        self.btn_fit_width.setChecked(False); self.btn_fit_page.setChecked(True); self.zoom_combo.setCurrentIndex(-1)
        PdfReaderWidget._cache.clear()
        if self.doc: self._update_label_pixmaps(); self._layout_labels(); self._pre_render_all()

    def set_zoom(self, factor: float):
        factor = max(0.25, min(4.0, round(factor*100)/100))
        self._zoom_mode = factor
        self.btn_fit_width.setChecked(False); self.btn_fit_page.setChecked(False)
        text = f"{int(factor*100)}%"; idx = self.zoom_combo.findText(text)
        self.zoom_combo.setCurrentIndex(idx if idx>=0 else -1)
        PdfReaderWidget._cache.clear()
        if self.doc: self._update_label_pixmaps(); self._layout_labels(); self._pre_render_all()
        self._show_zoom_popup(int(factor*100))

    def _show_zoom_popup(self, pct):
        self._zoom_popup.setText(f"🔍 {pct}%"); self._zoom_popup.adjustSize()
        r = self.rect(); x = (r.width()-self._zoom_popup.width())//2; y = r.height()//3
        self._zoom_popup.move(x,y); self._zoom_popup.show(); self._zoom_popup.raise_()
        self._zoom_popup_timer.start()

    def _hide_zoom_popup(self): self._zoom_popup.hide()

    # ═══════════════ Label pool (create once, reuse forever) ═══════════════

    def _build_labels(self):
        """Create labels for all pages. Called once on open_pdf."""
        for pi in range(self._total_pages):
            l = QLabel(); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setParent(self.page_container); l.hide()
            pl = pi
            l.mousePressEvent = lambda ev, p=pl: self._on_grid_thumb_click(p)
            self._labels.append(l)

    def _update_label_pixmaps(self):
        """Swap pixmaps on all labels (after zoom change — all new cache entries)."""
        vw, _ = self._viewport_size()
        for pi, l in enumerate(self._labels):
            pix = self._get_or_render(pi, vw)
            if pix: l.setPixmap(pix); l.setFixedSize(pix.size())

    def _destroy_labels(self):
        for l in self._labels:
            l.setParent(None); l.deleteLater()
        self._labels.clear()

    def _layout_labels(self):
        """Position labels according to current view mode."""
        vw, vh = self._viewport_size()
        current_mode = self._view_mode
        spacing, margin = 10, 20

        if current_mode == ViewMode.SCROLL:
            y = margin; max_w = 0
            for pi, l in enumerate(self._labels):
                pix = l.pixmap()
                if pix is None or pix.isNull():
                    pix = self._get_or_render(pi, vw, 99999)
                    if pix: l.setPixmap(pix); l.setFixedSize(pix.size())
                l.setStyleSheet("QLabel { background: white; }")
                l.setCursor(Qt.CursorShape.ArrowCursor)
                l.move(margin, y); l.show()
                y += (pix.height() + spacing) if pix and not pix.isNull() else (800 + spacing)
                max_w = max(max_w, pix.width() if pix and not pix.isNull() else 600)
            self.page_container.setFixedSize(max_w + 2*margin, y - spacing + margin)

        elif current_mode == ViewMode.SINGLE:
            pi = self._current_page
            for i, l in enumerate(self._labels):
                if i == pi:
                    pix = l.pixmap()
                    if not pix or pix.isNull():
                        pix = self._get_or_render(pi, vw, 99999)
                        if pix: l.setPixmap(pix); l.setFixedSize(pix.size())
                    l.setStyleSheet("QLabel { background: white; }")
                    l.move(0, 0); l.show()
                    self.page_container.setFixedSize(pix.width() if pix else 800, pix.height() if pix else 600)
                else:
                    l.hide()

        elif current_mode == ViewMode.GRID:
            COLS = 2
            thumb_w = max(80, (vw - 2*margin - (COLS-1)*spacing) // COLS)
            thumb_h = int(thumb_w * 1.414)
            for pi, l in enumerate(self._labels):
                pix = self._get_or_render(pi, thumb_w, thumb_h, force_fit=True)
                if pix: l.setPixmap(pix); l.setFixedSize(pix.size())
                l.setStyleSheet("QLabel { background: white; border: 1px solid #555; }")
                l.setCursor(Qt.CursorShape.PointingHandCursor)
                col, row = pi % COLS, pi // COLS
                l.move(margin + col*(thumb_w+spacing), margin + row*(thumb_h+spacing))
                l.show()
            rows = (self._total_pages + COLS - 1) // COLS
            self.page_container.setFixedSize(
                2*margin + COLS*thumb_w + (COLS-1)*spacing,
                2*margin + rows*thumb_h + (rows-1)*spacing,
            )

    def _pre_render_all(self):
        vw, _ = self._viewport_size()
        for pi in range(self._total_pages):
            self._get_or_render(pi, vw, 99999)

    def _scroll_to_current(self):
        if not self._total_pages: return
        l0 = self._labels[0]; pix0 = l0.pixmap()
        if not pix0: return
        page_h = pix0.height(); spacing = 10
        self.scroll_area.verticalScrollBar().setValue(self._current_page * (page_h + spacing))

    def _track_scroll_page(self):
        if not self.doc or self._view_mode != ViewMode.SCROLL or not self._labels: return
        l0 = self._labels[0]; pix0 = l0.pixmap()
        if not pix0: return
        page_h, spacing, margin = pix0.height(), 10, 20
        scroll_y = self.scroll_area.verticalScrollBar().value()
        est = max(0, min(self._total_pages-1, (scroll_y - margin) // (page_h + spacing)))
        if est != self._current_page: self._current_page = est; self._update_nav_ui()

    # ═══════════════ Zoom key ═══════════════

    def _zoom_key(self, max_w): return (
        f"fw:{max_w}" if self._zoom_mode == "fit_width" else
        f"fp:{max_w}" if self._zoom_mode == "fit_page" else
        f"z:{self._zoom_mode:.2f}"
    )

    @staticmethod
    def _render_page(doc, page_idx, zoom_key, max_w, max_h=99999, force_fit=False):
        import fitz
        page = doc[page_idx]; pw, ph = page.rect.width, page.rect.height
        if force_fit: zoom = min(max_w/pw, max_h/ph)
        elif zoom_key.startswith("fw:"): zoom = int(zoom_key[3:]) / pw
        elif zoom_key.startswith("fp:"): zoom = min(int(zoom_key[3:])/pw, 99999/ph)
        elif zoom_key.startswith("z:"): zoom = float(zoom_key[2:])
        else: zoom = max_w / pw

        mat = fitz.Matrix(zoom*RENDER_SCALE, zoom*RENDER_SCALE); pix = page.get_pixmap(matrix=mat)
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        tw, th = max(1, pix.width//RENDER_SCALE), max(1, pix.height//RENDER_SCALE)
        from PyQt6.QtCore import Qt as QtCore
        return QPixmap.fromImage(qimg).scaled(tw, th, QtCore.AspectRatioMode.IgnoreAspectRatio, QtCore.TransformationMode.SmoothTransformation)

    def _viewport_size(self):
        vp = self.scroll_area.viewport()
        return (max(800, vp.width()-4), max(600, vp.height()-4))

    def _get_or_render(self, page_idx, max_w, max_h=99999, force_fit=False):
        key = (page_idx, self._zoom_key(max_w))
        if key in PdfReaderWidget._cache: return PdfReaderWidget._cache[key]
        pix = PdfReaderWidget._render_page(self.doc, page_idx, key[1], max_w, max_h, force_fit)
        if len(PdfReaderWidget._cache) < MAX_CACHE: PdfReaderWidget._cache[key] = pix
        return pix

    def _on_grid_thumb_click(self, p): self._current_page = p; self._set_mode(ViewMode.SINGLE)

    def _on_fit_width(self): self.zoom_fit_width()
    def _on_fit_page(self): self.zoom_fit_page()

    def _on_resize(self):
        if self.doc: PdfReaderWidget._cache.clear(); self._update_label_pixmaps(); self._layout_labels(); self._pre_render_all()

    def _on_page_input(self):
        try: self.go_to_page(int(self.page_input.text()))
        except ValueError: self._update_nav_ui()

    def _on_zoom_combo(self, text):
        f = {"100%":1.0,"150%":1.5,"200%":2.0,"300%":3.0}.get(text)
        if f: self.set_zoom(f)

    def _update_nav_ui(self):
        self.page_input.setText(str(self._current_page+1)); self.label_total.setText(f"/ {self._total_pages}")
        self.btn_prev.setEnabled(self._current_page>0); self.btn_next.setEnabled(self._current_page<self._total_pages-1)
        self.page_input.setEnabled(self._total_pages>0)

    def _show_welcome(self, text="Open a PDF to start reading"):
        vw, vh = self._viewport_size()
        l = QLabel(text); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.setStyleSheet("QLabel { color: #888; font-size: 20px; background: transparent; }")
        l.setParent(self.page_container); l.setGeometry(0,0,vw,vh); l.show()

    def keyPressEvent(self, e):
        m = self._view_mode
        if e.key() == Qt.Key.Key_Left and m == ViewMode.SINGLE: self.prev_page()
        elif e.key() == Qt.Key.Key_Right and m == ViewMode.SINGLE: self.next_page()
        elif e.key() == Qt.Key.Key_Home: self.first_page()
        elif e.key() == Qt.Key.Key_End: self.last_page()
        else: super().keyPressEvent(e)

    def wheelEvent(self, e):
        cur = self._zoom_mode if isinstance(self._zoom_mode, float) else 1.0
        # Detect pinch-to-zoom on both macOS and Windows trackpads.
        # macOS: native gesture → phase set + angleDelta significant
        # Windows: precision touchpad sends Ctrl+wheel for pinch
        # Both: if angleDelta.y is large relative to pixelDelta, it's a pinch
        pinch = e.modifiers() & Qt.KeyboardModifier.ControlModifier
        if not pinch:
            try:
                ph = e.phase()
                pinch = (int(ph) >= 1)  # Qt.ScrollPhase: 1=Begin,2=Update,3=End
            except (AttributeError, TypeError):
                pass
        # Also detect pinch via ratio: macOS pinch has angleDelta but small or zero pixelDelta
        if not pinch:
            ad_y = abs(e.angleDelta().y()) if e.angleDelta() else 0
            pd_y = abs(e.pixelDelta().y()) if e.pixelDelta() else 1
            if ad_y > 0 and (pd_y == 0 or ad_y / max(pd_y, 1) > 3):
                pinch = True

        if pinch and e.angleDelta().y() != 0:
            self.set_zoom(max(0.25, min(4.0, cur * (1.0 + e.angleDelta().y() / 1200.0))))
        else:
            super().wheelEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.doc: self._resize_timer.start()

    def has_document(self) -> bool: return self.doc is not None
    def current_path(self) -> Optional[Path]: return self._path
    def retranslate_ui(self): pass
