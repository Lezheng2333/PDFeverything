"""PDF reader — LRU cache, dual-timer pages, on-demand prefetch."""

import os
from bisect import bisect_right
from collections import OrderedDict
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QIntValidator, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QApplication,
    QMessageBox, QFileDialog,
)

from .i18n import tr


_DARK = False  # set by main.launch_gui before any widgets are created

def _dc(dark, light):
    return dark if _DARK else light


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
MAX_CACHE_MB = 400
PAGE_THROTTLE_MS = 30  # rough page update
PAGE_DEBOUNCE_MS = 80  # precise bisect calibration + render trigger
# ── Lazy base-render window ─────────────────────────────────────────
# Only pages inside a bounded ring around the current page get a 100% base
# pixmap. Everything else keeps its geometry from PDF page rects, so opening a
# 1000-page document costs the same as opening a 3-page one.
PRE_RENDER_LOOKAHEAD = 1   # pages kept warm *above* the current page
PRE_RENDER_AHEAD = 2       # pages kept warm *below* the current page
LAZY_RENDER_INTERVAL_MS = 12  # gap between two background base renders
GRID_COLS = 3              # thumbnail columns in Grid view
GRID_CELL_RATIO = 1.414    # A4 cell aspect ratio
GRID_PAGE_LABEL_H = 16     # strip reserved under each thumbnail for its number
GRID_MIN_CELL_H = 150      # never shrink a grid cell below this
SIDEBAR_WIDTH = 230        # left panel (outline / search results)
SEARCH_DEBOUNCE_MS = 260   # typing pause before a document-wide search runs
SEARCH_MAX_HITS = 800      # cap on stored hits for very common words


