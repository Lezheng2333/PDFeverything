"""操作对话框 — 加密、解密、水印、旋转、压缩、拆分、信息、设置。"""

from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ── QSettings 键名 ──────────────────────────────────────────

SETTING_OUTPUT_DIR = "output_dir"
SETTING_DPI = "dpi"
SETTING_COMPRESSION = "compression_level"


# ── 加密对话框 ──────────────────────────────────────────────


class EncryptDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔒 加密 PDF")
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("输入密码")
        form.addRow("密码:", self.password_edit)

        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText("再次输入密码")
        form.addRow("确认密码:", self.confirm_edit)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _validate(self):
        pw = self.password_edit.text()
        if not pw:
            QMessageBox.warning(self, "错误", "密码不能为空")
            return
        if pw != self.confirm_edit.text():
            QMessageBox.warning(self, "错误", "两次输入的密码不一致")
            return
        self.accept()

    def get_password(self) -> str:
        return self.password_edit.text()


# ── 解密对话框 ──────────────────────────────────────────────


class DecryptDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔓 解密 PDF")
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("输入密码")
        form.addRow("密码:", self.password_edit)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _validate(self):
        if not self.password_edit.text():
            QMessageBox.warning(self, "错误", "密码不能为空")
            return
        self.accept()

    def get_password(self) -> str:
        return self.password_edit.text()


# ── 水印对话框 ──────────────────────────────────────────────


class WatermarkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("💧 添加水印")
        self.setMinimumWidth(400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 水印类型
        self.type_combo = QComboBox()
        self.type_combo.addItems(["文字水印", "PDF 水印"])
        layout.addWidget(QLabel("水印类型:"))
        layout.addWidget(self.type_combo)

        # 文字水印设置
        self.text_group = QGroupBox("文字水印设置")
        tf = QFormLayout(self.text_group)

        self.text_edit = QLineEdit("机密")
        tf.addRow("水印文字:", self.text_edit)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 200)
        self.font_size_spin.setValue(60)
        tf.addRow("字体大小:", self.font_size_spin)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(30)
        self.opacity_label = QLabel("30%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%"))
        op_layout = QHBoxLayout()
        op_layout.addWidget(self.opacity_slider)
        op_layout.addWidget(self.opacity_label)
        tf.addRow("透明度:", op_layout)

        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 360)
        self.rotation_spin.setValue(45)
        tf.addRow("旋转角度:", self.rotation_spin)

        layout.addWidget(self.text_group)

        # PDF 水印设置
        self.pdf_group = QGroupBox("PDF 水印设置")
        pf = QHBoxLayout(self.pdf_group)
        self.wm_path_edit = QLineEdit()
        self.wm_path_edit.setPlaceholderText("选择水印 PDF 文件...")
        pf.addWidget(self.wm_path_edit)
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_watermark)
        pf.addWidget(self.browse_btn)
        self.pdf_group.setVisible(False)
        layout.addWidget(self.pdf_group)

        # 切换显示
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _on_type_changed(self, idx):
        self.text_group.setVisible(idx == 0)
        self.pdf_group.setVisible(idx == 1)

    def _browse_watermark(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择水印 PDF", "", "PDF 文件 (*.pdf)")
        if path:
            self.wm_path_edit.setText(path)

    def _validate(self):
        if self.type_combo.currentIndex() == 1:
            if not Path(self.wm_path_edit.text()).exists():
                QMessageBox.warning(self, "错误", "请选择有效的水印 PDF 文件")
                return
        self.accept()

    def get_result(self) -> dict:
        if self.type_combo.currentIndex() == 0:
            return {
                "type": "text",
                "text": self.text_edit.text(),
                "font_size": self.font_size_spin.value(),
                "opacity": self.opacity_slider.value() / 100.0,
                "rotation": self.rotation_spin.value(),
            }
        else:
            return {
                "type": "pdf",
                "watermark_path": Path(self.wm_path_edit.text()),
            }


# ── 旋转对话框 ──────────────────────────────────────────────


class RotateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔄 旋转页面")
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.angle_combo = QComboBox()
        self.angle_combo.addItems(["90° 顺时针", "90° 逆时针", "180°"])
        form.addRow("旋转角度:", self.angle_combo)

        self.all_pages_check = QCheckBox("所有页面")
        self.all_pages_check.setChecked(True)
        self.all_pages_check.toggled.connect(
            lambda v: self.pages_edit.setEnabled(not v))
        form.addRow("", self.all_pages_check)

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("例: 1-5, 8, 10-12")
        self.pages_edit.setEnabled(False)
        form.addRow("页码范围:", self.pages_edit)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _validate(self):
        if not self.all_pages_check.isChecked():
            try:
                self._parse_pages()
            except ValueError as e:
                QMessageBox.warning(self, "错误", f"页码范围无效: {e}")
                return
        self.accept()

    def get_angle(self) -> int:
        return [90, 270, 180][self.angle_combo.currentIndex()]

    def get_pages(self) -> list:
        if self.all_pages_check.isChecked():
            return None
        return self._parse_pages()

    def _parse_pages(self) -> list:
        text = self.pages_edit.text().strip()
        if not text:
            return []
        result = []
        for part in text.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                result.extend(range(int(a), int(b) + 1))
            else:
                result.append(int(part))
        return sorted(set(result))


# ── 压缩设置对话框 ──────────────────────────────────────────


class CompressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🗜️ 压缩 PDF")
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("压缩模式:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "无损压缩（推荐）",
            "中等压缩",
            "最大压缩",
        ])
        layout.addWidget(self.mode_combo)

        layout.addSpacing(10)
        info = QLabel(
            "• 无损压缩: 保留原始质量，仅优化文件结构\n"
            "• 中等压缩: 轻微降低图片质量\n"
            "• 最大压缩: 会显著缩小文件但可能影响清晰度"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_mode(self) -> int:
        return self.mode_combo.currentIndex()


# ── 拆分设置对话框 ──────────────────────────────────────────


class SplitRangeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("✂️ 拆分 PDF")
        self.setMinimumWidth(400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 方式 1: 每 N 页
        self.n_pages_group = QGroupBox("按页数拆分")
        n_layout = QHBoxLayout(self.n_pages_group)
        n_layout.addWidget(QLabel("每"))
        self.n_spin = QSpinBox()
        self.n_spin.setRange(1, 9999)
        self.n_spin.setValue(1)
        n_layout.addWidget(self.n_spin)
        n_layout.addWidget(QLabel("页拆分为一个文件"))
        n_layout.addStretch()
        layout.addWidget(self.n_pages_group)

        # 方式 2: 自定义范围
        self.custom_group = QGroupBox("自定义页码范围")
        c_layout = QVBoxLayout(self.custom_group)
        self.range_edit = QTextEdit()
        self.range_edit.setPlaceholderText(
            "每行一个范围，例如:\n1-5\n6-12\n13-20"
        )
        self.range_edit.setMaximumHeight(120)
        c_layout.addWidget(self.range_edit)
        layout.addWidget(self.custom_group)

        # 模式切换
        mode_layout = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["每页拆分为一个文件", "按页数拆分", "自定义范围"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(QLabel("拆分方式:"))
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._on_mode_changed(0)

    def _on_mode_changed(self, idx):
        self.n_pages_group.setVisible(idx == 1)
        self.custom_group.setVisible(idx == 2)

    def _validate(self):
        if self.mode_combo.currentIndex() == 2:
            text = self.range_edit.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "错误", "请输入页码范围")
                return
            try:
                ranges = []
                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if "-" in line:
                        a, b = line.split("-", 1)
                        ranges.append((int(a), int(b)))
                    else:
                        v = int(line)
                        ranges.append((v, v))
                if not ranges:
                    raise ValueError("没有有效的范围")
            except ValueError as e:
                QMessageBox.warning(self, "错误", f"范围格式无效: {e}")
                return
        self.accept()

    def get_mode(self) -> int:
        """0=每页, 1=按N页, 2=自定义"""
        return self.mode_combo.currentIndex()

    def get_n_pages(self) -> int:
        return self.n_spin.value()

    def get_ranges(self) -> list:
        text = self.range_edit.toPlainText().strip()
        ranges = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "-" in line:
                a, b = line.split("-", 1)
                ranges.append((int(a), int(b)))
            else:
                v = int(line)
                ranges.append((v, v))
        return ranges


# ── 信息展示对话框 ──────────────────────────────────────────


class InfoDialog(QDialog):
    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ℹ️ PDF 信息")
        self.setMinimumWidth(400)
        self._init_ui(info)

    def _init_ui(self, info: dict):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        labels = [
            ("文件路径", info.get("path", "")),
            ("页数", str(info.get("pages", 0))),
            ("文件大小", info.get("size_bytes", 0)),
            ("是否加密", "是" if info.get("encrypted") else "否"),
            ("标题", info.get("title", "N/A")),
            ("作者", info.get("author", "N/A")),
            ("主题", info.get("subject", "N/A")),
            ("创建者", info.get("creator", "N/A")),
            ("生成工具", info.get("producer", "N/A")),
        ]

        from core.utils import format_bytes

        for label, value in labels:
            if label == "文件大小":
                value = format_bytes(int(value)) if isinstance(value, (int, float)) else value
            form.addRow(f"{label}:", QLabel(str(value)))

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
