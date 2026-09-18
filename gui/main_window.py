"""PDFeverything main window GUI."""

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QSettings, Qt, QThread, QTimer
from PyQt6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.merger import merge_mixed_files
from core.pdf_ops import PdfOperator
from core.utils import (
    check_office_availability,
    cleanup_temp_files,
    filter_by_category,
    format_bytes,
    get_file_category,
)

from .dialogs import (
    CompressDialog,
    DecryptDialog,
    EncryptDialog,
    InfoDialog,
    MetadataDialog,
    PageNumberDialog,
    RotateDialog,
    SplitRangeDialog,
    WatermarkDialog,
)
from .file_list_widget import FileListWidget
from .i18n import tr, set_language, current_language
from .pdf_reader_widget import PdfReaderWidget
from .workers import BaseWorker


VERSION = "1.8.0"


def _dc(dark, light):
    from . import pdf_reader_widget as _rw
    return dark if _rw._DARK else light


class MainWindow(QMainWindow):
    """PDFeverything main window."""

    def __init__(self):
        super().__init__()
        self._worker: Optional[QThread] = None
        self._office_worker: Optional[QThread] = None
        self._settings = QSettings("PDFeverything", "PDFeverything")
        self._init_ui()
        self._restore_geometry()
        self._start_office_probe()

    # ── UI ───────────────────────────────────────────

    def _init_ui(self):
        self.setWindowTitle(tr("window_title"))
        self.setMinimumSize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        self._init_merge_tab()
        self._init_reader_tab()
        main_layout.addWidget(self.tabs)

        self._init_status_bar(main_layout)
        self._create_menu()
        self.setAcceptDrops(True)

        # Apply initial language (default zh from QSettings, or user's previous choice)
        self._retranslate_ui()

    def _create_menu(self):
        mb = self.menuBar()

        self.menu_file = mb.addMenu(tr("menu_file"))
        self.act_add = self.menu_file.addAction(
            tr("menu_add_files"), "Ctrl+O", self._on_add_files_dialog)
        self.act_clear = self.menu_file.addAction(
            tr("menu_clear_list"), "Ctrl+Shift+N", self.file_list.clear)
        self.menu_file.addSeparator()
        self.act_open_reader = self.menu_file.addAction(
            tr("reader_open_pdf"), "Ctrl+P", self._open_pdf_in_reader)
        self.menu_file.addSeparator()
        self.act_quit = self.menu_file.addAction(
            tr("menu_quit"), "Ctrl+Q", self.close)

        self.menu_op = mb.addMenu(tr("menu_operations"))
        self.act_merge = self.menu_op.addAction(
            tr("menu_merge"), "Ctrl+M", self._on_merge_clicked)
        self.act_merge.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_split = self.menu_op.addAction(tr("btn_split"), self._on_split_clicked)
        self.act_compress = self.menu_op.addAction(tr("btn_compress"), self._on_compress_clicked)
        self.act_watermark = self.menu_op.addAction(tr("btn_watermark"), self._on_watermark_clicked)
        self.act_encrypt = self.menu_op.addAction(tr("btn_encrypt"), self._on_encrypt_clicked)
        self.act_decrypt = self.menu_op.addAction(tr("btn_decrypt"), self._on_decrypt_clicked)
        self.act_rotate = self.menu_op.addAction(tr("btn_rotate"), self._on_rotate_clicked)

        # Convert: the format tools moved out of the right-hand panel so the
        # panel keeps only what a file list actually needs (see design rule:
        # fewer buttons, less visual noise).
        self.menu_convert = mb.addMenu(tr("menu_convert"))
        self.act_extract_text = self.menu_convert.addAction(
            tr("tool_extract_text"), self._on_extract_text)
        self.act_extract_images = self.menu_convert.addAction(
            tr("tool_extract_images"), self._on_extract_images)
        self.act_pdf_to_images = self.menu_convert.addAction(
            tr("tool_pdf_to_images"), self._on_pdf_to_images)
        self.act_images_to_pdf = self.menu_convert.addAction(
            tr("tool_images_to_pdf"), self._on_single_images_to_pdf)
        self.menu_convert.addSeparator()
        self.act_to_word = self.menu_convert.addAction(
            tr("tool_to_word"), self._on_to_word)
        self.act_to_ppt = self.menu_convert.addAction(
            tr("tool_to_ppt"), self._on_to_ppt)
        self.act_to_excel = self.menu_convert.addAction(
            tr("tool_to_excel"), self._on_to_excel)

        # Compose: stamping, metadata, imposition, page insertion
        self.menu_compose = mb.addMenu(tr("menu_compose"))
        self.act_page_numbers = self.menu_compose.addAction(
            tr("pn_btn"), self._on_page_numbers_clicked)
        self.act_metadata = self.menu_compose.addAction(
            tr("meta_btn"), self._on_metadata_clicked)
        self.menu_compose.addSeparator()
        self.act_nup = self.menu_compose.addAction(tr("nup_btn"), self._on_nup_clicked)
        self.act_insert = self.menu_compose.addAction(
            tr("insert_btn"), self._on_insert_pages_clicked)

        # Settings → Language
        self.menu_settings = mb.addMenu(tr("menu_settings"))
        self.menu_lang = self.menu_settings.addMenu(tr("menu_language"))
        self.act_lang_zh = self.menu_lang.addAction(
            tr("menu_lang_zh"), lambda: self._switch_language("zh"))
        self.act_lang_en = self.menu_lang.addAction(
            tr("menu_lang_en"), lambda: self._switch_language("en"))
        self.act_lang_zh.setCheckable(True)
        self.act_lang_en.setCheckable(True)
        self._update_lang_check()

        self.menu_help = mb.addMenu(tr("menu_help"))
        self.act_about = self.menu_help.addAction(tr("menu_about"), self._on_about)

    def _switch_language(self, lang: str):
        set_language(lang)
        self._retranslate_ui()
        self._update_lang_check()

    def _update_lang_check(self):
        lang = current_language()
        self.act_lang_zh.setChecked(lang == "zh")
        self.act_lang_en.setChecked(lang == "en")

    def _retranslate_ui(self):
        """Refresh all UI text after language switch."""
        self.setWindowTitle(tr("window_title"))
        # Menus
        self.menu_file.setTitle(tr("menu_file"))
        self.act_add.setText(tr("menu_add_files"))
        self.act_clear.setText(tr("menu_clear_list"))
        self.act_open_reader.setText(tr("reader_open_pdf"))
        self.act_quit.setText(tr("menu_quit"))
        self.menu_op.setTitle(tr("menu_operations"))
        self.act_merge.setText(tr("menu_merge"))
        self.act_split.setText(tr("btn_split"))
        self.act_compress.setText(tr("btn_compress"))
        self.act_watermark.setText(tr("btn_watermark"))
        self.act_encrypt.setText(tr("btn_encrypt"))
        self.act_decrypt.setText(tr("btn_decrypt"))
        self.act_rotate.setText(tr("btn_rotate"))
        self.menu_convert.setTitle(tr("menu_convert"))
        self.act_extract_text.setText(tr("tool_extract_text"))
        self.act_extract_images.setText(tr("tool_extract_images"))
        self.act_pdf_to_images.setText(tr("tool_pdf_to_images"))
        self.act_images_to_pdf.setText(tr("tool_images_to_pdf"))
        self.act_to_word.setText(tr("tool_to_word"))
        self.act_to_ppt.setText(tr("tool_to_ppt"))
        self.act_to_excel.setText(tr("tool_to_excel"))
        # The panel buttons mirror these actions, so they are refreshed together.
        self.menu_compose.setTitle(tr("menu_compose"))
        self.act_page_numbers.setText(tr("pn_btn"))
        self.act_metadata.setText(tr("meta_btn"))
        self.act_nup.setText(tr("nup_btn"))
        self.act_insert.setText(tr("insert_btn"))
        self.menu_settings.setTitle(tr("menu_settings"))
        self.menu_lang.setTitle(tr("menu_language"))
        self.act_lang_zh.setText(tr("menu_lang_zh"))
        self.act_lang_en.setText(tr("menu_lang_en"))
        self.menu_help.setTitle(tr("menu_help"))
        self.act_about.setText(tr("menu_about"))
        # Group boxes
        self.merge_group.setTitle(tr("group_merge_ops"))
        self.single_group.setTitle(tr("group_pdf_ops"))
        # Buttons (the merge button text is derived from the file list, so it is
        # refreshed at the end of this method instead of being set directly)
        self.btn_split.setText(tr("btn_split"))
        self.btn_compress.setText(tr("btn_compress"))
        self.btn_watermark.setText(tr("btn_watermark"))
        self.btn_encrypt.setText(tr("btn_encrypt"))
        self.btn_decrypt.setText(tr("btn_decrypt"))
        self.btn_rotate.setText(tr("btn_rotate"))
        self.btn_info.setText(tr("btn_info"))
        self.btn_browse_out.setText(tr("btn_browse"))
        self.btn_cancel.setText(tr("btn_cancel"))
        self.label_output.setText(tr("label_output"))
        # Tab names
        self.tabs.setTabText(0, tr("tab_merge"))
        self.tabs.setTabText(1, tr("tab_reader"))
        # Reader edit button labels
        self.reader._normal_label = tr("reader_edit")
        self.reader._editing_label = tr("reader_editing")
        self.reader.btn_edit.setText(
            self.reader._editing_label if self.reader._edit_mode
            else self.reader._normal_label)
        # Reader toolbar
        self.reader.btn_scroll.setText(tr("reader_scroll"))
        self.reader.btn_scroll.setToolTip(tr("reader_scroll_tip"))
        self.reader.btn_grid.setText(tr("reader_grid"))
        self.reader.btn_grid.setToolTip(tr("reader_grid_tip"))
        self.reader.btn_prev.setToolTip(tr("reader_prev"))
        self.reader.btn_next.setToolTip(tr("reader_next"))
        self.reader.btn_fit_width.setText(tr("reader_fit_width"))
        self.reader.btn_fit_width.setToolTip(tr("reader_fit_width_tip"))
        self.reader.btn_fit_height.setText(tr("reader_fit_height"))
        self.reader.btn_fit_height.setToolTip(tr("reader_fit_height_tip"))
        self.reader.btn_zoom_out.setToolTip(tr("reader_zoom_out"))
        self.reader.btn_zoom_in.setToolTip(tr("reader_zoom_in"))
        self.reader.zoom_edit.setToolTip(tr("reader_zoom_edit"))
        self.reader.btn_close.setToolTip(tr("reader_close"))
        self.reader.btn_sidebar.setToolTip(tr("reader_sidebar_tip"))
        self.reader.btn_search.setToolTip(tr("reader_search_tip"))
        self.reader.btn_tab_outline.setText(tr("reader_tab_outline"))
        self.reader.btn_tab_search.setText(tr("reader_tab_search"))
        self.reader.search_edit.setPlaceholderText(tr("reader_search_placeholder"))
        self.reader.search_check_case.setText(tr("reader_search_case"))
        self.reader.btn_search_prev.setToolTip(tr("reader_search_prev"))
        self.reader.btn_search_next.setToolTip(tr("reader_search_next"))
        self.reader.btn_search_close.setToolTip(tr("reader_search_close"))
        if not self.reader._outline_entries:
            self.reader._update_outline_placeholder()
        # Reader edit toolbar
        self.reader.btn_edit.setToolTip(tr("reader_edit"))
        self.reader.btn_edit_sel.setText(tr("reader_edit_select"))
        self.reader.btn_edit_sel.setToolTip(tr("reader_edit_sel_tip"))
        self.reader.btn_edit_sort.setText(tr("reader_edit_sort"))
        self.reader.btn_edit_sort.setToolTip(tr("reader_edit_sort_tip"))
        self.reader.btn_edit_rot.setText(tr("reader_edit_rotate"))
        self.reader.btn_edit_rot.setToolTip(tr("reader_edit_rot_tip"))
        self.reader.btn_edit_del.setText(tr("reader_edit_delete"))
        self.reader.btn_edit_del.setToolTip(tr("reader_edit_del_tip"))
        self.reader.btn_edit_extract.setText(tr("reader_edit_extract"))
        self.reader.btn_edit_extract.setToolTip(tr("reader_edit_extract_tip"))
        self.reader.btn_edit_export.setText(tr("reader_edit_export"))
        self.reader.btn_edit_export.setToolTip(tr("reader_edit_export_tip"))
        self.reader.btn_edit_print.setText(tr("reader_edit_print"))
        self.reader.btn_edit_print.setToolTip(tr("reader_edit_print_tip"))
        self.reader.btn_edit_saveas.setText(tr("reader_edit_saveas"))
        self.reader.btn_edit_saveas.setToolTip(tr("reader_edit_saveas_tip"))
        self.reader.btn_edit_undo.setText(tr("reader_edit_undo"))
        self.reader.btn_edit_undo.setToolTip(tr("reader_edit_undo_tip"))
        self.reader.btn_edit_redo.setText(tr("reader_edit_redo"))
        self.reader.btn_edit_redo.setToolTip(tr("reader_edit_redo_tip"))
        self.reader._store_tooltips()  # capture translated text, kill Qt big tooltips
        # Refresh welcome screen text if no document loaded
        if not self.reader.has_document():
            self.reader._show_welcome(
                drop_text=tr("reader_drop_here"),
                load_btn_text=tr("reader_load_file"))
        # Convert menu actions (the panel group was folded into the menu)
        self.act_extract_text.setText(tr("tool_extract_text"))
        self.act_extract_images.setText(tr("tool_extract_images"))
        self.act_pdf_to_images.setText(tr("tool_pdf_to_images"))
        self.act_images_to_pdf.setText(tr("tool_images_to_pdf"))
        self.act_to_word.setText(tr("tool_to_word"))
        self.act_to_ppt.setText(tr("tool_to_ppt"))
        self.act_to_excel.setText(tr("tool_to_excel"))
        # Status
        if not self._worker or not self._worker.isRunning():
            self.status_label.setText(tr("status_ready"))
        # File list
        self.file_list.retranslate_ui()
        # Derived labels (merge button summary, button enablement)
        self._update_button_states()
        # Office (formats the cached probe result; never re-probes)
        self._check_office()

    def _init_merge_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.file_list = FileListWidget()
        self.file_list.files_changed.connect(self._update_button_states)
        self.file_list.list_widget.itemDoubleClicked.connect(
            self._on_file_list_double_click)
        splitter.addWidget(self.file_list)

        # Right panel wrapped in scroll area — tools scroll when window is too short
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        s_bg = _dc("#2c2c2c", "#f5f5f5"); sb_bg = _dc("#1e1e1e", "#e8e8e8"); sh = _dc("#555", "#bbb")
        scroll.setStyleSheet(
            f"QScrollArea{{background:{s_bg};border:none;}}"
            f"QScrollBar:vertical{{background:{sb_bg};width:8px;margin:0}}"
            f"QScrollBar::handle:vertical{{background:{sh};border-radius:3px;min-height:20px}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0}}")

        right = QWidget()
        right.setStyleSheet(f"background:{_dc('#2c2c2c','#f5f5f5')};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 20)

        self.merge_group = QGroupBox(tr("group_merge_ops"))
        mg_layout = QVBoxLayout(self.merge_group)

        self.btn_merge = QPushButton(tr("btn_merge_unified"))
        self.btn_merge.setMinimumHeight(40)
        self.btn_merge.setStyleSheet(
            "QPushButton { font-size: 14px; font-weight: bold; "
            "background-color: #007aff; color: white; border-radius: 6px; }"
            "QPushButton:hover { background-color: #0056cc; }"
            "QPushButton:disabled { background-color: #aaa; }")
        self.btn_merge.clicked.connect(self._on_merge_clicked)
        mg_layout.addWidget(self.btn_merge)
        right_layout.addWidget(self.merge_group)

        self.single_group = QGroupBox(tr("group_pdf_ops"))
        sg_layout = QVBoxLayout(self.single_group)
        self.btn_split = QPushButton(tr("btn_split"))
        self.btn_split.clicked.connect(self._on_split_clicked)
        sg_layout.addWidget(self.btn_split)
        self.btn_compress = QPushButton(tr("btn_compress"))
        self.btn_compress.clicked.connect(self._on_compress_clicked)
        sg_layout.addWidget(self.btn_compress)
        self.btn_watermark = QPushButton(tr("btn_watermark"))
        self.btn_watermark.clicked.connect(self._on_watermark_clicked)
        sg_layout.addWidget(self.btn_watermark)
        self.btn_encrypt = QPushButton(tr("btn_encrypt"))
        self.btn_encrypt.clicked.connect(self._on_encrypt_clicked)
        sg_layout.addWidget(self.btn_encrypt)
        self.btn_decrypt = QPushButton(tr("btn_decrypt"))
        self.btn_decrypt.clicked.connect(self._on_decrypt_clicked)
        sg_layout.addWidget(self.btn_decrypt)
        self.btn_rotate = QPushButton(tr("btn_rotate"))
        self.btn_rotate.clicked.connect(self._on_rotate_clicked)
        sg_layout.addWidget(self.btn_rotate)
        self.btn_info = QPushButton(tr("btn_info"))
        self.btn_info.clicked.connect(self._on_info_clicked)
        sg_layout.addWidget(self.btn_info)
        right_layout.addWidget(self.single_group)

        # The seven format-conversion actions live in the Convert menu; the
        # right-hand panel keeps only the operations that act on the file list
        # plus the merge button, so the layout stays quiet.
        self.tools_group = None
        self._tool_buttons = []

        self.office_status_label = QLabel(tr("office_checking"))
        self.office_status_label.setStyleSheet(f"color: {_dc('#999','#777')};")
        right_layout.addWidget(self.office_status_label)
        right_layout.addStretch()

        scroll.setWidget(right)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        out_layout = QHBoxLayout()
        self.label_output = QLabel(tr("label_output"))
        out_layout.addWidget(self.label_output)
        self.output_path_edit = QLineEdit()
        dfl = self._settings.value("output_dir", str(Path.home() / "Desktop"))
        self.output_path_edit.setText(dfl + "/" + tr("default_output"))
        out_layout.addWidget(self.output_path_edit)
        self.btn_browse_out = QPushButton(tr("btn_browse"))
        self.btn_browse_out.clicked.connect(self._on_browse_output)
        out_layout.addWidget(self.btn_browse_out)
        layout.addLayout(out_layout)

        self.tabs.addTab(tab, tr("tab_merge"))

    def _init_reader_tab(self):
        """Tab 3: PDF reader."""
        self.reader = PdfReaderWidget()
        self.reader.close_requested.connect(self._on_reader_close)
        self.reader.open_requested.connect(self._on_reader_open_requested)
        self.tabs.addTab(self.reader, tr("tab_reader"))

    def _on_reader_open_requested(self):
        """Handle Load file button or drag-drop in reader welcome screen."""
        drop_path = getattr(self.reader, '_path', None)
        if drop_path and drop_path.exists():
            self._open_pdf_in_reader(drop_path, from_file_list=False)
        else:
            self._open_pdf_in_reader()  # show file dialog

    def _open_pdf_in_reader(self, path: Path = None, from_file_list: bool = False) -> None:
        """Open a PDF in the reader tab. If path is None, show file dialog."""
        if path is None:
            from PyQt6.QtWidgets import QFileDialog
            path_str, _ = QFileDialog.getOpenFileName(
                self, tr("reader_open_pdf"), "", tr("reader_file_filter"))
            if not path_str:
                return
            path = Path(path_str)
        self.reader.opened_from_file_list = from_file_list
        self.reader.open_pdf(path)
        self.tabs.setCurrentIndex(1)  # switch to reader tab

    def _on_reader_close(self):
        """Handle user clicking × on reader. Jump back to file list if opened from there."""
        if self.reader.opened_from_file_list:
            self.tabs.setCurrentIndex(0)  # back to Merge tab

    def _on_file_list_double_click(self, item) -> None:
        """Double-click a file in the list → open in reader tab."""
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and path.suffix.lower() == ".pdf":
            self._open_pdf_in_reader(path, from_file_list=True)

    def _init_status_bar(self, parent_layout):
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)
        hlayout = QHBoxLayout()
        self.status_label = QLabel(tr("status_ready"))
        self.status_label.setStyleSheet(f"color: {_dc('#999','#777')};")
        hlayout.addWidget(self.status_label)
        hlayout.addStretch()
        self.btn_cancel = QPushButton(tr("btn_cancel"))
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        hlayout.addWidget(self.btn_cancel)
        status_layout.addLayout(hlayout)
        parent_layout.addWidget(status_widget)

    # ── Window events ────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()
                 if Path(url.toLocalFile()).exists()]
        if paths:
            self.file_list.add_files(paths)

    def closeEvent(self, event: QCloseEvent):
        # Check if reader has unsaved edits — only when a document is loaded
        if self.reader.has_document() and self.reader.has_unsaved_edits:
            result = self.reader._prompt_save_changes()
            if result == "cancel":
                event.ignore(); return
            if result == "save_as":
                self.reader._save_edited_copy()
        self._settings.setValue("window_geometry",
                                bytes(self.saveGeometry()).hex())
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        cleanup_temp_files()
        event.accept()

    def _restore_geometry(self):
        geo = self._settings.value("window_geometry")
        if geo:
            try:
                self.restoreGeometry(bytes.fromhex(geo))
            except Exception:
                pass

    def _check_office(self):
        """Render the Office status from the cached probe result.

        The probe itself shells out to osascript/COM (up to 30 s), so it runs on a
        worker thread started by _start_office_probe; this method only formats the
        now-known answer and is called from the language switch and the probe."""
        avail = check_office_availability()
        if avail is None:
            self.office_status_label.setText(tr("office_checking"))
            return
        try:
            w = tr("office_ok") if avail.get("word") else tr("office_fail")
            p = tr("office_ok") if avail.get("powerpoint") else tr("office_fail")
            e = tr("office_ok") if avail.get("excel") else tr("office_fail")
            self.office_status_label.setText(
                tr("office_status_fmt", word=w, ppt=p, excel=e))
        except Exception:
            self.office_status_label.setText(tr("office_checking"))

    def _start_office_probe(self):
        """Detect Word/PowerPoint/Excel off the GUI thread.

        Previously this ran inline in the constructor and froze the window for up
        to 30 seconds on machines where the AppleScript probe is slow."""
        if check_office_availability() is not None:
            self._check_office()
            return

        class _ProbeWorker(QThread):
            done = pyqtSignal(dict)

            def run(self):  # noqa: D102
                try:
                    self.done.emit(check_office_availability(use_cache=False))
                except Exception:
                    self.done.emit({})

        self._office_worker = _ProbeWorker(self)
        self._office_worker.done.connect(self._on_office_probed)
        self._office_worker.start()

    def _on_office_probed(self, avail: dict):
        import core.utils as utils
        utils.set_office_cache(avail)
        self._check_office()

    # ── Button state ─────────────────────────────────

    def _update_button_states(self):
        paths = self.file_list.get_file_paths()
        has_files = len(paths) > 0
        self.btn_merge.setEnabled(has_files)
        # Show a hint about what's in the list, but always keep one button.
        # The counter text comes from i18n so it follows the UI language, and the
        # label is used as-is (it already carries its own icon).
        if has_files:
            cats = set(get_file_category(p) for p in paths)
            if len(cats) > 1:
                label = tr("merge_mixed_files")
            elif cats == {"pdf"}:
                label = tr("merge_pdf_files")
            elif cats == {"image"}:
                label = tr("merge_image_files")
            elif cats == {"word"}:
                label = tr("merge_word_files")
            else:
                label = tr("merge_as_pdf")
            self.btn_merge.setText(tr("merge_count_fmt", label=label, count=len(paths)))
        else:
            self.btn_merge.setText(tr("btn_merge_unified"))

    # ── Output path ──────────────────────────────────

    def _get_output_path(self, suffix: str = None) -> Optional[Path]:
        if suffix is None:
            suffix = tr("default_output")
        current = self.output_path_edit.text().strip()
        if current and not current.endswith(suffix):
            current = str(Path(current).parent / suffix)
        if current and Path(current).parent.exists():
            path, _ = QFileDialog.getSaveFileName(
                self, tr("dlg_save_pdf"), current, tr("file_filter_pdf"))
        else:
            default = str(Path.home() / "Desktop" / suffix)
            path, _ = QFileDialog.getSaveFileName(
                self, tr("dlg_save_pdf"), default, tr("file_filter_pdf"))
        if path:
            self.output_path_edit.setText(path)
            self._settings.setValue("output_dir", str(Path(path).parent))
            return Path(path)
        return None

    # ── Worker ───────────────────────────────────────

    def _run_worker(self, func, *args, **kwargs):
        if self._worker and self._worker.isRunning():
            return
        self._worker = BaseWorker(func, *args, **kwargs)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(self._on_cancelled)
        self._set_busy(True)
        self._worker.start()

    def _is_current_worker(self) -> bool:
        """True when the signal we are handling came from the active worker.

        Without this guard a late signal from a cancelled job could clear the busy
        state of the job that replaced it."""
        sender = self.sender()
        if sender is None or self._worker is None:
            return True  # called directly (tests) rather than through a signal
        return sender is self._worker

    def _set_busy(self, busy: bool):
        # show()/hide() rather than setVisible(): they are explicit and leave no
        # ambiguity about a widget's visibility state for tests and for Qt.
        if busy:
            self.progress_bar.show()
            self.btn_cancel.show()
        else:
            self.progress_bar.hide()
            self.btn_cancel.hide()
        self.file_list.setEnabled(not busy)
        for w in [self.btn_merge,
                  self.btn_split, self.btn_compress, self.btn_watermark,
                  self.btn_encrypt, self.btn_decrypt, self.btn_rotate, self.btn_info]:
            w.setEnabled(not busy)
        if not busy:
            self._update_button_states()

    def _on_progress(self, msg: str, pct: int):
        if not self._is_current_worker():
            return
        self.status_label.setText(msg)
        self.progress_bar.setValue(pct)

    def _show_message(self, kind: str, title: str, text: str):
        """Open a modal box one event-loop turn later.

        Opening it directly from a queued-signal handler can deadlock: the modal
        loop runs nested event processing while the original handler is still on
        the stack, and the dialog never comes back (reproduced as a hard hang).
        """
        def show():
            getattr(QMessageBox, kind)(self, title, text)
        QTimer.singleShot(0, show)

    def _on_finished(self, result):
        if not self._is_current_worker():
            return
        self._set_busy(False)
        self.status_label.setText(tr("status_done"))
        self.progress_bar.setValue(100)
        if isinstance(result, dict):
            if "results" in result:
                failed = result.get("failed") or []
                info_text = tr("msg_batch_done", ok=result["converted"],
                               failed=len(failed), output=result["output"])
                if failed:
                    info_text += "\n\n" + "\n".join(
                        f"• {Path(f['path']).name}: {f['reason']}" for f in failed[:15])
                    if len(failed) > 15:
                        info_text += f"\n… +{len(failed) - 15}"
                self._show_message("warning" if failed else "information",
                                   tr("status_done"), info_text)
            elif "failed" in result and result["failed"]:
                failed_list = "\n".join(
                    f"• {f['path']}: {f['reason']}" for f in result["failed"])
                self._show_message("warning", tr("msg_op_failed"),
                                   tr("msg_partial_fail",
                                      converted=result["converted"],
                                      total=result["total_files"],
                                      failed_list=failed_list))
            elif "ratio" in result:
                self._show_message("information", tr("dlg_compress_title"),
                                   tr("msg_compress_done",
                                      before=format_bytes(result['before_bytes']),
                                      after=format_bytes(result['after_bytes']),
                                      ratio=result['ratio']))
            else:
                self._show_message("information", tr("status_done"),
                                   tr("msg_merge_done",
                                      count=result.get("converted",
                                                       result.get("total_files", 0)),
                                      output=result.get("output", "")))
        elif isinstance(result, int):
            self._show_message("information", tr("status_done"),
                               tr("msg_done_count", count=result))
        elif isinstance(result, list):
            self._show_message("information", tr("status_done"),
                               tr("msg_done_files", count=len(result)))

    def _on_error(self, msg: str):
        if not self._is_current_worker():
            return
        self._set_busy(False)
        self.status_label.setText(tr("status_error"))
        self._show_message("critical", tr("msg_op_failed"), msg)

    def _on_cancelled(self):
        if not self._is_current_worker():
            return
        self._set_busy(False)
        self.status_label.setText(tr("status_cancelled"))

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            # cancel() returns immediately and arms a delayed force-terminate, so
            # the window keeps repainting while the operation unwinds.
            self._worker.cancel()
            self.progress_bar.setVisible(False)
            self.btn_cancel.setVisible(False)
            self.status_label.setText(tr("status_cancelled"))

    # ── Action handlers ──────────────────────────────

    def _on_merge_clicked(self):
        paths = self.file_list.get_file_paths()
        if not paths:
            QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_no_files"))
            return
        out = self._get_output_path(tr("default_merged"))
        if not out:
            return
        cats = set(get_file_category(p) for p in paths)
        if cats == {"pdf"}:
            self._run_worker(PdfOperator.merge, paths, out)
        else:
            self._run_worker(merge_mixed_files, paths, out)

    MAX_BATCH = 200
    BATCH_CONFIRM_THRESHOLD = 20

    def _run_batch(self, files, suffix, op_func, *extra_args, ext=".pdf",
                   out_dir: Optional[Path] = None):
        """Batch helper: process multiple files with the same op into a directory.

        Asks for confirmation above BATCH_CONFIRM_THRESHOLD files, caps the run at
        MAX_BATCH, and keeps going when a single file fails so one bad input no
        longer aborts the whole batch."""
        if len(files) > self.MAX_BATCH:
            reply = QMessageBox.question(
                self, tr("msg_batch_limit_title"),
                tr("msg_batch_limit_body", count=len(files), max=self.MAX_BATCH),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
            if reply != QMessageBox.StandardButton.Ok:
                return
            files = files[:self.MAX_BATCH]
        elif len(files) > self.BATCH_CONFIRM_THRESHOLD:
            reply = QMessageBox.question(
                self, tr("msg_batch_large_title"),
                tr("msg_batch_large_body", count=len(files)),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
            if reply != QMessageBox.StandardButton.Ok:
                return

        if out_dir is None:
            out_dir = self._get_batch_output_dir()
        if not out_dir:
            return

        def batch_fn(progress_callback=None):
            results, failed = [], []
            total = len(files)
            for i, fp in enumerate(files):
                out = self._get_batch_output_path(fp, suffix, out_dir, ext)
                if progress_callback:
                    progress_callback(f"{suffix} ({i+1}/{total}): {fp.name}",
                                      int((i + 1) / total * 100))
                try:
                    op_func(fp, out, *extra_args)
                    results.append(str(out))
                except Exception as e:      # keep processing the remaining files
                    failed.append({"path": str(fp),
                                   "reason": str(e) or type(e).__name__})
            return {"converted": len(results), "total_files": total,
                    "failed": failed, "output": str(out_dir), "results": results}

        self._run_worker(batch_fn)

    def _run_batch_with_dialog(self, files, suffix, dlg_cls, op_no_extra, *extra_args):
        """Like _run_batch, but opens a dialog first for shared params."""
        dlg = dlg_cls(self)
        if not dlg.exec():
            return
        extra = list(extra_args)
        if hasattr(dlg, 'get_password'):
            extra.append(dlg.get_password())
        if hasattr(dlg, 'get_angle'):
            extra.extend([dlg.get_angle(), dlg.get_pages()])
        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_{suffix}.pdf")
            if not out:
                return
            self._run_worker(op_no_extra, files[0], out, *extra)
        else:
            self._run_batch(files, suffix, op_no_extra, *extra)

    def _on_split_clicked(self):
        ip = self._pick_input_file()
        if not ip:
            return
        dlg = SplitRangeDialog(self)
        if not dlg.exec():
            return
        start_dir = Path(self._settings.value(
            "output_dir", str(Path.home() / "Desktop")))
        chosen = QFileDialog.getExistingDirectory(
            self, tr("dlg_select_output_dir"), str(start_dir))
        if not chosen:
            return
        out_dir = Path(chosen)
        mode = dlg.get_mode()
        if mode == 0:
            self._run_worker(PdfOperator.split, ip, out_dir, None)
        elif mode == 1:
            info = PdfOperator.get_info(ip)
            total = info["pages"]
            n = dlg.get_n_pages()
            ranges = [(s, min(s + n - 1, total)) for s in range(1, total + 1, n)]
            self._run_worker(PdfOperator.split, ip, out_dir, ranges)
        else:
            self._run_worker(PdfOperator.split, ip, out_dir, dlg.get_ranges())

    def _on_compress_clicked(self):
        files = self._pick_input_files()
        if not files:
            return
        dlg = CompressDialog(self)
        if not dlg.exec():
            return
        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_compressed.pdf")
            if not out:
                return
            self._run_worker(PdfOperator.compress, files[0], out)
        else:
            self._run_batch(files, "compressed", PdfOperator.compress)

    def _on_watermark_clicked(self):
        files = self._pick_input_files()
        if not files:
            return
        dlg = WatermarkDialog(self)
        if not dlg.exec():
            return
        r = dlg.get_result()
        if r["type"] == "text":
            wm_fn = PdfOperator.text_watermark
            wm_args = [r["text"], r["font_size"], r["opacity"], r["rotation"]]
        else:
            wm_fn = PdfOperator.watermark
            wm_args = [r["watermark_path"]]

        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_watermarked.pdf")
            if not out:
                return
            self._run_worker(wm_fn, files[0], out, *wm_args)
        else:
            self._run_batch(files, "watermarked", wm_fn, *wm_args)

    def _on_encrypt_clicked(self):
        files = self._pick_input_files()
        if not files:
            return
        dlg = EncryptDialog(self)
        if not dlg.exec():
            return
        pw = dlg.get_password()
        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_encrypted.pdf")
            if not out:
                return
            self._run_worker(PdfOperator.encrypt, files[0], out, pw)
        else:
            self._run_batch(files, "encrypted", PdfOperator.encrypt, pw)

    def _on_decrypt_clicked(self):
        files = self._pick_input_files()
        if not files:
            return
        dlg = DecryptDialog(self)
        if not dlg.exec():
            return
        pw = dlg.get_password()
        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_decrypted.pdf")
            if not out:
                return
            self._run_worker(PdfOperator.decrypt, files[0], out, pw)
        else:
            self._run_batch(files, "decrypted", PdfOperator.decrypt, pw)

    def _on_rotate_clicked(self):
        files = self._pick_input_files()
        if not files:
            return
        dlg = RotateDialog(self)
        if not dlg.exec():
            return
        angle, pages = dlg.get_angle(), dlg.get_pages()
        if pages is not None and not pages:
            # [] means "rotate no page" in PdfOperator — refuse instead of
            # writing an identical copy and reporting success.
            QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_rot_empty"))
            return
        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_rotated.pdf")
            if not out:
                return
            self._run_worker(PdfOperator.rotate, files[0], out, angle, pages)
        else:
            self._run_batch(files, "rotated", PdfOperator.rotate, angle, pages)

    def _on_info_clicked(self):
        ip = self._pick_input_file()
        if not ip:
            return
        InfoDialog(PdfOperator.get_info(ip), self).exec()

    def _on_extract_text(self):
        files = self._pick_input_files()
        if not files:
            return
        if len(files) == 1:
            out, _ = QFileDialog.getSaveFileName(
                self, tr("dlg_save_text"), f"{files[0].stem}.txt", tr("file_filter_text"))
            if not out:
                return
            self._run_worker(PdfOperator.extract_text, files[0], Path(out))
        else:
            self._run_batch(files, "text", PdfOperator.extract_text, ext=".txt")

    def _on_extract_images(self):
        files = self._pick_input_files()
        if not files:
            return
        if len(files) == 1:
            out_dir = QFileDialog.getExistingDirectory(self, tr("dlg_select_output_dir"))
            if not out_dir:
                return
            self._run_worker(PdfOperator.extract_images, files[0], Path(out_dir))
        else:
            self._run_batch(files, "images", PdfOperator.extract_images)

    def _on_pdf_to_images(self):
        files = self._pick_input_files()
        if not files:
            return
        dpi = int(self._settings.value("dpi", 200))
        if len(files) == 1:
            out_dir = QFileDialog.getExistingDirectory(self, tr("dlg_select_output_dir"))
            if not out_dir:
                return
            self._run_worker(PdfOperator.to_images, files[0], Path(out_dir), dpi)
        else:
            self._run_batch(files, "pages", PdfOperator.to_images, dpi)

    def _on_single_images_to_pdf(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg_select_images"), "", tr("file_filter_images"))
        if not files:
            return
        out = self._get_output_path(tr("default_images"))
        if not out:
            return
        self._run_worker(PdfOperator.from_images, [Path(f) for f in files], out)

    def _pick_input_files(self) -> List[Path]:
        """Get PDFs to process: from file list if available, else from dialog.
        If user selected specific rows in the list, use only those.
        Returns empty list if user cancelled."""
        paths = self.file_list.get_file_paths()
        pdfs = filter_by_category(paths, "pdf")
        if pdfs:
            return pdfs
        # Fallback: multi-select file dialog
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg_select_pdf"), "", tr("file_filter_pdf"))
        return [Path(f) for f in files] if files else []

    def _pick_input_file(self) -> Optional[Path]:
        """Select a single PDF (prefer from list, else dialog)."""
        files = self._pick_input_files()
        return files[0] if files else None

    def _get_batch_output_dir(self) -> Optional[Path]:
        """Ask user to pick a directory for batch output."""
        d = Path(self._settings.value(
            "output_dir", str(Path.home() / "Desktop")))
        path = QFileDialog.getExistingDirectory(
            self, tr("dlg_select_output_dir"), str(d))
        return Path(path) if path else None

    def _get_batch_output_path(self, input_path: Path, suffix: str, out_dir: Path,
                                ext: str = ".pdf") -> Path:
        """Generate output path for a single file in a batch."""
        return out_dir / f"{input_path.stem}_{suffix}{ext}"

    def _on_add_files_dialog(self):
        self.file_list._on_add_files()

    def _on_browse_output(self):
        current = self.output_path_edit.text().strip()
        if not current:
            current = str(Path.home() / "Desktop" / tr("default_output"))
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_save_pdf"), current, tr("file_filter_pdf"))
        if path:
            self.output_path_edit.setText(path)

    def _on_to_word(self):
        files = self._pick_input_files()
        if not files:
            return
        if len(files) == 1:
            out, _ = QFileDialog.getSaveFileName(
                self, tr("dlg_save_text"), f"{files[0].stem}.docx",
                tr("file_filter_word"))
            if not out:
                return
            self._run_worker(PdfOperator.to_word, files[0], Path(out))
        else:
            self._run_batch(files, "word", PdfOperator.to_word, ext=".docx")

    def _on_to_ppt(self):
        files = self._pick_input_files()
        if not files:
            return
        dpi = int(self._settings.value("dpi", 200))
        if len(files) == 1:
            out, _ = QFileDialog.getSaveFileName(
                self, tr("dlg_save_text"), f"{files[0].stem}.pptx",
                tr("file_filter_ppt"))
            if not out:
                return
            self._run_worker(PdfOperator.to_ppt, files[0], Path(out), dpi)
        else:
            self._run_batch(files, "ppt", PdfOperator.to_ppt, dpi, ext=".pptx")

    def _on_to_excel(self):
        files = self._pick_input_files()
        if not files:
            return
        if len(files) == 1:
            out, _ = QFileDialog.getSaveFileName(
                self, tr("dlg_save_text"), f"{files[0].stem}.xlsx",
                tr("file_filter_excel"))
            if not out:
                return
            self._run_worker(PdfOperator.to_excel, files[0], Path(out))
        else:
            self._run_batch(files, "excel", PdfOperator.to_excel, ext=".xlsx")

    # ── Compose actions ──────────────────────────────

    def _on_page_numbers_clicked(self):
        files = self._pick_input_files()
        if not files:
            return
        dlg = PageNumberDialog(self)
        if not dlg.exec():
            return
        pages = dlg.get_pages()
        position = dlg.get_position()
        template = dlg.get_template()
        start = dlg.get_start()
        size = dlg.get_font_size()
        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_numbered.pdf")
            if not out:
                return
            self._run_worker(PdfOperator.add_page_numbers, files[0], out,
                             position, start, size, template, 28.0, pages)
        else:
            self._run_batch(files, "numbered", PdfOperator.add_page_numbers,
                            position, start, size, template, 28.0, pages)

    def _on_metadata_clicked(self):
        files = self._pick_input_files()
        if not files:
            return
        try:
            info = PdfOperator.get_info(files[0])
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("msg_op_failed"), str(e))
            return
        dlg = MetadataDialog(info, self)
        dlg.set_original(info)
        if not dlg.exec():
            return
        fields = dlg.get_metadata()
        if not fields:
            return
        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_meta.pdf")
            if not out:
                return
            self._run_worker(PdfOperator.set_metadata, files[0], out, fields)
        else:
            self._run_batch(files, "meta", PdfOperator.set_metadata, fields)

    def _on_nup_clicked(self):
        files = self._pick_input_files()
        if not files:
            return
        per_sheet, ok = QInputDialog.getItem(
            self, tr("dlg_nup_title"), tr("nup_per_sheet"),
            ["2", "4", "6", "8", "9", "16"], 0, False)
        if not ok:
            return
        paper, ok = QInputDialog.getItem(
            self, tr("dlg_nup_title"), tr("nup_paper"),
            ["A4", "A3", "Letter"], 0, False)
        if not ok:
            return
        n = int(per_sheet)
        if len(files) == 1:
            out = self._get_output_path(f"{files[0].stem}_{n}up.pdf")
            if not out:
                return
            self._run_worker(PdfOperator.nup, files[0], out, n, paper.lower(), 18.0, 8.0)
        else:
            self._run_batch(files, f"{n}up", PdfOperator.nup, n, paper.lower(), 18.0, 8.0)

    def _on_insert_pages_clicked(self):
        target = self._pick_input_file()
        if not target:
            return
        source_str, _ = QFileDialog.getOpenFileName(
            self, tr("dlg_select_pdf"), "", tr("file_filter_pdf"))
        if not source_str:
            return
        source = Path(source_str)
        try:
            target_pages = PdfOperator.get_info(target).get("pages", 0)
        except Exception:
            target_pages = 0
        at, ok = QInputDialog.getInt(
            self, tr("dlg_insert_title"), tr("insert_at"),
            max(1, target_pages + 1), 1, max(1, target_pages + 1))
        if not ok:
            return
        out = self._get_output_path(f"{target.stem}_inserted.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.insert_pages, target, source, out, at - 1)

    def _on_about(self):
        QMessageBox.about(self, tr("about_title"), tr("about_text", version=VERSION))
