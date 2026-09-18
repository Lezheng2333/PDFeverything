"""Operation dialogs — encrypt, decrypt, watermark, rotate, compress, split, info."""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
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
)

from core.utils import format_page_ranges, parse_page_ranges

from .i18n import tr


# ── Encrypt ──────────────────────────────────────────────

class EncryptDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_encrypt_title"))
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(tr("placeholder_password"))
        form.addRow(tr("label_password"), self.password_edit)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText(tr("placeholder_confirm"))
        form.addRow(tr("label_confirm_pw"), self.confirm_edit)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _validate(self):
        pw = self.password_edit.text()
        if not pw:
            QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_pw_empty"))
            return
        if pw != self.confirm_edit.text():
            QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_pw_mismatch"))
            return
        self.accept()

    def get_password(self) -> str:
        return self.password_edit.text()


# ── Decrypt ──────────────────────────────────────────────

class DecryptDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_decrypt_title"))
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(tr("placeholder_password"))
        form.addRow(tr("label_password"), self.password_edit)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _validate(self):
        if not self.password_edit.text():
            QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_pw_empty"))
            return
        self.accept()

    def get_password(self) -> str:
        return self.password_edit.text()


# ── Watermark ────────────────────────────────────────────

class WatermarkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_watermark_title"))
        self.setMinimumWidth(400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.type_combo = QComboBox()
        self.type_combo.addItems([tr("wm_type_text"), tr("wm_type_pdf")])
        layout.addWidget(QLabel(tr("wm_type_label")))
        layout.addWidget(self.type_combo)

        # Text watermark group
        self.text_group = QGroupBox(tr("wm_group_text"))
        tf = QFormLayout(self.text_group)
        self.text_edit = QLineEdit(tr("wm_default_text"))
        tf.addRow(tr("wm_text"), self.text_edit)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 200)
        self.font_size_spin.setValue(60)
        tf.addRow(tr("wm_font_size"), self.font_size_spin)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(30)
        self.opacity_label = QLabel(tr("wm_opacity_fmt", v=30))
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(tr("wm_opacity_fmt", v=v)))
        op_layout = QHBoxLayout()
        op_layout.addWidget(self.opacity_slider)
        op_layout.addWidget(self.opacity_label)
        tf.addRow(tr("wm_opacity"), op_layout)
        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 360)
        self.rotation_spin.setValue(45)
        tf.addRow(tr("wm_rotation"), self.rotation_spin)
        layout.addWidget(self.text_group)

        # PDF watermark group
        self.pdf_group = QGroupBox(tr("wm_group_pdf"))
        pf = QHBoxLayout(self.pdf_group)
        self.wm_path_edit = QLineEdit()
        self.wm_path_edit.setPlaceholderText(tr("wm_placeholder_pdf"))
        pf.addWidget(self.wm_path_edit)
        self.browse_btn = QPushButton(tr("btn_browse"))
        self.browse_btn.clicked.connect(self._browse_watermark)
        pf.addWidget(self.browse_btn)
        self.pdf_group.setVisible(False)
        layout.addWidget(self.pdf_group)

        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _on_type_changed(self, idx):
        self.text_group.setVisible(idx == 0)
        self.pdf_group.setVisible(idx == 1)

    def _browse_watermark(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg_select_pdf"), "", tr("file_filter_pdf"))
        if path:
            self.wm_path_edit.setText(path)

    def _validate(self):
        if self.type_combo.currentIndex() == 1:
            text = self.wm_path_edit.text().strip()
            # Path("") is Path("."), which exists — validate the raw text too.
            if not text or not Path(text).is_file():
                QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_wm_pdf_invalid"))
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


# ── Rotate ──────────────────────────────────────────────

class RotateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_rotate_title"))
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.angle_combo = QComboBox()
        self.angle_combo.addItems([tr("rot_90_cw"), tr("rot_90_ccw"), tr("rot_180")])
        form.addRow(tr("rot_angle_label"), self.angle_combo)
        self.all_pages_check = QCheckBox(tr("rot_all_pages"))
        self.all_pages_check.setChecked(True)
        self.all_pages_check.toggled.connect(lambda v: self.pages_edit.setEnabled(not v))
        form.addRow("", self.all_pages_check)
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText(tr("rot_range_placeholder"))
        self.pages_edit.setEnabled(False)
        form.addRow(tr("rot_page_range"), self.pages_edit)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _validate(self):
        if not self.all_pages_check.isChecked():
            try:
                pages = self._parse_pages()
            except ValueError as e:
                QMessageBox.warning(
                    self, tr("msg_op_failed"), tr("msg_rot_range_invalid", e=str(e)))
                return
            if not pages:
                # An empty selection would make PdfOperator write a copy that is
                # identical to the input while reporting success.
                QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_rot_empty"))
                return
        self.accept()

    def get_angle(self) -> int:
        # 90 CW / 90 CCW / 180 — pypdf only rotates clockwise, so CCW is 270.
        return [90, 270, 180][self.angle_combo.currentIndex()]

    def get_pages(self) -> Optional[list]:
        """0-based page list, or None for "all pages"."""
        if self.all_pages_check.isChecked():
            return None
        return self._parse_pages()

    def _parse_pages(self) -> list:
        return parse_page_ranges(self.pages_edit.text(), one_based=True)


# ── Compress ─────────────────────────────────────────────

class CompressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_compress_title"))
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("cmp_mode_label")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("cmp_lossless"), tr("cmp_medium"), tr("cmp_max")])
        layout.addWidget(self.mode_combo)
        layout.addSpacing(10)
        info = QLabel(tr("cmp_info_text"))
        info.setWordWrap(True)
        layout.addWidget(info)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_mode(self) -> int:
        return self.mode_combo.currentIndex()


