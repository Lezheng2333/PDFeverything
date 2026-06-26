"""PDF reader — Scroll+Grid, label pool, pre-render, pinch-zoom, instant zoom switch."""

from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget, QToolTip, QSizePolicy,
)


class ViewMode(Enum):
    SCROLL = "scroll"
    GRID = "grid"


RENDER_SCALE = 2
RESIZE_DEBOUNCE = 300
BATCH_SIZE = 40


class PdfReaderWidget(QWidget):
    document_changed = pyqtSignal(str)
    close_requested = pyqtSignal()
    open_requested = pyqtSignal()
    _cache: dict = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None; self._path = None
        self._current_page = 0; self._total_pages = 0
        self._view_mode = ViewMode.SCROLL
        self._zoom_mode = "fit_height"   # default is fit_height = 100%
        self._fw_ratio = 1.0   # pre-computed fit-width zoom ratio
        self._fh_ratio = 1.0   # pre-computed fit-height zoom ratio
        self._labels: list[QLabel] = []

        self._resize_timer = QTimer(self); self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(RESIZE_DEBOUNCE)
        self._resize_timer.timeout.connect(self._on_resize)

        self._scroll_timer = QTimer(self); self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(30)
        self._scroll_timer.timeout.connect(self._track_scroll_page)

        self._pre_render_timer = QTimer(self); self._pre_render_timer.setSingleShot(True)
        self._pre_render_timer.setInterval(0)
        self._pre_render_timer.timeout.connect(self._pre_render_batch)

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

        self._pre_render_idx = 0; self._welcome_widget = None
        self._page_heights: list[float] = []  # cached for fast scroll tracking
        self._scroll_y_on_prev = 0

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
        self.scroll_area.setAcceptDrops(True)

        self.page_container = QWidget(); self.page_container.setStyleSheet("background: transparent;")
        self.scroll_area.setWidget(self.page_container)

        root.addWidget(self.scroll_area, 1)

        # ── Bottom toolbar ──
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
            #btn_close { color: #ccc; background: transparent; border: none; font-size: 16px; padding: 2px 6px; }
            #btn_close:hover { color: #fff; background: #c33; border-radius: 4px; }
            #zoom_display { color: #fff; background: #2a2a2a; border: 1px solid #555; border-radius:4px;
                padding: 4px 10px; font-size: 13px; min-width: 60px; qproperty-alignment: AlignCenter; }
        """)
        tb = QHBoxLayout(self.toolbar); tb.setContentsMargins(8, 6, 8, 6); tb.setSpacing(8)

        self.btn_scroll = QPushButton("Scroll"); self.btn_scroll.setCheckable(True); self.btn_scroll.setChecked(True)
        self.btn_scroll.clicked.connect(lambda: self._set_mode(ViewMode.SCROLL)); self._hover_on(self.btn_scroll)

        self.btn_grid = QPushButton("Grid"); self.btn_grid.setCheckable(True)
        self.btn_grid.clicked.connect(lambda: self._set_mode(ViewMode.GRID)); self._hover_on(self.btn_grid)

        tb.addWidget(self.btn_scroll); tb.addWidget(self.btn_grid)

        # Nav bar — compact, centered page number
        tb.addStretch()
        self.nav_widget = QWidget()
        nl = QHBoxLayout(self.nav_widget); nl.setContentsMargins(0,0,0,0); nl.setSpacing(4)
        self.btn_prev = QPushButton("◀"); self.btn_prev.setFixedSize(30,30)
        self.btn_prev.clicked.connect(self.prev_page); self._hover_on(self.btn_prev)
        self.page_label = QLabel("1 / 1")
        self.page_label.setStyleSheet("QLabel { color: #bbb; font-size: 13px; }")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setFixedWidth(70)
        self.btn_next = QPushButton("▶"); self.btn_next.setFixedSize(30,30)
        self.btn_next.clicked.connect(self.next_page); self._hover_on(self.btn_next)
        nl.addWidget(self.btn_prev); nl.addWidget(self.page_label); nl.addWidget(self.btn_next)
        tb.addWidget(self.nav_widget)
        tb.addStretch()

        # Zoom controls: [-] [150%] [+]
        self.btn_zoom_out = QPushButton("−"); self.btn_zoom_out.setFixedSize(30,30)
        self.btn_zoom_out.clicked.connect(lambda: self._adjust_zoom(-1)); self._hover_on(self.btn_zoom_out)
        self.zoom_label = QLabel("100%"); self.zoom_label.setObjectName("zoom_display")
        self.zoom_label.setFixedWidth(60)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_zoom_in = QPushButton("+"); self.btn_zoom_in.setFixedSize(30,30)
        self.btn_zoom_in.clicked.connect(lambda: self._adjust_zoom(+1)); self._hover_on(self.btn_zoom_in)

        tb.addWidget(self.btn_zoom_out)
        tb.addWidget(self.zoom_label)
        tb.addWidget(self.btn_zoom_in)

        # Fit Width / Fit Height
        self.btn_fit_width = QPushButton("Fit W"); self.btn_fit_width.setCheckable(True)
        self.btn_fit_width.clicked.connect(self._on_fit_width); self._hover_on(self.btn_fit_width)

        self.btn_fit_height = QPushButton("Fit H"); self.btn_fit_height.setCheckable(True)
        self.btn_fit_height.setChecked(True)
        self.btn_fit_height.clicked.connect(self._on_fit_height); self._hover_on(self.btn_fit_height)

        self.zoom_combo = QComboBox(); self.zoom_combo.addItems(["100%","150%","200%","300%"])
        self.zoom_combo.setCurrentIndex(-1)
        self.zoom_combo.currentTextChanged.connect(self._on_combo)

        tb.addWidget(self.btn_fit_width); tb.addWidget(self.btn_fit_height)
        tb.addWidget(self.zoom_combo); tb.addStretch()

        self.label_filename = QLabel(""); self.label_filename.setStyleSheet("color: #777;"); tb.addWidget(self.label_filename)

        self.btn_close = QPushButton("✕"); self.btn_close.setObjectName("btn_close")
        self.btn_close.setFixedSize(26,26); self.btn_close.setToolTip("Close this document")
        self.btn_close.clicked.connect(self._on_close); tb.addWidget(self.btn_close)

        root.addWidget(self.toolbar)
        self._show_welcome()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

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
                if getattr(self,'_hover_widget',None) is w:
                    self._hover_pos = e.globalPosition().toPoint()
                    self._hover_timer.start(3000)
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

    def _on_close(self):
        self.close_document(); self.close_requested.emit()

    # ═══════════════ Public API ═══════════════

    def _destroy_welcome(self):
        if self._welcome_widget:
            self._welcome_widget.setParent(None); self._welcome_widget.deleteLater()
            self._welcome_widget = None


    def open_pdf(self, path: Path) -> None:
        import fitz
        PdfReaderWidget._cache.clear(); self._destroy_labels(); self._destroy_welcome()
        try: self.doc = fitz.open(path)
        except: self._show_welcome(); return
        if self.doc.is_encrypted:
            if not self.doc.authenticate(""):
                self.doc.close(); self.doc = None; self._show_welcome(); return
        self._path = path; self._total_pages = len(self.doc); self._current_page = 0
        self._btn_open_source = getattr(self, '_btn_open_source', 'dialog')
        self._zoom_mode = "fit_height"
        self.btn_fit_width.setChecked(False); self.btn_fit_height.setChecked(True)
        self.zoom_combo.setCurrentIndex(-1)
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True); self.btn_grid.setChecked(False)
        # Pre-compute zoom ratios (instant math — no rendering needed)
        page = self.doc[0]; pw, ph = page.rect.width, page.rect.height
        vw, vh = self._viewport_size()
        self._fw_ratio = vw / pw if pw > 0 else 1.0
        self._fh_ratio = vh / ph if ph > 0 else 1.0
        self._default_zoom_pct = int(self._fh_ratio * 100)
        self.zoom_label.setText(f"{self._default_zoom_pct}%")
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
        self._update_nav_ui(); self.label_filename.clear(); self._show_welcome()

    def go_to_page(self, num: int):
        if not self.doc: return
        num = max(1, min(num, self._total_pages))
        self._current_page = num - 1
        self._scroll_to_page_top()
        self._update_nav_ui()

    def next_page(self):
        if self.doc and self._current_page < self._total_pages - 1:
            self._current_page += 1; self._scroll_to_page_top(); self._update_nav_ui()

    def prev_page(self):
        if self.doc and self._current_page > 0:
            self._current_page -= 1; self._scroll_to_page_top(); self._update_nav_ui()

    def first_page(self): self.go_to_page(1)
    def last_page(self): self.go_to_page(self._total_pages)

    # ═══════════════ Zoom — instant ratio pre-compute ═══════════════

    def _start_pre_render(self):
        self._pre_render_idx = 0; self._pre_render_timer.start()

    def _pre_render_batch(self):
        if not self.doc: return
        vw, vh = self._viewport_size(); end = min(self._pre_render_idx + BATCH_SIZE, self._total_pages)
        for pi in range(self._pre_render_idx, end):
            self._get_or_render(pi, vw, vh)
        self._pre_render_idx = end
        if self._pre_render_idx < self._total_pages:
            self._pre_render_timer.start()
        else:
            self._update_label_pixmaps()

    def _set_zoom_pct(self, pct: int):
        """Set zoom by integer percentage. Updates display instantly, triggers re-render."""
        pct = max(25, min(400, pct))
        factor = pct / 100.0
        if self._zoom_mode == "fit_height" and pct == self._default_zoom_pct:
            return  # already at default
        self._zoom_mode = factor
        self.btn_fit_width.setChecked(False); self.btn_fit_height.setChecked(False)
        self.zoom_combo.setCurrentIndex(-1)
        self.zoom_label.setText(f"{pct}%")
        PdfReaderWidget._cache.clear()
        if self.doc:
            self._update_label_pixmaps(); self._layout_labels()
        self._start_pre_render()
        self._show_zoom_popup(pct)

    def _set_fit_mode(self, mode: str):
        """Apply fit_width or fit_height instantly via pre-computed ratio."""
        if self._zoom_mode == mode: return
        self._zoom_mode = mode
        self.btn_fit_width.setChecked(mode == "fit_width")
        self.btn_fit_height.setChecked(mode == "fit_height")
        self.zoom_combo.setCurrentIndex(-1)
        if mode == "fit_height":
            self.zoom_label.setText(f"{self._default_zoom_pct}%")
        else:
            pct = int(self._fw_ratio * 100)
            self.zoom_label.setText(f"{pct}%")
        PdfReaderWidget._cache.clear()
        if self.doc:
            self._update_label_pixmaps(); self._layout_labels()
        self._start_pre_render()

    def _adjust_zoom(self, delta_pct: int):
        """+/- buttons: adjust zoom by 1%."""
        cur = self._current_zoom_pct()
        self._set_zoom_pct(cur + delta_pct)

    def _current_zoom_pct(self) -> int:
        if self._zoom_mode == "fit_width":
            return int(self._fw_ratio * 100)
        if self._zoom_mode == "fit_height":
            return self._default_zoom_pct
        return int(self._zoom_mode * 100)

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
        for l in self._labels:
            l.setParent(None); l.deleteLater()
        self._labels.clear(); self._pre_render_idx = 0

    def _layout_labels(self):
        vw, vh = self._viewport_size()
        spacing = 16; margin = 20

        if self._view_mode == ViewMode.SCROLL:
            # Clear Y offsets; compute page heights for fast scroll tracking
            self._page_heights = []
            y = margin; max_w = 0
            for pi, l in enumerate(self._labels):
                pix = l.pixmap()
                if pix is None or pix.isNull():
                    pix = self._get_or_render(pi, vw, vh)
                    if pix: l.setPixmap(pix); l.setFixedSize(pix.size())
                h = pix.height() if pix else 800; w = pix.width() if pix else 600
                l.setStyleSheet("QLabel { background: white; }")
                l.setCursor(Qt.CursorShape.ArrowCursor)
                l.move(margin, y); l.show()
                max_w = max(max_w, w)
                self._page_heights.append(y)  # store top-Y
                y += h + spacing
            self.page_container.setFixedSize(max_w + 2*margin, y - spacing + margin)

        elif self._view_mode == ViewMode.GRID:
            self._page_heights = []
            COLS = 3; gutter = 16
            thumb_w = max(80, (vw - 2*margin - (COLS-1)*gutter) // COLS)
            thumb_h = int(thumb_w * 1.414)
            for pi, l in enumerate(self._labels):
                pix = self._get_or_render(pi, thumb_w, thumb_h, force_fit=True)
                if pix: l.setPixmap(pix); l.setFixedSize(pix.size())
                l.setStyleSheet("QLabel { background: white; border: 1px solid #555; }")
                l.setCursor(Qt.CursorShape.PointingHandCursor)
                col, row = pi % COLS, pi // COLS
                x = margin + col*(thumb_w + gutter)
                y = margin + row*(thumb_h + gutter)
                l.move(x, y); l.show()
            rows = (self._total_pages + COLS - 1)//COLS
            self.page_container.setFixedSize(
                2*margin + COLS*thumb_w + (COLS-1)*gutter,
                2*margin + rows*thumb_h + (rows-1)*gutter)

    # ═══════════════ Scroll tracking (fast: binary search on pre-computed Ys) ═══════════════

    def _scroll_to_page_top(self):
        """Scroll such that current_page's top aligns with viewport top."""
        if not self._page_heights or self._current_page >= len(self._page_heights):
            return
        target = self._page_heights[self._current_page]
        self.scroll_area.verticalScrollBar().setValue(max(0, target))

    def _track_scroll_page(self):
        """Fast page tracking: binary search on pre-computed page Y positions.
        Find which page top is closest to (scroll_pos + viewport/2)."""
        if not self.doc or self._view_mode != ViewMode.SCROLL or not self._page_heights:
            return
        sb = self.scroll_area.verticalScrollBar()
        scroll_y = sb.value(); mid = scroll_y + sb.pageStep() // 2
        # Binary search on _page_heights (sorted list of page-top Y positions)
        arr = self._page_heights
        lo, hi = 0, len(arr)-1
        while lo < hi:
            m = (lo + hi + 1)//2
            if arr[m] <= mid: lo = m
            else: hi = m - 1
        if lo != self._current_page:
            self._current_page = lo; self._update_nav_ui()

    # ═══════════════ Zoom key + Render ═══════════════

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

    def _on_grid_dbl_click(self, p):
        """Grid double-click: switch to Scroll, apply fit height, jump to page.
        Ignored in Scroll mode."""
        if self._view_mode != ViewMode.GRID:
            return
        self._current_page = p
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True); self.btn_grid.setChecked(False)
        self._zoom_mode = "fit_height"
        self.btn_fit_width.setChecked(False); self.btn_fit_height.setChecked(True)
        self.zoom_combo.setCurrentIndex(-1)
        self.zoom_label.setText(f"{self._default_zoom_pct}%")
        PdfReaderWidget._cache.clear()
        self._update_label_pixmaps(); self._layout_labels()
        self._start_pre_render()
        self._scroll_to_page_top()
        self._update_nav_ui()

    # ═══════════════ Slots ═══════════════

    def _on_fit_width(self):
        self._set_fit_mode("fit_width")
        if self.doc: self._scroll_to_page_top()

    def _on_fit_height(self):
        self._set_fit_mode("fit_height")
        if self.doc: self._scroll_to_page_top()

    def _on_combo(self, text):
        f = {"100%":100,"150%":150,"200%":200,"300%":300}.get(text)
        if f: self._set_zoom_pct(f)

    def _on_resize(self):
        if self.doc:
            # Recompute fit ratios
            page = self.doc[0]; pw,ph = page.rect.width, page.rect.height
            vw,vh = self._viewport_size()
            self._fw_ratio = vw/pw if pw>0 else 1.0; self._fh_ratio = vh/ph if ph>0 else 1.0
            self._default_zoom_pct = int(self._fh_ratio*100)
            PdfReaderWidget._cache.clear()
            self._update_label_pixmaps(); self._layout_labels()
            self._start_pre_render()
            self.zoom_label.setText(
                f"{int(self._fw_ratio*100)}%" if self._zoom_mode=="fit_width"
                else f"{self._default_zoom_pct}%" if self._zoom_mode=="fit_height"
                else f"{int(self._zoom_mode*100)}%")

    def _update_nav_ui(self):
        self.page_label.setText(f"{self._current_page+1} / {self._total_pages}")
        self.btn_prev.setEnabled(self._current_page>0)
        self.btn_next.setEnabled(self._current_page<self._total_pages-1)

    # ═══════════════ Welcome ═══════════════

    def _show_welcome(self, drop_text="Drop PDF here to read", load_btn_text="Load file..."):
        vw,vh = self._viewport_size()
        for c in self.page_container.findChildren(QWidget):
            if c is not self.page_container and c is not self._zoom_popup and c not in self._labels:
                c.setParent(None); c.deleteLater()

        center = QWidget(self.page_container)
        center.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(center); cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setSpacing(12)
        self._welcome_text = QLabel(drop_text)
        self._welcome_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome_text.setStyleSheet("QLabel { color: #555; font-size: 16px; background: transparent; }")
        cl.addWidget(self._welcome_text)
        self._welcome_btn = QPushButton(load_btn_text)
        self._welcome_btn.setFixedWidth(120); self._welcome_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._welcome_btn.setStyleSheet(
            "QPushButton { color: #666; background: #2a2a2a; border: 1px solid #444; "
            "border-radius: 4px; padding: 5px 16px; font-size: 12px; }"
            "QPushButton:hover { color: #999; background: #333; border-color: #555; }")
        self._welcome_btn.clicked.connect(lambda: self.open_requested.emit())
        cl.addWidget(self._welcome_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        center.adjustSize()
        cx = (vw - center.width())//2; cy = (vh - center.height())//2
        center.move(cx, cy); center.show()
        center.raise_()   # ensure it's on top of any old labels
        self._welcome_widget = center

        # Drag-drop onto reader
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

    # ═══════════════ Touchpad pinch-zoom (Scroll mode only) ═══════════════

    def wheelEvent(self, e):
        if self._view_mode != ViewMode.SCROLL:
            super().wheelEvent(e); return

        ad_y = e.angleDelta().y() if e.angleDelta() else 0
        pd_y = e.pixelDelta().y() if e.pixelDelta() else 0
        pinch = (e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if not pinch:
            try:
                ph = e.phase(); pinch = (int(ph) >= 1)
            except (AttributeError,TypeError): pass
        if not pinch and pd_y != 0 and ad_y != 0:
            # macOS pinch: pixelDelta non-zero + angleDelta significantly larger
            if abs(ad_y) > abs(pd_y) * 1.5:
                pinch = True

        if pinch:
            self._set_zoom_pct(self._current_zoom_pct() + (1 if ad_y > 0 else -1))
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
