"""PDF reader — LRU cache, dual-timer pages, on-demand prefetch."""

from bisect import bisect_right
from collections import OrderedDict
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent, QWheelEvent, QIntValidator
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget, QToolTip, QPinchGesture,
)


class ViewMode(Enum):
    SCROLL = "scroll"
    GRID = "grid"


# Rendering philosophy: MuPDF's built-in sub-pixel anti-aliasing produces
# vector-quality output at ANY resolution. We render at exact zoom × devicePixelRatio
# with NO oversampling and NO downscaling — just like Acrobat/WPS which render
# vector PDF content directly to the framebuffer at native resolution.
# The SSAA→downscale approach is counterproductive: it adds an unnecessary bilinear
# filter pass that softens MuPDF's already-perfect anti-aliased output.
RESIZE_DEBOUNCE = 350
MAX_CACHE_MB = 400; CACHE_TARGET_MB = 280
PRE_RENDER_EAGER = 5  # render first N pages eagerly, rest lazily
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

        self._welcome = None
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

        self.page_label = QLabel("0 / 0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setFixedWidth(70)
        self.page_label.setStyleSheet("QLabel{color:#bbb}")

        self.btn_next = QPushButton("▶"); self.btn_next.setFixedSize(34,34)
        self.btn_next.clicked.connect(self.next_page)
        self._hover_on(self.btn_next)

        tb.addWidget(self.btn_prev); tb.addWidget(self.page_label); tb.addWidget(self.btn_next)

        # Initially disabled — no document loaded yet
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
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
        self.label_filename.setStyleSheet(
            "QLabel{color:#888;background:#1a1a1a;border:1px solid #333;"
            "border-radius:6px;padding:4px 10px;font-size:12px;"
            "border-top:1px solid #222;border-left:1px solid #222;}")
        self.label_filename.hide()  # hidden until a document is loaded
        tb.addWidget(self.label_filename)

        self.btn_close = QPushButton("✕"); self.btn_close.setObjectName("btn_close")
        self.btn_close.setFixedSize(26,26); self.btn_close.setToolTip("Close this document")
        self.btn_close.clicked.connect(self._on_close)
        self.btn_close.hide()  # hidden until a document is loaded
        tb.addWidget(self.btn_close)

        root.addWidget(self.toolbar)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setMouseTracking(True)
        # Native trackpad pinch-to-zoom via macOS gesture recognition
        self.grabGesture(Qt.GestureType.PinchGesture)

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
            if t:
                # Position tooltip above the button, using its top edge
                pos = w.mapToGlobal(w.rect().topLeft())
                pos.setY(pos.y() - 6)
                QToolTip.showText(pos, t, self)

    # ═══════════ Mode ═══════════

    def _set_mode(self, mode: ViewMode):
        self._view_mode = mode
        self.btn_scroll.setChecked(mode == ViewMode.SCROLL)
        self.btn_grid.setChecked(mode == ViewMode.GRID)
        if self.doc:
            self._layout_labels()
            if mode == ViewMode.SCROLL:
                self._scroll_to_page_top()

    def _on_close(self):
        """Close button handler — only acts when document is loaded."""
        if self.doc:
            self.close_document()
            self.close_requested.emit()

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
        # Configure MuPDF for maximum text rendering quality.
        # fz_set_aa_level(8) gives highest sub-pixel anti-aliasing (8 bits).
        self._configure_mupdf_aa()
        self._path = path
        self._total_pages = len(self.doc); self._current_page = 0
        self._zoom_mode = 1.0              # default: 100%
        self.btn_fit_width.setChecked(False); self.btn_fit_height.setChecked(False)
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True); self.btn_grid.setChecked(False)
        # Pre-compute fit ratios for later use
        page = self.doc[0]; pw, ph = page.rect.width, page.rect.height
        vw, vh = self._viewport_size()
        self._fw_ratio = vw / pw if pw > 0 else 1.0
        self._fh_ratio = vh / ph if ph > 0 else 1.0
        self._default_zoom_pct = max(50, min(300, int(self._fh_ratio * 100)))
        self.zoom_edit.setText("100")
        self._build_labels()
        # Pre-render ALL pages at 100% — scale base for future zooms
        self._pre_render_100_all()
        self._layout_labels(render_missing=True)
        self._update_nav_ui()
        self.label_filename.setText(path.name)
        self.label_filename.show()
        self.btn_close.show()
        self.document_changed.emit(str(path))
        self.setFocus()

    def close_document(self):
        self._cancel_deferred_renders()
        if self.doc: self.doc.close(); self.doc = None
        self._path = None; self._total_pages = 0; self._current_page = 0
        PdfReaderWidget._clear_cache()
        self.scroll_area.verticalScrollBar().blockSignals(True)
        self._destroy_labels()
        self._page_heights.clear()
        self.label_filename.clear()
        self.label_filename.hide()
        self.btn_close.hide()
        self._update_nav_ui()
        self.page_container.setFixedSize(0, 0); self.page_container.resize(0, 0)
        self.scroll_area.verticalScrollBar().blockSignals(False)
        self._show_welcome()

    def _cancel_deferred_renders(self):
        """Cancel all pending timers to prevent stale callbacks."""
        self._pending_zoom_pct = None
        self._lazy_pre_render_index = 999999  # stops _lazy_pre_render loop
        self._resize_timer.stop()
        self._scroll_throttle.stop()
        self._scroll_debounce.stop()

    # ═══════════ Zoom — two-pass: instant scale → sharp render ═══════════

    def _current_zoom_pct(self) -> int:
        if self._zoom_mode == "fit_width":
            return max(50, min(300, int(self._fw_ratio * 100)))
        if self._zoom_mode == "fit_height":
            return self._default_zoom_pct
        if isinstance(self._zoom_mode, (int, float)):
            return max(50, min(300, int(self._zoom_mode * 100)))
        return 100

    def _set_zoom_pct(self, pct: int, skip_deferred: bool = False):
        """Two-pass zoom — always scales from 100% immortal base.
        Pass 1 (instant, <5ms): scale 100% base pixmaps to target zoom.
        Pass 2 (deferred): render visible range at target zoom for sharpness."""
        pct = max(50, min(300, int(round(pct))))
        if not self.doc or not self._labels:
            self._zoom_mode = pct / 100.0
            self.zoom_edit.setText(str(pct))
            return

        self._zoom_mode = pct / 100.0
        self.btn_fit_width.setChecked(False)
        self.btn_fit_height.setChecked(False)
        self.zoom_edit.setText(str(pct))

        # Pass 1: scale each page's 100% base pixmap to target zoom.
        # Use LOGICAL size: the 100% base may have devicePixelRatio set (HiDPI),
        # and QPixmap.scaled() returns a pixmap with dpr=1.0 — so targets must
        # be in logical pixels or the label appears 2× oversized.
        target_factor = pct / 100.0
        from PyQt6.QtCore import Qt as QtCore
        for pi, label in enumerate(self._labels):
            try:
                base_key = (pi, "z:1.000")
                base = PdfReaderWidget._cache_get(base_key)
                if base is None or base.isNull(): continue
                bw, bh = self._logical_size(base)
                tw, th = max(1, int(bw * target_factor)), max(1, int(bh * target_factor))
                label.setPixmap(base.scaled(tw, th,
                    QtCore.AspectRatioMode.IgnoreAspectRatio,
                    QtCore.TransformationMode.SmoothTransformation))
                label.setFixedSize(tw, th)
            except Exception: pass

        self._show_zoom_popup(pct)
        self._layout_labels()
        self._scroll_to_page_top()  # preserve scroll position after zoom

        if not skip_deferred:
            self._pending_zoom_pct = pct
            QTimer.singleShot(40, self._sharp_render)

    def _sharp_render(self):
        """Deferred: render only the visible ±2 pages at target zoom, then layout."""
        if not self.doc or not self._labels or self._pending_zoom_pct is None:
            return
        try:
            self._render_visible_range()
            self._layout_labels()
        except Exception:
            pass
        finally:
            self._pending_zoom_pct = None

    def _visible_page_range(self):
        """Return (start, end) of pages to render — current page ± 1, clamped."""
        s = max(0, self._current_page - 1)
        e = min(self._total_pages, self._current_page + 2)
        return s, e

    def _configure_mupdf_aa(self):
        """Set MuPDF anti-aliasing to maximum quality (8 bits).
        This gives the best sub-pixel text rendering — equivalent to Acrobat/WPS.
        fz_set_aa_level() controls glyph edge smoothing; 8 = highest quality."""
        try:
            import fitz
            if hasattr(fitz.Tools, 'set_aa_level'):
                fitz.Tools.set_aa_level(8)
            # Also try the text-specific AA level if available
            if hasattr(fitz.Tools, 'set_text_aa_level'):
                fitz.Tools.set_text_aa_level(8)
            if hasattr(fitz.Tools, 'set_graphics_aa_level'):
                fitz.Tools.set_graphics_aa_level(8)
        except Exception:
            pass  # best-effort; MuPDF's default AA (8 bits) is already good

    def _pre_render_100_all(self):
        """Render first few pages at 100% eagerly, queue the rest lazily.
        Creates a high-quality base that all future zooms can scale from."""
        if not self.doc or not self._labels: return
        vw, vh = self._viewport_size()
        # Preserve original zoom_key: use "z:1.000" manually
        orig_key = self._zoom_key(vw, vh)
        self._zoom_mode = 1.0  # ensure _zoom_key returns "z:1.000"
        for pi in range(min(PRE_RENDER_EAGER, self._total_pages)):
            self._get_or_render(pi, vw, vh)
        self._zoom_mode = orig_key if isinstance(orig_key, float) else (
            1.0 if orig_key.startswith("z:") else orig_key)
        # Queue remaining pages one-by-one with low-priority timers
        if self._total_pages > PRE_RENDER_EAGER:
            self._lazy_pre_render_index = PRE_RENDER_EAGER
            QTimer.singleShot(50, self._lazy_pre_render)

    def _lazy_pre_render(self):
        """Render one more page at 100%, then queue next."""
        if not self.doc or not self._labels: return
        vw, vh = self._viewport_size()
        pi = getattr(self, '_lazy_pre_render_index', 0)
        if pi >= self._total_pages: return
        old = self._zoom_mode
        self._zoom_mode = 1.0
        self._get_or_render(pi, vw, vh)
        self._zoom_mode = old
        self._lazy_pre_render_index = pi + 1
        if self._lazy_pre_render_index < self._total_pages:
            QTimer.singleShot(10, self._lazy_pre_render)

    def _render_visible_range(self):
        """Render pages near the current position at native HiDPI resolution (~3 pages).
        Uses cache when available, renders fresh for misses."""
        if not self.doc or not self._labels:
            return
        vw, vh = self._viewport_size()
        zk = self._zoom_key(vw, vh)
        s, e = self._visible_page_range()
        # Render current page first (it's the priority), then neighbors
        order = [self._current_page] + [p for p in range(s, e) if p != self._current_page]
        for pi in order:
            if pi < 0 or pi >= len(self._labels):
                continue
            try:
                key = (pi, zk)
                pix = PdfReaderWidget._cache_get(key)
                if pix is None:
                    pix = self._get_or_render(pi, vw, vh)
                if pix:
                    self._labels[pi].setPixmap(pix)
                    lw, lh = self._logical_size(pix)
                    self._labels[pi].setFixedSize(lw, lh)
            except Exception:
                pass

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
        """Fit W/H: instant visible-only scaling, deferred real render."""
        if not self.doc or not self._labels:
            self._zoom_mode = mode
            self.btn_fit_width.setChecked(mode == "fit_width")
            self.btn_fit_height.setChecked(mode == "fit_height")
            self.zoom_edit.setText(str(pct))
            return

        old_pct = self._current_zoom_pct()
        self._zoom_mode = mode
        self.btn_fit_width.setChecked(mode == "fit_width")
        self.btn_fit_height.setChecked(mode == "fit_height")
        self.zoom_edit.setText(str(pct))

        # Pass 1: instant — scale from 100% base using LOGICAL size
        # (base may have HiDPI devicePixelRatio set; scaled result has dpr=1.0)
        target_factor = pct / 100.0
        from PyQt6.QtCore import Qt as QtCore
        for pi, label in enumerate(self._labels):
            try:
                base_key = (pi, "z:1.000")
                base = PdfReaderWidget._cache_get(base_key)
                if base is None or base.isNull(): continue
                bw, bh = self._logical_size(base)
                tw, th = max(1, int(bw * target_factor)), max(1, int(bh * target_factor))
                label.setPixmap(base.scaled(tw, th,
                    QtCore.AspectRatioMode.IgnoreAspectRatio,
                    QtCore.TransformationMode.SmoothTransformation))
                label.setFixedSize(tw, th)
            except Exception: pass

        self._layout_labels()
        self._show_zoom_popup(pct)
        self._pending_zoom_pct = pct
        # Preserve scroll position: after zoom change, snap to current_page
        self._scroll_to_page_top()
        QTimer.singleShot(40, self._sharp_render)

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
        self._labels.clear()
        self.scroll_area.verticalScrollBar().blockSignals(False)

    def _layout_labels(self, render_missing: bool = False):
        vw, vh = self._viewport_size(); sp, mg = 16, 20

        if self._view_mode == ViewMode.SCROLL:
            self._page_heights = []; y = mg
            for pi, label in enumerate(self._labels):
                pix = label.pixmap()
                # Initial load: render everything. Otherwise, keep existing pixmap
                # (already set by Pass 1 or prior render) and just reflow layout.
                if render_missing and (pix is None or pix.isNull()):
                    if self.doc and pi < self._total_pages:
                        pix = self._get_or_render(pi, vw, vh)
                        if pix:
                            label.setPixmap(pix)
                            lw, lh = self._logical_size(pix)
                            label.setFixedSize(lw, lh)
                if pix and not pix.isNull():
                    w, h = self._logical_size(pix)
                else:
                    # Compute expected dimensions from PDF page size × current zoom
                    # instead of hardcoded 600×800 — prevents Y-offset cascade
                    # when pages are not yet rendered at current zoom level.
                    if self.doc and pi < self._total_pages:
                        pw = self.doc[pi].rect.width
                        ph = self.doc[pi].rect.height
                        pct = self._current_zoom_pct()
                        z = pct / 100.0
                        w, h = int(pw * z), int(ph * z)
                    else:
                        w, h = 600, 800
                label.setStyleSheet("QLabel{background:white;}")
                label.setCursor(Qt.CursorShape.ArrowCursor)
                x = max(0, (vw - w) // 2)
                label.move(x, y); label.show()
                self._page_heights.append(y); y += h + sp
            self.page_container.setFixedSize(vw, y - sp + mg)

        elif self._view_mode == ViewMode.GRID:
            self._page_heights = []
            COLS = 3; gutter = 20; side_margin = 20
            usable = vw - 2*side_margin - (COLS-1)*gutter
            thumb_w = max(120, usable // COLS); thumb_h = int(thumb_w * 1.414)
            grid_w = COLS*thumb_w + (COLS-1)*gutter; left = (vw - grid_w) // 2

            for pi, label in enumerate(self._labels):
                pix = self._get_or_render(pi, thumb_w, thumb_h, force_fit=True)
                if pix: label.setPixmap(pix); lw, lh = self._logical_size(pix); label.setFixedSize(lw, lh)
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

    # pre-render removed — now lazy-renders visible range on scroll stop

    # ═══════════ Scroll tracking (bisect, O(log n)) ═══════════

    def _scroll_to_page_top(self):
        if not self._page_heights or self._current_page >= len(self._page_heights):
            return
        self.scroll_area.verticalScrollBar().setValue(
            max(0, self._page_heights[self._current_page]))

    def _on_scrollbar_changed(self, value):
        """Scrollbar moved — fire throttle (rough page), debounce (precise+render)."""
        if self.doc:
            self._scroll_throttle.start()
            self._scroll_debounce.start()
            # When scroll stops, debounce triggers _do_debounce_calibration
            # which calls _render_visible_range for the current viewport

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
        """Precise calibration via bisect on _page_heights — O(log n).
        On page change, trigger visible-range lazy render."""
        try:
            if not self.doc or not self._page_heights: return
            sb = self.scroll_area.verticalScrollBar()
            if not sb: return
            mid = max(0, sb.value() + sb.pageStep() // 2)
            idx = bisect_right(self._page_heights, mid) - 1
            if idx < 0: idx = 0
            elif idx >= len(self._page_heights): idx = len(self._page_heights) - 1
            if idx != self._current_page:
                self._current_page = idx
                self._update_nav_ui()
                self._render_visible_range()  # lazy-render nearby pages
        except Exception: pass

    # ═══════════ Render ═══════════

    def _zoom_key(self, vw, vh):
        if self._zoom_mode == "fit_width": return "fw"
        if self._zoom_mode == "fit_height": return "fh"
        return f"z:{self._zoom_mode:.3f}"

    @staticmethod
    def _render_page(doc, pi, zk, vw, vh, force_fit=False, dpr=1.0):
        """Render a page at exact target resolution — MuPDF's built-in
        sub-pixel anti-aliasing handles quality at all zoom levels.
        No oversampling, no downscaling — pure vector-to-pixel rendering."""
        import fitz
        page = doc[pi]; pw, ph = page.rect.width, page.rect.height
        if zk == "fw": zoom = vw / pw
        elif zk == "fh": zoom = vh / ph
        elif zk.startswith("z:"): zoom = float(zk[2:])
        elif force_fit: zoom = min(vw/pw, vh/ph)
        else: zoom = vw / pw
        # Render at exact physical-pixel resolution.
        # MuPDF anti-aliases text with sub-pixel precision at whatever
        # resolution we request — no oversampling needed.
        mat = fitz.Matrix(zoom * dpr, zoom * dpr)
        pix = page.get_pixmap(matrix=mat)
        qimg = QImage(pix.samples, pix.width, pix.height,
                      pix.stride, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        if dpr != 1.0:
            pixmap.setDevicePixelRatio(dpr)
        return pixmap

    def _viewport_size(self):
        vp = self.scroll_area.viewport()
        w, h = max(800, vp.width() - 4), max(600, vp.height() - 4)
        return w, h

    def _device_pixel_ratio(self) -> float:
        """Get the device pixel ratio for native-resolution rendering on HiDPI."""
        try:
            vp = self.scroll_area.viewport()
            if vp:
                return vp.devicePixelRatio()
        except Exception:
            pass
        return 1.0

    @staticmethod
    def _logical_size(pix: QPixmap) -> tuple:
        """Return (width, height) in logical pixels for a pixmap."""
        r = pix.devicePixelRatio()
        if r != 1.0:
            sz = pix.deviceIndependentSize()
            return int(sz.width()), int(sz.height())
        return pix.width(), pix.height()

    @classmethod
    def _cache_put(cls, key, pix: QPixmap):
        """LRU insert with memory-aware eviction. 100% base + fit modes are immortal.
        Memory tracking accounts for devicePixelRatio: Qt6 returns logical-pixel
        dimensions from pix.width()/height(), but RAM is consumed by physical pixels."""
        if key in cls._cache:
            cls._cache.move_to_end(key)
            cls._cache[key] = pix
            return
        # Physical pixel memory: logical_px × dpr × logical_px × dpr × 4 bytes
        mem = pix.width() * pix.height() * 4
        r = pix.devicePixelRatio()
        if r != 1.0:
            mem = int(mem * r * r)
        cls._cache_memory_bytes += mem
        cls._cache[key] = pix
        while cls._cache_memory_bytes > MAX_CACHE_MB * 1024 * 1024 and len(cls._cache) > 1:
            oldest_key, oldest_pix = next(iter(cls._cache.items()))
            pi, zk = oldest_key
            # Immortal: 100% base + fit modes
            if zk in ("fh", "fw", "z:1.000"):
                break
            ow, oh = oldest_pix.width(), oldest_pix.height()
            orr = oldest_pix.devicePixelRatio()
            oldest_mem = ow * oh * 4
            if orr != 1.0:
                oldest_mem = int(oldest_mem * orr * orr)
            cls._cache_memory_bytes -= oldest_mem
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

    def _get_or_render(self, pi, vw, vh=99999, force_fit=False, render_hq=False):
        key = (pi, self._zoom_key(vw, vh))
        cached = PdfReaderWidget._cache_get(key)
        if cached is not None and not render_hq:
            return cached
        dpr = self._device_pixel_ratio()
        pix = PdfReaderWidget._render_page(self.doc, pi, key[1], vw, vh, force_fit, dpr=dpr)
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
        self._fw_ratio = vw / pw if pw > 0 else 1.0
        self._fh_ratio = vh / ph if ph > 0 else 1.0
        self._default_zoom_pct = max(50, min(300, int(self._fh_ratio * 100)))
        cur_pct = self._current_zoom_pct()
        self.zoom_edit.setText(str(cur_pct))
        self._pending_zoom_pct = cur_pct
        QTimer.singleShot(40, self._sharp_render)

    def _update_nav_ui(self):
        if self._total_pages == 0:
            self.page_label.setText("0 / 0")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
        else:
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

    # ═══════════ Native gesture + wheel pinch-to-zoom ═══════════

    def event(self, e):
        """Catch native trackpad pinch gestures (QPinchGesture) for smooth zoom."""
        try:
            if e.type() == QEvent.Type.Gesture:
                pinch = e.gesture(Qt.GestureType.PinchGesture)
                if pinch:
                    return self._handle_pinch_gesture(pinch, e)
        except Exception:
            pass
        return super().event(e)

    def _handle_pinch_gesture(self, pinch: QPinchGesture, e):
        """Process native macOS trackpad pinch-to-zoom via QPinchGesture.
        scaleFactor: relative scale since last event (~0.95–1.05 per frame).
        This is how Acrobat/WPS/Preview do it — native gesture, no fragile
        angleDelta phase heuristics."""
        if not self.doc or self._view_mode != ViewMode.SCROLL:
            return False
        try:
            sf = pinch.scaleFactor()
            # scaleFactor=1.0 means no change. 1.03 = user pinched OUT slightly.
            # Convert to zoom delta: each 0.01 in scaleFactor ≈ 2.5% zoom change.
            # This gives a smooth, proportional feel matching macOS Preview.
            if sf != 1.0:
                # Proportional zoom delta: the further from 1.0, the larger the step
                delta_pct = int((sf - 1.0) * 250)  # 0.01 → 2.5%, 0.05 → 12.5%
                if abs(delta_pct) >= 1:
                    self._set_zoom_pct(self._current_zoom_pct() + delta_pct,
                                       skip_deferred=True)
            # On pinch finished, trigger sharp render
            state = pinch.state()
            if state == Qt.GestureState.GestureFinished:
                self._pending_zoom_pct = self._current_zoom_pct()
                QTimer.singleShot(40, self._sharp_render)
            return True
        except Exception:
            return False

    def wheelEvent(self, e):
        """Ctrl+wheel zoom fallback. Native pinch handled by event()/QPinchGesture."""
        if not self.doc or self._view_mode != ViewMode.SCROLL:
            super().wheelEvent(e); return
        # Only handle Ctrl+wheel for manual zoom — native pinch goes through event()
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            ad = e.angleDelta().y() if e.angleDelta() else 0
            if abs(ad) >= 120:
                delta = 5 if ad > 0 else -5
                self._set_zoom_pct(self._current_zoom_pct() + delta,
                                   skip_deferred=True)
                self._pending_zoom_pct = self._current_zoom_pct()
                QTimer.singleShot(40, self._sharp_render)
            return
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