# ── Split ───────────────────────────────────────────────

class SplitRangeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_split_title"))
        self.setMinimumWidth(400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        # By-N mode
        self.n_pages_group = QGroupBox(tr("spl_group_by_n"))
        n_layout = QHBoxLayout(self.n_pages_group)
        n_layout.addWidget(QLabel(tr("spl_every")))
        self.n_spin = QSpinBox()
        self.n_spin.setRange(1, 9999)
        self.n_spin.setValue(1)
        n_layout.addWidget(self.n_spin)
        n_layout.addWidget(QLabel(tr("spl_pages_unit")))
        n_layout.addStretch()
        layout.addWidget(self.n_pages_group)
        # Custom mode
        self.custom_group = QGroupBox(tr("spl_group_custom"))
        c_layout = QVBoxLayout(self.custom_group)
        self.range_edit = QTextEdit()
        self.range_edit.setPlaceholderText(tr("spl_range_placeholder"))
        self.range_edit.setMaximumHeight(120)
        self.range_edit.textChanged.connect(self._update_range_hint)
        c_layout.addWidget(self.range_edit)
        self.range_hint = QLabel("")
        self.range_hint.setStyleSheet("color:#888;font-size:11px;")
        c_layout.addWidget(self.range_hint)
        layout.addWidget(self.custom_group)
        # Mode selector
        mode_layout = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("spl_mode_each"), tr("spl_mode_by_n"), tr("spl_mode_custom")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(QLabel(tr("spl_mode_label")))
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._on_mode_changed(0)

    def _on_mode_changed(self, idx):
        self.n_pages_group.setVisible(idx == 1)
        self.custom_group.setVisible(idx == 2)

    def _update_range_hint(self):
        """Live preview so the user sees the parsed ranges before clicking OK."""
        try:
            ranges = self._parse_ranges(self.range_edit.toPlainText())
        except ValueError:
            self.range_hint.setText("")
            return
        if ranges:
            preview = ", ".join(
                format_page_ranges(list(range(a - 1, b))) for a, b in ranges[:6])
            more = f" +{len(ranges) - 6}" if len(ranges) > 6 else ""
            self.range_hint.setText(f"{len(ranges)} → {preview}{more}")
        else:
            self.range_hint.setText("")

    def _validate(self):
        if self.mode_combo.currentIndex() == 2:
            text = self.range_edit.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_spl_empty"))
                return
            try:
                self._ranges = self._parse_ranges(text)
            except ValueError as e:
                QMessageBox.warning(
                    self, tr("msg_op_failed"), tr("msg_spl_invalid", e=str(e)))
                return
            if not self._ranges:
                QMessageBox.warning(self, tr("msg_op_failed"), tr("msg_spl_empty"))
                return
        self.accept()

    def get_mode(self) -> int:
        return self.mode_combo.currentIndex()

    def get_n_pages(self) -> int:
        return self.n_spin.value()

    def get_ranges(self) -> list:
        """1-based inclusive (start, end) tuples, one per output file.

        Parsed once during validation so a malformed line can never raise out of
        a dialog accessor."""
        return list(getattr(self, "_ranges", []))

    @staticmethod
    def _parse_ranges(text: str) -> list:
        ranges = []
        normalized = text.replace("，", ",").replace("；", "\n").replace(";", "\n")
        for line in normalized.splitlines():
            line = line.strip().strip(",")
            if not line:
                continue
            pages = parse_page_ranges(line, one_based=True)
            if not pages:
                raise ValueError(line)
            # "1-5" stays one output file; "1,3,5" becomes three.
            if len(pages) > 1 and pages == list(range(pages[0], pages[-1] + 1)):
                ranges.append((pages[0] + 1, pages[-1] + 1))
            else:
                ranges.extend((p + 1, p + 1) for p in pages)
        return ranges


# ── Info ─────────────────────────────────────────────────

class InfoDialog(QDialog):
    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_info_title"))
        self.setMinimumWidth(400)
        self._init_ui(info)

    def _init_ui(self, info: dict):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        from core.utils import format_bytes

        field_map = [
            (tr("info_label_path"), info.get("path", "")),
            (tr("info_label_pages"), str(info.get("pages", 0))),
            (tr("info_label_size"), format_bytes(int(info.get("size_bytes") or 0))),
            (tr("info_label_encrypted"), tr("info_yes") if info.get("encrypted") else tr("info_no")),
            (tr("info_label_title"), info.get("title") or tr("info_na")),
            (tr("info_label_author"), info.get("author") or tr("info_na")),
            (tr("info_label_subject"), info.get("subject") or tr("info_na")),
            (tr("info_label_creator"), info.get("creator") or tr("info_na")),
            (tr("info_label_producer"), info.get("producer") or tr("info_na")),
        ]

        for label, value in field_map:
            form.addRow(QLabel(label), QLabel(str(value)))

        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