class PdfReaderWidget(QWidget):
    document_changed = pyqtSignal(str)
    close_requested = pyqtSignal()
    open_requested = pyqtSignal()
    _cache: OrderedDict = OrderedDict()
    _cache_memory_bytes: int = 0
    _protected_pages: set = set()   # pages whose entries survive eviction longest
    _cache_budget: Optional[int] = None  # resolved once from the machine's RAM

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None; self._path = None
        self._current_page = 0; self._total_pages = 0
        self._view_mode = ViewMode.SCROLL
        self._zoom_mode = "fit_height"
        self._fw_ratio = self._fh_ratio = 1.0
        self._labels: list[QLabel] = []
        self._page_heights: list[int] = []
        self._page_geoms: list[tuple] = []
        self._page_rects = None      # cached per-page (w, h) for layout hot paths
        self._btn_open_source = 'dialog'
        # Lazy base-render state
        self._lazy_rendering = False
        self._lazy_pre_render_index = 0
        self._lazy_window = (0, 0)
        # Grid geometry cache (populated by _layout_labels)
        self._grid_geom = None
        self._pending_scroll_page = None
        # Search state
        self._search_hits = []          # list[SearchHit]
        self._search_index = -1         # current hit
        self._search_query = ""
        self._search_case = False
        self._highlight_rects = {}      # {page: [fitz.Rect]}
        self._sidebar_visible = True

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
        self._hover_timer.setInterval(500)
        self._hover_timer.timeout.connect(self._show_tooltip)

        # Search: debounce so a document-wide search only runs once typing stops
        self._search_debounce = QTimer(self); self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(self._run_debounced_search)
        self._outline_entries = []
        self.btn_sidebar = None

        self._hide_timer = QTimer(self); self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(200)

        self._auto_hide_timer = QTimer(self); self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.setInterval(5000)
        self._auto_hide_timer.timeout.connect(lambda: self._tooltip.hide())

        self._zoom_popup_timer = QTimer(self); self._zoom_popup_timer.setSingleShot(True)
        self._zoom_popup_timer.setInterval(1200)
        self._zoom_popup_timer.timeout.connect(self._hide_zoom_popup)
        self._zoom_popup = QLabel(self)
        self._zoom_popup.setStyleSheet(
            "QLabel{background:rgba(0,0,0,180);color:#fff;font-size:18px;"
            "font-weight:bold;border-radius:10px;padding:8px 16px;}")
        self._zoom_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_popup.hide()

        # ── Pinch zoom accumulator ──
        self._pinch_acc = 0
        # ── Grid edit mode ──
        self._edit_mode = False
        self._drag_sort_mode = False
        self._normal_label = "✎ Edit"     # i18n overrides in main_window
        self._editing_label = "✎ Editing"
        self._original_snapshot = None
        self._page_editor = None     # PdfPageEditor (lazy init on edit)
        self._selected_pages: set[int] = set()
        self._prev_selected: set[int] = set()
        self._drag_source = None     # page index being dragged
        self._rubber_origin = None   # QPoint of box-select / drag start
        self._rubber_rect = None     # (x, y, w, h) of the live rubber band
        self._rubber_band = None     # overlay widget drawing the rubber band
        self._drag_active = False
        self._drag_target = None
        self._saved_scroll_zoom = None  # zoom before entering Grid
        self._unsaved_edits = False     # track whether edit ops have been performed

        # ── Custom compact tooltip (small, at cursor, not system QToolTip) ──
        self._tooltip_texts = {}
        self._tooltip = QLabel(self)
        self._tooltip.setStyleSheet(
            "QLabel{color:#ddd;background:#2a2a2a;border:1px solid #555;"
            "border-radius:3px;padding:2px 7px;font-size:11px;}")
        self._tooltip.hide()

        self._welcome = None
        self._welcome_drop = "Drop PDF here to read"
        self._welcome_btn_text = "Load file..."
        self._init_ui()
        # Late bind: _hide_timer needs _tooltip which is created in _init_ui
        self._hide_timer.timeout.connect(self._tooltip.hide)

    def showEvent(self, e):
        super().showEvent(e)
        if not self.doc and not self._welcome:
            # Defer to ensure layout is complete
            QTimer.singleShot(100, self._try_show_welcome)
        # A document opened while this widget's tab was hidden was laid out with
        # a placeholder viewport size. Re-layout as soon as the real size is known.
        if self.doc:
            QTimer.singleShot(0, self._check_viewport_layout)

    def _check_viewport_layout(self):
        """Re-layout when the viewport width no longer matches the last layout."""
        if not self.doc or not self._labels:
            return
        vw, _ = self._viewport_size()
        if vw != getattr(self, "_layout_vw", None):
            self._on_resize()

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
        bg = _dc("#2c2c2c", "#f5f5f5")
        self.setStyleSheet(f"background-color:{bg};")
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setWidgetResizable(False)
        s_bg = _dc("#2c2c2c", "#f5f5f5"); sb_bg = _dc("#1e1e1e", "#e8e8e8"); sh = _dc("#555", "#bbb")
        self.scroll_area.setStyleSheet(
            f"QScrollArea{{background:{s_bg};border:none;}}"
            f"QScrollBar:vertical{{background:{sb_bg};width:10px;margin:0}}"
            f"QScrollBar::handle:vertical{{background:{sh};border-radius:4px;min-height:30px}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0}}"
            f"QScrollBar:horizontal{{background:{sb_bg};height:10px;margin:0}}"
            f"QScrollBar::handle:horizontal{{background:{sh};border-radius:4px;min-width:30px}}"
            f"QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0}}")
        self.scroll_area.verticalScrollBar().valueChanged.connect(
            self._on_scrollbar_changed)
        self.scroll_area.setAcceptDrops(True)

        # Edit toolbar (hidden by default, shown in edit mode)
        self.edit_toolbar = QWidget(); self.edit_toolbar.setObjectName("edit_toolbar")
        etb_bg = _dc("#252525", "#f0f0f0"); etb_brd = _dc("#3a3a3a", "#d0d0d0")
        etb_txt = _dc("#ccc", "#333"); etb_btn = _dc("#333", "#e8e8e8"); etb_btn_bdr = _dc("#555", "#bbb")
        etb_btn_hov = _dc("#444", "#ddd"); etb_dis_txt = _dc("#555", "#bbb"); etb_dis_bg = _dc("#2a2a2a", "#eee")
        self.edit_toolbar.setStyleSheet(
            f"QWidget#edit_toolbar{{background:{etb_bg};border-top:1px solid {etb_brd};border-bottom:1px solid {etb_brd}}}"
            f"QPushButton{{color:{etb_txt};background:{etb_btn};border:1px solid {etb_btn_bdr};border-radius:4px;padding:5px 10px;font-size:12px}}"
            f"QPushButton:hover{{background:{etb_btn_hov}}}"
            f"QPushButton:disabled{{color:{etb_dis_txt};background:{etb_dis_bg}}}")
        etb = QHBoxLayout(self.edit_toolbar); etb.setContentsMargins(8,4,8,4); etb.setSpacing(6)
        self.btn_edit_sel = QPushButton("☝ Select"); self.btn_edit_sel.clicked.connect(self._edit_select_mode)
        self.btn_edit_sel.setToolTip("退出排序模式，返回选择模式")
        etb.addWidget(self.btn_edit_sel)
        self.btn_edit_sort = QPushButton("↕ Sort"); self.btn_edit_sort.clicked.connect(self._edit_sort_mode)
        self.btn_edit_sort.setCheckable(True)
        self.btn_edit_sort.setToolTip("拖拽排序：选中页面后拖拽到目标位置重新排列")
        etb.addWidget(self.btn_edit_sort)
        etb.addSpacing(8)
        self.btn_edit_rot = QPushButton("↻ Rotate 90°"); self.btn_edit_rot.clicked.connect(self._edit_rotate)
        self.btn_edit_rot.setToolTip("顺时针旋转选中页面 90°")
        etb.addWidget(self.btn_edit_rot)
        self.btn_edit_del = QPushButton("✕ Delete"); self.btn_edit_del.clicked.connect(self._edit_delete)
        self.btn_edit_del.setToolTip("删除选中的页面（需二次确认）")
        etb.addWidget(self.btn_edit_del)
        etb.addSpacing(8)
        self.btn_edit_extract = QPushButton("📄 Extract"); self.btn_edit_extract.clicked.connect(self._edit_extract)
        self.btn_edit_extract.setToolTip("将选中的页面提取合并为一个新 PDF")
        etb.addWidget(self.btn_edit_extract)
        self.btn_edit_export = QPushButton("💾 Export")
        self.btn_edit_export.clicked.connect(self._edit_export_menu)
        self.btn_edit_export.setToolTip("导出选中页面为 PDF / JPG / Word / PowerPoint")
        etb.addWidget(self.btn_edit_export)
        self.btn_edit_print = QPushButton("🖨 Print"); self.btn_edit_print.clicked.connect(self._edit_print)
        self.btn_edit_print.setToolTip("调系统打印对话框打印选中页面")
        etb.addWidget(self.btn_edit_print)
        etb.addStretch()
        self.btn_edit_saveas = QPushButton("💾 Save As"); self.btn_edit_saveas.clicked.connect(self._save_edited_copy)
        self.btn_edit_saveas.setToolTip("保存修改后的 PDF 到新文件")
        etb.addWidget(self.btn_edit_saveas)
        self.btn_edit_undo = QPushButton("↩ Undo"); self.btn_edit_undo.clicked.connect(self._edit_undo)
        self.btn_edit_undo.setToolTip("撤销上一次操作 (Ctrl+Z)")
        etb.addWidget(self.btn_edit_undo)
        self.btn_edit_redo = QPushButton("↪ Redo"); self.btn_edit_redo.clicked.connect(self._edit_redo)
        self.btn_edit_redo.setToolTip("重做已撤销的操作 (Ctrl+Shift+Z)")
        etb.addWidget(self.btn_edit_redo)
        self.edit_toolbar.hide()
        # Attach hover tracking for tooltips
        for btn in [self.btn_edit_sel, self.btn_edit_sort, self.btn_edit_rot,
                     self.btn_edit_del, self.btn_edit_extract, self.btn_edit_export,
                     self.btn_edit_print, self.btn_edit_saveas, self.btn_edit_undo,
                     self.btn_edit_redo]:
            self._hover_on(btn)

        self.page_container = QWidget()
        self.page_container.setStyleSheet("background:transparent;")
        self.scroll_area.setWidget(self.page_container)

        # ── Sidebar (outline / search results) + page area ──
        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.sidebar = self._build_sidebar()
        self.body_splitter.addWidget(self.sidebar)
        self.body_splitter.addWidget(self.scroll_area)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setSizes([SIDEBAR_WIDTH, 1000])
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH)

        root.addWidget(self.edit_toolbar)
        root.addWidget(self._build_search_bar())
        root.addWidget(self.body_splitter, 1)

        # toolbar
        self.toolbar = QWidget(); self.toolbar.setObjectName("reader_toolbar")
        tbg = _dc("#1e1e1e", "#f0f0f0"); tbrd = _dc("#3a3a3a", "#d0d0d0")
        tct = _dc("#ccc", "#333"); tbtn = _dc("#333", "#e8e8e8"); tbdr = _dc("#555", "#bbb")
        tbhv = _dc("#444", "#ddd"); tdst = _dc("#555", "#bbb"); tdbg = _dc("#2a2a2a", "#eee")
        itxt = _dc("#fff", "#333"); ibg = _dc("#2a2a2a", "#fff"); ibrd = _dc("#555", "#bbb")
        lt = _dc("#999", "#666"); bct = _dc("#ccc", "#333"); bcthv = _dc("#fff", "#fff")
        self.toolbar.setStyleSheet(
            f"QWidget#reader_toolbar{{background:{tbg};border-top:1px solid {tbrd}}}"
            f"QPushButton{{color:{tct};background:{tbtn};border:1px solid {tbdr};border-radius:4px;padding:5px 12px;font-size:13px}}"
            f"QPushButton:hover{{background:{tbhv}}}"
            f"QPushButton:checked{{background:#007aff;color:#fff;border-color:#007aff}}"
            f"QPushButton:disabled{{color:{tdst};background:{tdbg}}}"
            f"QLineEdit{{color:{itxt};background:{ibg};border:1px solid {ibrd};border-radius:4px;padding:4px 6px;font-size:13px}}"
            f"QLabel{{color:{lt};font-size:13px}}"
            f"#btn_close{{color:{bct};background:transparent;border:none;font-size:16px;padding:2px 6px}}"
            f"#btn_close:hover{{color:{bcthv};background:#c33;border-radius:4px}}")
        tb = QHBoxLayout(self.toolbar); tb.setContentsMargins(8,6,8,6); tb.setSpacing(8)

        self.btn_scroll = QPushButton("Scroll")
        self.btn_scroll.setCheckable(True); self.btn_scroll.setChecked(True)
        self.btn_scroll.clicked.connect(lambda: self._set_mode(ViewMode.SCROLL))
        self._hover_on(self.btn_scroll)

        self.btn_grid = QPushButton("Grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.clicked.connect(lambda: self._set_mode(ViewMode.GRID))
        self._hover_on(self.btn_grid)

        self.btn_sidebar = QPushButton("☰")
        self.btn_sidebar.setCheckable(True)
        self.btn_sidebar.setChecked(True)
        self.btn_sidebar.setFixedSize(34, 34)
        self.btn_sidebar.setToolTip(tr("reader_sidebar_tip"))
        self.btn_sidebar.clicked.connect(lambda: self.toggle_sidebar())
        self._hover_on(self.btn_sidebar)

        self.btn_search = QPushButton("🔍")
        self.btn_search.setFixedSize(34, 34)
        self.btn_search.setToolTip(tr("reader_search_tip"))
        self.btn_search.clicked.connect(lambda: self.show_search_bar(True))
        self._hover_on(self.btn_search)

        tb.addWidget(self.btn_sidebar)
        tb.addWidget(self.btn_scroll); tb.addWidget(self.btn_grid)
        tb.addWidget(self.btn_search)
        tb.addSpacing(16)
        self.btn_edit = QPushButton("✎ Edit"); self.btn_edit.setCheckable(True)
        self.btn_edit.clicked.connect(self._toggle_edit_mode)
        self.btn_edit.hide()  # only visible in Grid mode
        self._hover_on(self.btn_edit)
        tb.addWidget(self.btn_edit)
        tb.addStretch()

        self.btn_prev = QPushButton("◀"); self.btn_prev.setFixedSize(34,34)
        self.btn_prev.clicked.connect(self.prev_page)
        self._hover_on(self.btn_prev)

        self.page_label = QLabel("0 / 0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setFixedWidth(70)
        pl = _dc("#bbb", "#555")
        self.page_label.setStyleSheet(f"QLabel{{color:{pl}}}")

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
        fn_c = _dc("#888", "#777"); fn_bg = _dc("#1a1a1a", "#e8e8e8"); fn_b = _dc("#333", "#ccc")
        fn_bt = _dc("#222", "#ddd"); fn_bl = _dc("#222", "#ddd")
        self.label_filename.setStyleSheet(
            f"QLabel{{color:{fn_c};background:{fn_bg};border:1px solid {fn_b};"
            f"border-radius:6px;padding:4px 10px;font-size:12px;"
            f"border-top:1px solid {fn_bt};border-left:1px solid {fn_bl};}}")
        self.label_filename.hide()  # hidden until a document is loaded
        tb.addWidget(self.label_filename)

        self.btn_close = QPushButton("✕"); self.btn_close.setObjectName("btn_close")
        self.btn_close.setFixedSize(26,26); self.btn_close.setToolTip("Close this document")
        self.btn_close.clicked.connect(self._on_close)
        self.btn_close.hide()  # hidden until a document is loaded
        tb.addWidget(self.btn_close)

        root.addWidget(self.toolbar)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setMouseTracking(True)
        # Collect all toolbar widgets for tooltip management
        self._toolbar_buttons = [
            self.btn_sidebar, self.btn_search,
            self.btn_scroll, self.btn_grid, self.btn_edit, self.btn_prev, self.btn_next,
            self.btn_zoom_out, self.btn_zoom_in, self.zoom_edit, self.btn_fit_width,
            self.btn_fit_height, self.btn_close,
            # Edit toolbar buttons
            self.btn_edit_sel, self.btn_edit_sort, self.btn_edit_rot,
            self.btn_edit_del, self.btn_edit_extract, self.btn_edit_export,
            self.btn_edit_print, self.btn_edit_saveas, self.btn_edit_undo,
            self.btn_edit_redo,
        ]
        self._store_tooltips()

    # ═══════════ Sidebar (outline + search) ═══════════

    def _build_sidebar(self) -> QWidget:
        """Left panel with a Contents tab and a Search-results tab."""
        panel = QWidget()
        panel.setObjectName("reader_sidebar")
        sb_bg = _dc("#252525", "#efefef")
        sb_brd = _dc("#3a3a3a", "#d0d0d0")
        sb_fg = _dc("#ccc", "#333")
        panel.setStyleSheet(
            f"QWidget#reader_sidebar{{background:{sb_bg};"
            f"border-right:1px solid {sb_brd};}}"
            f"QLabel{{color:{sb_fg};font-size:12px;}}"
            f"QTreeWidget,QListWidget{{background:transparent;border:none;"
            f"color:{sb_fg};font-size:12px;outline:none;}}"
            f"QTreeWidget::item,QListWidget::item{{padding:3px 2px;}}"
            f"QTreeWidget::item:selected,QListWidget::item:selected"
            f"{{background:#007aff;color:#fff;border-radius:3px;}}"
            f"QCheckBox{{color:{sb_fg};font-size:11px;}}")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Tabs
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.btn_tab_outline = QToolButton()
        self.btn_tab_search = QToolButton()
        for btn in (self.btn_tab_outline, self.btn_tab_search):
            btn.setCheckable(True)
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            tabs.addWidget(btn)
        tabs.addStretch()
        self.btn_tab_outline.setChecked(True)
        self.btn_tab_outline.clicked.connect(lambda: self._show_sidebar_tab(0))
        self.btn_tab_search.clicked.connect(lambda: self._show_sidebar_tab(1))
        layout.addLayout(tabs)

        self.sidebar_stack = QStackedWidget()

        # Page 0 — outline
        self.outline_tree = QTreeWidget()
        self.outline_tree.setHeaderHidden(True)
        self.outline_tree.itemClicked.connect(self._on_outline_clicked)
        self.outline_tree.itemActivated.connect(self._on_outline_clicked)
        self.sidebar_stack.addWidget(self.outline_tree)

        # Page 1 — search results
        search_page = QWidget()
        sp_layout = QVBoxLayout(search_page)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(4)
        self.search_list = QListWidget()
        self.search_list.itemClicked.connect(self._on_search_item_clicked)
        sp_layout.addWidget(self.search_list, 1)
        self.search_status = QLabel("")
        self.search_status.setWordWrap(True)
        sp_layout.addWidget(self.search_status)
        self.sidebar_stack.addWidget(search_page)

        layout.addWidget(self.sidebar_stack, 1)
        return panel

    def _show_sidebar_tab(self, index: int):
        self.sidebar_stack.setCurrentIndex(index)
        self.btn_tab_outline.setChecked(index == 0)
        self.btn_tab_search.setChecked(index == 1)
        if not self._sidebar_visible:
            self.toggle_sidebar(True)

    def toggle_sidebar(self, show: bool = None):
        """Show/hide the left panel, keeping the splitter handle in sync."""
        if show is None:
            show = not self._sidebar_visible
        self._sidebar_visible = show
        self.sidebar.setVisible(show)
        if self.btn_sidebar is not None:
            self.btn_sidebar.setChecked(show)
        if show:
            sizes = self.body_splitter.sizes()
            if sizes and sizes[0] < 60:
                self.body_splitter.setSizes([SIDEBAR_WIDTH, max(200, sizes[1] - SIDEBAR_WIDTH)])
        QTimer.singleShot(0, self._on_resize)

    def _load_outline(self):
        """Populate the Contents tab from the document outline."""
        self.outline_tree.clear()
        if not self._path:
            self._update_outline_placeholder()
            return
        try:
            from core.search import get_outline
            entries = get_outline(self._path)
        except Exception:
            entries = []
        self._outline_entries = entries
        for entry in entries:
            self.outline_tree.addTopLevelItem(self._outline_item(entry))
        if entries:
            self.outline_tree.expandToDepth(0)
        self._update_outline_placeholder()

    def _outline_item(self, entry) -> QTreeWidgetItem:
        label = entry.title.strip() or f"Page {entry.page + 1}"
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, entry.page)
        if entry.bold:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        if entry.page >= 0:
            item.setToolTip(0, f"{label} — p.{entry.page + 1}")
        for child in entry.children:
            item.addChild(self._outline_item(child))
        return item

    def _update_outline_placeholder(self):
        """Explain an empty outline instead of showing a blank panel."""
        if self._outline_entries:
            self.outline_tree.setHeaderHidden(True)
            return
        placeholder = QTreeWidgetItem([tr("reader_no_outline")])
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self.outline_tree.addTopLevelItem(placeholder)

    def _on_outline_clicked(self, item: QTreeWidgetItem, _column: int = 0):
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is None or page < 0:
            return
        if self._view_mode == ViewMode.GRID:
            self._on_grid_dbl_click(int(page))
        else:
            self.go_to_page(int(page) + 1)

    # ═══════════ Search ═══════════

    def _build_search_bar(self):
        """Find bar shown above the toolbar when Ctrl+F is pressed."""
        bar = QWidget()
        bar.setObjectName("search_bar")
        bg = _dc("#2a2a2a", "#ffffff")
        brd = _dc("#3a3a3a", "#c8c8c8")
        fg = _dc("#ccc", "#333")
        bar.setStyleSheet(
            f"QWidget#search_bar{{background:{bg};border-top:1px solid {brd};"
            f"border-bottom:1px solid {brd};}}"
            f"QLineEdit{{color:{fg};background:{_dc('#1e1e1e', '#f7f7f7')};"
            f"border:1px solid {brd};border-radius:4px;padding:4px 8px;font-size:13px;}}"
            f"QLabel{{color:{fg};font-size:12px;}}"
            f"QCheckBox{{color:{fg};font-size:12px;}}")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("reader_search_placeholder"))
        self.search_edit.returnPressed.connect(self.find_next)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.search_edit.setMinimumWidth(200)
        row.addWidget(self.search_edit, 1)

        self.search_check_case = QCheckBox(tr("reader_search_case"))
        self.search_check_case.toggled.connect(self._on_search_option_changed)
        row.addWidget(self.search_check_case)

        self.search_count_label = QLabel("")
        row.addWidget(self.search_count_label)

        self.btn_search_prev = QPushButton("◀")
        self.btn_search_prev.setFixedSize(28, 26)
        self.btn_search_prev.setToolTip(tr("reader_search_prev"))
        self.btn_search_prev.clicked.connect(self.find_prev)
        row.addWidget(self.btn_search_prev)

        self.btn_search_next = QPushButton("▶")
        self.btn_search_next.setFixedSize(28, 26)
        self.btn_search_next.setToolTip(tr("reader_search_next"))
        self.btn_search_next.clicked.connect(self.find_next)
        row.addWidget(self.btn_search_next)

        self.btn_search_close = QPushButton("✕")
        self.btn_search_close.setFixedSize(28, 26)
        self.btn_search_close.setToolTip(tr("reader_search_close"))
        self.btn_search_close.clicked.connect(lambda: self.show_search_bar(False))
        row.addWidget(self.btn_search_close)

        self.search_bar = bar
        bar.hide()
        return bar

    def show_search_bar(self, show: bool = True, query: str = None):
        if show:
            self.search_bar.show()
            if query is not None:
                self.search_edit.setText(query)
            self.search_edit.setFocus()
            self.search_edit.selectAll()
            if self.search_edit.text().strip():
                self.start_search(self.search_edit.text())
        else:
            self.search_bar.hide()
            self.clear_search()
            self.setFocus()

    def _on_search_text_changed(self, _text: str):
        self._search_debounce.start()

    def _on_search_option_changed(self, _checked: bool):
        if self.search_edit.text().strip():
            self._search_debounce.start()

    def _run_debounced_search(self):
        self.start_search(self.search_edit.text())

    def start_search(self, query: str, select_first: bool = True):
        """Run a document-wide search and show the hits in the sidebar."""
        self._search_debounce.stop()
        query = (query or "").strip()
        self._search_query = query
        self._search_case = self.search_check_case.isChecked()
        self._search_hits = []
        self._search_index = -1
        self._highlight_rects = {}
        self.search_list.clear()
        if not query or not self.doc or not self._path:
            self.search_count_label.setText("")
            self.search_status.setText("")
            PdfReaderWidget._invalidate_pages(range(self._total_pages))
            self._refresh_visible_pixmaps()
            if self._view_mode == ViewMode.SCROLL:
                self._render_visible_range_async(0)
            return
        try:
            from core.search import search_pdf
            result = search_pdf(self._path, query,
                                case_sensitive=self._search_case,
                                max_hits=SEARCH_MAX_HITS)
        except Exception as ex:
            self.search_status.setText(str(ex))
            return
        self._search_hits = result.hits
        for i, hit in enumerate(result.hits):
            text = hit.context or hit.text
            item = QListWidgetItem(f"p.{hit.page + 1}  {text[:60]}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setToolTip(text)
            self.search_list.addItem(item)
        self._refresh_highlight_cache()
        if self._search_hits:
            self.search_status.setText(
                tr("reader_search_found", count=len(self._search_hits),
                   pages=len(result.pages_with_hits())))
            self.search_count_label.setText(
                f"{len(self._search_hits)}" + ("+" if result.truncated else ""))
            self._show_sidebar_tab(1)
            if select_first:
                self._goto_hit(0)
        else:
            self.search_status.setText(tr("reader_search_none"))
            self.search_count_label.setText("0")
        self._repaint_highlights()

    def _refresh_highlight_cache(self):
        """Group hit rectangles per page for fast repaint."""
        rects = {}
        for hit in self._search_hits:
            rects.setdefault(hit.page, []).append(hit.rect)
        self._highlight_rects = rects
        # Affected pages must be re-rendered: the highlights are painted into the
        # cached pixmap, so the old entries are stale.
        PdfReaderWidget._invalidate_pages(list(rects.keys()))

    def clear_search(self):
        self._search_hits = []
        self._search_index = -1
        self._search_query = ""
        self._highlight_rects = {}
        self.search_list.clear()
        self.search_count_label.setText("")
        self.search_status.setText("")
        if self.doc:
            PdfReaderWidget._invalidate_pages(range(self._total_pages))
            self._repaint_highlights()

    def find_next(self):
        self._step_search(1)

    def find_prev(self):
        self._step_search(-1)

    def _step_search(self, delta: int):
        if not self._search_hits:
            if self.search_edit.text().strip():
                self.start_search(self.search_edit.text())
            return
        self._goto_hit((self._search_index + delta) % len(self._search_hits))

    def _goto_hit(self, index: int):
        if not self._search_hits:
            return
        index = max(0, min(index, len(self._search_hits) - 1))
        self._search_index = index
        hit = self._search_hits[index]
        # A hit carried over from a previously opened document could point past
        # the end of the new one, which made the page label read e.g. "61 / 3".
        if hit.page >= self._total_pages:
            return
        self.search_list.setCurrentRow(index)
        self._current_page = hit.page
        self._pending_scroll_page = hit.page
        self._layout_labels()
        self._apply_pending_scroll()
        self._scroll_to_hit(hit)
        self._update_nav_ui()
        self.search_count_label.setText(f"{index + 1}/{len(self._search_hits)}")
        self._repaint_highlights()

    def _scroll_to_hit(self, hit):
        """Nudge the viewport so the hit itself is visible, not just its page."""
        if self._view_mode != ViewMode.SCROLL:
            return
        if hit.page >= len(self._page_heights):
            return
        page_top = self._page_heights[hit.page]
        pct = self._current_zoom_pct() / 100.0
        y0 = page_top + hit.rect[1] * pct
        sb = self.scroll_area.verticalScrollBar()
        view_h = self._viewport_height()
        if y0 < sb.value() or y0 > sb.value() + view_h - 60:
            sb.setValue(max(0, int(y0 - view_h / 3)))

    def _repaint_highlights(self):
        """Redraw the affected pages so search highlights appear/disappear."""
        if self._view_mode == ViewMode.GRID:
            self._refresh_visible_pixmaps()
            return
        self._render_visible_range_async(0)

    def _on_search_item_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None:
            self._goto_hit(int(idx))

    def _hover_on(self, widget):
        """Attach mouse tracking to a toolbar button."""
        widget._oe = widget.enterEvent; widget._ol = widget.leaveEvent
        def enter_event(e):
            self._hover_widget = widget; self._hover_timer.start(500)
            self._hover_pos = e.globalPosition().toPoint()
            # Cancel any pending leave-hide timer
            if self._hide_timer.isActive(): self._hide_timer.stop()
            if widget._oe: widget._oe(e)
        def leave_event(e):
            self._hover_timer.stop()
            # Delay hide by 200ms to prevent flicker on brief boundary crossings
            self._hide_timer.start(200)
            if widget._ol: widget._ol(e)
        widget.enterEvent = enter_event; widget.leaveEvent = leave_event
        widget.setMouseTracking(True)
        if hasattr(widget, 'mouseMoveEvent'):
            widget._om = widget.mouseMoveEvent
            def move_event(e):
                if getattr(self, '_hover_widget', None) is widget:
                    self._hover_pos = e.globalPosition().toPoint()
                    self._hover_timer.start(500)
                if widget._om: widget._om(e)
            widget.mouseMoveEvent = move_event

    def _store_tooltips(self):
        """Read all tooltip texts from buttons, then clear Qt system tooltips
        so only our compact custom QLabel shows."""
        for w in self._toolbar_buttons:
            t = w.toolTip()
            if t:
                self._tooltip_texts[id(w)] = t
            w.setToolTip("")   # kill Qt system big tooltip

    def _show_tooltip(self):
        w = getattr(self, '_hover_widget', None)
        if w and hasattr(self, '_hover_pos'):
            t = self._tooltip_texts.get(id(w), "")
            if t:
                p = self.mapFromGlobal(self._hover_pos)
                self._tooltip.setText(t); self._tooltip.adjustSize()
                x = p.x() + 12  # right of cursor
                y = p.y() - self._tooltip.height() - 8  # above cursor
                if x + self._tooltip.width() > self.width():
                    x = p.x() - self._tooltip.width() - 12
                if y < 0: y = p.y() + 16
                self._tooltip.move(x, y)
                self._tooltip.show(); self._tooltip.raise_()
                # Cancel hide timer if tooltip was re-shown, then set 5s auto-hide
                self._hide_timer.stop()  # stop any pending leave-hide
                # One reusable timer: allocating a fresh QTimer per hover left 6
                # live timers after 6 hovers, and an older 5s timer would hide a
                # later tooltip early.
                self._auto_hide_timer.start(5000)

    # ═══════════ Mode ═══════════

    def _hide_page_numbers(self):
        """Destroy all page-number labels in the container."""
        for label in self._labels:
            pn = getattr(label, '_page_num_label', None)
            if pn:
                pn.hide()
                pn.setParent(None)
                pn.deleteLater()
                label._page_num_label = None

    def _set_mode(self, mode: ViewMode):
        if mode == ViewMode.GRID and self._view_mode == ViewMode.SCROLL:
            # Save Scroll zoom before entering Grid
            self._saved_scroll_zoom = self._zoom_mode
            self.btn_edit.show()
        if mode == ViewMode.SCROLL and self._view_mode == ViewMode.GRID:
            self.btn_edit.hide()   # Edit button only in Grid mode
            self._hide_page_numbers()
            # Restore Scroll zoom from before Grid
            if self._saved_scroll_zoom is not None:
                saved = self._saved_scroll_zoom
                self._view_mode = mode
                self.btn_scroll.setChecked(True)
                self.btn_grid.setChecked(False)
                if isinstance(saved, float):
                    self._set_zoom_pct(int(saved * 100))
                elif saved == "fit_width":
                    self._on_fit_width()
                elif saved == "fit_height":
                    self._on_fit_height()
                else:
                    self._on_fit_height()  # fallback
                return
        self._view_mode = mode
        self.btn_scroll.setChecked(mode == ViewMode.SCROLL)
        self.btn_grid.setChecked(mode == ViewMode.GRID)
        if self.doc:
            # The container size — and therefore the scrollable range — depends on
            # the mode, so the scroll target must be re-applied once Qt has
            # processed the resize; otherwise the stale range clamps it.
            self._pending_scroll_page = self._current_page
            self._layout_labels()
            self._deferred_relayout()
            if mode == ViewMode.SCROLL:
                self._schedule_render_visible(0)

    def _on_close(self):
        """Close button handler — warns if unsaved edits exist."""
        if self.doc:
            if self._unsaved_edits:
                result = self._prompt_save_changes()
                if result == "cancel": return
                if result == "save_as":
                    self._save_edited_copy()
            self.close_document()
            self.close_requested.emit()

    def _prompt_save_changes(self) -> str:
        """Show save-before-close dialog. Returns 'save_as', 'discard', or 'cancel'."""
        msg = QMessageBox(self)
        msg.setWindowTitle(tr("reader_unsaved_title"))
        msg.setText(tr("reader_unsaved_body"))
        msg.setIcon(QMessageBox.Icon.Warning)
        btn_save = msg.addButton(tr("reader_unsaved_saveas"), QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton(tr("reader_unsaved_discard"),
                                    QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(tr("reader_unsaved_cancel"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_cancel)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_save: return "save_as"
        if clicked == btn_discard: return "discard"
        return "cancel"

    def _save_edited_copy(self):
        """Save the edited document to a new file."""
        path, _ = QFileDialog.getSaveFileName(
            self, tr("reader_saveas_title"), "edited.pdf", tr("file_filter_pdf"))
        if path:
            self._page_editor.save(Path(path))
            self._unsaved_edits = False
        self._layout_labels()  # Bug 4 fix: re-layout after dialog

    def _revert_to_original(self):
        """Discard all edits: reload the original document snapshot."""
        if self._original_snapshot and self.doc:
            import io, fitz
            self.doc.close()
            new_doc = fitz.open(stream=self._original_snapshot, filetype="pdf")
            buf = io.BytesIO()
            new_doc.save(buf)
            new_doc.close()
            buf.seek(0)
            self.doc = fitz.open(stream=buf.read(), filetype="pdf")
            if self._page_editor:
                self._page_editor.attach(self.doc)
            self._unsaved_edits = False
            self._total_pages = len(self.doc)
            self._current_page = 0
            PdfReaderWidget._clear_cache()
            self._destroy_labels()
            self._build_labels()
            # Don't call _layout_labels here — _leave_edit_mode calls it after cleanup.
            self._edit_buttons_dirty = True

    def closeEvent(self, event):
        """Window close — check unsaved edits before closing."""
        if self.doc and self._unsaved_edits:
            result = self._prompt_save_changes()
            if result == "cancel":
                event.ignore()
                return
            if result == "save_as":
                self._save_edited_copy()
        event.accept()

    # ═══════════ Open / Close ═══════════

    def open_pdf(self, path: Path) -> None:
        import fitz
        # Leave any previous editing session first: its page editor still points
        # at the OLD document, so an edit made after this open would silently act
        # on (and then display) the previous file while the filename chip showed
        # the new one.
        self._reset_document_state()
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
        if self._total_pages == 0:
            # MuPDF happily opens a PDF with an empty page tree; self.doc[0]
            # below would raise IndexError inside a menu-action slot.
            self.doc.close(); self.doc = None; self._path = None
            self._show_welcome()
            return
        self._zoom_mode = "fit_height"     # open at page-height fit
        self.btn_fit_width.setChecked(False); self.btn_fit_height.setChecked(True)
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True); self.btn_grid.setChecked(False)
        self._page_rects = None      # geometry is per-document
        # Pre-compute fit ratios for later use
        page = self.doc[0]; pw, ph = page.rect.width, page.rect.height
        vw, vh = self._viewport_size()
        self._fw_ratio = vw / pw if pw > 0 else 1.0
        self._fh_ratio = vh / ph if ph > 0 else 1.0
        self._default_zoom_pct = max(50, min(300, int(self._fh_ratio * 100)))
        # Show the first page fitted to the window instead of a 100% crop: a
        # full A4 page at 100% is taller than a typical viewport, so the reader
        # would open mid-page. Fit-height makes the first screen readable and
        # matches what Acrobat/Preview do.
        self.zoom_edit.setText(str(self._default_zoom_pct))
        self._build_labels()
        self._layout_labels()
        self._load_outline()
        # Seed only the visible window's 100% base; the rest fills in lazily.
        self._pre_render_100_all()
        self._render_visible_range_async(0)
        self._update_nav_ui()
        self.label_filename.setText(path.name)
        self.label_filename.show()
        self.btn_close.show()
        self._restore_reading_position(path)
        self.document_changed.emit(str(path))
        self.setFocus()

    def _reset_document_state(self):
        """Drop every piece of per-document state before another file is opened.

        Search hits, highlight rectangles, the sidebar list and the page editor
        all used to survive the switch: search results from a 100-page document
        stayed in the sidebar over a 3-page one, the page label could read
        "61 / 3", and the old document's hit rectangles were baked into the new
        document's pixmaps. Edit mode also stayed armed on the old editor."""
        if self._edit_mode:
            self._leave_edit_mode(skip_prompt=True)
        self._page_editor = None
        self._original_snapshot = None
        self._unsaved_edits = False
        self._selected_pages.clear()
        self._prev_selected.clear()
        self._drag_source = None
        self._drag_active = False
        self._drag_target = None
        self._rubber_origin = None
        self._rubber_rect = None
        self._search_hits = []
        self._search_index = -1
        self._search_query = ""
        self._highlight_rects = {}
        self._outline_entries = []
        if getattr(self, "outline_tree", None) is not None:
            self.outline_tree.clear()
        if getattr(self, "search_list", None) is not None:
            self.search_list.clear()
        if getattr(self, "search_status", None) is not None:
            self.search_status.setText("")
        if getattr(self, "search_count_label", None) is not None:
            self.search_count_label.setText("")
        if getattr(self, "search_edit", None) is not None:
            self.search_edit.clear()

    # ═══════════ Reading position memory ═══════════

    def _remember_reading_position(self):
        """Persist the current page + zoom so reopening continues where you left."""
        if not self._path or not self._total_pages:
            return
        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings("PDFeverything", "PDFeverything")
            entries = settings.value("reader_positions", {}) or {}
            if not isinstance(entries, dict):
                entries = {}
            key = str(Path(self._path).resolve())
            zoom = self._zoom_mode if isinstance(self._zoom_mode, str) else \
                f"{self._zoom_mode:.3f}"
            entries[key] = {"page": self._current_page, "zoom": zoom}
            # Keep the store bounded — most recent 40 documents.
            if len(entries) > 40:
                for old in list(entries.keys())[:-40]:
                    entries.pop(old, None)
            settings.setValue("reader_positions", entries)
        except Exception:
            pass

    def _restore_reading_position(self, path: Path):
        """Jump back to the remembered page for this document, if any."""
        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings("PDFeverything", "PDFeverything")
            entries = settings.value("reader_positions", {}) or {}
            entry = entries.get(str(Path(path).resolve())) if isinstance(entries, dict) else None
        except Exception:
            entry = None
        if not entry:
            return
        zoom = entry.get("zoom")
        if zoom == "fit_width":
            self._zoom_mode = "fit_width"
            self.btn_fit_width.setChecked(True)
            self.btn_fit_height.setChecked(False)
            self.zoom_edit.setText(str(self._current_zoom_pct()))
        elif zoom == "fit_height":
            self._zoom_mode = "fit_height"
            self.btn_fit_height.setChecked(True)
            self.zoom_edit.setText(str(self._default_zoom_pct))
        else:
            try:
                self._zoom_mode = max(0.5, min(3.0, float(zoom)))
                self.zoom_edit.setText(str(int(self._zoom_mode * 100)))
            except (TypeError, ValueError):
                pass
        self._layout_labels()
        page = int(entry.get("page", 0))
        if 0 <= page < self._total_pages:
            self._current_page = page
            self._pending_scroll_page = page
            self._apply_pending_scroll()
            self._update_nav_ui()

    def close_document(self):
        self._remember_reading_position()
        self._original_snapshot = None   # a full copy of the file must not outlive it
        self._cancel_deferred_renders()
        self._grid_geom = None
        self._page_heights = []
        if self._edit_mode: self._leave_edit_mode(skip_prompt=True)  # prompt handled by caller
        if self._page_editor:
            # Don't close the editor's doc — it's our shared self.doc. We'll close it below.
            self._page_editor._doc = None
            self._page_editor = None
        if self.doc: self.doc.close(); self.doc = None
        self._path = None; self._total_pages = 0; self._current_page = 0
        self._saved_scroll_zoom = None
        self.clear_search()
        self._outline_entries = []
        self.outline_tree.clear()
        # Reset to default Scroll mode
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True); self.btn_grid.setChecked(False)
        self.btn_edit.hide(); self.btn_edit.setChecked(False)
        self._zoom_mode = 1.0; self.zoom_edit.setText("100")
        self._unsaved_edits = False
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
        self._cancel_lazy_pre_render()
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

        # Pass 1: scale only VISIBLE pages' 100% base pixmap to target zoom.
        # Non-visible pages don't need a pixmap — _layout_labels computes their
        # dimensions from PDF geometry × zoom. This saves ~500 iterations for
        # large PDFs while producing identical visual results.
        target_factor = pct / 100.0
        from PyQt6.QtCore import Qt as QtCore
        s, e = self._visible_page_range()
        for pi in range(s, e):
            try:
                label = self._labels[pi]
                base_key = (pi, "z:1.000")
                base = PdfReaderWidget._cache_get(base_key)
                if base is None or base.isNull():
                    old_zm = self._zoom_mode
                    self._zoom_mode = 1.0
                    vw2, vh2 = self._viewport_size()
                    base = self._get_or_render(pi, vw2, vh2)
                    self._zoom_mode = old_zm
                if base is None or base.isNull(): continue
                bw, bh = self._logical_size(base)
                tw, th = max(1, int(bw * target_factor)), max(1, int(bh * target_factor))
                label.setPixmap(base.scaled(tw, th,
                    QtCore.AspectRatioMode.IgnoreAspectRatio,
                    QtCore.TransformationMode.SmoothTransformation))
                label.setFixedSize(tw, th)
            except Exception: pass

        self._show_zoom_popup(pct)
        self._pending_scroll_page = self._current_page
        self._layout_labels()
        self._apply_pending_scroll()  # preserve scroll position after zoom

        if not skip_deferred:
            self._pending_zoom_pct = pct
            QTimer.singleShot(40, self._sharp_render)

    def _sharp_render(self):
        """Deferred: render visible pages at target zoom asynchronously.
        Yields to event loop between pages — UI stays responsive."""
        if not self.doc or not self._labels or self._pending_zoom_pct is None:
            return
        try:
            self._render_visible_range_async(0)
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
        """Seed the 100% immortal base for the pages the user can actually see.

        Rendering *every* page up front does not scale: a 500-page document would
        cost ~2s of CPU and ~1GB of RAM before the first pixel is shown. Instead we
        render the visible window synchronously (so the first screen is sharp) and
        let _lazy_pre_render walk a bounded ring around the current page while the
        event loop is idle. Geometry for the remaining pages comes from
        _layout_labels, which derives sizes from PDF page rects — no pixmap needed.
        """
        if not self.doc or not self._labels:
            return
        vw, vh = self._viewport_size()
        old = self._zoom_mode
        self._zoom_mode = 1.0
        first, last = self._render_window()
        for pi in range(first, last):
            self._get_or_render(pi, vw, vh)
        self._zoom_mode = old
        self._queue_lazy_pre_render()

    # ── Lazy 100%-base queue (bounded ring around the current page) ──

    def _render_window(self) -> tuple:
        """(first, last) page indices worth having a base pixmap for."""
        first = max(0, self._current_page - PRE_RENDER_LOOKAHEAD)
        last = min(self._total_pages,
                   self._current_page + PRE_RENDER_LOOKAHEAD + PRE_RENDER_AHEAD + 1)
        return first, last

    def _queue_lazy_pre_render(self):
        """(Re)start the background base-render walk for the current window."""
        if not self.doc or not self._labels:
            return
        first, last = self._render_window()
        self._lazy_window = (first, last)
        # Tell the shared cache which pages must not be evicted: these are the
        # ones Pass 1 zoom scaling and the next re-layout read from.
        PdfReaderWidget._protected_pages = set(range(first, last))
        self._lazy_pre_render_index = first
        self._lazy_rendering = True
        QTimer.singleShot(LAZY_RENDER_INTERVAL_MS, self._lazy_pre_render)

    def _cancel_lazy_pre_render(self):
        """Stop the background walk (document closed / replaced)."""
        self._lazy_rendering = False

    def _lazy_pre_render(self):
        """Render at most one missing 100% base pixmap, then yield.

        The walk is bounded to the current ± lookahead window, so a 1000-page
        PDF never renders pages the user will not scroll to. When the window is
        complete the loop stops until the next navigation restarts it."""
        if not self.doc or not self._labels or not self._lazy_rendering:
            return
        target = self._lazy_pre_render_index
        first, last = self._lazy_window
        if target >= last:
            self._lazy_rendering = False
            return
        vw, vh = self._viewport_size()
        old = self._zoom_mode
        self._zoom_mode = 1.0
        try:
            if target >= first and 0 <= target < len(self._labels):
                self._get_or_render(target, vw, vh)
        except Exception:
            pass
        finally:
            self._zoom_mode = old
        self._lazy_pre_render_index = target + 1
        QTimer.singleShot(LAZY_RENDER_INTERVAL_MS, self._lazy_pre_render)

    def _schedule_render_visible(self, delay_ms: int = 0):
        """Schedule the visible-range render. Every render trigger (zoom, scroll
        stop, navigation) funnels through here so there is a single place that
        re-arms the background base cache."""
        if not self.doc:
            return
        self._cancel_lazy_pre_render()
        self._queue_lazy_pre_render()
        if delay_ms <= 0:
            self._render_visible_range_async(0)
        else:
            QTimer.singleShot(delay_ms, lambda: self._render_visible_range_async(0))

    def _render_visible_range_async(self, pi_index=0):
        """Render visible pages one at a time, yielding to the event loop
        between each page. Current page always rendered first.
        On first call (pi_index=0), builds the ordered page list."""
        if not self.doc or not self._labels:
            return
        if pi_index == 0:
            vw, vh = self._viewport_size()
            s, e = self._visible_page_range()
            self._async_order = [self._current_page] + [p for p in range(s, e) if p != self._current_page]
            self._async_vw, self._async_vh = vw, vh
        if pi_index >= len(self._async_order):
            self._layout_labels()
            return
        pi = self._async_order[pi_index]
        if pi < 0 or pi >= len(self._labels):
            QTimer.singleShot(0, lambda: self._render_visible_range_async(pi_index + 1))
            return
        try:
            key = (pi, self._zoom_key(self._async_vw, self._async_vh))
            pix = PdfReaderWidget._cache_get(key)
            if pix is None:
                pix = self._get_or_render(pi, self._async_vw, self._async_vh)
            if pix:
                self._labels[pi].setPixmap(pix)
                lw, lh = self._logical_size(pix)
                self._labels[pi].setFixedSize(lw, lh)
        except Exception:
            pass
        QTimer.singleShot(0, lambda: self._render_visible_range_async(pi_index + 1))

    def _render_visible_range(self):
        """Deprecated — kept for backward compat. Routes to async version."""
        self._render_visible_range_async(0)

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
        """Flash the zoom level centred over the *page area*.

        The popup is parented to the scroll viewport at creation time so its
        coordinates are relative to the visible page region; parenting it to the
        widget would place it too low by the height of the reader toolbars."""
        self._zoom_popup.setText(f"🔍 {pct}%")
        self._zoom_popup.adjustSize()
        host = self.scroll_area.viewport()
        if self._zoom_popup.parent() is not host:
            self._zoom_popup.setParent(host)
        r = host.rect()
        x = max(0, (r.width() - self._zoom_popup.width()) // 2)
        y = max(0, r.height() // 3)
        self._zoom_popup.move(x, y)
        self._zoom_popup.show()
        self._zoom_popup.raise_()
        self._zoom_popup_timer.start()

    def _hide_zoom_popup(self):
        self._zoom_popup.hide()

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

        # Pass 1: instant — scale VISIBLE pages' 100% base using LOGICAL size.
        # Visible-only: same optimization as _set_zoom_pct Pass 1.
        target_factor = pct / 100.0
        from PyQt6.QtCore import Qt as QtCore
        s, e = self._visible_page_range()
        for pi in range(s, e):
            try:
                label = self._labels[pi]
                base_key = (pi, "z:1.000")
                base = PdfReaderWidget._cache_get(base_key)
                if base is None or base.isNull():
                    old_zm = self._zoom_mode
                    self._zoom_mode = 1.0
                    vw2, vh2 = self._viewport_size()
                    base = self._get_or_render(pi, vw2, vh2)
                    self._zoom_mode = old_zm
                if base is None or base.isNull(): continue
                bw, bh = self._logical_size(base)
                tw, th = max(1, int(bw * target_factor)), max(1, int(bh * target_factor))
                label.setPixmap(base.scaled(tw, th,
                    QtCore.AspectRatioMode.IgnoreAspectRatio,
                    QtCore.TransformationMode.SmoothTransformation))
                label.setFixedSize(tw, th)
            except Exception: pass

        self._pending_scroll_page = self._current_page
        self._layout_labels()
        self._show_zoom_popup(pct)
        self._pending_zoom_pct = pct
        self._apply_pending_scroll()   # keep the reader on the same page
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
            # Destroy attached page number labels
            pn = getattr(label, '_page_num_label', None)
            if pn: pn.setParent(None); pn.deleteLater()
            label.setParent(None); label.deleteLater()
        self._labels.clear()
        self.scroll_area.verticalScrollBar().blockSignals(False)

    def _layout_labels(self, render_missing: bool = False):
        """Recompute the page layout for the active view mode.

        Geometry always comes from PDF page rects × zoom (never from pixmap
        dimensions, which may be stale) so heights stay consistent and page Y
        offsets never cascade. Scroll mode is O(1) per page; grid mode pushes
        thumbnails only for the rows that intersect the viewport.
        """
        vw, vh = self._viewport_size()
        self._layout_vw = vw
        if self._view_mode == ViewMode.SCROLL:
            self._layout_scroll(vw)
        elif self._view_mode == ViewMode.GRID:
            self._layout_grid(vw, vh)

    # ── Scroll mode ──────────────────────────────────

    def _page_rects_px(self) -> list:
        """Per-page (width, height) in PDF points, cached per document.

        _layout_scroll runs on every scroll-stop, zoom tick, mode switch and
        resize, and it needs every page's geometry. Reading `doc[pi].rect` inside
        that loop accounted for 7.5ms of the 9.5ms a 1000-page layout cost, so a
        pinch-zoom tick spent most of its 16.7ms frame budget there. The geometry
        only changes when the document changes, so one cached pass pays off."""
        if self._page_rects is not None and len(self._page_rects) == self._total_pages:
            return self._page_rects
        rects = []
        if self.doc is not None:
            for pi in range(self._total_pages):
                try:
                    r = self.doc[pi].rect
                    rects.append((r.width, r.height))
                except Exception:
                    rects.append((595.0, 842.0))
        self._page_rects = rects
        return rects

    def _layout_scroll(self, vw: int):
        sp, mg = 16, 20
        z = self._current_zoom_pct() / 100.0
        heights = self._page_heights = []
        rects = self._page_rects_px()
        y = mg
        visible_y0 = self.scroll_area.verticalScrollBar().value()
        visible_y1 = visible_y0 + self._viewport_height()
        for pi, label in enumerate(self._labels):
            if pi < len(rects):
                w, h = int(rects[pi][0] * z), int(rects[pi][1] * z)
            else:
                w, h = 600, 800
            label.setFixedSize(w, h)
            label.move(max(0, (vw - w) // 2), y)
            self._apply_page_style(label, selected=False, grid=False)
            # Only materialise widgets that are inside (or near) the viewport.
            if y + h >= visible_y0 - self._viewport_height() and y <= visible_y1 + self._viewport_height():
                if not label.isVisible():
                    label.show()
            elif label.isVisible():
                label.hide()
            heights.append(y)
            y += h + sp
        self.page_container.setFixedSize(vw, max(1, y - sp + mg))

    # ── Grid mode ────────────────────────────────────

    def _grid_geometry(self, vw: int) -> dict:
        """Cell + per-page thumbnail geometry. Cached so selection changes never
        touch the document or the layout maths."""
        cache = self._grid_geom
        if cache is not None and cache["vw"] == vw and cache["pages"] == self._total_pages:
            return cache
        cols = GRID_COLS
        side_margin, gutter_h, gutter_v, mg = 20, 20, 30, 20
        usable = vw - 2 * side_margin - (cols - 1) * gutter_h
        cell_w = max(140, usable // cols)
        # A full A4 cell is tall enough that barely one row fits on screen; cap the
        # row height so a tall window always shows ~2 rows (thumbnails stay legible).
        cell_h = min(int(cell_w * GRID_CELL_RATIO),
                     max(GRID_MIN_CELL_H, (self._viewport_height() - 2 * mg) // 2))
        cell_h = max(GRID_MIN_CELL_H, cell_h)
        label_h = GRID_PAGE_LABEL_H
        dims = []
        for pi in range(self._total_pages):
            if self.doc and pi < len(self.doc):
                rect = self.doc[pi].rect
                pw, ph = rect.width, rect.height
            else:
                pw, ph = 595, 842
            scale = min(cell_w / pw if pw else 1.0,
                        (cell_h - label_h) / ph if ph else 1.0)
            dw, dh = max(1, int(pw * scale)), max(1, int(ph * scale))
            dims.append((dw, dh, max(0, (cell_w - dw) // 2),
                         max(0, (cell_h - label_h - dh) // 2)))
        grid_w = cols * cell_w + (cols - 1) * gutter_h
        rows = (self._total_pages + cols - 1) // cols
        cache = {
            "vw": vw, "pages": self._total_pages, "cols": cols,
            "cell_w": cell_w, "cell_h": cell_h, "label_h": label_h,
            "gutter_h": gutter_h, "gutter_v": gutter_v, "mg": mg,
            "left": (vw - grid_w) // 2, "dims": dims, "rows": rows,
        }
        self._grid_geom = cache
        return cache

    def _cell_rect(self, pi: int):
        """Cell rectangle for page index pi (used by hit-testing)."""
        g = self._grid_geometry(self._viewport_size()[0])
        col, row = pi % g["cols"], pi // g["cols"]
        return (g["left"] + col * (g["cell_w"] + g["gutter_h"]),
                g["mg"] + row * (g["cell_h"] + g["gutter_v"]),
                g["cell_w"], g["cell_h"])

    def _layout_grid(self, vw: int, vh: int, pixmaps: bool = True):
        g = self._grid_geometry(vw)
        cell_w, cell_h, label_h = g["cell_w"], g["cell_h"], g["label_h"]
        cols, gutter_h, gutter_v, mg, left = (g["cols"], g["gutter_h"],
                                              g["gutter_v"], g["mg"], g["left"])
        # Row window that intersects the viewport (±1 row of slack for inertia).
        sb = self.scroll_area.verticalScrollBar()
        top = min(sb.value(), max(0, self.page_container.height() - self._viewport_height()))
        bottom = top + self._viewport_height()
        row_px = cell_h + gutter_v
        first_row = max(0, (top - mg) // row_px - 1)
        last_row = min(g["rows"] - 1, (bottom - mg) // row_px + 1)
        lo, hi = first_row * cols, min(self._total_pages, (last_row + 1) * cols)

        page_num_style = self._page_num_style()
        for pi, label in enumerate(self._labels):
            if pi < lo or pi >= hi:
                if label.isVisible():
                    label.hide()
                pn = getattr(label, "_page_num_label", None)
                if pn is not None and pn.isVisible():
                    pn.hide()
                continue
            dw, dh, ox, oy = g["dims"][pi]
            if pixmaps and label.pixmap() is None:
                pix = self._get_or_render(pi, dw, dh, force_fit=True)
                if pix:
                    label.setPixmap(pix)
            label.setFixedSize(dw, dh)
            self._apply_page_style(
                label,
                selected=self._edit_mode and pi in self._selected_pages,
                grid=True,
                drop_target=(self._edit_mode and self._drag_target == pi))
            col, row = pi % cols, pi // cols
            cell_x = left + col * (cell_w + gutter_h)
            cell_y = self._page_grid_y(pi, g)
            label.move(cell_x + ox, cell_y + oy)
            label.show()
            page_num = getattr(label, "_page_num_label", None)
            if page_num is None:
                page_num = QLabel(str(pi + 1), self.page_container)
                page_num.setStyleSheet(page_num_style)
                page_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label._page_num_label = page_num
            elif page_num.text() != str(pi + 1):
                page_num.setText(str(pi + 1))
            page_num.setFixedWidth(cell_w)
            page_num.move(cell_x, cell_y + cell_h - label_h + 2)
            page_num.show()
            if not hasattr(label, "_grid_click_set"):
                label._grid_click_set = True
                orig_press = label.mousePressEvent
                label.mousePressEvent = self._make_grid_press(orig_press, pi)
                label.mouseDoubleClickEvent = self._grid_dbl_click_handler

        self.page_container.setFixedSize(
            vw, 2 * mg + g["rows"] * cell_h + max(0, g["rows"] - 1) * gutter_v)

    def _make_grid_press(self, orig_press, page_index: int):
        """Press handler for one grid cell.

        The index is passed in rather than derived from the event: a Qt event
        delivered to a QLabel carries *label-local* coordinates, while
        _grid_page_at_pos works in container space, so hit-testing the event
        position made every thumbnail resolve to page 1 (and its left edge to
        the phantom index -1) — i.e. "click page 5, press Delete" deleted page 1.
        The embedding loop already knows which page this label is."""
        def handler(e):
            pi = page_index
            if self._edit_mode:
                self._on_grid_click(pi, e)
                return
            if pi >= 0:
                self._grid_last_press = pi
            if orig_press:
                orig_press(e)
        return handler

    def _grid_dbl_click_handler(self, ev):
        pi = getattr(self, "_grid_last_press", -1)
        if pi >= 0:
            self._on_grid_dbl_click(pi)

    def _apply_page_style(self, label, selected: bool, grid: bool,
                          drop_target: bool = False):
        """Set a label's frame style, touching the stylesheet only when it changes
        (a Qt stylesheet assignment forces a full re-polish of the widget)."""
        state = (selected, grid, drop_target)
        if getattr(label, "_style_state", None) == state:
            return
        label._style_state = state
        if grid:
            if drop_target:
                label.setStyleSheet(
                    "QLabel{background:white;border:2px dashed #ff9500;border-radius:4px;}")
            elif selected:
                label.setStyleSheet(
                    "QLabel{background:white;border:2px solid #007aff;border-radius:4px;}")
            else:
                label.setStyleSheet(
                    f"QLabel{{background:white;border:1px solid {_dc('#555', '#9a9a9a')};}}")
            label.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            label.setStyleSheet("QLabel{background:white;}")
            label.setCursor(Qt.CursorShape.ArrowCursor)

    def _page_num_style(self) -> str:
        return f"QLabel{{color:{_dc('#888', '#666')};font-size:10px;background:transparent;}}"

    def _on_grid_dbl_click(self, page_idx: int):
        if self._view_mode != ViewMode.GRID or self._edit_mode:
            return
        self._hide_page_numbers()
        self._current_page = page_idx
        self._pending_scroll_page = page_idx
        # Switch to Scroll mode and restore the zoom that was active before Grid
        self._view_mode = ViewMode.SCROLL
        self.btn_scroll.setChecked(True)
        self.btn_grid.setChecked(False)
        saved = self._saved_scroll_zoom
        if isinstance(saved, float):
            self._set_zoom_pct(int(saved * 100))   # applies the pending scroll
        elif saved == "fit_width":
            self._on_fit_width()
        else:
            self._on_fit_height()
        self._layout_labels()
        self._apply_pending_scroll()
        self._update_nav_ui()
        self._schedule_render_visible(0)

    # ═══════════ Grid Edit Mode ═══════════

    def _toggle_edit_mode(self):
        if not self.doc or self._view_mode != ViewMode.GRID:
            self.btn_edit.setChecked(False); return
        if self._edit_mode:
            self._leave_edit_mode()
        else:
            self._enter_edit_mode()

    def _enter_edit_mode(self):
        self._edit_mode = True; self.btn_edit.setChecked(True)
        self.btn_edit.setText(self._editing_label)  # use i18n string
        self._selected_pages.clear()
        # Snapshot current document state for "discard changes" revert
        if self.doc:
            import io
            buf = io.BytesIO()
            self.doc.save(buf)
            self._original_snapshot = buf.getvalue()
        # Lazy init page editor — share the GUI's fitz doc
        if self._page_editor is None and self.doc:
            from core.page_editor import PdfPageEditor
            self._page_editor = PdfPageEditor(self.doc, self._path)
        self._update_edit_buttons()
        # Install container-level event handlers for box-select + drag
        self.page_container._edit_widget = self
        self.page_container.setMouseTracking(True)
        self.page_container.mousePressEvent = self._grid_mouse_press
        self.page_container.mouseMoveEvent = self._grid_mouse_move
        self.page_container.mouseReleaseEvent = self._grid_mouse_release
        self.edit_toolbar.show()
        self._layout_labels()

    def _leave_edit_mode(self, skip_prompt=False):
        if not skip_prompt and self._unsaved_edits:
            result = self._prompt_save_changes()
            if result == "cancel": return
            if result == "save_as":
                self._save_edited_copy()
            elif result == "discard":
                self._revert_to_original()
        self._edit_mode = False; self.btn_edit.setChecked(False)
        self.btn_edit.setText(self._normal_label)  # use i18n string
        self._selected_pages.clear(); self._drag_source = None
        self.edit_toolbar.hide()
        # Restore container event handlers
        self.page_container.mousePressEvent = lambda e: None
        self.page_container.mouseMoveEvent = lambda e: None
        self.page_container.mouseReleaseEvent = lambda e: None
        self._layout_labels()

    # ── Rectangle box-select ──

    def _page_grid_y(self, pi: int, g: dict = None) -> int:
        """Container Y of page pi's row in Grid mode."""
        if g is None:
            g = self._grid_geometry(self._viewport_size()[0])
        row = pi // g["cols"]
        return g["mg"] + row * (g["cell_h"] + g["gutter_v"])

    def _page_scroll_pos(self, pi: int) -> int:
        """Scrollbar value that puts page pi's row/top inside the viewport."""
        if not self._total_pages:
            return 0
        pi = max(0, min(pi, self._total_pages - 1))
        if self._view_mode == ViewMode.GRID:
            return max(0, self._page_grid_y(pi) - 4)
        if pi < len(self._page_heights):
            return max(0, self._page_heights[pi])
        return 0

    def _apply_pending_scroll(self):
        """Move the viewport to the pending page once the layout it depends on is
        in place. Setting the value is also re-issued on the next event-loop turn
        because the scrollbar range only adopts the new container size after Qt
        has processed the layout request."""
        pi = self._pending_scroll_page
        if pi is None:
            return
        self._pending_scroll_page = None
        if pi >= self._total_pages:
            return
        target = self._page_scroll_pos(pi)
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(target)
        QTimer.singleShot(0, lambda t=target: sb.setValue(t))

    def _deferred_relayout(self):
        """Re-run the layout after the scrollbar range has caught up with the new
        container size, then apply any scroll target that was waiting on it."""
        if not self.doc:
            return
        self._layout_labels()
        self._apply_pending_scroll()
        self._refresh_visible_pixmaps()

    def _refresh_visible_pixmaps(self):
        """Render pixmaps for the labels that are on screen (grid view renders
        lazily, so a scroll can reveal labels that have no pixmap yet)."""
        if self._view_mode != ViewMode.GRID or not self.doc:
            return
        sb = self.scroll_area.verticalScrollBar()
        top, bottom = sb.value(), sb.value() + self._viewport_height()
        g = self._grid_geometry(self._viewport_size()[0])
        row_px = g["cell_h"] + g["gutter_v"]
        first_row = max(0, (top - g["mg"]) // row_px - 1)
        last_row = min(g["rows"] - 1, (bottom - g["mg"]) // row_px + 1)
        for pi in range(first_row * g["cols"],
                        min(self._total_pages, (last_row + 1) * g["cols"])):
            label = self._labels[pi]
            dw, dh, _, _ = g["dims"][pi]
            pix = self._get_or_render(pi, dw, dh, force_fit=True)
            if pix and label.pixmap() is None:
                label.setPixmap(pix)

    def _grid_page_at_pos(self, pos):
        """Find which page cell contains the given point, or -1 if none.
        O(1) via the cached grid geometry instead of a scan over all pages."""
        if self._total_pages <= 0:
            return -1
        g = self._grid_geometry(self._viewport_size()[0])
        col = (pos.x() - g["left"]) // (g["cell_w"] + g["gutter_h"])
        row = (pos.y() - g["mg"]) // (g["cell_h"] + g["gutter_v"])
        if col < 0 or col >= g["cols"] or row < 0:
            return -1
        pi = int(row) * g["cols"] + int(col)
        if pi < 0 or pi >= self._total_pages:
            return -1
        cx, cy, cw, ch = self._cell_rect(pi)
        if cx <= pos.x() <= cx + cw and cy <= pos.y() <= cy + ch:
            return pi
        return -1

    def _grid_mouse_press(self, e):
        """Container-level mouse press: selection or start drag-sort."""
        if not self._edit_mode:
            return
        pos = e.position().toPoint()
        self._rubber_origin = pos
        self._rubber_rect = None
        pi = self._grid_page_at_pos(pos)
        self._drag_start_page = pi

        # Sort mode: if Sort is checked and page is selected, prepare to drag
        if self.btn_edit_sort.isChecked() and pi >= 0 and pi in self._selected_pages:
            self._drag_active = True
            self._drag_source_page = pi
            return

        # Normal selection
        mods = QApplication.keyboardModifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        if pi >= 0:
            if ctrl:
                if pi in self._selected_pages:
                    self._selected_pages.discard(pi)
                else:
                    self._selected_pages.add(pi)
            elif shift and self._selected_pages:
                start = min(self._selected_pages)
                end = pi
                if end < start:
                    start, end = end, start
                self._selected_pages = set(range(start, end + 1))
            else:
                self._selected_pages = {pi}
            self._drag_active = False
            self._refresh_selection_view()

    def _grid_mouse_move(self, e):
        """Container-level mouse move: rectangle select or drag-sort tracking."""
        if not self._edit_mode or not self._rubber_origin:
            return
        pos = e.position().toPoint()

        if self._drag_active and self._drag_start_page is not None:
            target = self._grid_page_at_pos(pos)
            new_target = target if target >= 0 else None
            if new_target != self._drag_target:
                for pi in (self._drag_target, new_target):
                    if pi is not None and 0 <= pi < len(self._labels):
                        self._labels[pi]._style_state = None
                self._drag_target = new_target
                self._refresh_selection_view()
            return

        # Rectangle select (non-drag mode)
        if self._drag_active:
            return
        if (pos - self._rubber_origin).manhattanLength() < 8:
            return
        x1, y1 = self._rubber_origin.x(), self._rubber_origin.y()
        x2, y2 = pos.x(), pos.y()
        rx, ry = min(x1, x2), min(y1, y2)
        rw, rh = abs(x2 - x1), abs(y2 - y1)
        if rw < 4 and rh < 4:
            return
        self._rubber_rect = (rx, ry, rw, rh)
        self._update_rubber_band()
        self._select_pages_in_rect(self._rubber_band_cells())

    def _cell_index_at(self, x: int, y: int):
        """(row, col) of the grid cell that owns a point, with tiny overshoot
        clamped into the nearest cell so dragging past an edge still selects."""
        g = self._grid_geometry(self._viewport_size()[0])
        col_px, row_px = g["cell_w"] + g["gutter_h"], g["cell_h"] + g["gutter_v"]
        col = (x - g["left"]) // col_px
        row = (y - g["mg"]) // row_px
        col = max(0, min(g["cols"] - 1, int(col)))
        row = max(0, min(g["rows"] - 1, int(row)))
        return row, col

    def _rubber_band_cells(self) -> set:
        """Pages covered by the rubber band, as the full rectangle of grid cells
        between the drag anchor and the current pointer (Finder-style marquee)."""
        if not self._rubber_rect or not self._rubber_origin:
            return set()
        rx, ry, rw, rh = self._rubber_rect
        r0, c0 = self._cell_index_at(self._rubber_origin.x(), self._rubber_origin.y())
        r1, c1 = self._cell_index_at(rx + rw, ry + rh)
        if r1 < r0:
            r0, r1 = r1, r0
        if c1 < c0:
            c0, c1 = c1, c0
        g = self._grid_geometry(self._viewport_size()[0])
        cols = g["cols"]
        out = set()
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                pi = row * cols + col
                if 0 <= pi < self._total_pages:
                    out.add(pi)
        return out

    def _select_pages_in_rect(self, selected):
        """Apply a new selection set, repainting only what changed."""
        if selected != self._selected_pages:
            self._selected_pages = selected
            self._refresh_selection_view()
        else:
            self._refresh_selection_view(buttons_only=True)

    def _refresh_selection_view(self, buttons_only: bool = False):
        """Repaint selection without rebuilding the whole grid.

        Older builds called _layout_labels() on every mouse-move, which re-rendered
        every thumbnail in the document. Here only the pages whose selected state
        actually changed get a new stylesheet, and the button state is refreshed."""
        previous = getattr(self, "_prev_selected", set())
        changed = previous.symmetric_difference(self._selected_pages)
        self._prev_selected = set(self._selected_pages)
        if not buttons_only:
            for pi in changed:
                if 0 <= pi < len(self._labels):
                    lbl = self._labels[pi]
                    lbl._style_state = None
                    self._apply_page_style(
                        lbl, selected=self._edit_mode and pi in self._selected_pages,
                        grid=True)
        self._update_edit_buttons()

    def _update_rubber_band(self):
        """Thin overlay rectangle so box-select gives live feedback."""
        if not self._rubber_rect:
            if getattr(self, "_rubber_band", None):
                self._rubber_band.hide()
            return
        band = getattr(self, "_rubber_band", None)
        if band is None:
            band = QWidget(self.page_container)
            band.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            band.setStyleSheet(
                "background:rgba(0,122,255,40);"
                f"border:1px solid {_dc('#4da3ff', '#007aff')};")
            self._rubber_band = band
        rx, ry, rw, rh = self._rubber_rect
        band.setGeometry(rx, ry, rw, rh)
        band.show()
        band.raise_()

    def _grid_mouse_release(self, e):
        """End selection or complete drag-sort move."""
        if not self._edit_mode:
            return
        pos = e.position().toPoint()

        if self._drag_active and self._selected_pages and self._page_editor:
            target = self._grid_page_at_pos(pos)
            if target >= 0 and target not in self._selected_pages:
                source_list = sorted(self._selected_pages)
                # Adjust target: if source pages are before target, they shift after deletion
                offset = sum(1 for s in source_list if s < target)
                effective_target = target - offset
                self._page_editor.move_pages(source_list, effective_target)
                # move_pages rebuilds the document through pypdf and binds a new
                # fitz.Document; keeping the old handle made the very next line
                # raise ValueError("document closed") inside a Qt slot, which
                # aborts the process and loses the unsaved edits without a prompt.
                self.doc = self._page_editor.doc
                self._unsaved_edits = True
                self._selected_pages.clear()
                PdfReaderWidget._clear_cache()
                self._rebuild_labels_from_editor()
                self._layout_labels()
                self._update_edit_buttons()
                self._update_nav_ui()

        # Reset drag state
        self._rubber_rect = None
        self._update_rubber_band()
        self._rubber_origin = None
        self._drag_active = False
        self._drag_target = None
        self._drag_start_page = None

    def _on_grid_click(self, pi: int, e):
        """Handle click in Grid edit mode for selection."""
        if not self._edit_mode: return
        mods = QApplication.keyboardModifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        if ctrl:
            if pi in self._selected_pages:
                self._selected_pages.discard(pi)
            else:
                self._selected_pages.add(pi)
        elif shift and self._selected_pages:
            # Range select
            start = min(self._selected_pages)
            end = pi
            if end < start: start, end = end, start
            self._selected_pages = set(range(start, end + 1))
        else:
            # Toggle single
            if pi < 0 or pi >= self._total_pages:
                return
            if pi in self._selected_pages and len(self._selected_pages) == 1:
                self._selected_pages.clear()
            else:
                self._selected_pages = {pi}
        self._refresh_selection_view()

    def _update_edit_buttons(self):
        has_sel = len(self._selected_pages) > 0
        self.btn_edit_rot.setEnabled(has_sel)
        self.btn_edit_del.setEnabled(has_sel)
        self.btn_edit_extract.setEnabled(has_sel)
        self.btn_edit_export.setEnabled(has_sel)
        self.btn_edit_print.setEnabled(has_sel)
        self.btn_edit_sort.setEnabled(has_sel)
        if self._page_editor:
            self.btn_edit_undo.setEnabled(self._page_editor.can_undo())
            self.btn_edit_redo.setEnabled(self._page_editor.can_redo())

    # ── Edit mode toggles ──

    def _edit_select_mode(self):
        """Exit drag-sort mode: Sort→unchecked, drag off. Use this to select pages normally."""
        self._drag_sort_mode = False
        self.btn_edit_sort.setChecked(False)
        self._drag_active = False; self._drag_target = None

    def _edit_sort_mode(self):
        """Toggle drag-sort mode. When checked, click+drag selected pages to reorder them.
        When unchecked, clicking selects pages without dragging."""
        if self.btn_edit_sort.isChecked():
            if not self._selected_pages:
                self.btn_edit_sort.setChecked(False)
                QMessageBox.information(self, tr("reader_sort_hint_title"),
                                        tr("reader_sort_hint_body"))
                return
            self._drag_sort_mode = True
            self._drag_active = False; self._drag_target = None
        else:
            self._drag_sort_mode = False
            self._drag_active = False; self._drag_target = None

    # ── Edit operations ──

    def _edit_print(self):
        if not self._selected_pages or not self._page_editor: return
        try:
            import tempfile
            tmp = Path(tempfile.gettempdir()) / "pdfeverything_print.pdf"
            self._page_editor.extract_pages(list(self._selected_pages), tmp)
            import subprocess, sys
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(tmp)])
            elif sys.platform == "win32":
                os.startfile(str(tmp))  # noqa: S606 — Windows shell open
            else:
                subprocess.Popen(["xdg-open", str(tmp)])
        except Exception as ex:
            QMessageBox.warning(self, tr("reader_print_title"),
                                tr("reader_print_failed", error=ex))

    def _edit_rotate(self):
        if not self._page_editor or not self._selected_pages: return
        self._page_editor.rotate_pages(list(self._selected_pages), 90)
        self.doc = self._page_editor.doc
        self._unsaved_edits = True
        # Invalidate every cached rendering of the rotated pages — both the grid
        # thumbnails and the 100% base. Rotation changes the page's visual output,
        # so all entries for these page indices are stale. One sweep over the cache
        # instead of one sweep per selected page.
        PdfReaderWidget._invalidate_pages(self._selected_pages)
        # Page rects changed (rotation swaps width/height for 90°/270°), so both
        # the grid geometry and the cached page rects are stale.
        self._grid_geom = None
        self._page_rects = None
        if self._view_mode == ViewMode.GRID:
            self._grid_geometry(self._viewport_size()[0])
        for pi in self._selected_pages:
            if 0 <= pi < len(self._labels):
                self._labels[pi].setPixmap(QPixmap())
                self._labels[pi]._style_state = None
        self._layout_labels()
        self._refresh_visible_pixmaps()
        self._update_edit_buttons()

    def _edit_delete(self):
        if not self._page_editor or not self._selected_pages: return
        reply = QMessageBox.question(self, tr("reader_delete_title"),
            tr("reader_delete_body", count=len(self._selected_pages)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        self._page_editor.delete_pages(list(self._selected_pages))
        self.doc = self._page_editor.doc  # undo/redo swap the handle — re-read it
        self._unsaved_edits = True
        self._selected_pages.clear()
        PdfReaderWidget._clear_cache()  # ALL cache is stale after page deletion
        self._rebuild_labels_from_editor()
        self._layout_labels(); self._update_edit_buttons()
        self._update_nav_ui()

    def _edit_extract(self):
        if not self._page_editor or not self._selected_pages: return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("reader_extract_title"), "extracted.pdf", tr("file_filter_pdf"))
        if not path:
            self._layout_labels()
            return
        self._page_editor.extract_pages(list(self._selected_pages), Path(path))
        self._layout_labels()
        QMessageBox.information(self, tr("reader_done_title"),
                                tr("reader_extracted_body", path=path))

    def _edit_export_menu(self):
        """Show a popup menu for export file type selection."""
        if not self._selected_pages: return
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        act_pdf = menu.addAction(tr("reader_export_pdf"))
        act_jpg = menu.addAction(tr("reader_export_jpg"))
        act_word = menu.addAction(tr("reader_export_word"))
        act_ppt = menu.addAction(tr("reader_export_ppt"))
        act = menu.exec(self.btn_edit_export.mapToGlobal(
            self.btn_edit_export.rect().bottomLeft()))
        if act == act_pdf:
            self._edit_export("pdf")
        elif act == act_jpg:
            self._edit_export("jpg")
        elif act == act_word:
            self._edit_export("word")
        elif act == act_ppt:
            self._edit_export("ppt")

    def _edit_export(self, fmt: str = "pdf"):
        if not self._page_editor or not self._selected_pages: return
        filters = {"pdf": tr("file_filter_pdf"), "jpg": "JPG (*.jpg)",
                   "word": tr("file_filter_word"), "ppt": tr("file_filter_ppt")}
        default_ext = {"pdf": ".pdf", "jpg": ".jpg", "word": ".docx", "ppt": ".pptx"}
        filter_str = filters.get(fmt, filters["pdf"])
        ext = default_ext.get(fmt, ".pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("reader_export_title"), "exported" + ext, filter_str)
        if not path: return
        if fmt == "pdf":
            self._page_editor.extract_pages(list(self._selected_pages), Path(path))
        elif fmt == "jpg":
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
                tmp = Path(fh.name)
            try:
                self._page_editor.extract_pages(list(self._selected_pages), tmp)
                written = PdfReaderWidget._export_pages_to_images(tmp, Path(path))
                if len(written) > 1:
                    path = str(Path(path).parent / f"{Path(path).stem}_p*.jpg")
            finally:
                tmp.unlink(missing_ok=True)
        elif fmt == "word":
            import tempfile
            tmp = Path(tempfile.gettempdir()) / "pdfeverything_export_tmp.pdf"
            self._page_editor.extract_pages(list(self._selected_pages), tmp)
            from core.pdf_ops import PdfOperator
            PdfOperator.to_word(tmp, Path(path))
            tmp.unlink(missing_ok=True)
        elif fmt == "ppt":
            import tempfile
            tmp = Path(tempfile.gettempdir()) / "pdfeverything_export_tmp.pdf"
            self._page_editor.extract_pages(list(self._selected_pages), tmp)
            from core.pdf_ops import PdfOperator
            PdfOperator.to_ppt(tmp, Path(path))
            tmp.unlink(missing_ok=True)
        QMessageBox.information(self, tr("reader_done_title"),
                                tr("reader_exported_body", path=path))

    @staticmethod
    def _export_pages_to_images(pdf_path: Path, output_path: Path) -> list:
        """Export PDF pages as JPGs, honouring the path the user picked.

        Selecting "photo.jpg" used to write "photo_p0001.jpg" and nothing at the
        chosen name, while the success dialog still reported the path the user
        typed — a file that did not exist. Now one page is written exactly where
        the user asked, and multiple pages go to a folder beside it. Returns the
        paths actually written."""
        import fitz
        doc = fitz.open(pdf_path)
        total = len(doc)
        written = []
        try:
            if total <= 1:
                for i in range(total):
                    pix = doc[i].get_pixmap(dpi=200)
                    pix.save(str(output_path))
                    written.append(output_path)
            else:
                stem, parent = output_path.stem, output_path.parent
                for i in range(total):
                    img_path = parent / f"{stem}_p{i + 1:04d}.jpg"
                    pix = doc[i].get_pixmap(dpi=200)
                    pix.save(str(img_path))
                    written.append(img_path)
        finally:
            doc.close()
        return written

    def _edit_undo(self):
        if self._page_editor and self._page_editor.can_undo():
            self._page_editor.undo()
            # Undo restores snapshot → new fitz.Document in editor._doc
            self.doc = self._page_editor.doc
            self._unsaved_edits = self._page_editor.can_undo()  # still unsaved if more undos possible
            self._selected_pages.clear()
            PdfReaderWidget._clear_cache()
            self._rebuild_labels_from_editor()
            self._layout_labels(); self._update_edit_buttons()
            self._update_nav_ui()

    def _edit_redo(self):
        if self._page_editor and self._page_editor.can_redo():
            self._page_editor.redo()
            self.doc = self._page_editor.doc  # sync after snapshot restore
            self._selected_pages.clear()
            PdfReaderWidget._clear_cache()
            self._rebuild_labels_from_editor()
            self._layout_labels(); self._update_edit_buttons()
            self._update_nav_ui()

    def _rebuild_labels_from_editor(self):
        """Sync labels with shared doc state after page deletion/reorder."""
        if not self.doc: return
        new_count = len(self.doc)
        self._hide_page_numbers()
        self._destroy_labels()
        self._total_pages = new_count
        self._build_labels()
        self._current_page = min(self._current_page, new_count - 1) if new_count else 0
        # Stay lazy: only the pages on screen get a pixmap. Rendering every page
        # here defeated the whole windowed renderer — one delete on a 100-page
        # document allocated 189MB on the GUI thread, and a 1000-page one would
        # have needed ~1.9GB. _layout_labels + _refresh_visible_pixmaps already
        # fill exactly the visible rows.
        self._grid_geom = None
        self._page_rects = None      # rotation/pages changed with the edit
        self._selected_pages = {p for p in self._selected_pages if p < new_count}
        self._queue_lazy_pre_render()

    def _edit_select_all(self):
        if not self._edit_mode: return
        self._selected_pages = set(range(self._total_pages))
        self._layout_labels(); self._update_edit_buttons()

    def _edit_clear_selection(self):
        self._selected_pages.clear()
        self._layout_labels(); self._update_edit_buttons()

    # ═══════════ Pre-render ═══════════

    # pre-render removed — now lazy-renders visible range on scroll stop

    # ═══════════ Scroll tracking (bisect, O(log n)) ═══════════

    def _scroll_to_page_top(self, defer: bool = False):
        """Bring the current page into view (works in both view modes).

        defer=True records the target and lets the next layout pass apply it,
        which is required when the container size is about to change."""
        if not self.doc or not self._total_pages:
            return
        self._pending_scroll_page = self._current_page
        if not defer:
            self._apply_pending_scroll()

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
                self._queue_lazy_pre_render()
            self._throttle_last = rough
        except Exception: pass

    def _do_debounce_calibration(self):
        """Scroll has stopped: recalibrate the current page and refresh pixmaps.

        Scroll mode bisects the cached page offsets (O(log n)). Grid mode derives
        the row from the scroll offset, then materialises the thumbnails that the
        new position revealed."""
        try:
            if not self.doc:
                return
            sb = self.scroll_area.verticalScrollBar()
            if not sb:
                return
            if self._view_mode == ViewMode.GRID:
                idx = self._page_at_scroll_pos(sb.value())
                if idx != self._current_page:
                    self._current_page = idx
                    self._update_nav_ui()
                self._refresh_visible_pixmaps()
                self._queue_lazy_pre_render()
                return
            if not self._page_heights:
                return
            mid = max(0, sb.value() + sb.pageStep() // 2)
            idx = bisect_right(self._page_heights, mid) - 1
            if idx < 0: idx = 0
            elif idx >= len(self._page_heights): idx = len(self._page_heights) - 1
            if idx != self._current_page:
                self._current_page = idx
                self._update_nav_ui()
            self._schedule_render_visible(50)  # 50ms for inertia to fully stop
        except Exception:
            pass

    def _page_at_scroll_pos(self, y: int) -> int:
        """Page index visible at container offset y (mode aware)."""
        if self._view_mode == ViewMode.GRID:
            g = self._grid_geometry(self._viewport_size()[0])
            row = max(0, (y - g["mg"])) // (g["cell_h"] + g["gutter_v"])
            return int(min(self._total_pages - 1, row * g["cols"]))
        if not self._page_heights:
            return self._current_page
        idx = bisect_right(self._page_heights, y + self._viewport_height() // 2) - 1
        return max(0, min(self._total_pages - 1, idx))

    # ═══════════ Render ═══════════

    def _zoom_key(self, vw, vh):
        if self._zoom_mode == "fit_width": return "fw"
        if self._zoom_mode == "fit_height": return "fh"
        return f"z:{self._zoom_mode:.3f}"

    @staticmethod
    def _render_zoom(doc, pi, zk, vw, vh, force_fit=False) -> float:
        """Zoom factor the renderer uses for this page/cache key."""
        page = doc[pi]
        pw, ph = page.rect.width, page.rect.height
        if zk == "fw":
            return vw / pw if pw else 1.0
        if zk == "fh":
            return vh / ph if ph else 1.0
        if isinstance(zk, str) and zk.startswith("z:"):
            return float(zk[2:])
        if force_fit:
            return min(vw / pw, vh / ph) if pw and ph else 1.0
        return vw / pw if pw else 1.0

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
        # QImage does not take ownership of (or copy) the buffer it is handed, so
        # it pointed straight at the MuPDF pixmap's memory. fromImage() copies
        # synchronously today, but that is an implementation detail of Qt — an
        # explicit copy keeps the renderer correct by construction.
        samples = bytes(pix.samples)
        qimg = QImage(samples, pix.width, pix.height,
                      pix.stride, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        if dpr != 1.0:
            pixmap.setDevicePixelRatio(dpr)
        return pixmap

    def _paint_search_highlights(self, pixmap: QPixmap, pi: int, zoom: float,
                                dpr: float) -> QPixmap:
        """Draw search hits onto a freshly rendered page pixmap.

        The pixmap is in physical pixels (zoom × dpr), while hit rectangles are in
        PDF points, so each rect is scaled by zoom × dpr before painting."""
        rects = self._highlight_rects.get(pi)
        if not rects:
            return pixmap
        painter = QPainter(pixmap)
        try:
            scale = zoom * dpr
            current = (self._search_index >= 0
                       and self._search_index < len(self._search_hits)
                       and self._search_hits[self._search_index].page == pi)
            for i, rect in enumerate(rects):
                x0, y0, x1, y1 = [v * scale for v in rect]
                is_current = current and self._is_current_hit(pi, rect)
                painter.fillRect(
                    int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0)),
                    QColor(255, 165, 0, 130) if is_current else QColor(255, 235, 59, 110))
            if current:
                painter.setPen(QPen(QColor(255, 120, 0), 2))
                for rect in rects:
                    x0, y0, x1, y1 = [v * scale for v in rect]
                    if self._is_current_hit(pi, rect):
                        painter.drawRect(int(x0) - 1, int(y0) - 1,
                                         max(2, int(x1 - x0) + 2),
                                         max(2, int(y1 - y0) + 2))
        finally:
            painter.end()
        return pixmap

    def _is_current_hit(self, pi: int, rect) -> bool:
        if not (0 <= self._search_index < len(self._search_hits)):
            return False
        hit = self._search_hits[self._search_index]
        return hit.page == pi and tuple(hit.rect) == tuple(rect)

    def _viewport_size(self):
        vp = self.scroll_area.viewport()
        w, h = max(800, vp.width() - 4), max(600, vp.height() - 4)
        return w, h

    def _viewport_height(self) -> int:
        """Raw viewport height (no minimum clamp) — used for visibility maths."""
        try:
            return max(1, self.scroll_area.viewport().height())
        except Exception:
            return 600

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
    def _cache_budget_bytes(cls) -> int:
        """Memory ceiling for the pixmap cache, adapted to the actual machine.

        400MB is the ceiling on a well-endowed desktop, but on a small laptop
        that is a large slice of RAM for a cache. Take a quarter of physical
        memory, clamped to [128MB, 400MB]."""
        if cls._cache_budget is None:
            cap = MAX_CACHE_MB * 1024 * 1024
            try:
                page = os.sysconf("SC_PAGE_SIZE")
                avail = os.sysconf("SC_PHYS_PAGES") * page
                cap = min(cap, max(128 * 1024 * 1024, avail // 4))
            except (ValueError, OSError, AttributeError):
                pass
            cls._cache_budget = cap
        return cls._cache_budget

    @staticmethod
    def _pixmap_bytes(pix: QPixmap) -> int:
        """RAM held by one pixmap, in bytes.

        ``QPixmap.width()``/``height()`` already report *device* pixels in Qt6
        (a 100-logical-px pixmap at dpr 2 reports 200), so the devicePixelRatio
        must NOT be multiplied in again — doing so over-counted by 4× on every
        Retina screen and made the 400MB budget behave like 100MB, which caused
        constant eviction and re-rendering."""
        return pix.width() * pix.height() * 4

    @classmethod
    def _cache_put(cls, key, pix: QPixmap):
        """LRU insert with a hard memory ceiling.

        The 100% base ("z:1.000") and fit-mode ("fh"/"fw") entries are the ones
        Pass 1 scaling reads from, so they are evicted *last* — but they are no
        longer immortal. Treating them as immortal used to stop eviction dead on
        the first base entry it met, letting the cache grow past its budget
        without limit (measured: 638MB against a 400MB cap). Now the eviction
        runs two tiers: everything unprotected first, and only if that is not
        enough, the protected entries outside the live page window."""
        if key in cls._cache:
            # Replacing an entry must account for the size it already occupied,
            # otherwise the tracked total drifts below reality and eviction
            # stops firing early.
            cls._cache_memory_bytes -= cls._pixmap_bytes(cls._cache[key])
            cls._cache.move_to_end(key)
            cls._cache[key] = pix
            cls._cache_memory_bytes += cls._pixmap_bytes(pix)
            return

        cls._cache[key] = pix
        cls._cache_memory_bytes += cls._pixmap_bytes(pix)

        budget = cls._cache_budget_bytes()
        if cls._cache_memory_bytes <= budget:
            return

        protected = cls._protected_pages
        is_base = lambda k: k[1] in ("fh", "fw", "z:1.000")  # noqa: E731
        # Tier 1 — evict the disposable zoomed/thumbnail entries only. This keeps
        # every 100% base (the source Pass 1 scales from) plus the live pages.
        for k in list(cls._cache.keys()):
            if cls._cache_memory_bytes <= budget:
                break
            if k == key or len(cls._cache) <= 1 or is_base(k):
                continue
            cls._cache_pop(k)
        # Tier 2 — still over budget: the base pixmaps themselves are the bulk,
        # so give up the off-screen ones. The page the reader is looking at is
        # never dropped, so a zoom still has a base to scale from.
        if cls._cache_memory_bytes > budget:
            for k in list(cls._cache.keys()):
                if cls._cache_memory_bytes <= budget:
                    break
                if k == key or len(cls._cache) <= 1 or k[0] in protected:
                    continue
                cls._cache_pop(k)

    @classmethod
    def _cache_get(cls, key):
        if key in cls._cache:
            cls._cache.move_to_end(key)
            return cls._cache[key]
        return None

    @classmethod
    def _cache_pop(cls, key):
        """Remove a specific key from cache (e.g. stale thumbnail)."""
        if key in cls._cache:
            pix = cls._cache.pop(key)
            r = pix.devicePixelRatio()
            mem = pix.width() * pix.height() * 4
            if r != 1.0:
                mem = int(mem * r * r)
            cls._cache_memory_bytes -= mem

    @classmethod
    def _invalidate_zoom_keys(cls, zoom_keys) -> None:
        """Drop every cache entry whose zoom key is in `zoom_keys`.

        Used for viewport-dependent renders ("fh"/"fw"), which are invalidated by
        a resize even though the page index is unchanged."""
        wanted = set(zoom_keys)
        if not wanted or not cls._cache:
            return
        for key in [k for k in cls._cache if k[1] in wanted]:
            cls._cache_pop(key)

    @classmethod
    def _invalidate_pages(cls, ordinals):
        """Drop every cache entry belonging to the given page indices.
        One pass over the cache no matter how many pages are affected."""
        wanted = set(ordinals)
        if not wanted or not cls._cache:
            return
        for key in [k for k in cls._cache if k[0] in wanted]:
            cls._cache_pop(key)

    @classmethod
    def _clear_cache(cls):
        cls._cache.clear()
        cls._cache_memory_bytes = 0

    def _get_or_render(self, pi, vw, vh=99999, force_fit=False, render_hq=False):
        """Get from cache or render a page. force_fit thumbnails use a
        separate cache namespace to avoid colliding with 100% base renders."""
        if force_fit:
            key = (pi, f"thumb_{vw}_{vh}")  # Grid-specific key: avoids base cache collision
        else:
            key = (pi, self._zoom_key(vw, vh))
        cached = PdfReaderWidget._cache_get(key)
        if cached is not None and not render_hq:
            return cached
        dpr = self._device_pixel_ratio()
        pix = PdfReaderWidget._render_page(self.doc, pi, key[1], vw, vh, force_fit, dpr=dpr)
        if self._highlight_rects.get(pi):
            pix = self._paint_search_highlights(
                pix, pi, PdfReaderWidget._render_zoom(self.doc, pi, key[1], vw, vh,
                                                      force_fit), dpr)
        PdfReaderWidget._cache_put(key, pix)
        return pix

    # ═══════════ Navigation ═══════════

    def go_to_page(self, n):
        if not self.doc: return
        n = max(1, min(n, self._total_pages))
        self._current_page = n - 1; self._scroll_to_page_top(); self._update_nav_ui()
        self._schedule_render_visible(0)  # instant high-quality render

    def next_page(self):
        if self.doc and self._current_page < self._total_pages - 1:
            self._current_page += 1; self._scroll_to_page_top(); self._update_nav_ui()
            self._schedule_render_visible(0)  # instant high-quality render

    def prev_page(self):
        if self.doc and self._current_page > 0:
            self._current_page -= 1; self._scroll_to_page_top(); self._update_nav_ui()
            self._schedule_render_visible(0)  # instant high-quality render

    def first_page(self): self.go_to_page(1)
    def last_page(self): self.go_to_page(self._total_pages)

    # ═══════════ Slots ═══════════

    def _on_resize(self):
        """Viewport changed (window resize): re-derive fit ratios, re-lay out and
        re-render. Without the explicit re-layout the page labels keep their old
        size and stop being centred in the new viewport."""
        if not self.doc or not self._labels:
            return
        page = self.doc[0]; pw, ph = page.rect.width, page.rect.height
        vw, vh = self._viewport_size()
        self._fw_ratio = vw / pw if pw > 0 else 1.0
        self._fh_ratio = vh / ph if ph > 0 else 1.0
        self._default_zoom_pct = max(50, min(300, int(self._fh_ratio * 100)))
        # A fit-mode pixmap is only valid for the viewport it was rendered in, and
        # its cache key ("fh"/"fw") does not encode the size. Without this purge
        # the label kept the pre-resize pixmap inside the new, larger frame
        # (measured: 424x600 inside 809x1145) and never filled the window again.
        PdfReaderWidget._invalidate_zoom_keys(("fh", "fw"))
        # While a fit mode is active the page size itself tracks the viewport,
        # so the layout must be recomputed (not just re-rendered).
        self._layout_labels()
        cur_pct = self._current_zoom_pct()
        self.zoom_edit.setText(str(cur_pct))
        self._pending_zoom_pct = cur_pct
        self._scroll_to_page_top()
        QTimer.singleShot(40, self._sharp_render)
        self._schedule_render_visible(0)

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
        # welcome card colors following theme
        cc = _dc("#555", "#666")
        bc = _dc("#666", "#555"); bbg = _dc("#2a2a2a", "#ffffff"); bb = _dc("#444", "#bbb")
        bhc = _dc("#999", "#333"); bhb = _dc("#555", "#aaa")
        self.page_container.setFixedSize(vp.width(), vp.height())
        c = QWidget(self.page_container)
        c.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(c); cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setSpacing(12)
        t = QLabel(drop_text); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(f"QLabel{{color:{cc};font-size:16px;background:transparent;}}")
        cl.addWidget(t)
        b = QPushButton(load_btn_text); b.setFixedWidth(120)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{color:{bc};background:{bbg};border:1px solid {bb};"
            f"border-radius:4px;padding:5px 16px;font-size:12px}}"
            f"QPushButton:hover{{color:{bhc};background:{_dc('#333','#e8e8e8')};border-color:{bhb}}}")
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
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier) or \
               bool(mods & Qt.KeyboardModifier.MetaModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        # Find bar
        if ctrl and e.key() == Qt.Key.Key_F:
            self.show_search_bar(True)
            return
        if e.key() == Qt.Key.Key_Escape and self.search_bar.isVisible():
            self.show_search_bar(False)
            return
        if ctrl and e.key() == Qt.Key.Key_G:
            self.find_prev() if shift else self.find_next()
            return
        if e.key() in (Qt.Key.Key_F3,):
            self.find_prev() if shift else self.find_next()
            return
        # View shortcuts
        if ctrl and e.key() == Qt.Key.Key_B:
            self.toggle_sidebar()
            return
        if ctrl and e.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._adjust_zoom(+10)
            return
        if ctrl and e.key() == Qt.Key.Key_Minus:
            self._adjust_zoom(-10)
            return
        if ctrl and e.key() == Qt.Key.Key_0:
            self._on_fit_height()
            return
        if ctrl and e.key() == Qt.Key.Key_1:
            self._on_fit_width()
            return

        # Edit mode shortcuts
        if self._edit_mode and self._view_mode == ViewMode.GRID:
            if e.key() == Qt.Key.Key_A and ctrl:
                self._edit_select_all(); return
            if e.key() == Qt.Key.Key_Escape:
                self._edit_clear_selection(); return
            if e.key() == Qt.Key.Key_Z and ctrl and bool(mods & Qt.KeyboardModifier.ShiftModifier):
                self._edit_redo(); return
            if e.key() == Qt.Key.Key_Z and ctrl:
                self._edit_undo(); return

        # Normal navigation. PageUp/PageDown/space stay with the scroll area so
        # they keep their native smooth-scrolling behaviour.
        if e.key() == Qt.Key.Key_Left:
            self.prev_page()
        elif e.key() == Qt.Key.Key_Right:
            self.next_page()
        elif e.key() == Qt.Key.Key_Home:
            self.first_page()
        elif e.key() == Qt.Key.Key_End:
            self.last_page()
        else:
            super().keyPressEvent(e)

    # ═══════════ Touchpad pinch-to-zoom + Ctrl+wheel ═══════════
    #
    # Pinch detection: macOS sends QWheelEvent with .phase() during native
    # pinch gestures. phase>=1 and pixelDelta.y==0 means pinch (not scroll).
    # Overscroll rubber-band has BOTH non-zero — we filter those out.
    # The accumulator _pinch_acc smoothes the signal; each 60 angle-units
    # produces 2.5% zoom change (= 5% per 120, same ratio as before but
    # twice as responsive).
    # Phase 3 (ScrollEnd) triggers the deferred sharp render.

    def mouseDoubleClickEvent(self, e):
        """Toggle between fit-width and fit-height zoom (Preview/Acrobat habit)."""
        if not self.doc or self._edit_mode:
            super().mouseDoubleClickEvent(e)
            return
        if self._zoom_mode == "fit_width":
            self._on_fit_height()
        else:
            self._on_fit_width()

    def wheelEvent(self, e):
        if not self.doc or self._view_mode != ViewMode.SCROLL:
            super().wheelEvent(e); return
        try:
            ad = e.angleDelta().y() if e.angleDelta() else 0
            pd = e.pixelDelta().y() if e.pixelDelta() else 0
            pinch = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            # macOS native pinch: phase>=1 with no pixelDelta
            # (only angleDelta). Overscroll rubber-banding has BOTH non-zero.
            if not pinch:
                try:
                    ph = e.phase()
                    pinch = (int(ph) >= 1 and pd == 0)
                except (AttributeError, TypeError):
                    pass
            # Windows / fallback: extreme angle/pixel ratio = pinch
            if not pinch and pd != 0 and ad != 0:
                if abs(ad) > abs(pd) * 5:
                    pinch = True
            if pinch:
                self._pinch_acc += ad
                threshold = 60  # was 120; 2× more responsive
                if abs(self._pinch_acc) >= threshold:
                    ticks = int(abs(self._pinch_acc) // threshold)
                    ticks = ticks if self._pinch_acc > 0 else -ticks
                    self._pinch_acc %= threshold
                    self._set_zoom_pct(self._current_zoom_pct() + ticks * 5,
                                       skip_deferred=True)
                try:
                    if e.phase() and int(e.phase()) == 3:
                        self._pending_zoom_pct = self._current_zoom_pct()
                        QTimer.singleShot(40, self._sharp_render)
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
    @property
    def has_unsaved_edits(self) -> bool: return self._unsaved_edits
    def current_path(self) -> Optional[Path]: return self._path
    @property
    def opened_from_file_list(self) -> bool:
        return self._btn_open_source == 'file_list'
    @opened_from_file_list.setter
    def opened_from_file_list(self, v: bool):
        self._btn_open_source = 'file_list' if v else 'dialog'
    def retranslate_ui(self):
        """Re-read the editable labels after a language switch."""
        self.btn_edit.setText(self._editing_label if self._edit_mode
                              else self._normal_label)
