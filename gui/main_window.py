"""主窗口 — PDF 处理工具的完整 GUI。"""

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
from .workers import BaseWorker


class MainWindow(QMainWindow):
    """PDFeverything 主窗口。"""

    def __init__(self):
        super().__init__()
        self._worker: Optional[QThread] = None
        self._settings = QSettings("PDFeverything", "PDFeverything")
        self._init_ui()
        self._restore_geometry()
        self._check_office()

    # ── UI 构建 ─────────────────────────────────────

    def _init_ui(self):
        self.setWindowTitle("PDFeverything")
        self.setMinimumSize(900, 600)

        # 中央区域
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Tab 页
        self.tabs = QTabWidget()
        self._init_merge_tab()
        self._init_tools_tab()
        main_layout.addWidget(self.tabs)

        # 底部状态栏
        self._init_status_bar(main_layout)

        # 菜单栏（必须在 tab 初始化之后，因为引用了 file_list）
        self._create_menu()

        # 接受外部拖入
        self.setAcceptDrops(True)

    def _create_menu(self):
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        file_menu.addAction("添加文件...", "Ctrl+O", self._on_add_files_dialog)
        file_menu.addAction("清空列表", "Ctrl+Shift+N", self.file_list.clear)
        file_menu.addSeparator()
        file_menu.addAction("退出(&Q)", "Ctrl+Q", self.close)

        # 操作菜单
        op_menu = menubar.addMenu("操作(&O)")
        op_menu.addAction("合并 → PDF", "Ctrl+M", self._on_merge_clicked)
        op_menu.addAction("拆分...", self._on_split_clicked)
        op_menu.addAction("压缩...", self._on_compress_clicked)
        op_menu.addAction("水印...", self._on_watermark_clicked)
        op_menu.addAction("加密...", self._on_encrypt_clicked)
        op_menu.addAction("解密...", self._on_decrypt_clicked)
        op_menu.addAction("旋转...", self._on_rotate_clicked)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        help_menu.addAction("关于", self._on_about)

    def _init_merge_tab(self):
        """tab 1: 合并与转换"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 内容区：文件列表 + 操作面板
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：文件列表
        self.file_list = FileListWidget()
        self.file_list.files_changed.connect(self._update_button_states)
        splitter.addWidget(self.file_list)

        # 右侧：操作面板
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 0)

        # 合并操作组
        merge_group = QGroupBox("📦 合并操作")
        mg_layout = QVBoxLayout(merge_group)

        self.btn_merge = QPushButton("🔀 合并为统一 PDF")
        self.btn_merge.setMinimumHeight(40)
        self.btn_merge.setStyleSheet(
            "QPushButton { font-size: 14px; font-weight: bold; "
            "background-color: #007aff; color: white; border-radius: 6px; }"
            "QPushButton:hover { background-color: #0056cc; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self.btn_merge.clicked.connect(self._on_merge_clicked)
        mg_layout.addWidget(self.btn_merge)

        self.btn_images_pdf = QPushButton("🖼️ 选中图片 → 生成 PDF")
        self.btn_images_pdf.clicked.connect(self._on_images_to_pdf)
        mg_layout.addWidget(self.btn_images_pdf)

        self.btn_word_pdf = QPushButton("📝 选中 Word → 合并 PDF")
        self.btn_word_pdf.clicked.connect(self._on_word_to_pdf)
        mg_layout.addWidget(self.btn_word_pdf)

        right_layout.addWidget(merge_group)

        # 单文件操作组
        single_group = QGroupBox("🔧 PDF 操作（选中列表中的 PDF）")
        sg_layout = QVBoxLayout(single_group)

        self.btn_split = QPushButton("✂️ 拆分")
        self.btn_split.clicked.connect(self._on_split_clicked)
        sg_layout.addWidget(self.btn_split)

        self.btn_compress = QPushButton("🗜️ 压缩")
        self.btn_compress.clicked.connect(self._on_compress_clicked)
        sg_layout.addWidget(self.btn_compress)

        self.btn_watermark = QPushButton("💧 水印")
        self.btn_watermark.clicked.connect(self._on_watermark_clicked)
        sg_layout.addWidget(self.btn_watermark)

        self.btn_encrypt = QPushButton("🔒 加密")
        self.btn_encrypt.clicked.connect(self._on_encrypt_clicked)
        sg_layout.addWidget(self.btn_encrypt)

        self.btn_decrypt = QPushButton("🔓 解密")
        self.btn_decrypt.clicked.connect(self._on_decrypt_clicked)
        sg_layout.addWidget(self.btn_decrypt)

        self.btn_rotate = QPushButton("🔄 旋转")
        self.btn_rotate.clicked.connect(self._on_rotate_clicked)
        sg_layout.addWidget(self.btn_rotate)

        self.btn_info = QPushButton("ℹ️ 信息")
        self.btn_info.clicked.connect(self._on_info_clicked)
        sg_layout.addWidget(self.btn_info)

        right_layout.addWidget(single_group)
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # 输出路径行
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("输出路径:"))
        self.output_path_edit = QLineEdit()
        default_dir = self._settings.value("output_dir", str(Path.home() / "Desktop"))
        self.output_path_edit.setText(default_dir + "/output.pdf")
        out_layout.addWidget(self.output_path_edit)
        self.btn_browse_out = QPushButton("浏览...")
        self.btn_browse_out.clicked.connect(self._on_browse_output)
        out_layout.addWidget(self.btn_browse_out)
        layout.addLayout(out_layout)

        self.tabs.addTab(tab, "📦 合并与转换")

    def _init_tools_tab(self):
        """tab 2: 快捷 PDF 工具"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        tools = [
            ("📄 PDF 提取文字", self._on_extract_text),
            ("🖼️ PDF 提取图片", self._on_extract_images),
            ("🖼️ PDF → 图片", self._on_pdf_to_images),
            ("📄 图片 → PDF", self._on_single_images_to_pdf),
        ]

        for label, slot in tools:
            btn = QPushButton(label)
            btn.setMinimumHeight(36)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        layout.addStretch()

        # Office 状态
        self.office_status_label = QLabel("检测中...")
        self.office_status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.office_status_label)

        self.tabs.addTab(tab, "🔧 PDF 工具")

    def _init_status_bar(self, parent_layout):
        """底部进度条 + 状态 + 取消。"""
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)

        hlayout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666;")
        hlayout.addWidget(self.status_label)
        hlayout.addStretch()

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        hlayout.addWidget(self.btn_cancel)

        status_layout.addLayout(hlayout)
        parent_layout.addWidget(status_widget)

    # ── 窗口事件 ────────────────────────────────────

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
        """启动时检测 Office 可用性并在状态栏显示。"""
        try:
            avail = check_office_availability()
            parts = []
            parts.append("Word ✅" if avail.get("word") else "Word ❌")
            parts.append("PPT ✅" if avail.get("powerpoint") else "PPT ❌")
            parts.append("Excel ✅" if avail.get("excel") else "Excel ❌")
            self.office_status_label.setText(
                "Office 状态: " + " | ".join(parts) +
                "\n（❌ 时将使用纯 Python 渲染，保文本但舍格式）")
        except Exception:
            self.office_status_label.setText("Office 状态: 检测失败")

    # ── 按钮状态管理 ────────────────────────────────

    def _update_button_states(self):
        paths = self.file_list.get_file_paths()
        has_files = len(paths) > 0

        # 合并按钮
        self.btn_merge.setEnabled(has_files)
        if has_files:
            categories = set(get_file_category(p) for p in paths)
            if categories == {"pdf"}:
                self.btn_merge.setText("🔀 合并 PDF 文件")
            elif categories == {"image"}:
                self.btn_merge.setText("🖼️ 图片 → 合并 PDF")
            elif categories == {"word"}:
                self.btn_merge.setText("📝 Word → 合并 PDF")
            elif len(categories) > 1:
                self.btn_merge.setText("🔀 混合文件 → 统一 PDF")
            else:
                self.btn_merge.setText("🔀 合并为 PDF")

        # 图片 → PDF
        images = filter_by_category(paths, "image")
        self.btn_images_pdf.setEnabled(len(images) > 0)
        if len(images) > 0:
            self.btn_images_pdf.setText(f"🖼️ 选中图片 ({len(images)}张) → PDF")

        # Word → PDF
        words = filter_by_category(paths, "word")
        self.btn_word_pdf.setEnabled(len(words) > 0)
        if len(words) > 0:
            self.btn_word_pdf.setText(f"📝 选中 Word ({len(words)}个) → 合并 PDF")

    # ── 输出路径 ────────────────────────────────────

    def _get_output_path(self, suffix: str = "output.pdf") -> Optional[Path]:
        """获取/生成输出路径。返回 None 表示用户取消。"""
        current = self.output_path_edit.text().strip()
        if current and not current.endswith(suffix):
            current = str(Path(current).parent / suffix)

        if current and Path(current).parent.exists():
            path, _ = QFileDialog.getSaveFileName(
                self, "保存输出文件", current, "PDF 文件 (*.pdf)")
        else:
            default = str(Path.home() / "Desktop" / suffix)
            path, _ = QFileDialog.getSaveFileName(
                self, "保存输出文件", default, "PDF 文件 (*.pdf)")

        if path:
            self.output_path_edit.setText(path)
            self._settings.setValue("output_dir", str(Path(path).parent))
            return Path(path)
        return None

    # ── Worker 管理 ─────────────────────────────────

    def _run_worker(self, func, *args, **kwargs):
        """启动后台 worker。"""
        if self._worker and self._worker.isRunning():
            return

        self._worker = BaseWorker(func, *args, **kwargs)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)

        self._set_busy(True)
        self._worker.start()

    def _set_busy(self, busy: bool):
        """切换忙碌/空闲状态。"""
        self.progress_bar.setVisible(busy)
        self.btn_cancel.setVisible(busy)
        self.file_list.setEnabled(not busy)
        self.btn_merge.setEnabled(not busy)
        self.btn_images_pdf.setEnabled(not busy)
        self.btn_word_pdf.setEnabled(not busy)
        self.btn_split.setEnabled(not busy)
        self.btn_compress.setEnabled(not busy)
        self.btn_watermark.setEnabled(not busy)
        self.btn_encrypt.setEnabled(not busy)
        self.btn_decrypt.setEnabled(not busy)
        self.btn_rotate.setEnabled(not busy)
        self.btn_info.setEnabled(not busy)
        if not busy:
            self._update_button_states()

    def _on_progress(self, msg: str, pct: int):
        self.status_label.setText(msg)
        self.progress_bar.setValue(pct)

    def _on_finished(self, result):
        self._set_busy(False)
        self.status_label.setText("✅ 完成")
        self.progress_bar.setValue(100)

        if isinstance(result, dict):
            # 合并结果
            if "failed" in result and result["failed"]:
                failed_list = "\n".join(
                    f"• {f['path']}: {f['reason']}" for f in result["failed"])
                QMessageBox.warning(
                    self, "部分失败",
                    f"成功转换 {result['converted']}/{result['total_files']} 个文件。\n\n"
                    f"以下文件未能转换:\n{failed_list}")
            else:
                QMessageBox.information(
                    self, "完成",
                    f"已成功处理 {result.get('converted', result.get('total_files', 0))} 个文件。\n"
                    f"输出: {result.get('output', '')}")
        elif isinstance(result, dict) and "ratio" in result:
            QMessageBox.information(
                self, "压缩完成",
                f"原始大小: {format_bytes(result['before_bytes'])}\n"
                f"压缩后: {format_bytes(result['after_bytes'])}\n"
                f"减小: {result['ratio']:.1f}%")
        elif isinstance(result, int):
            QMessageBox.information(self, "完成", f"已成功处理，共 {result} 项。")
        elif isinstance(result, list):
            QMessageBox.information(self, "完成", f"已生成 {len(result)} 个文件。")

    def _on_error(self, msg: str):
        self._set_busy(False)
        self.status_label.setText("❌ 错误")
        QMessageBox.critical(self, "操作失败", msg)

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status_label.setText("⏹️ 已取消")

    # ── 操作入口 ────────────────────────────────────

    def _pick_input_file(self) -> Optional[Path]:
        """选择一个输入 PDF 文件。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)")
        return Path(path) if path else None

    def _on_merge_clicked(self):
        paths = self.file_list.get_file_paths()
        if not paths:
            QMessageBox.warning(self, "提示", "请先添加文件到列表")
            return

        out = self._get_output_path("merged.pdf")
        if not out:
            return

        categories = set(get_file_category(p) for p in paths)
        if categories == {"pdf"}:
            self._run_worker(PdfOperator.merge, paths, out)
        else:
            self._run_worker(merge_mixed_files, paths, out)

    def _on_split_clicked(self):
        input_path = self._pick_input_file()
        if not input_path:
            return

        dlg = SplitRangeDialog(self)
        if not dlg.exec():
            return

        out_dir = Path(self._settings.value(
            "output_dir", str(Path.home() / "Desktop")))
        out_dir = Path(QFileDialog.getExistingDirectory(
            self, "选择输出目录", str(out_dir)))
        if not out_dir:
            return

        mode = dlg.get_mode()
        if mode == 0:
            # 每页
            self._run_worker(PdfOperator.split, input_path, out_dir, None)
        elif mode == 1:
            # 每 N 页
            info = PdfOperator.get_info(input_path)
            total = info["pages"]
            n = dlg.get_n_pages()
            ranges = []
            for start in range(1, total + 1, n):
                end = min(start + n - 1, total)
                ranges.append((start, end))
            self._run_worker(PdfOperator.split, input_path, out_dir, ranges)
        else:
            # 自定义
            self._run_worker(PdfOperator.split, input_path, out_dir, dlg.get_ranges())

    def _on_compress_clicked(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        dlg = CompressDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{input_path.stem}_compressed.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.compress, input_path, out)

    def _on_watermark_clicked(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        dlg = WatermarkDialog(self)
        if not dlg.exec():
            return
        result = dlg.get_result()
        out = self._get_output_path(f"{input_path.stem}_watermarked.pdf")
        if not out:
            return

        if result["type"] == "text":
            self._run_worker(
                PdfOperator.text_watermark, input_path, out,
                result["text"], result["font_size"],
                result["opacity"], result["rotation"])
        else:
            self._run_worker(
                PdfOperator.watermark, input_path,
                result["watermark_path"], out)

    def _on_encrypt_clicked(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        dlg = EncryptDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{input_path.stem}_encrypted.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.encrypt, input_path, out, dlg.get_password())

    def _on_decrypt_clicked(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        dlg = DecryptDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{input_path.stem}_decrypted.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.decrypt, input_path, out, dlg.get_password())

    def _on_rotate_clicked(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        dlg = RotateDialog(self)
        if not dlg.exec():
            return
        out = self._get_output_path(f"{input_path.stem}_rotated.pdf")
        if not out:
            return
        self._run_worker(
            PdfOperator.rotate, input_path, out,
            dlg.get_angle(), dlg.get_pages())

    def _on_info_clicked(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        info = PdfOperator.get_info(input_path)
        dlg = InfoDialog(info, self)
        dlg.exec()

    def _on_extract_text(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, "保存文本文件", f"{input_path.stem}.txt",
            "文本文件 (*.txt)")
        if not out:
            return
        self._run_worker(PdfOperator.extract_text, input_path, Path(out))

    def _on_extract_images(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not out_dir:
            return
        self._run_worker(PdfOperator.extract_images, input_path, Path(out_dir))

    def _on_pdf_to_images(self):
        input_path = self._pick_input_file()
        if not input_path:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not out_dir:
            return
        dpi = int(self._settings.value("dpi", 200))
        self._run_worker(PdfOperator.to_images, input_path, Path(out_dir), dpi)

    def _on_single_images_to_pdf(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp);;所有文件 (*)")
        if not files:
            return
        out = self._get_output_path("images.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.from_images, [Path(f) for f in files], out)

    def _on_images_to_pdf(self):
        images = filter_by_category(self.file_list.get_file_paths(), "image")
        if not images:
            QMessageBox.warning(self, "提示", "列表中未发现图片文件")
            return
        out = self._get_output_path("images.pdf")
        if not out:
            return
        self._run_worker(PdfOperator.from_images, images, out)

    def _on_word_to_pdf(self):
        words = filter_by_category(self.file_list.get_file_paths(), "word")
        if not words:
            QMessageBox.warning(self, "提示", "列表中未发现 Word 文档")
            return
        out = self._get_output_path("word_merged.pdf")
        if not out:
            return
        self._run_worker(merge_mixed_files, words, out)

    def _on_add_files_dialog(self):
        self.file_list._on_add_files()

    def _on_browse_output(self):
        current = self.output_path_edit.text().strip()
        if not current:
            current = str(Path.home() / "Desktop" / "output.pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, "选择输出位置", current, "PDF 文件 (*.pdf)")
        if path:
            self.output_path_edit.setText(path)

    def _on_about(self):
        QMessageBox.about(
            self, "关于 PDFeverything",
            "PDFeverything v1.0\n\n"
            "一站式 PDF 处理桌面应用\n"
            "支持合并、拆分、格式转换、混合文件合并等\n\n"
            "技术栈: Python + PyQt6 + PyMuPDF\n"
            "© 2026",
        )
