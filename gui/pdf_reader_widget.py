"""PDF reader — LRU cache, dual-timer pages, on-demand prefetch."""

from bisect import bisect_right
from collections import OrderedDict
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent, QWheelEvent, QIntValidator
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget, QToolTip,
)


class ViewMode(Enum):
    SCROLL = "scroll"
    GRID = "grid"


RENDER_SCALE = 2; RESIZE_DEBOUNCE = 350; BATCH = 30
MAX_CACHE_MB = 250; CACHE_TARGET_MB = 180
PAGE_THROTTLE_MS = 30  # rough page update
PAGE_DEBOUNCE_MS = 150  # precise bisect calibration


class PdfReaderWidget(QWidget):
    document_changed = pyqtSignal(str)
    close_requested = pyqtSignal()
    open_requested = pyqtSignal()
    _cache: OrderedDict = OrderedDict()
    _cache_memory_bytes: int = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None; self._path = None
        self._current_page = 0; self._total_pages = 0
        self._view_mode = ViewMode.SCROLL
        self._zoom_mode = "fit_height"
        self._fw_ratio = self._fh_ratio = 1.0
        self._labels: list[QLabel] = []
        self._page_heights: list[int] = []
        self._pinch_acc = 0
        self._btn_open_source = 'dialog'

        self._resize_timer = QTimer(self); self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(RESIZE_DEBOUNCE)
        self._resize_timer.timeout.connect(self._on_resize)

        self._scroll_throttle = QTimer(self); self._scroll_throttle.setSingleShot(True)
        self._scroll_throttle.setInterval(PAGE_THROTTLE_MS)
        self._scroll_throttle.timeout.connect(self._do_throttle_page)

        self._scroll_debounce = QTimer(self); self._scroll_debounce.setSingleShot(True)
        self._scroll_debounce.setInterval(PAGE_DEBOUNCE_MS)
        self._scroll_debounce.timeout.connect(self._do_debounce_calibration)

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
            "QLabel{background:rgba(0,0,0,180);color:#fff;font-size:18px;"
            "font-weight:bold;border-radius:10px;padding:8px 16px;}")
        self._zoom_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_popup.hide()

        self._pre_render_idx = 0; self._welcome = None
        self._welcome_drop = "Drop PDF here to read"
        self._welcome_btn_text = "Load file..."
        self._init_ui()

    def showEvent(self, e):
        super().showEvent(e)
        if not self.doc and not self._welcome:
            # Defer to ensure layout is complete
            QTimer.singleShot(100, self._try_show_welcome)

    def _try_show_welcome(self):
        """Safely show welcome. Retries if viewport not yet sized."""
        try:
            if self.doc or self._welcome: return
            vp = self.scroll_area.viewport()
            if vp and vp.width() > 100 and vp.height() > 50:
                self._show_welcome()
            else:
                QTimer.singleShot(200, self._try_show_welcome)  # retry
        except Exception: pass

    # ═══════════ UI ═══════════

    def _init_ui(self):
        self.setStyleSheet("background-color:#2c2c2c;")
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet(
            "QScrollArea{background:#2c2c2c;border:none;}"
            "QScrollBar:vertical{background:#1e1e1e;width:10px;margin:0}"
            "QScrollBar::handle:vertical{background:#555;border-radius:4px;min-height:30px}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}"
            "QScrollBar:horizontal{background:#1e1e1e;height:10px;margin:0}"
            "QScrollBar::handle:horizontal{background:#555;border-radius:4px;min-width:30px}"
            "QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0}")
        self.scroll_area.verticalScrollBar().valueChanged.connect(
            self._on_scrollbar_changed)
        self.scroll_area.setAcceptDrops(True)

        self.page_container = QWidget()
        self.page_container.setStyleSheet("background:transparent;")
        self.scroll_area.setWidget(self.page_container)
        root.addWidget(self.scroll_area, 1)

        # toolbar
        self.toolbar = QWidget(); self.toolbar.setObjectName("reader_toolbar")
        self.toolbar.setStyleSheet(
            "QWidget#reader_toolbar{background:#1e1e1e;border-top:1px solid #3a3a3a}"
            "QPushButton{color:#ccc;background:#333;border:1px solid #555;border-radius:4px;padding:5px 12px;font-size:13px}"
            "QPushButton:hover{background:#444}"
            "QPushButton:checked{background:#007aff;color:#fff;border-color:#007aff}"
            "QPushButton:disabled{color:#555;background:#2a2a2a}"
            "QLineEdit{color:#fff;background:#2a2a2a;border:1px solid #555;border-radius:4px;padding:4px 6px;font-size:13px}"
            "QLabel{color:#999;font-size:13px}"
            "#btn_close{color:#ccc;background:transparent;border:none;font-size:16px;padding:2px 6px}"
            "#btn_close:hover{color:#fff;background:#c33;border-radius:4px}")
        tb = QHBoxLayout(self.toolbar); tb.setContentsMargins(8,6,8,6); tb.setSpacing(8)

        self.btn_scroll = QPushButton("Scroll")
        self.btn_scroll.setCheckable(True); self.btn_scroll.setChecked(True)
        self.btn_scroll.clicked.connect(lambda: self._set_mode(ViewMode.SCROLL))
        self._hover_on(self.btn_scroll)

        self.btn_grid = QPushButton("Grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.clicked.connect(lambda: self._set_mode(ViewMode.GRID))
        self._hover_on(self.btn_grid)

        tb.addWidget(self.btn_scroll); tb.addWidget(self.btn_grid)
        tb.addStretch()

        self.btn_prev = QPushButton("◀"); self.btn_prev.setFixedSize(34,34)
        self.btn_prev.clicked.connect(self.prev_page)
        self._hover_on(self.btn_prev)

        self.page_label = QLabel("1 / 1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setFixedWidth(70)
        self.page_label.setStyleSheet("QLabel{color:#bbb}")

        self.btn_next = QPushButton("▶"); self.btn_next.setFixedSize(34,34)
        self.btn_next.clicked.connect(self.next_page)
        self._hover_on(self.btn_next)

        tb.addWidget(self.btn_prev); tb.addWidget(self.page_label); tb.addWidget(self.btn_next)
        tb.addStretch()

        self.btn_zoom_out = QPushButton("−"); self.btn_zoom_out.setFixedSize(34,34)
        self.btn_zoom_out.clicked.connect(lambda: self._adjust_zoom(-5))
        self._hover_on(self.btn_zoom_out)

        self.zoom_edit = QLineEdit("100"); self.zoom_edit.setObjectName("zoom_edit")
        self.zoom_edit.setFixedWidth(55)
        self.zoom_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_edit.setMaxLength(3)
        self.zoom_edit.setValidator(QIntValidator(25, 300, self))
        self.zoom_edit.returnPressed.connect(self._on_zoom_edit)
        self.zoom_edit.editingFinished.connect(self._on_zoom_edit)

        self.btn_zoom_in = QPushButton("+"); self.btn_zoom_in.setFixedSize(34,34)
        self.btn_zoom_in.clicked.connect(lambda: self._adjust_zoom(+5))
        self._hover_on(self.btn_zoom_in)

        tb.addWidget(self.btn_zoom_out); tb.addWidget(self.zoom_edit); tb.addWidget(self.btn_zoom_in)

        self.btn_fit_width = QPushButton("Fit W")
        self.btn_fit_width.setCheckable(True)
        self.btn_fit_width.clicked.connect(self._on_fit_width)
        self._hover_on(self.btn_fit_width)

        self.btn_fit_height = QPushButton("Fit H")
        self.btn_fit_height.setCheckable(True); self.btn_fit_height.setChecked(True)
        self.btn_fit_height.clicked.connect(self._on_fit_height)
        self._hover_on(self.btn_fit_height)

        tb.addWidget(self.btn_fit_width); tb.addWidget(self.btn_fit_height); tb.addStretch()

        self.label_filename = QLabel("")
        self.label_filename.setStyleSheet("color:#777;")
        tb.addWidget(self.label_filename)

        self.btn_close = QPushButton("✕"); self.btn_close.setObjectName("btn_close")
        self.btn_close.setFixedSize(26,26); self.btn_close.setToolTip("Close this document")
        self.btn_close.clicked.connect(
            lambda: (self.close_document(), self.close_requested.emit()))
        tb.addWidget(self.btn_close)

        root.addWidget(self.toolbar)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setMouseTracking(True)

    def _hover_on(self, widget):
        widget._oe = widget.enterEvent; widget._ol = widget.leaveEvent
        def enter_event(e):
            self._hover_widget = widget; self._hover_timer.start(3000)
            if widget._oe: widget._oe(e)
        def leave_event(e):
            self._hover_timer.stop(); QToolTip.hideText()
            if widget._ol: widget._ol(e)
        widget.enterEvent = enter_event; widget.leaveEvent = leave_event
        if hasattr(widget, 'mouseMoveEvent'):
            widget._om = widget.mouseMoveEvent
            def move_event(e):
                if getattr(self, '_hover_widget', None) is widget:
                    self._hover_pos = e.globalPosition().toPoint()
                    self._hover_timer.start(3000)
                if widget._om: widget._om(e)
            widget.mouseMoveEvent = move_event

    def _show_tooltip(self):
        w = getattr(self, '_hover_widget', None)
        if w and hasattr(self, '_hover_pos'):
            t = w.toolTip()
            if t: QToolTip.showText(self._hover_pos, t, self)

    # ═══════════ Mode ═══════════

    def _set_mode(self, mode: ViewMode):
        self._view_mode = mode
        self.btn_scroll.setChecked(mode == ViewMode.SCROLL)
        self.btn_grid.setChecked(mode == ViewMode.GRID)
        if self.doc:
            self._layout_labels()
            if mode == ViewMode.SCROLL:
                self._scroll_to_page_top()

    # ═══════════ Open / Close ═══════════

    def open_pdf(self, path: Path) -> None:
        import fitz
        self._cancel_deferred_renders()
        PdfReaderWidget._clear_cache(); self._destroy_labels(); self._destroy_welcome()
        try: self.doc = fitz.open(path)
        except Exception: self._show_welcome(); return
        if self.doc.is_encrypted:
            if not self.doc.authenticate(""):
                self.doc.close(); self.doc = None; self._show_welcome(); return
        self._path = path
        self._total_pages = len(self.doc); self._current_page = 0
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
        self._pre_render_all()
        self._layout_labels()
        self._update_nav_ui()
        self.label_filename.setText(path.name)
        self.document_changed.emit(str(path))
        self.setFocus()

    def close_document(self):
        self._cancel_deferred_renders()
        if self.doc: self.doc.close(); self.doc = None
        self._path = None; self._total_pages = 0; self._current_page = 0
        PdfReaderWidget._clear_cache()
        self.scroll_area.verticalScrollBar().blockSignals(True)
        self._destroy_labels()
        self._page_heights.clear(); self._update_nav_ui(); self.label_filename.clear()
        self.page_container.setFixedSize(0, 0); self.page_container.resize(0, 0)
        self.scroll_area.verticalScrollBar().blockSignals(False)
        self._show_welcome()

    def _cancel_deferred_renders(self):
        """Cancel all pending timers to prevent stale callbacks."""
        self._pending_zoom_pct = None
        self._resize_timer.stop()
        self._scroll_throttle.stop()
        self._scroll_debounce.stop()

    # ═══════════ Zoom — two-pass: instant scale → sharp render ═══════════

    def _current_zoom_pct(self) -> int:
        if self._zoom_mode == "fit_width":
            return max(50, min(300, int(self._fw_ratio * 100)))
        if self._zoom_mode == "fit_height":
            return self._default_zoom_pct
        return max(50, min(300, int(self._zoom_mode * 100)))

    def _set_zoom_pct(self, pct: int, skip_deferred: bool = False):
        """Two-pass zoom with correct relative scaling.
        Pass 1 (instant): QPixmap.scaled() using new/old ratio — <1ms visual feedback.
        Pass 2 (deferred): 180ms → PyMuPDF re-render for sharp quality."""
        pct = max(50, min(300, int(round(pct))))
        if not self.doc or not self._labels:
            self._zoom_mode = pct / 100.0
            self.zoom_edit.setText(str(pct))
            return

        old_pct = self._current_zoom_pct()
        new_factor = pct / 100.0
        old_factor = old_pct / 100.0

        # Update state BEFORE rendering so _zoom_key sees new zoom
        self._zoom_mode = new_factor
        self.btn_fit_width.setChecked(False)
        self.btn_fit_height.setChecked(False)
        self.zoom_edit.setText(str(pct))

        # Pass 1: instant smooth pixel scaling using correct relative ratio
        scale = new_factor / old_factor if old_factor > 0 else 1.0
        if abs(scale - 1.0) > 0.001:
            from PyQt6.QtCore import Qt as QtCore
            for label in self._labels:
                try:
                    pix = label.pixmap()
                    if pix is None or pix.isNull(): continue
                    pw, ph = pix.size().width(), pix.size().height()
                    tw, th = max(1, int(pw * scale)), max(1, int(ph * scale))
                    label.setPixmap(pix.scaled(tw, th,
                        QtCore.AspectRatioMode.IgnoreAspectRatio,
                        QtCore.TransformationMode.SmoothTransformation))
                    label.setFixedSize(tw, th)
                except Exception:
                    pass
            self._layout_labels()

        self._show_zoom_popup(pct)

        # Pass 2: deferred sharp render (skip for pinch / already cached)
        if not skip_deferred:
            vw, vh = self._viewport_size()
            zk = self._zoom_key(vw, vh)
            if (0, zk) not in PdfReaderWidget._cache:
                self._pending_zoom_pct = pct
                QTimer.singleShot(180, self._sharp_render)

    def _sharp_render(self):
        """Deferred real rendering: only re-render cache-missed pages at current zoom."""
        if not self.doc or not self._labels or self._pending_zoom_pct is None:
            return
        try:
            pct = self._pending_zoom_pct; self._zoom_mode = pct / 100.0
            vw, vh = self._viewport_size()
            zk = self._zoom_key(vw, vh); any_miss = False
            for pi, label in enumerate(self._labels):
                try:
                    key = (pi, zk)
                    pix = PdfReaderWidget._cache_get(key)
                    if pix is None:
                        pix = self._get_or_render(pi, vw, vh)
                        any_miss = True
                    if pix: label.setPixmap(pix); label.setFixedSize(pix.size())
                except Exception: pass
            if any_miss: self._layout_labels()
        except Exception: pass
        finally:
            self._pending_zoom_pct = None

    def _adjust_zoom(self, delta: int):
        if not self.doc: return
        self._set_zoom_pct(self._current_zoom_pct() + delta)

    def _on_zoom_edit(self):
        if not self.doc: return
        txt = self.zoom_edit.text().strip()
        if not txt:
            self.zoom_edit.setText(str(self._current_zoom_pct()))
            return
        try:
            v = int(txt); v = max(50, min(500, v))
            self._set_zoom_pct(v)
        except ValueError:
            self.zoom_edit.setText(str(self._current_zoom_pct()))

    def _show_zoom_popup(self, pct):
        self._zoom_popup.setText(f"🔍 {pct}%"); self._zoom_popup.adjustSize()
        r = self.rect(); x = (r.width() - self._zoom_popup.width()) // 2
        y = max(0, r.height() // 3)
        self._zoom_popup.move(x, y); self._zoom_popup.show(); self._zoom_popup.raise_()
        self._zoom_popup_timer.start()

    def _hide_zoom_popup(self): self._zoom_popup.hide()

    def _on_fit_width(self):
        if not self.doc: return
        if self._zoom_mode == "fit_width": return
        self._apply_fit_mode("fit_width", max(50, min(300, int(self._fw_ratio * 100))))

    def _on_fit_height(self):
        if not self.doc: return
        if self._zoom_mode == "fit_height": return
        self._apply_fit_mode("fit_height", self._default_zoom_pct)

    def _apply_fit_mode(self, mode: str, pct: int):
        """Fit W/H: same two-pass zoom as _set_zoom_pct."""
        if not self.doc or not self._labels:
            self._zoom_mode = mode
            self.btn_fit_width.setChecked(mode == "fit_width")
            self.btn_fit_height.setChecked(mode == "fit_height")
            self.zoom_edit.setText(str(pct))
            return

        old_pct = self._current_zoom_pct()
        old_factor = old_pct / 100.0
        new_factor = pct / 100.0

        self._zoom_mode = mode
        self.btn_fit_width.setChecked(mode == "fit_width")
        self.btn_fit_height.setChecked(mode == "fit_height")
        self.zoom_edit.setText(str(pct))

        # Pass 1: instant relative scaling
        scale = new_factor / old_factor if old_factor > 0 else 1.0
        if abs(scale - 1.0) > 0.001:
            from PyQt6.QtCore import Qt as QtCore
            for label in self._labels:
                try:
                    pix = label.pixmap()
                    if pix is None or pix.isNull(): continue
                    pw, ph = pix.size().width(), pix.size().height()
                    tw, th = max(1, int(pw * scale)), max(1, int(ph * scale))
                    label.setPixmap(pix.scaled(tw, th,
                        QtCore.AspectRatioMode.IgnoreAspectRatio,
                        QtCore.TransformationMode.SmoothTransformation))
                    label.setFixedSize(tw, th)
                except Exception:
                    pass
            self._layout_labels()

        self._show_zoom_popup(pct)
        self._pending_zoom_pct = pct
        QTimer.singleShot(180, self._sharp_render)

    # ═══════════ Labels ═══════════

    def _build_labels(self):
        for _ in range(self._total_pages):
            label = QLabel(); label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setParent(self.page_container); label.hide()
            self._labels.append(label)

    def _destroy_labels(self):
        self.scroll_area.verticalScrollBar().blockSignals(True)
        for label in self._labels:
            label.setParent(None); label.deleteLater()
        self._labels.clear(); self._pre_render_idx = 0
        self.scroll_area.verticalScrollBar().blockSignals(False)

    def _layout_labels(self):
        vw, vh = self._viewport_size(); sp, mg = 16, 20

        if self._view_mode == ViewMode.SCROLL:
            self._page_heights = []; y = mg; mx = 0
            for pi, label in enumerate(self._labels):
                pix = label.pixmap()
                if not pix or pix.isNull():
                    pix = self._get_or_render(pi, vw, vh)
                    if pix: label.setPixmap(pix); label.setFixedSize(pix.size())
                h = pix.height() if pix else 800; w = pix.width() if pix else 600
                label.setStyleSheet("QLabel{background:white;}")
                label.setCursor(Qt.CursorShape.ArrowCursor)
                label.move(mg, y); label.show()
                mx = max(mx, w); self._page_heights.append(y); y += h + sp
            self.page_container.setFixedSize(mx + 2*mg, y - sp + mg)

        elif self._view_mode == ViewMode.GRID:
            self._page_heights = []
            COLS = 3; gutter = 20; side_margin = 20
            usable = vw - 2*side_margin - (COLS-1)*gutter
            thumb_w = max(120, usable // COLS); thumb_h = int(thumb_w * 1.414)
            grid_w = COLS*thumb_w + (COLS-1)*gutter; left = (vw - grid_w) // 2

            for pi, label in enumerate(self._labels):
                pix = self._get_or_render(pi, thumb_w, thumb_h, force_fit=True)
                if pix: label.setPixmap(pix); label.setFixedSize(pix.size())
                label.setStyleSheet("QLabel{background:white;border:1px solid #555;}")
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                col, row = pi % COLS, pi // COLS
                label.move(left + col*(thumb_w + gutter), mg + row*(thumb_h + gutter))
                label.show()
                page_idx = pi
                label.mouseDoubleClickEvent = lambda ev, p=page_idx: self._on_grid_dbl_click(p)

            rows = (self._total_pages + COLS - 1) // COLS
            self.page_container.setFixedSize(vw, 2*mg + rows*thumb_h + (rows-1)*gutter)

    def _on_grid_dbl_click(self, page_idx: int):
        if self._view_mode != ViewMode.GRID: return
        self._current_page = page_idx
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True); self.btn_grid.setChecked(False)
        self._apply_fit_mode("fit_height", self._default_zoom_pct)
        self._scroll_to_page_top(); self._update_nav_ui()

    # ═══════════ Pre-render ═══════════

    def _pre_render_all(self):
        self._pre_render_idx = 0; self._pre_render_timer.start()

    def _pre_render_batch(self):
        if not self.doc: return
        vw, vh = self._viewport_size()
        end = min(self._pre_render_idx + BATCH, self._total_pages)
        for pi in range(self._pre_render_idx, end):
            self._get_or_render(pi, vw, vh)
        self._pre_render_idx = end
        if self._pre_render_idx < self._total_pages:
            self._pre_render_timer.start()

    # ═══════════ Scroll tracking (bisect, O(log n)) ═══════════

    def _scroll_to_page_top(self):
        if not self._page_heights or self._current_page >= len(self._page_heights):
            return
        self.scroll_area.verticalScrollBar().setValue(
            max(0, self._page_heights[self._current_page]))

    def _on_scrollbar_changed(self, value):
        """Scrollbar moved — fire both throttle (rough) and debounce (precise)."""
        if self.doc:
            self._scroll_throttle.start()
            self._scroll_debounce.start()

    def _do_throttle_page(self):
        """Throttle: only update when the estimated page has changed significantly
        (jumped >1 page away). This prevents flicker from small ±1 page oscillations
        where the rough-division estimate briefly disagrees with the bisect ground truth.

        For small movements (±1 page), the debounce timer is the sole authority."""
        try:
            if not self.doc or not self._page_heights or not self._total_pages: return
            if not hasattr(self, '_throttle_last'):
                self._throttle_last = self._current_page
            sb = self.scroll_area.verticalScrollBar()
            if not sb: return
            total_h = self.page_container.height()
            if total_h <= 0: return
            avg_h = total_h / self._total_pages
            rough = max(0, min(self._total_pages - 1, int(sb.value() / avg_h)))
            # Only propagate if the jump is significant (>1 page difference).
            # This avoids racing with the debounce bisect for ±1 flicker.
            if abs(rough - self._throttle_last) > 1:
                self._current_page = rough
                self._update_nav_ui()
            self._throttle_last = rough
        except Exception: pass

    def _do_debounce_calibration(self):
        """Precise calibration via bisect on _page_heights — O(log n)."""
        try:
            if not self.doc or not self._page_heights:
                return
            sb = self.scroll_area.verticalScrollBar()
            if not sb: return
            mid = max(0, sb.value() + sb.pageStep() // 2)
            idx = bisect_right(self._page_heights, mid) - 1
            if idx < 0: idx = 0
            elif idx >= len(self._page_heights): idx = len(self._page_heights) - 1
            if idx != self._current_page:
                self._current_page = idx
                self._update_nav_ui()
                self._prefetch_around(idx)
        except Exception:
            pass

    def _prefetch_around(self, page_idx: int):
        """Low-priority prefetch of N-1 and N+1 pages after scroll stops.
        Uses a single-shot timer that re-validates self.doc before executing."""
        if not self.doc: return
        vw, vh = self._viewport_size()
        for pi in (page_idx - 1, page_idx + 1):
            if 0 <= pi < self._total_pages:
                key = (pi, self._zoom_key(vw, vh))
                if key not in PdfReaderWidget._cache:
                    # Deferred prefetch — validates doc is still alive before rendering
                    QTimer.singleShot(300, lambda p=pi, w=vw, h=vh: self._safe_prefetch(p, w, h))

    def _safe_prefetch(self, pi, vw, vh):
        """Prefetch guard: only render if doc and labels still alive."""
        if not self.doc or not self._labels or pi >= len(self._labels):
            return
        try:
            self._get_or_render(pi, vw, vh)
        except Exception:
            pass

    # ═══════════ Render ═══════════

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
        mat = fitz.Matrix(zoom * RENDER_SCALE, zoom * RENDER_SCALE)
        pix = page.get_pixmap(matrix=mat)
        qimg = QImage(pix.samples, pix.width, pix.height,
                      pix.stride, QImage.Format.Format_RGB888)
        tw = max(1, pix.width // RENDER_SCALE)
        th = max(1, pix.height // RENDER_SCALE)
        from PyQt6.QtCore import Qt as QtCore
        return QPixmap.fromImage(qimg).scaled(
            tw, th,
            QtCore.AspectRatioMode.IgnoreAspectRatio,
            QtCore.TransformationMode.SmoothTransformation)

    def _viewport_size(self):
        vp = self.scroll_area.viewport()
        return (max(800, vp.width() - 4), max(600, vp.height() - 4))

    @classmethod
    def _cache_put(cls, key, pix: QPixmap):
        """LRU insert with memory-aware eviction. Pinned keys never evicted."""
        # Move to end (most-recently-used) if already present
        if key in cls._cache:
            cls._cache.move_to_end(key)
            cls._cache[key] = pix
            return
        # Estimate memory: RGBA = width * height * 4 bytes
        mem = pix.width() * pix.height() * 4
        cls._cache_memory_bytes += mem
        cls._cache[key] = pix
        # Evict until under target, skipping pinned entries
        while cls._cache_memory_bytes > MAX_CACHE_MB * 1024 * 1024 and len(cls._cache) > 1:
            oldest_key, oldest_pix = next(iter(cls._cache.items()))
            pi, zk = oldest_key
            if zk in ("fh", "fw"):  # pinned: fit_height / fit_width for first page
                break  # cannot evict, will exceed limit (acceptable edge case)
            ow, oh = oldest_pix.width(), oldest_pix.height()
            cls._cache_memory_bytes -= ow * oh * 4
            cls._cache.popitem(last=False)

    @classmethod
    def _cache_get(cls, key):
        if key in cls._cache:
            cls._cache.move_to_end(key)
            return cls._cache[key]
        return None

    @classmethod
    def _clear_cache(cls):
        cls._cache.clear()
        cls._cache_memory_bytes = 0

    def _get_or_render(self, pi, vw, vh=99999, force_fit=False):
        key = (pi, self._zoom_key(vw, vh))
        cached = PdfReaderWidget._cache_get(key)
        if cached is not None:
            return cached
        pix = PdfReaderWidget._render_page(self.doc, pi, key[1], vw, vh, force_fit)
        PdfReaderWidget._cache_put(key, pix)
        return pix

    # ═══════════ Navigation ═══════════

    def go_to_page(self, n):
        if not self.doc: return
        n = max(1, min(n, self._total_pages))
        self._current_page = n - 1; self._scroll_to_page_top(); self._update_nav_ui()

    def next_page(self):
        if self.doc and self._current_page < self._total_pages - 1:
            self._current_page += 1; self._scroll_to_page_top(); self._update_nav_ui()

    def prev_page(self):
        if self.doc and self._current_page > 0:
            self._current_page -= 1; self._scroll_to_page_top(); self._update_nav_ui()

    def first_page(self): self.go_to_page(1)
    def last_page(self): self.go_to_page(self._total_pages)

    # ═══════════ Slots ═══════════

    def _on_resize(self):
        if not self.doc or not self._labels:
            return
        page = self.doc[0]; pw, ph = page.rect.width, page.rect.height
        vw, vh = self._viewport_size()
        old_fw, old_fh = self._fw_ratio, self._fh_ratio
        self._fw_ratio = vw / pw if pw > 0 else 1.0
        self._fh_ratio = vh / ph if ph > 0 else 1.0
        self._default_zoom_pct = max(50, min(300, int(self._fh_ratio * 100)))

        # Compute relative scale from old viewport to new viewport
        cur_pct = self._current_zoom_pct()
        new_factor = cur_pct / 100.0
        old_factor = old_fh if self._zoom_mode == "fit_height" else (
            old_fw if self._zoom_mode == "fit_width" else self._zoom_mode if isinstance(self._zoom_mode, float) else old_fh)
        old_factor_val = old_factor if isinstance(old_factor, (int, float)) else old_fh
        scale = new_factor / old_factor_val if old_factor_val > 0 else 1.0

        if abs(scale - 1.0) > 0.001:
            from PyQt6.QtCore import Qt as QtCore
            for label in self._labels:
                try:
                    pix = label.pixmap()
                    if pix is None or pix.isNull(): continue
                    pw_i, ph_i = pix.size().width(), pix.size().height()
                    tw, th = max(1, int(pw_i * scale)), max(1, int(ph_i * scale))
                    label.setPixmap(pix.scaled(tw, th,
                        QtCore.AspectRatioMode.IgnoreAspectRatio,
                        QtCore.TransformationMode.SmoothTransformation))
                    label.setFixedSize(tw, th)
                except Exception:
                    pass
            self._layout_labels()

        self.zoom_edit.setText(str(cur_pct))
        self._pending_zoom_pct = cur_pct
        QTimer.singleShot(180, self._sharp_render)

    def _update_nav_ui(self):
        self.page_label.setText(f"{self._current_page + 1} / {self._total_pages}")
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < self._total_pages - 1)

    # ═══════════ Welcome (overlay on self, immune to scroll) ═══════════

    def _destroy_welcome(self):
        if self._welcome:
            self._welcome.setParent(None); self._welcome.deleteLater(); self._welcome = None

    def _show_welcome(self, drop_text=None, load_btn_text=None):
        if drop_text is None: drop_text = self._welcome_drop or "Drop PDF here to read"
        if load_btn_text is None: load_btn_text = self._welcome_btn_text or "Load file..."
        self._welcome_drop = drop_text
        self._welcome_btn_text = load_btn_text
        if self.doc: return
        vp = self.scroll_area.viewport()
        if not vp or vp.width() < 100 or vp.height() < 50: return

        self._destroy_welcome()
        # Use the scroll_area's own container: put welcome text inside page_container
        self.page_container.setFixedSize(vp.width(), vp.height())
        c = QWidget(self.page_container)
        c.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(c); cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setSpacing(12)
        t = QLabel(drop_text); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet("QLabel{color:#555;font-size:16px;background:transparent;}")
        cl.addWidget(t)
        b = QPushButton(load_btn_text); b.setFixedWidth(120)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{color:#666;background:#2a2a2a;border:1px solid #444;"
            "border-radius:4px;padding:5px 16px;font-size:12px}"
            "QPushButton:hover{color:#999;background:#333;border-color:#555}")
        b.clicked.connect(lambda: self.open_requested.emit())
        cl.addWidget(b, alignment=Qt.AlignmentFlag.AlignCenter)
        c.adjustSize()
        c.move(max(0, (vp.width() - c.width()) // 2),
               max(0, (vp.height() - c.height()) // 2))
        c.show(); c.raise_()
        self._welcome = c

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
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls()
                 if Path(u.toLocalFile()).exists()]
        pdfs = [p for p in paths if p.suffix.lower() == ".pdf"]
        if pdfs: self._path = pdfs[0]; self.open_requested.emit()
        e.acceptProposedAction()

    # ═══════════ Keyboard ═══════════

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Left: self.prev_page()
        elif e.key() == Qt.Key.Key_Right: self.next_page()
        elif e.key() == Qt.Key.Key_Home: self.first_page()
        elif e.key() == Qt.Key.Key_End: self.last_page()
        else: super().keyPressEvent(e)

    # ═══════════ Touchpad pinch ═══════════

    def wheelEvent(self, e):
        if not self.doc or self._view_mode != ViewMode.SCROLL:
            super().wheelEvent(e); return
        try:
            ad = e.angleDelta().y() if e.angleDelta() else 0
            pd = e.pixelDelta().y() if e.pixelDelta() else 0
            pinch = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if not pinch:
                try: ph = e.phase(); pinch = (int(ph) >= 1)
                except (AttributeError, TypeError): pass
            if not pinch and pd and ad:
                if abs(ad) > abs(pd) * 1.5: pinch = True
            if pinch:
                self._pinch_acc += ad
                threshold = 120
                if abs(self._pinch_acc) >= threshold:
                    ticks = int(abs(self._pinch_acc) // threshold)
                    ticks = ticks if self._pinch_acc > 0 else -ticks
                    self._pinch_acc %= threshold
                    self._set_zoom_pct(self._current_zoom_pct() + ticks * 5,
                                       skip_deferred=True)
                try:
                    if e.phase() and int(e.phase()) == 3:
                        self._pending_zoom_pct = self._current_zoom_pct()
                        QTimer.singleShot(180, self._sharp_render)
                except (AttributeError, TypeError): pass
            else:
                super().wheelEvent(e)
        except Exception:
            super().wheelEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.doc: self._resize_timer.start()

    # ═══════════ Public ═══════════

    def has_document(self) -> bool: return self.doc is not None
    def current_path(self) -> Optional[Path]: return self._path
    @property
    def opened_from_file_list(self) -> bool:
        return self._btn_open_source == 'file_list'
    @opened_from_file_list.setter
    def opened_from_file_list(self, v: bool):
        self._btn_open_source = 'file_list' if v else 'dialog'
    def retranslate_ui(self): pass
