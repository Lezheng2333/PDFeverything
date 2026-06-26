"""文件列表组件 — 支持拖拽添加、内部排序、右键菜单。"""

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

# 文件类型 → emoji 图标映射
FILE_ICONS = {
    "pdf": "📄",
    "image": "🖼️",
    "word": "📝",
    "powerpoint": "📊",
    "excel": "📈",
    "text": "📃",
    "unknown": "📎",
}

# 支持的文件扩展名
SUPPORTED_EXTS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp",
    ".docx", ".doc", ".rtf",
    ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv",
    ".txt", ".md", ".log", ".py", ".json", ".xml", ".html", ".htm",
    ".yaml", ".yml", ".ini", ".cfg", ".sh", ".bat", ".ps1",
}


class FileListWidget(QWidget):
    """拖拽式文件列表，内嵌工具栏。"""

    files_changed = pyqtSignal()  # 文件列表变动时发射

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        btn_style = "QPushButton { padding: 4px 10px; }"

        self.btn_add = QPushButton("📂 添加文件")
        self.btn_add.setStyleSheet(btn_style)
        self.btn_add.clicked.connect(self._on_add_files)

        self.btn_remove = QPushButton("🗑️ 移除")
        self.btn_remove.setStyleSheet(btn_style)
        self.btn_remove.clicked.connect(self._on_remove)

        self.btn_clear = QPushButton("✖️ 清空")
        self.btn_clear.setStyleSheet(btn_style)
        self.btn_clear.clicked.connect(self._on_clear)

        self.btn_up = QPushButton("⬆")
        self.btn_up.setFixedWidth(36)
        self.btn_up.setToolTip("上移")
        self.btn_up.clicked.connect(self._on_move_up)

        self.btn_down = QPushButton("⬇")
        self.btn_down.setFixedWidth(36)
        self.btn_down.setToolTip("下移")
        self.btn_down.clicked.connect(self._on_move_down)

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_remove)
        toolbar.addWidget(self.btn_clear)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_up)
        toolbar.addWidget(self.btn_down)
        layout.addLayout(toolbar)

        # ── 列表 ──
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.model().rowsMoved.connect(lambda *a: self.files_changed.emit())

        # 启用外部拖入
        self.list_widget.setAcceptDrops(True)
        self.list_widget.dragEnterEvent = self._drag_enter
        self.list_widget.dropEvent = self._drop_event

        layout.addWidget(self.list_widget)

    # ── 公共接口 ─────────────────────────────────────

    def add_files(self, paths: List[Path]) -> None:
        """向列表添加文件（去重，仅支持的类型）。"""
        existing = set(self.get_file_paths())
        added = 0
        skipped_unsupported = 0
        for p in paths:
            # 跳过文件夹
            if p.is_dir():
                continue
            # 检查扩展名
            if p.suffix.lower() not in SUPPORTED_EXTS:
                skipped_unsupported += 1
                continue
            if p not in existing:
                existing.add(p)
                cat = get_file_category(p)
                icon = FILE_ICONS.get(cat, "📎")
                size = format_bytes(p.stat().st_size)
                item = QListWidgetItem(f"{icon}  {p.name}  ({size})")
                item.setData(Qt.ItemDataRole.UserRole, p)
                item.setToolTip(str(p))
                self.list_widget.addItem(item)
                added += 1

        if added > 0:
            self.files_changed.emit()

        if skipped_unsupported > 0:
            QMessageBox.information(
                self, "提示",
                f"已跳过 {skipped_unsupported} 个不支持的文件格式。\n"
                f"支持格式: PDF, 图片, Word, PPT, Excel, 文本文件",
            )

    def get_file_paths(self) -> List[Path]:
        """返回当前列表中的所有文件路径（按列表顺序）。"""
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

    # ── 槽 ───────────────────────────────────────────

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            "所有支持的文件 (*.pdf *.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp "
            "*.docx *.doc *.rtf *.pptx *.ppt *.xlsx *.xls *.csv "
            "*.txt *.md *.log *.py *.json *.xml *.html *.yaml *.ini *.sh);;"
            "所有文件 (*)",
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
        remove_action = QAction("🗑️ 移除", self)
        remove_action.triggered.connect(self._on_remove)
        menu.addAction(remove_action)

        top_action = QAction("⬆ 移到最前", self)
        top_action.triggered.connect(self._move_to_top)
        menu.addAction(top_action)

        bottom_action = QAction("⬇ 移到最后", self)
        bottom_action.triggered.connect(self._move_to_bottom)
        menu.addAction(bottom_action)

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

    # ── 外部拖入 ─────────────────────────────────────

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
