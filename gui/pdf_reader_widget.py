"""PDF reader — Scroll+Grid, smooth zoom 50-300%, WPS-style grid, click-edit zoom, fast page tracking."""

from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent, QWheelEvent, QIntValidator
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget, QToolTip, QSizePolicy,
)


class ViewMode(Enum):
    SCROLL = "scroll"
    GRID = "grid"


RENDER_SCALE = 2; RESIZE_DEBOUNCE = 350
BATCH_SIZE = 30; PINCH_STEP = 3  # % per pinch tick


class PdfReaderWidget(QWidget):
    document_changed = pyqtSignal(str); close_requested = pyqtSignal(); open_requested = pyqtSignal()
    _cache: dict = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None; self._path = None; self._current_page = 0; self._total_pages = 0
        self._view_mode = ViewMode.SCROLL
        self._zoom_mode = "fit_height"
        self._fw_ratio = 1.0; self._fh_ratio = 1.0
        self._labels: list[QLabel] = []
        self._page_heights: list[int] = []
        self._pinch_acc = 0  # accumulated pinch delta for smooth grouping

        self._resize_timer = QTimer(self); self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(RESIZE_DEBOUNCE)
        self._resize_timer.timeout.connect(self._on_resize)

        self._scroll_timer = QTimer(self); self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(16)  # ~60fps
        self._scroll_timer.timeout.connect(self._track_scroll_page)

        self._pre_render_timer = QTimer(self); self._pre_render_timer.setSingleShot(True)
        self._pre_render_timer.setInterval(0)
        self._pre_render_timer.timeout.connect(self._pre_render_batch)

        self._real_zoom_timer = QTimer(self); self._real_zoom_timer.setSingleShot(True)
        self._real_zoom_timer.setInterval(250)  # 250ms after zoom stops, do real render
        self._real_zoom_timer.timeout.connect(self._do_real_render)

        self._hover_timer = QTimer(self); self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(3000)
        self._hover_timer.timeout.connect(self._show_tooltip)

        self._zoom_popup_timer = QTimer(self); self._zoom_popup_timer.setSingleShot(True)
        self._zoom_popup_timer.setInterval(1200)
        self._zoom_popup_timer.timeout.connect(self._hide_zoom_popup)
        self._zoom_popup = QLabel(self)
        self._zoom_popup.setStyleSheet(
            "QLabel { background: rgba(0,0,0,180); color:#fff; font-size:18px; "
            "font-weight:bold; border-radius:10px; padding:8px 16px; }")
        self._zoom_popup.setAlignment(Qt.AlignmentFlag.AlignCenter); self._zoom_popup.hide()

        self._pre_render_idx = 0; self._welcome_widget = None
        self._init_ui()
        # Delay welcome to ensure viewport is sized
        QTimer.singleShot(100, self._show_welcome)

    # ═══════════════ UI ═══════════════

    def _init_ui(self):
        self.setStyleSheet("background-color:#2c2c2c;")
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        self.scroll_area = QScrollArea(); self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("""
            QScrollArea{background:#2c2c2c;border:none;}
            QScrollBar:vertical{background:#1e1e1e;width:10px;margin:0;}
            QScrollBar::handle:vertical{background:#555;border-radius:4px;min-height:30px;}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
            QScrollBar:horizontal{background:#1e1e1e;height:10px;margin:0;}
            QScrollBar::handle:horizontal{background:#555;border-radius:4px;min-width:30px;}
            QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;}
        """)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._scroll_timer.start)
        self.scroll_area.setAcceptDrops(True)
        self.page_container = QWidget(); self.page_container.setStyleSheet("background:transparent;")
        self.scroll_area.setWidget(self.page_container)
        root.addWidget(self.scroll_area, 1)

        # ── Bottom toolbar ──
        self.toolbar = QWidget(); self.toolbar.setObjectName("reader_toolbar")
        self.toolbar.setStyleSheet("""
            QWidget#reader_toolbar{background:#1e1e1e;border-top:1px solid #3a3a3a;}
            QPushButton{color:#ccc;background:#333;border:1px solid #555;border-radius:4px;padding:5px 12px;font-size:13px;}
            QPushButton:hover{background:#444;}
            QPushButton:checked{background:#007aff;color:#fff;border-color:#007aff;}
            QPushButton:disabled{color:#555;background:#2a2a2a;}
            QLineEdit{color:#fff;background:#2a2a2a;border:1px solid #555;border-radius:4px;padding:4px 6px;font-size:13px;}
            QLabel{color:#999;font-size:13px;}
            #btn_close{color:#ccc;background:transparent;border:none;font-size:16px;padding:2px 6px;}
            #btn_close:hover{color:#fff;background:#c33;border-radius:4px;}
            #zoom_edit{color:#fff;background:#2a2a2a;border:1px solid #555;border-radius:4px;padding:3px 8px;font-size:13px;min-width:55px;}
        """)
        tb = QHBoxLayout(self.toolbar); tb.setContentsMargins(8,6,8,6); tb.setSpacing(8)

        self.btn_scroll = QPushButton("Scroll"); self.btn_scroll.setCheckable(True); self.btn_scroll.setChecked(True)
        self.btn_scroll.clicked.connect(lambda: self._set_mode(ViewMode.SCROLL)); self._hover_on(self.btn_scroll)
        self.btn_grid = QPushButton("Grid"); self.btn_grid.setCheckable(True)
        self.btn_grid.clicked.connect(lambda: self._set_mode(ViewMode.GRID)); self._hover_on(self.btn_grid)
        tb.addWidget(self.btn_scroll); tb.addWidget(self.btn_grid)

        # ── Centered nav ──
        tb.addStretch()
        self.btn_prev = QPushButton("◀"); self.btn_prev.setFixedSize(30,30)
        self.btn_prev.clicked.connect(self.prev_page); self._hover_on(self.btn_prev)
        self.page_label = QLabel("1 / 1"); self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setFixedWidth(70)
        self.page_label.setStyleSheet("QLabel{color:#bbb;font-size:13px;}")
        self.btn_next = QPushButton("▶"); self.btn_next.setFixedSize(30,30)
        self.btn_next.clicked.connect(self.next_page); self._hover_on(self.btn_next)
        tb.addWidget(self.btn_prev); tb.addWidget(self.page_label); tb.addWidget(self.btn_next)
        tb.addStretch()

        # ── Zoom: [-] [editable%] [+]  ──
        self.btn_zoom_out = QPushButton("−"); self.btn_zoom_out.setFixedSize(30,30)
        self.btn_zoom_out.clicked.connect(lambda: self._adjust_zoom(-1)); self._hover_on(self.btn_zoom_out)

        self.zoom_edit = QLineEdit("100"); self.zoom_edit.setObjectName("zoom_edit")
        self.zoom_edit.setFixedWidth(55); self.zoom_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_edit.setMaxLength(3)
        self.zoom_edit.setValidator(QIntValidator(25, 500, self))
        self.zoom_edit.returnPressed.connect(self._on_zoom_edit)
        self.zoom_edit.editingFinished.connect(self._on_zoom_edit)  # also on focus loss

        self.btn_zoom_in = QPushButton("+"); self.btn_zoom_in.setFixedSize(30,30)
        self.btn_zoom_in.clicked.connect(lambda: self._adjust_zoom(+1)); self._hover_on(self.btn_zoom_in)

        tb.addWidget(self.btn_zoom_out); tb.addWidget(self.zoom_edit); tb.addWidget(self.btn_zoom_in)

        # ── Fit Width / Fit Height ──
        self.btn_fit_width = QPushButton("Fit W"); self.btn_fit_width.setCheckable(True)
        self.btn_fit_width.clicked.connect(self._on_fit_width); self._hover_on(self.btn_fit_width)
        self.btn_fit_height = QPushButton("Fit H"); self.btn_fit_height.setCheckable(True); self.btn_fit_height.setChecked(True)
        self.btn_fit_height.clicked.connect(self._on_fit_height); self._hover_on(self.btn_fit_height)
        tb.addWidget(self.btn_fit_width); tb.addWidget(self.btn_fit_height)
        tb.addStretch()

        self.label_filename = QLabel(""); self.label_filename.setStyleSheet("color:#777;"); tb.addWidget(self.label_filename)
        self.btn_close = QPushButton("✕"); self.btn_close.setObjectName("btn_close")
        self.btn_close.setFixedSize(26,26); self.btn_close.setToolTip("Close this document")
        self.btn_close.clicked.connect(self._on_close); tb.addWidget(self.btn_close)

        root.addWidget(self.toolbar)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setMouseTracking(True)

    def _hover_on(self, w):
        w._orig_enter = w.enterEvent; w._orig_leave = w.leaveEvent
        def enter(e):
            self._hover_widget = w; self._hover_timer.start(3000)
            if w._orig_enter: w._orig_enter(e)
        def leave(e):
            self._hover_timer.stop(); QToolTip.hideText()
            if w._orig_leave: w._orig_leave(e)
        w.enterEvent = enter; w.leaveEvent = leave
        if hasattr(w,'mouseMoveEvent'):
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
        self.btn_grid.setChecked(mode == ViewMode.GRID)
        if self.doc:
            self._layout_labels()
            if mode == ViewMode.SCROLL:
                self._scroll_to_page_top()

    def _on_close(self): self.close_document(); self.close_requested.emit()

    # ═══════════════ Public API ═══════════════

    def open_pdf(self, path: Path) -> None:
        import fitz
        PdfReaderWidget._cache.clear(); self._destroy_labels(); self._destroy_welcome()
        try: self.doc = fitz.open(path)
        except: self._show_welcome(); return
        if self.doc.is_encrypted:
            if not self.doc.authenticate(""):
                self.doc.close(); self.doc = None; self._show_welcome(); return
        self._path = path; self._total_pages = len(self.doc); self._current_page = 0
        self._btn_open_source = getattr(self,'_btn_open_source','dialog')
        self._zoom_mode = "fit_height"
        self.btn_fit_width.setChecked(False); self.btn_fit_height.setChecked(True)
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True); self.btn_grid.setChecked(False)
        # Pre-compute zoom ratios
        page = self.doc[0]; pw, ph = page.rect.width, page.rect.height
        vw, vh = self._viewport_size()
        self._fw_ratio = vw / pw if pw > 0 else 1.0
        self._fh_ratio = vh / ph if ph > 0 else 1.0
        self._default_zoom_pct = max(50, min(300, int(self._fh_ratio * 100)))
        self.zoom_edit.setText(str(self._default_zoom_pct))
        self._build_labels()
        self._start_pre_render()
        self._layout_labels()
        self._update_nav_ui()
        self.label_filename.setText(path.name)
        self.document_changed.emit(str(path))
        self.setFocus()

    def close_document(self):
        if self.doc: self.doc.close(); self.doc = None
        self._path = None; self._total_pages = 0; self._current_page = 0
        PdfReaderWidget._cache.clear(); self._destroy_labels()
        self._page_heights.clear()
        self._update_nav_ui(); self.label_filename.clear()
        QTimer.singleShot(50, self._show_welcome)

    # ═══════════════ Zoom — smooth, follow-finger ═══════════════

    def _zoom_pct(self) -> int:
        """Return current zoom as integer percentage."""
        if self._zoom_mode == "fit_width": return max(50, min(300, int(self._fw_ratio * 100)))
        if self._zoom_mode == "fit_height": return self._default_zoom_pct
        return max(50, min(300, int(self._zoom_mode * 100)))

    def _set_zoom_pct(self, pct: int, smooth: bool = False):
        """Change zoom to pct%. Clamped 50-300.
        If smooth=True, applies instantly via pixmap scaling; defers real re-render."""
        pct = max(50, min(300, pct))
        factor = pct / 100.0
        self._zoom_mode = factor
        self.btn_fit_width.setChecked(False); self.btn_fit_height.setChecked(False)
        self.zoom_edit.setText(str(pct))
        if self.doc:
            if smooth:
                self._apply_smooth_zoom(factor)
            else:
                PdfReaderWidget._cache.clear()
                self._update_label_pixmaps(); self._layout_labels()
            self._start_pre_render()
            self._real_zoom_timer.start()

    def _apply_smooth_zoom(self, factor: float):
        """Instantly scale existing pixmaps (no re-render). fw_ratio acts as base."""
        base = self._fw_ratio
        scale = factor / base if base > 0 else factor
        for pi, l in enumerate(self._labels):
            pix = l.pixmap()
            if pix is None or pix.isNull(): continue
            pw, ph = pix.size().width(), pix.size().height()
            tw, th = max(1, int(pw * scale)), max(1, int(ph * scale))
            from PyQt6.QtCore import Qt as QtCore
            scaled = pix.scaled(tw, th,
                QtCore.AspectRatioMode.IgnoreAspectRatio,
                QtCore.TransformationMode.SmoothTransformation)
            l.setPixmap(scaled); l.setFixedSize(scaled.size())

    def _do_real_render(self):
        """Zoom debounce expired — do the actual re-render at current zoom."""
        if not self.doc: return
        PdfReaderWidget._cache.clear()
        # Recompute page heights after real render
        vw, vh = self._viewport_size()
        for pi, l in enumerate(self._labels):
            pix = self._get_or_render(pi, vw, vh)
            if pix: l.setPixmap(pix); l.setFixedSize(pix.size())
        self._layout_labels()

    def _set_fit_mode(self, mode: str):
        """Apply fit_width or fit_height instantly via pre-computed ratio."""
        if self._zoom_mode == mode: return
        self._zoom_mode = mode
        self.btn_fit_width.setChecked(mode == "fit_width")
        self.btn_fit_height.setChecked(mode == "fit_height")
        pct = int(self._fw_ratio * 100) if mode == "fit_width" else self._default_zoom_pct
        pct = max(50, min(300, pct))
        self.zoom_edit.setText(str(pct))
        PdfReaderWidget._cache.clear()
        if self.doc:
            self._update_label_pixmaps(); self._layout_labels()
        self._start_pre_render()

    def _adjust_zoom(self, delta: int):
        """+/- button: 1% step."""
        self._set_zoom_pct(self._zoom_pct() + delta, smooth=True)

    def _on_zoom_edit(self):
        """User typed a zoom value and pressed Enter or lost focus."""
        try:
            val = int(self.zoom_edit.text())
            val = max(50, min(500, val))
            self._set_zoom_pct(val)
        except ValueError:
            self.zoom_edit.setText(str(self._zoom_pct()))

    def _show_zoom_popup(self, pct):
        self._zoom_popup.setText(f"🔍 {pct}%"); self._zoom_popup.adjustSize()
        r = self.rect(); x = (r.width()-self._zoom_popup.width())//2; y = r.height()//3
        self._zoom_popup.move(x,y); self._zoom_popup.show(); self._zoom_popup.raise_()
        self._zoom_popup_timer.start()

    def _hide_zoom_popup(self): self._zoom_popup.hide()

    # ═══════════════ Label pool ═══════════════

    def _build_labels(self):
        for pi in range(self._total_pages):
            l = QLabel(); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setParent(self.page_container); l.hide()
            pl = pi
            l.mouseDoubleClickEvent = lambda ev, p=pl: self._on_grid_dbl_click(p)
            self._labels.append(l)

    def _update_label_pixmaps(self):
        vw, vh = self._viewport_size()
        for pi, l in enumerate(self._labels):
            pix = self._get_or_render(pi, vw, vh)
            if pix: l.setPixmap(pix); l.setFixedSize(pix.size())

    def _destroy_labels(self):
        for l in self._labels: l.setParent(None); l.deleteLater()
        self._labels.clear(); self._pre_render_idx = 0

    def _destroy_welcome(self):
        if self._welcome_widget:
            self._welcome_widget.setParent(None); self._welcome_widget.deleteLater()
            self._welcome_widget = None

    def _layout_labels(self):
        vw, vh = self._viewport_size()
        spacing = 16; margin = 20

        if self._view_mode == ViewMode.SCROLL:
            self._page_heights = []
            y = margin; max_w = 0
            for pi, l in enumerate(self._labels):
                pix = l.pixmap()
                if pix is None or pix.isNull():
                    pix = self._get_or_render(pi, vw, vh)
                    if pix: l.setPixmap(pix); l.setFixedSize(pix.size())
                h = pix.height() if pix else 800
                w = pix.width() if pix else 600
                l.setStyleSheet("QLabel{background:white;}")
                l.setCursor(Qt.CursorShape.ArrowCursor)
                l.move(margin, y); l.show()
                max_w = max(max_w, w)
                self._page_heights.append(y)
                y += h + spacing
            self.page_container.setFixedSize(max_w + 2*margin, y - spacing + margin)

        elif self._view_mode == ViewMode.GRID:
            self._page_heights = []
            COLS = 3; gutter = 20; side_margin = 20
            # Available width, distribute evenly
            usable = vw - 2*side_margin - (COLS-1)*gutter
            thumb_w = max(120, usable // COLS)
            thumb_h = int(thumb_w * 1.414)

            # Recalculate side margins to center the grid
            total_grid_w = COLS*thumb_w + (COLS-1)*gutter
            left_margin = (vw - total_grid_w) // 2

            for pi, l in enumerate(self._labels):
                pix = self._get_or_render(pi, thumb_w, thumb_h, force_fit=True)
                if pix: l.setPixmap(pix); l.setFixedSize(pix.size())
                l.setStyleSheet("QLabel{background:white;border:1px solid #555;}")
                l.setCursor(Qt.CursorShape.PointingHandCursor)
                col, row = pi % COLS, pi // COLS
                x = left_margin + col*(thumb_w + gutter)
                y = margin + row*(thumb_h + gutter)
                l.move(x, y); l.show()

            rows = (self._total_pages + COLS - 1)//COLS
            self.page_container.setFixedSize(vw, 2*margin + rows*thumb_h + (rows-1)*gutter)
            # Center horizontally in scroll area
            self.page_container.move(0, 0)

    # ═══════════════ Scroll tracking — binary search on _page_heights ═══════════════

    def _scroll_to_page_top(self):
        if not self._page_heights or self._current_page >= len(self._page_heights): return
        target = self._page_heights[self._current_page]
        self.scroll_area.verticalScrollBar().setValue(max(0, target))

    def _track_scroll_page(self):
        if not self.doc or self._view_mode != ViewMode.SCROLL or not self._page_heights: return
        sb = self.scroll_area.verticalScrollBar()
        scroll_y = sb.value(); mid = scroll_y + sb.pageStep() // 2
        arr = self._page_heights
        lo, hi = 0, len(arr)-1
        while lo < hi:
            m = (lo + hi + 1)//2
            if arr[m] <= mid: lo = m
            else: hi = m - 1
        if lo != self._current_page:
            self._current_page = lo; self._update_nav_ui()

    # ═══════════════ Grid double-click ═══════════════

    def _on_grid_dbl_click(self, p):
        if self._view_mode != ViewMode.GRID: return
        self._current_page = p
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True); self.btn_grid.setChecked(False)
        self._zoom_mode = "fit_height"
        self.btn_fit_width.setChecked(False); self.btn_fit_height.setChecked(True)
        self.zoom_edit.setText(str(self._default_zoom_pct))
        PdfReaderWidget._cache.clear()
        self._update_label_pixmaps(); self._layout_labels()
        self._start_pre_render()
        self._scroll_to_page_top()
        self._update_nav_ui()

    # ═══════════════ Pre-render ═══════════════

    def _start_pre_render(self):
        self._pre_render_idx = 0; self._pre_render_timer.start()

    def _pre_render_batch(self):
        if not self.doc: return
        vw, vh = self._viewport_size()
        end = min(self._pre_render_idx + BATCH_SIZE, self._total_pages)
        for pi in range(self._pre_render_idx, end):
            self._get_or_render(pi, vw, vh)
        self._pre_render_idx = end
        if self._pre_render_idx < self._total_pages:
            self._pre_render_timer.start()
        else:
            self._update_label_pixmaps()

    # ═══════════════ Key + Render ═══════════════

    def _zoom_key(self, vw, vh):
        if self._zoom_mode == "fit_width": return "fw"
        if self._zoom_mode == "fit_height": return "fh"
        return f"z:{self._zoom_mode:.3f}"

    @staticmethod
    def _render_page(doc, pi, zk, vw, vh, force_fit=False):
        import fitz
        page = doc[pi]; pw, ph = page.rect.width, page.rect.height
        if zk == "fw": zoom = vw / pw
        elif zk == "fh": zoom = vh / ph
        elif zk.startswith("z:"): zoom = float(zk[2:])
        elif force_fit: zoom = min(vw/pw, vh/ph)
        else: zoom = vw / pw
        mat = fitz.Matrix(zoom*RENDER_SCALE, zoom*RENDER_SCALE)
        pix = page.get_pixmap(matrix=mat)
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        tw, th = max(1,pix.width//RENDER_SCALE), max(1,pix.height//RENDER_SCALE)
        from PyQt6.QtCore import Qt as QtCore
        return QPixmap.fromImage(qimg).scaled(tw,th, QtCore.AspectRatioMode.IgnoreAspectRatio, QtCore.TransformationMode.SmoothTransformation)

    def _viewport_size(self):
        vp = self.scroll_area.viewport()
        return (max(800, vp.width()-4), max(600, vp.height()-4))

    def _get_or_render(self, pi, vw, vh=99999, force_fit=False):
        key = (pi, self._zoom_key(vw,vh))
        if key in PdfReaderWidget._cache: return PdfReaderWidget._cache[key]
        pix = PdfReaderWidget._render_page(self.doc, pi, key[1], vw, vh, force_fit)
        PdfReaderWidget._cache[key] = pix
        return pix

    # ═══════════════ Navigation ═══════════════

    def go_to_page(self, num: int):
        if not self.doc: return
        num = max(1, min(num, self._total_pages))
        self._current_page = num - 1; self._scroll_to_page_top(); self._update_nav_ui()

    def next_page(self):
        if self.doc and self._current_page < self._total_pages-1:
            self._current_page += 1; self._scroll_to_page_top(); self._update_nav_ui()

    def prev_page(self):
        if self.doc and self._current_page > 0:
            self._current_page -= 1; self._scroll_to_page_top(); self._update_nav_ui()

    def first_page(self): self.go_to_page(1)
    def last_page(self): self.go_to_page(self._total_pages)

    # ═══════════════ Slots ═══════════════

    def _on_fit_width(self): self._set_fit_mode("fit_width")
    def _on_fit_height(self): self._set_fit_mode("fit_height")

    def _on_resize(self):
        if self.doc:
            page = self.doc[0]; pw,ph = page.rect.width, page.rect.height
            vw,vh = self._viewport_size()
            self._fw_ratio = vw/pw if pw>0 else 1.0; self._fh_ratio = vh/ph if ph>0 else 1.0
            self._default_zoom_pct = max(50, min(300, int(self._fh_ratio*100)))
            PdfReaderWidget._cache.clear()
            self._update_label_pixmaps(); self._layout_labels()
            self._start_pre_render()
            self.zoom_edit.setText(str(self._zoom_pct()))

    def _update_nav_ui(self):
        self.page_label.setText(f"{self._current_page+1} / {self._total_pages}")
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < self._total_pages - 1)

    # ═══════════════ Welcome ═══════════════

    def _show_welcome(self, drop_text="Drop PDF here to read", load_btn_text="Load file..."):
        vw,vh = self._viewport_size()
        # Clean up old welcome
        for c in self.page_container.findChildren(QWidget):
            if c not in (self.page_container,) + tuple(self._labels) and c is not self._zoom_popup:
                c.setParent(None); c.deleteLater()
        if self.doc: return  # don't show welcome if a doc is loaded

        center = QWidget(self.page_container)
        center.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(center); cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setSpacing(12)

        t = QLabel(drop_text); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet("QLabel{color:#555;font-size:16px;background:transparent;}")
        cl.addWidget(t)

        btn = QPushButton(load_btn_text); btn.setFixedWidth(120)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("QPushButton{color:#666;background:#2a2a2a;border:1px solid #444;border-radius:4px;padding:5px 16px;font-size:12px;}QPushButton:hover{color:#999;background:#333;border-color:#555;}")
        btn.clicked.connect(lambda: self.open_requested.emit())
        cl.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        center.adjustSize()
        cx = max(0, (vw - center.width())//2)
        cy = max(0, (vh - center.height())//2)
        center.move(cx, cy)
        center.show()
        center.raise_()
        self._welcome_widget = center

        self.scroll_area.setAcceptDrops(True)
        self.scroll_area.dragEnterEvent = self._drag_enter
        self.scroll_area.dropEvent = self._drop_event

    def _drag_enter(self, e):
        if e.mimeData().hasUrls():
            ext = Path(e.mimeData().urls()[0].toLocalFile()).suffix.lower()
            if ext == ".pdf": e.acceptProposedAction()
            else: e.ignore()
        else: e.ignore()

    def _drop_event(self, e):
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if Path(u.toLocalFile()).exists()]
        pdfs = [p for p in paths if p.suffix.lower()==".pdf"]
        if pdfs: self._path = pdfs[0]; self.open_requested.emit()
        e.acceptProposedAction()

    # ═══════════════ Keyboard ═══════════════

    def keyPressEvent(self, e):
        if e.key()==Qt.Key.Key_Left: self.prev_page()
        elif e.key()==Qt.Key.Key_Right: self.next_page()
        elif e.key()==Qt.Key.Key_Home: self.first_page()
        elif e.key()==Qt.Key.Key_End: self.last_page()
        else: super().keyPressEvent(e)

    # ═══════════════ Touchpad pinch-zoom (Scroll only, smooth) ═══════════════

    def wheelEvent(self, e):
        if self._view_mode != ViewMode.SCROLL:
            super().wheelEvent(e); return

        ad_y = e.angleDelta().y() if e.angleDelta() else 0
        pd_y = e.pixelDelta().y() if e.pixelDelta() else 0
        pinch = (e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if not pinch:
            try: ph = e.phase(); pinch = (int(ph) >= 1)
            except (AttributeError,TypeError): pass
        if not pinch and pd_y != 0 and ad_y != 0:
            if abs(ad_y) > abs(pd_y)*1.5: pinch = True

        if pinch:
            # Accumulate pinch deltas — apply zoom when threshold reached
            self._pinch_acc += ad_y
            step = 120  # ~1 notch of scroll = 120 angle units
            if abs(self._pinch_acc) >= step:
                ticks = int(abs(self._pinch_acc) / step) * (1 if self._pinch_acc > 0 else -1)
                self._pinch_acc %= step
                cur = self._zoom_pct()
                # Each tick = PINCH_STEP% change
                new_pct = max(50, min(300, cur + ticks * PINCH_STEP))
                self._set_zoom_pct(new_pct, smooth=True)
                self._show_zoom_popup(new_pct)
        else:
            super().wheelEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.doc: self._resize_timer.start()

    # ═══════════════ Helpers ═══════════════

    def has_document(self) -> bool: return self.doc is not None
    def current_path(self) -> Optional[Path]: return self._path
    @property
    def opened_from_file_list(self) -> bool: return getattr(self,'_btn_open_source','dialog')=='file_list'
    @opened_from_file_list.setter
    def opened_from_file_list(self, v: bool): self._btn_open_source = 'file_list' if v else 'dialog'
    def retranslate_ui(self): pass
