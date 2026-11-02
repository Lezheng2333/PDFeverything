"""Draggable file list widget with toolbar and context menu."""

from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRectF
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor, QPainter, QFont, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QStyledItemDelegate,
    QStyle,
    QToolButton,
)

from core.utils import format_bytes, get_file_category
from .i18n import tr
from .theme import colors
from .workspace import clean_title


def _colors():
    from .pdf_reader_widget import _DARK
    return colors(_DARK)


class FileQueue(QListWidget):
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count():
            return
        c = _colors(); p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.viewport().width(), self.viewport().height()
        cy = h // 2 - 42
        p.setPen(QPen(QColor(c["border"]), 1, Qt.PenStyle.DashLine))
        p.setBrush(QColor(c["tint"]))
        p.drawRoundedRect(QRectF(w / 2 - 32, cy - 48, 64, 72), 12, 12)
        p.setPen(QColor(c["accent"])); p.setFont(QFont("Arial", 25))
        p.drawText(QRectF(w / 2 - 32, cy - 44, 64, 64), Qt.AlignmentFlag.AlignCenter, "+")
        p.setPen(QColor(c["text"])); f = self.font(); f.setPixelSize(17); f.setBold(True); p.setFont(f)
        p.drawText(QRectF(10, cy + 46, w - 20, 28), Qt.AlignmentFlag.AlignCenter, tr("studio_empty_title"))
        f.setPixelSize(12); f.setBold(False); p.setFont(f); p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(10, cy + 82, w - 20, 24), Qt.AlignmentFlag.AlignCenter, tr("studio_empty_desc"))
        f.setPixelSize(10); p.setFont(f)
        p.drawText(QRectF(10, cy + 118, w - 20, 24), Qt.AlignmentFlag.AlignCenter, tr("studio_formats"))
        p.end()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)


class FileRowDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(200, 74)

    def paint(self, painter, option, index):
        path = index.data(Qt.ItemDataRole.UserRole)
        if not path:
            return super().paint(painter, option, index)
        c = _colors(); p = painter; p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect.adjusted(2, 3, -2, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(c["tint"] if selected else c["hover"] if hover else c["surface"]))
        p.drawRoundedRect(QRectF(r), 10, 10)
        cat = get_file_category(path)
        ink = {"pdf": "#a96250", "word": "#4f78a0", "excel": "#498464",
               "powerpoint": "#b17c44", "image": "#8b6d9f"}.get(cat, "#728176")
        badge = QColor(ink); badge.setAlpha(22)
        p.setBrush(badge); p.drawRoundedRect(QRectF(r.x() + 12, r.y() + 13, 42, 42), 9, 9)
        p.setPen(QColor(ink)); f = option.font; f.setPixelSize(10); f.setBold(True); p.setFont(f)
        p.drawText(QRectF(r.x() + 12, r.y() + 13, 42, 42), Qt.AlignmentFlag.AlignCenter, path.suffix[1:].upper()[:4])
        f.setPixelSize(13); p.setFont(f); p.setPen(QColor(c["text"]))
        text_rect = r.adjusted(67, 10, -38, -32)
        name = p.fontMetrics().elidedText(path.name, Qt.TextElideMode.ElideMiddle, max(20, text_rect.width()))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, name)
        f.setPixelSize(11); f.setBold(False); p.setFont(f); p.setPen(QColor(c["muted"]))
        size = index.data(Qt.ItemDataRole.UserRole + 1) or 0
        pages = index.data(Qt.ItemDataRole.UserRole + 2)
        meta = format_bytes(size) + (f"  ·  {pages}p" if pages else "")
        p.drawText(r.adjusted(67, 36, -35, -8), Qt.AlignmentFlag.AlignVCenter, meta)
        p.drawText(r.adjusted(0, 0, -13, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{index.row() + 1:02d}")
        p.restore()


def _pdf_page_count(path: Path):
    """Page count for a .pdf, or None when it cannot be read.

    Reading this eagerly for every dropped file would open the whole document, so
    the count is only refreshed for newly added PDFs and cached on the item — the
    summary line is the one place a user expects a total page count."""
    if path.suffix.lower() != ".pdf":
        return None
    try:
        import fitz
        doc = fitz.open(path)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        return None

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
        self._summary = None

        # Toolbar
        toolbar = QHBoxLayout()
        btn_style = "QPushButton { padding: 4px 10px; }"

        self.btn_add = QPushButton(tr("fl_btn_add"))
        self.btn_add.setObjectName("primary")
        self.btn_add.clicked.connect(self._on_add_files)

        self.btn_remove = QPushButton(tr("fl_btn_remove"))
        self.btn_remove.setStyleSheet(btn_style)
        self.btn_remove.clicked.connect(self._on_remove)

        self.btn_clear = QPushButton(tr("fl_btn_clear"))
        self.btn_clear.setStyleSheet(btn_style)
        self.btn_clear.clicked.connect(self._on_clear)

        self.btn_up = QPushButton("↑")
        self.btn_up.setFixedWidth(36)
        self.btn_up.setToolTip(tr("fl_btn_up_tip"))
        self.btn_up.clicked.connect(self._on_move_up)

        self.btn_down = QPushButton("↓")
        self.btn_down.setFixedWidth(36)
        self.btn_down.setToolTip(tr("fl_btn_down_tip"))
        self.btn_down.clicked.connect(self._on_move_down)

        toolbar.addWidget(self.btn_add)
        self.btn_more = QToolButton(); self.btn_more.setText("▾")
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_more.setStyleSheet("QToolButton::menu-indicator{image:none;}")
        menu = QMenu(self.btn_more)
        self.act_folder = menu.addAction(tr("queue_folder"), self._on_add_folder)
        self.act_sort = menu.addAction(tr("queue_sort"), self.sort_by_name)
        self.btn_more.setMenu(menu); toolbar.addWidget(self.btn_more)
        toolbar.addWidget(self.btn_remove)
        toolbar.addWidget(self.btn_clear)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_up)
        toolbar.addWidget(self.btn_down)
        layout.addLayout(toolbar)

        # List
        self.list_widget = FileQueue()
        self.list_widget.setItemDelegate(FileRowDelegate(self.list_widget))
        self.list_widget.setMouseTracking(True)
        self.list_widget.setMinimumHeight(100)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self.list_widget.itemSelectionChanged.connect(self._update_selection)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.dragEnterEvent = self._drag_enter
        self.list_widget.dropEvent = self._drop_event

        layout.addWidget(self.list_widget, 1)

        # Summary line: what is actually in the list, at a glance.
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("file_list_summary")
        self.summary_label.setStyleSheet("font-size:11px;padding:2px 2px;")
        layout.addWidget(self.summary_label)
        self._summary = self.summary_label
        self._update_summary()
        self._update_selection()

    def retranslate_ui(self):
        """Refresh all UI strings after language change."""
        self.act_folder.setText(tr("queue_folder")); self.act_sort.setText(tr("queue_sort"))
        self.btn_add.setText("+  " + clean_title(tr("fl_btn_add")))
        self.btn_remove.setText(clean_title(tr("fl_btn_remove")))
        self.btn_clear.setText(clean_title(tr("fl_btn_clear")))
        self.btn_up.setToolTip(tr("fl_btn_up_tip"))
        self.btn_down.setToolTip(tr("fl_btn_down_tip"))
        self._update_summary()
        self.list_widget.viewport().update()

    # ── Public API ────────────────────────────────────

    MAX_FILES = 200          # hard limit
    MAX_SIZE_BYTES = 500 * 1024 * 1024  # 500MB per file

    def add_files(self, paths: List[Path]) -> None:
        existing = set(self.get_file_paths())
        added, skipped_unsupported, skipped_large, skipped_empty, skipped_full = 0, 0, 0, 0, 0
        remaining = self.MAX_FILES - self.count()

        for p in paths:
            p = Path(p).expanduser().resolve()
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
                # Keep counting instead of breaking, so the report tells the user
                # exactly how many files were dropped.
                skipped_full += 1
                continue

            existing.add(p)
            cat = get_file_category(p)
            icon = FILE_ICONS.get(cat, "\U0001f4ce")
            size = format_bytes(fsize)
            pages = _pdf_page_count(p)
            label = f"{icon}  {p.name}  ({size}"
            label += f", {pages}p)" if pages else ")"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setData(Qt.ItemDataRole.UserRole + 1, fsize)
            item.setData(Qt.ItemDataRole.UserRole + 2, pages)
            tip = f"{p}\n{size}"
            if pages:
                tip += tr("fl_tip_pages", count=pages)
            item.setToolTip(tip)
            self.list_widget.addItem(item)
            added += 1
            remaining -= 1

        if added > 0:
            self._update_summary()
            self.files_changed.emit()

        total_skipped = (skipped_unsupported + skipped_large
                         + skipped_empty + skipped_full)
        if total_skipped:
            detail = tr("fl_msg_skip_detail", unsupported=skipped_unsupported,
                        large=skipped_large, empty=skipped_empty, full=skipped_full)
            QMessageBox.information(
                self, tr("fl_msg_skip_title"),
                tr("fl_msg_skip_body", count=total_skipped) + "\n" + detail)

    def _update_summary(self):
        """Show file count, total size and total pages under the list."""
        self._update_selection()
        if self._summary is None:
            return
        count = self.count()
        if count == 0:
            self._summary.setText(tr("fl_summary_empty"))
            return
        total_size = 0
        total_pages = 0
        cats = {}
        for i in range(count):
            item = self.list_widget.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            size = item.data(Qt.ItemDataRole.UserRole + 1)
            pages = item.data(Qt.ItemDataRole.UserRole + 2)
            if size is None and path:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
            total_size += size or 0
            total_pages += pages or 0
            if path:
                cat = get_file_category(path)
                cats[cat] = cats.get(cat, 0) + 1
        kind = max(cats.items(), key=lambda kv: kv[1])[0] if cats else "unknown"
        self._summary.setText(tr(
            "fl_summary", count=count, size=format_bytes(total_size),
            pages=total_pages, kind=tr(f"kind_{kind}")))

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
        self._update_summary()
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
        self._update_summary()
        self.files_changed.emit()

    def _on_clear(self):
        self.clear()

    def total_pages(self) -> int:
        """Total known page count across the listed PDFs (0 when unknown)."""
        total = 0
        for i in range(self.count()):
            pages = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole + 2)
            total += pages or 0
        return total

    def _move_selected(self, direction):
        selected = self.list_widget.selectedItems()
        if not selected: return
        rows = range(self.count()) if direction < 0 else range(self.count() - 1, -1, -1)
        self.list_widget.blockSignals(True)
        for row in rows:
            item = self.list_widget.item(row); target = row + direction
            if item in selected and 0 <= target < self.count() and self.list_widget.item(target) not in selected:
                self.list_widget.takeItem(row); self.list_widget.insertItem(target, item)
        for item in selected: item.setSelected(True)
        self.list_widget.blockSignals(False)
        self._update_selection(); self.files_changed.emit()

    def _on_move_up(self):
        self._move_selected(-1)

    def _on_move_down(self):
        self._move_selected(1)

    @staticmethod
    def _name_key(path):
        import re
        return [int(token) if token.isdigit() else token.casefold()
                for token in re.split(r"(\d+)", path.name)]

    def sort_by_name(self):
        selected_paths = {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
        }
        self.list_widget.blockSignals(True)
        items = [self.list_widget.takeItem(0) for _ in range(self.count())]
        for item in sorted(items, key=lambda i: self._name_key(i.data(Qt.ItemDataRole.UserRole))):
            self.list_widget.addItem(item)
            if item.data(Qt.ItemDataRole.UserRole) in selected_paths:
                item.setSelected(True)
        self.list_widget.blockSignals(False)
        self._update_selection()
        self._update_summary(); self.files_changed.emit()

    def add_folder(self, folder):
        paths = sorted((p for p in Path(folder).iterdir() if p.is_file()
                        and p.suffix.lower() in SUPPORTED_EXTS), key=self._name_key)
        self.add_files(paths)

    def _on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("queue_folder"))
        if folder: self.add_folder(folder)

    def _on_rows_moved(self, *_args):
        self._update_summary()
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
        if 0 <= row < count - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(count - 1, item)
            self.list_widget.setCurrentRow(count - 1)
            self.files_changed.emit()

    def _drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            QListWidget.dragEnterEvent(self.list_widget, event)

    def _drop_event(self, event: QDropEvent):
        if not event.mimeData().hasUrls():
            QListWidget.dropEvent(self.list_widget, event)
            return
        paths = []
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.exists():
                paths.append(p)
        if paths:
            self.add_files(paths)
        event.acceptProposedAction()

    def _update_selection(self):
        row = self.list_widget.currentRow()
        self.btn_remove.setEnabled(bool(self.list_widget.selectedItems()))
        self.btn_clear.setEnabled(self.count() > 0)
        self.btn_up.setEnabled(row > 0)
        self.btn_down.setEnabled(0 <= row < self.count() - 1)
