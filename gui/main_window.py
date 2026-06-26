"""PDFeverything main window GUI."""

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
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
    register_temp,
)

from .dialogs import (
    CompressDialog,
    DecryptDialog,
    EncryptDialog,
    InfoDialog,
    RotateDialog,
    SplitRangeDialog,
    WatermarkDialog,
)
from .file_list_widget import FileListWidget
from .i18n import tr, set_language, current_language
from .workers import BaseWorker


class MainWindow(QMainWindow):
    """PDFeverything main window."""

    def __init__(self):
        super().__init__()
        self._worker: Optional[QThread] = None
        self._settings = QSettings("PDFeverything", "PDFeverything")
        self._init_ui()
        self._restore_geometry()
        self._check_office()

    # ── UI ───────────────────────────────────────────

    def _init_ui(self):
        self.setWindowTitle(tr("window_title"))
        self.setMinimumSize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        self._init_merge_tab()
        self._init_tools_tab()
        main_layout.addWidget(self.tabs)

        self._init_status_bar(main_layout)
        self._create_menu()
        self.setAcceptDrops(True)

    def _create_menu(self):
        mb = self.menuBar()

        self.menu_file = mb.addMenu(tr("menu_file"))
        self.act_add = self.menu_file.addAction(
            tr("menu_add_files"), "Ctrl+O", self._on_add_files_dialog)
        self.act_clear = self.menu_file.addAction(
            tr("menu_clear_list"), "Ctrl+Shift+N", self.file_list.clear)
        self.menu_file.addSeparator()
        self.act_quit = self.menu_file.addAction(
            tr("menu_quit"), "Ctrl+Q", self.close)

        self.menu_op = mb.addMenu(tr("menu_operations"))
        self.act_merge = self.menu_op.addAction(
            "🔀 Merge → PDF", "Ctrl+M", self._on_merge_clicked)
        self.act_split = self.menu_op.addAction(tr("btn_split"), self._on_split_clicked)
        self.act_compress = self.menu_op.addAction(tr("btn_compress"), self._on_compress_clicked)
        self.act_watermark = self.menu_op.addAction(tr("btn_watermark"), self._on_watermark_clicked)
        self.act_encrypt = self.menu_op.addAction(tr("btn_encrypt"), self._on_encrypt_clicked)
        self.act_decrypt = self.menu_op.addAction(tr("btn_decrypt"), self._on_decrypt_clicked)
        self.act_rotate = self.menu_op.addAction(tr("btn_rotate"), self._on_rotate_clicked)

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
        self.menu_help.addAction(tr("menu_about"), self._on_about)

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
        self.act_quit.setText(tr("menu_quit"))
        self.menu_op.setTitle(tr("menu_operations"))
        self.act_split.setText(tr("btn_split"))
        self.act_compress.setText(tr("btn_compress"))
        self.act_watermark.setText(tr("btn_watermark"))
        self.act_encrypt.setText(tr("btn_encrypt"))
        self.act_decrypt.setText(tr("btn_decrypt"))
        self.act_rotate.setText(tr("btn_rotate"))
        self.menu_settings.setTitle(tr("menu_settings"))
        self.menu_lang.setTitle(tr("menu_language"))
        self.act_lang_zh.setText(tr("menu_lang_zh"))
        self.act_lang_en.setText(tr("menu_lang_en"))
        self.menu_help.setTitle(tr("menu_help"))
        # Group boxes
        self.merge_group.setTitle(tr("group_merge_ops"))
        self.single_group.setTitle(tr("group_pdf_ops"))
        # Buttons
        self.btn_merge.setText(tr("btn_merge_unified"))
        self.btn_split.setText(tr("btn_split"))
        self.btn_compress.setText(tr("btn_compress"))
        self.btn_watermark.setText(tr("btn_watermark"))
        self.btn_encrypt.setText(tr("btn_encrypt"))
        self.btn_decrypt.setText(tr("btn_decrypt"))
        self.btn_rotate.setText(tr("btn_rotate"))
        self.btn_info.setText(tr("btn_info"))
        self.btn_images_pdf.setText(tr("btn_images_to_pdf"))
        self.btn_word_pdf.setText(tr("btn_word_to_pdf"))
        self.btn_browse_out.setText(tr("btn_browse"))
        self.btn_cancel.setText(tr("btn_cancel"))
        self.label_output.setText(tr("label_output"))
        # Tab names
        self.tabs.setTabText(0, tr("tab_merge"))
        self.tabs.setTabText(1, tr("tab_tools"))
        # Tool buttons
        if self._tool_buttons:
            labels = ["tool_extract_text", "tool_extract_images",
                      "tool_pdf_to_images", "tool_images_to_pdf",
                      "tool_to_word", "tool_to_ppt", "tool_to_excel"]
            for btn, key in zip(self._tool_buttons, labels):
                btn.setText(tr(key))
        # Status
        if not self._worker or not self._worker.isRunning():
            self.status_label.setText(tr("status_ready"))
        # File list
        self.file_list.retranslate_ui()
        # Office
        self._check_office()

    def _init_merge_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.file_list = FileListWidget()
        self.file_list.files_changed.connect(self._update_button_states)
        splitter.addWidget(self.file_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 0)

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

        self.btn_images_pdf = QPushButton(tr("btn_images_to_pdf"))
        self.btn_images_pdf.clicked.connect(self._on_images_to_pdf)
        mg_layout.addWidget(self.btn_images_pdf)

        self.btn_word_pdf = QPushButton(tr("btn_word_to_pdf"))
        self.btn_word_pdf.clicked.connect(self._on_word_to_pdf)
        mg_layout.addWidget(self.btn_word_pdf)

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
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
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

    def _init_tools_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        tool_keys = [
            ("tool_extract_text", self._on_extract_text),
            ("tool_extract_images", self._on_extract_images),
            ("tool_pdf_to_images", self._on_pdf_to_images),
            ("tool_images_to_pdf", self._on_single_images_to_pdf),
            ("tool_to_word", self._on_to_word),
            ("tool_to_ppt", self._on_to_ppt),
            ("tool_to_excel", self._on_to_excel),
        ]
        self._tool_buttons = []
        for key, slot in tool_keys:
            btn = QPushButton(tr(key))
            btn.setMinimumHeight(36)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            self._tool_buttons.append(btn)

        layout.addStretch()
        self.office_status_label = QLabel(tr("office_checking"))
        self.office_status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.office_status_label)

        self.tabs.addTab(tab, tr("tab_tools"))

    def _init_status_bar(self, parent_layout):
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)
        hlayout = QHBoxLayout()
        self.status_label = QLabel(tr("status_ready"))
        self.status_label.setStyleSheet("color: #666;")
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
        try:
            avail = check_office_availability()
            w = tr("office_ok") if avail.get("word") else tr("office_fail")
            p = tr("office_ok") if avail.get("powerpoint") else tr("office_fail")
            e = tr("office_ok") if avail.get("excel") else tr("office_fail")
            self.office_status_label.setText(
                tr("office_status_fmt", word=w, ppt=p, excel=e))
        except Exception:
            self.office_status_label.setText(tr("office_checking"))

    # ── Button state ─────────────────────────────────

    def _update_button_states(self):
        paths = self.file_list.get_file_paths()
        has_files = len(paths) > 0
        self.btn_merge.setEnabled(has_files)
        if has_files:
            cats = set(get_file_category(p) for p in paths)
            if cats == {"pdf"}:
                self.btn_merge.setText(tr("merge_pdf_files"))
            elif cats == {"image"}:
                self.btn_merge.setText(tr("merge_image_files"))
            elif cats == {"word"}:
                self.btn_merge.setText(tr("merge_word_files"))
            elif len(cats) > 1:
                self.btn_merge.setText(tr("merge_mixed_files"))
            else:
                self.btn_merge.setText(tr("merge_as_pdf"))
        else:
            self.btn_merge.setText(tr("btn_merge_unified"))

        images = filter_by_category(paths, "image")
        self.btn_images_pdf.setEnabled(len(images) > 0)
        if len(images) > 0:
            self.btn_images_pdf.setText(
                f"\U0001f5bc  ({len(images)}) → PDF")

        words = filter_by_category(paths, "word")
        self.btn_word_pdf.setEnabled(len(words) > 0)
        if len(words) > 0:
            self.btn_word_pdf.setText(
                f"\U0001f4dd  ({len(words)}) → PDF")

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
        self._set_busy(True)
        self._worker.start()

    def _set_busy(self, busy: bool):
        self.progress_bar.setVisible(busy)
        self.btn_cancel.setVisible(busy)
        self.file_list.setEnabled(not busy)
        for w in [self.btn_merge, self.btn_images_pdf, self.btn_word_pdf,
                  self.btn_split, self.btn_compress, self.btn_watermark,
                  self.btn_encrypt, self.btn_decrypt, self.btn_rotate, self.btn_info]:
            w.setEnabled(not busy)
        if not busy:
            self._update_button_states()

    def _on_progress(self, msg: str, pct: int):
        self.status_label.setText(msg)
        self.progress_bar.setValue(pct)

    def _on_finished(self, result):
        self._set_busy(False)
        self.status_label.setText(tr("status_done"))
        self.progress_bar.setValue(100)
        if isinstance(result, dict):
            if "failed" in result and result["failed"]:
                failed_list = "\n".join(
                    f"• {f['path']}: {f['reason']}" for f in result["failed"])
                QMessageBox.warning(
                    self, tr("msg_op_failed"),
                    tr("msg_partial_fail",
                       converted=result["converted"],
                       total=result["total_files"],
                       failed_list=failed_list))
            elif "ratio" in result:
                QMessageBox.information(
                    self, tr("dlg_compress_title"),
                    tr("msg_compress_done",
                       before=format_bytes(result['before_bytes']),
                       after=format_bytes(result['after_bytes']),
                       ratio=result['ratio']))
            else:
                QMessageBox.information(
                    self, tr("status_done"),
                    tr("msg_merge_done",
                       count=result.get("converted", result.get("total_files", 0)),
                       output=result.get("output", "")))
        elif isinstance(result, int):
            QMessageBox.information(self, tr("status_done"),
                                    tr("msg_done_count", count=result))
        elif isinstance(result, list):
            QMessageBox.information(self, tr("status_done"),
                                    tr("msg_done_files", count=len(result)))

    def _on_error(self, msg: str):
        self._set_busy(False)
        self.status_label.setText(tr("status_error"))
        QMessageBox.critical(self, tr("msg_op_failed"), msg)

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status_label.setText(tr("status_cancelled"))

    # ── Action handlers ──────────────────────────────

    def _pick_input_file(self) -> Optional[Path]:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg_select_pdf"), "", tr("file_filter_pdf"))
        return Path(path) if path else None

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

    def _on_split_clicked(self):
        ip = self._pick_input_file()
        if not ip:
            return
        dlg = SplitRangeDialog(self)
        if not dlg.exec():
            return
        out_dir = Path(self._settings.value(
            "output_dir", str(Path.home() / "Desktop")))
        out_dir = Path(QFileDialog.getExistingDirectory(
            self, tr("dlg_select_output_dir"), str(out_dir)))
        if not out_dir:
            return
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
        ip = self._pick_input_file()
        if not ip:
            return
        dlg = CompressDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{ip.stem}_compressed.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.compress, ip, out)

    def _on_watermark_clicked(self):
        ip = self._pick_input_file()
        if not ip:
            return
        dlg = WatermarkDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{ip.stem}_watermarked.pdf")
        if not out:
            return
        r = dlg.get_result()
        if r["type"] == "text":
            self._run_worker(PdfOperator.text_watermark, ip, out,
                             r["text"], r["font_size"], r["opacity"], r["rotation"])
        else:
            self._run_worker(PdfOperator.watermark, ip, r["watermark_path"], out)

    def _on_encrypt_clicked(self):
        ip = self._pick_input_file()
        if not ip:
            return
        dlg = EncryptDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{ip.stem}_encrypted.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.encrypt, ip, out, dlg.get_password())

    def _on_decrypt_clicked(self):
        ip = self._pick_input_file()
        if not ip:
            return
        dlg = DecryptDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{ip.stem}_decrypted.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.decrypt, ip, out, dlg.get_password())

    def _on_rotate_clicked(self):
        ip = self._pick_input_file()
        if not ip:
            return
        dlg = RotateDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{ip.stem}_rotated.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.rotate, ip, out, dlg.get_angle(), dlg.get_pages())

    def _on_info_clicked(self):
        ip = self._pick_input_file()
        if not ip:
            return
        InfoDialog(PdfOperator.get_info(ip), self).exec()

    def _on_extract_text(self):
        ip = self._pick_input_file()
        if not ip:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_save_text"), f"{ip.stem}.txt", tr("file_filter_text"))
        if not out:
            return
        self._run_worker(PdfOperator.extract_text, ip, Path(out))

    def _on_extract_images(self):
        ip = self._pick_input_file()
        if not ip:
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, tr("dlg_select_output_dir"))
        if not out_dir:
            return
        self._run_worker(PdfOperator.extract_images, ip, Path(out_dir))

    def _on_pdf_to_images(self):
        ip = self._pick_input_file()
        if not ip:
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, tr("dlg_select_output_dir"))
        if not out_dir:
            return
        dpi = int(self._settings.value("dpi", 200))
        self._run_worker(PdfOperator.to_images, ip, Path(out_dir), dpi)

    def _on_single_images_to_pdf(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg_select_images"), "", tr("file_filter_images"))
        if not files:
            return
        out = self._get_output_path(tr("default_images"))
        if not out:
            return
        self._run_worker(PdfOperator.from_images, [Path(f) for f in files], out)

    def _on_images_to_pdf(self):
        images = filter_by_category(self.file_list.get_file_paths(), "image")
        if not images:
            QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_no_images"))
            return
        out = self._get_output_path(tr("default_images"))
        if not out:
            return
        self._run_worker(PdfOperator.from_images, images, out)

    def _on_word_to_pdf(self):
        words = filter_by_category(self.file_list.get_file_paths(), "word")
        if not words:
            QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_no_word"))
            return
        out = self._get_output_path(tr("default_word_merged"))
        if not out:
            return
        self._run_worker(merge_mixed_files, words, out)

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
        ip = self._pick_input_file()
        if not ip:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_save_text"), f"{ip.stem}.docx",
            "Word (*.docx);;All files (*)")
        if not out:
            return
        self._run_worker(PdfOperator.to_word, ip, Path(out))

    def _on_to_ppt(self):
        ip = self._pick_input_file()
        if not ip:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_save_text"), f"{ip.stem}.pptx",
            "PowerPoint (*.pptx);;All files (*)")
        if not out:
            return
        dpi = int(self._settings.value("dpi", 200))
        self._run_worker(PdfOperator.to_ppt, ip, Path(out), dpi)

    def _on_to_excel(self):
        ip = self._pick_input_file()
        if not ip:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_save_text"), f"{ip.stem}.xlsx",
            "Excel (*.xlsx);;All files (*)")
        if not out:
            return
        self._run_worker(PdfOperator.to_excel, ip, Path(out))

    def _on_about(self):
        QMessageBox.about(self, tr("about_title"), tr("about_text"))
