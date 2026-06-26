"""Draggable file list widget with toolbar and context menu."""

from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.utils import format_bytes, get_file_category
from .i18n import tr

FILE_ICONS = {
    "pdf": "\U0001f4c4", "image": "\U0001f5bc", "word": "\U0001f4dd",
    "powerpoint": "\U0001f4ca", "excel": "\U0001f4c8", "text": "\U0001f4c3",
    "unknown": "\U0001f4ce",
}

SUPPORTED_EXTS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp",
    ".docx", ".doc", ".rtf",
    ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv",
    ".txt", ".md", ".log", ".py", ".json", ".xml", ".html", ".htm",
    ".yaml", ".yml", ".ini", ".cfg", ".sh", ".bat", ".ps1",
}


class FileListWidget(QWidget):
    """Drag-and-drop file list with inline toolbar."""

    files_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        btn_style = "QPushButton { padding: 4px 10px; }"

        self.btn_add = QPushButton(tr("fl_btn_add"))
        self.btn_add.setStyleSheet(btn_style)
        self.btn_add.clicked.connect(self._on_add_files)

        self.btn_remove = QPushButton(tr("fl_btn_remove"))
        self.btn_remove.setStyleSheet(btn_style)
        self.btn_remove.clicked.connect(self._on_remove)

        self.btn_clear = QPushButton(tr("fl_btn_clear"))
        self.btn_clear.setStyleSheet(btn_style)
        self.btn_clear.clicked.connect(self._on_clear)

        self.btn_up = QPushButton("⬆")
        self.btn_up.setFixedWidth(36)
        self.btn_up.setToolTip(tr("fl_btn_up_tip"))
        self.btn_up.clicked.connect(self._on_move_up)

        self.btn_down = QPushButton("⬇")
        self.btn_down.setFixedWidth(36)
        self.btn_down.setToolTip(tr("fl_btn_down_tip"))
        self.btn_down.clicked.connect(self._on_move_down)

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_remove)
        toolbar.addWidget(self.btn_clear)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_up)
        toolbar.addWidget(self.btn_down)
        layout.addLayout(toolbar)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.model().rowsMoved.connect(lambda *a: self.files_changed.emit())
        self.list_widget.setAcceptDrops(True)
        self.list_widget.dragEnterEvent = self._drag_enter
        self.list_widget.dropEvent = self._drop_event

        layout.addWidget(self.list_widget)

    def retranslate_ui(self):
        """Refresh all UI strings after language change."""
        self.btn_add.setText(tr("fl_btn_add"))
        self.btn_remove.setText(tr("fl_btn_remove"))
        self.btn_clear.setText(tr("fl_btn_clear"))
        self.btn_up.setToolTip(tr("fl_btn_up_tip"))
        self.btn_down.setToolTip(tr("fl_btn_down_tip"))

    # ── Public API ────────────────────────────────────

    MAX_FILES = 200          # hard limit
    MAX_SIZE_BYTES = 500 * 1024 * 1024  # 500MB per file

    def add_files(self, paths: List[Path]) -> None:
        existing = set(self.get_file_paths())
        added, skipped_unsupported, skipped_large, skipped_empty = 0, 0, 0, 0
        remaining = self.MAX_FILES - self.count()

        for p in paths:
            if p.is_dir():
                continue
            if p.suffix.lower() not in SUPPORTED_EXTS:
                skipped_unsupported += 1
                continue
            if p in existing:
                continue
            try:
                fsize = p.stat().st_size
            except OSError:
                continue
            if fsize == 0:
                skipped_empty += 1
                continue
            if fsize > self.MAX_SIZE_BYTES:
                skipped_large += 1
                continue
            if remaining <= 0:
                break

            existing.add(p)
            cat = get_file_category(p)
            icon = FILE_ICONS.get(cat, "\U0001f4ce")
            size = format_bytes(fsize)
            item = QListWidgetItem(f"{icon}  {p.name}  ({size})")
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(str(p))
            self.list_widget.addItem(item)
            added += 1
            remaining -= 1

        if added > 0:
            self.files_changed.emit()

        msgs = []
        if skipped_unsupported:
            msgs.append(f"{skipped_unsupported} unsupported format(s)")
        if skipped_large:
            msgs.append(f"{skipped_large} file(s) >500MB")
        if skipped_empty:
            msgs.append(f"{skipped_empty} empty file(s)")
        if remaining <= 0 and added > 0:
            msgs.append(f"List full (max {self.MAX_FILES} files)")
        if msgs:
            QMessageBox.information(
                self, tr("fl_msg_skip_title"),
                "Skipped: " + ", ".join(msgs))

    def get_file_paths(self) -> List[Path]:
        paths = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                paths.append(path)
        return paths

    def count(self) -> int:
        return self.list_widget.count()

    def clear(self) -> None:
        self.list_widget.clear()
        self.files_changed.emit()

    # ── Slots ─────────────────────────────────────────

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("fl_dialog_title"), "",
            tr("fl_dialog_filter"),
        )
        if files:
            self.add_files([Path(f) for f in files])

    def _on_remove(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self.files_changed.emit()

    def _on_clear(self):
        self.clear()

    def _on_move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)
            self.files_changed.emit()

    def _on_move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)
            self.files_changed.emit()

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction(tr("fl_menu_remove"), self._on_remove)
        menu.addAction(tr("fl_menu_top"), self._move_to_top)
        menu.addAction(tr("fl_menu_bottom"), self._move_to_bottom)
        menu.exec(self.list_widget.mapToGlobal(pos))

    def _move_to_top(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(0, item)
            self.list_widget.setCurrentRow(0)
            self.files_changed.emit()

    def _move_to_bottom(self):
        row = self.list_widget.currentRow()
        count = self.list_widget.count()
        if row < count - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(count - 1, item)
            self.list_widget.setCurrentRow(count - 1)
            self.files_changed.emit()

    def _drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def _drop_event(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.exists():
                paths.append(p)
        if paths:
            self.add_files(paths)
        event.acceptProposedAction()
