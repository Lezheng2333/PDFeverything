"""Small, reusable Studio surfaces: hero, tool discovery and command search."""

import re

from PyQt6.QtCore import Qt, QRectF, QSize, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .i18n import tr
from .theme import colors, file_icon


def label(text, name="muted"):
    w = QLabel(text); w.setObjectName(name)
    return w


class DocumentArt(QWidget):
    """Resolution-independent artwork, painted locally by Qt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 150)
        self.setMaximumWidth(350)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = colors()
        p.translate(self.width() / 2, self.height() / 2)
        p.setPen(QPen(QColor(c["hero_muted"]), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(-128, -128, 256, 256))
        p.drawEllipse(QRectF(-95, -95, 190, 190))
        cards = [(-16, -78, -50, c["hero_muted"], "DOC", c["hero"]),
                 (12, 4, -57, c["accent"], "IMG", c["on_accent"]),
                 (0, -42, -45, c["hero_text"], "PDF", c["hero"])]
        for angle, x, y, fill, text, ink in cards:
            p.save(); p.rotate(angle); p.translate(x, y)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(fill))
            p.drawRoundedRect(QRectF(0, 0, 83, 109), 8, 8)
            p.setPen(QColor(ink)); p.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            p.drawText(QRectF(13, 14, 60, 26), text)
            line = QColor(c["hero"]); line.setAlpha(110)
            p.setPen(QPen(line, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for yy, ww in [(56, 49), (66, 49), (76, 32)]:
                p.drawLine(15, yy, 15 + ww, yy)
            p.restore()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(c["accent"]))
        p.drawEllipse(QRectF(57, 40, 36, 36))
        p.setPen(QColor(c["on_accent"])); p.setFont(QFont("Arial", 19))
        p.drawText(QRectF(57, 37, 36, 36), Qt.AlignmentFlag.AlignCenter, "↗")
        p.end()


class WorkspaceHero(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workspace_hero")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self); row.setContentsMargins(28, 8, 20, 8)
        words = QVBoxLayout(); words.setSpacing(8)
        self.overline = QLabel("D O C U M E N T   S T U D I O  /  2.0")
        self.title = QLabel(); self.title.setStyleSheet("font-size:29px;font-weight:600;")
        self.title.setWordWrap(True)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        words.addWidget(self.overline); words.addWidget(self.title); words.addWidget(self.desc)
        self.art = DocumentArt()
        row.addLayout(words, 3); row.addWidget(self.art, 2)
        self.retranslate_ui()
        self.apply_theme()

    def apply_theme(self):
        c = colors()
        self.setStyleSheet(
            f"QWidget#workspace_hero{{background:{c['hero']};border-radius:18px;}}"
            f"QWidget#workspace_hero QLabel{{color:{c['hero_text']};background:transparent;}}")
        self.overline.setStyleSheet(f"font-size:10px;color:{c['hero_muted']};")
        self.desc.setStyleSheet(f"font-size:12px;color:{c['hero_muted']};")
        self.art.update()

    def retranslate_ui(self):
        self.title.setText(tr("studio_hero"))
        self.desc.setText(tr("studio_hero_desc"))


# (translation key, menu action attribute, category, icon stamp, English/Chinese aliases)
TOOLS = [
    ("btn_merge_unified", "act_merge", "organize", "↗", "merge 合并 混合"),
    ("btn_split", "act_split", "organize", "÷", "split 拆分"),
    ("btn_rotate", "act_rotate", "organize", "↻", "rotate 旋转"),
    ("insert_btn", "act_insert", "organize", "+", "insert 插入"),
    ("pn_btn", "act_page_numbers", "organize", "01", "number 页码 页眉 页脚"),
    ("nup_btn", "act_nup", "organize", "▦", "nup 排版 打印 拼版"),
    ("tool_to_word", "act_to_word", "convert", "W", "word docx 转换"),
    ("tool_to_ppt", "act_to_ppt", "convert", "P", "powerpoint ppt 幻灯片"),
    ("tool_to_excel", "act_to_excel", "convert", "X", "excel xlsx 表格"),
    ("tool_pdf_to_images", "act_pdf_to_images", "convert", "JPG", "png jpg 图片 导出"),
    ("tool_images_to_pdf", "act_images_to_pdf", "convert", "PDF", "image 图片 转换"),
    ("tool_extract_text", "act_extract_text", "extract", "T", "text txt 文字 文本 提取"),
    ("tool_extract_images", "act_extract_images", "extract", "IMG", "extract 提取 图片"),
    ("meta_btn", "act_metadata", "extract", "i", "metadata 属性 标题 作者"),
    ("btn_compress", "act_compress", "secure", "↓", "compress 压缩 优化"),
    ("btn_watermark", "act_watermark", "secure", "≈", "watermark 水印"),
    ("btn_encrypt", "act_encrypt", "secure", "●", "encrypt 加密 密码"),
    ("btn_decrypt", "act_decrypt", "secure", "○", "decrypt 解密 密码"),
]


def clean_title(text):
    """Keep translations as the source of truth; omit legacy emoji decoration."""
    return re.sub(r"^[^\w\u4e00-\u9fff]+", "", text)


class ToolCard(QPushButton):
    def __init__(self):
        super().__init__()
        self.setObjectName("tool_card")
        row = QHBoxLayout(self); row.setContentsMargins(16, 16, 12, 16); row.setSpacing(12)
        self.badge = QLabel(); self.badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.badge)
        words = QVBoxLayout(); words.setSpacing(6)
        self.heading = QLabel(); self.heading.setStyleSheet("font-size:14px;font-weight:600;")
        self.detail = label(""); self.detail.setWordWrap(True); self.detail.setStyleSheet("font-size:11px;")
        for w in (self.heading, self.detail): w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        words.addWidget(self.heading); words.addWidget(self.detail); row.addLayout(words, 1)

    def setText(self, text):
        self.heading.setText(text.strip()); self.setAccessibleName(text.strip())

    def text(self):
        return self.heading.text()

    def setIcon(self, icon):
        self.badge.setPixmap(icon.pixmap(40, 40))


class ToolLibrary(QWidget):
    def __init__(self, window):
        super().__init__(); self.window = window; self.setObjectName("tool_library")
        self.category = "all"; self.cards = []
        root = QVBoxLayout(self); root.setContentsMargins(0, 8, 0, 0); root.setSpacing(16)
        self.title = label("", "section_title"); root.addWidget(self.title)
        self.subtitle = label(""); root.addWidget(self.subtitle)
        self.search = QLineEdit(); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_tools); root.addWidget(self.search)
        filters = QHBoxLayout(); self.filters = {}
        for category in ("all", "organize", "convert", "extract", "secure"):
            b = QPushButton(); b.setCheckable(True)
            b.clicked.connect(lambda checked=False, cat=category: self.set_category(cat))
            self.filters[category] = b; filters.addWidget(b)
        filters.addStretch(); root.addLayout(filters)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); grid = QGridLayout(content); grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12); grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        for i, tool in enumerate(TOOLS):
            key, action, category, stamp, aliases = tool
            b = ToolCard(); b.setMinimumHeight(108)
            b.setIconSize(QSize(40, 40)); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda checked=False, attr=action: getattr(window, attr).trigger())
            self.cards.append((b, tool)); grid.addWidget(b, i // 3, i % 3)
        for col in range(3): grid.setColumnStretch(col, 1)
        scroll.setWidget(content); root.addWidget(scroll, 1)
        self.empty = label(""); root.addWidget(self.empty)
        self.retranslate_ui()
        self.apply_theme()

    def apply_theme(self):
        """Repaint the tool badges when the color scheme changes."""
        accent = colors()["accent"]
        for b, (_key, _action, category, stamp, _aliases) in self.cards:
            ink = {"organize": accent, "convert": "#4774a1",
                   "extract": "#897345", "secure": "#a26756"}[category]
            b.setIcon(file_icon(stamp, ink))

    def set_category(self, category):
        self.category = category; self.filter_tools()

    def filter_tools(self, *_):
        query = self.search.text().strip().casefold(); visible = 0
        grid = self.cards[0][0].parentWidget().layout()
        for b, (key, action, category, stamp, aliases) in self.cards:
            show = (self.category in ("all", category)
                    and (not query or query in (tr(key) + " " + aliases).casefold()))
            grid.removeWidget(b); b.setVisible(show)
            if show:
                grid.addWidget(b, visible // 3, visible % 3); visible += 1
        self.empty.setVisible(visible == 0)
        for category, b in self.filters.items(): b.setChecked(category == self.category)

    def retranslate_ui(self):
        self.title.setText(tr("studio_tools_title")); self.subtitle.setText(tr("studio_tools_desc"))
        self.search.setPlaceholderText(tr("studio_search_tools")); self.empty.setText(tr("studio_no_tools"))
        for cat, b in self.filters.items(): b.setText(tr("studio_cat_" + cat))
        for b, (key, action, *_rest) in self.cards:
            b.setText(clean_title(tr(key))); b.detail.setText(tr("desc_" + action))
        self.filter_tools()


class CommandPalette(QDialog):
    def __init__(self, window):
        super().__init__(window); self.window = window
        self.setWindowTitle(tr("studio_commands")); self.resize(540, 470)
        root = QVBoxLayout(self); root.setContentsMargins(20, 20, 20, 16); root.setSpacing(12)
        root.addWidget(label(tr("studio_commands"), "section_title"))
        self.search = QLineEdit(); self.search.setPlaceholderText(tr("studio_search_tools"))
        self.search.setClearButtonEnabled(True); root.addWidget(self.search)
        self.results = QListWidget(); root.addWidget(self.results, 1)
        root.addWidget(label(tr("studio_command_hint")))
        self.search.textChanged.connect(self.filter_results)
        self.search.returnPressed.connect(self.run_current)
        self.results.itemActivated.connect(self.run_current)
        self.results.itemClicked.connect(self.run_current)
        self.filter_results(); QTimer.singleShot(0, self.search.setFocus)

    def filter_results(self, *_):
        self.results.clear(); q = self.search.text().strip().casefold()
        entries = [("reader_open_pdf", "act_open_reader", "PDF", "open read 阅读 打开"),
                   ("menu_add_files", "act_add", "+", "add 添加 导入")]
        entries += [(key, action, stamp, aliases) for key, action, _, stamp, aliases in TOOLS]
        for key, action, stamp, aliases in entries:
            if q and q not in (tr(key) + " " + aliases).casefold(): continue
            item = QListWidgetItem(file_icon(stamp), clean_title(tr(key)))
            item.setData(Qt.ItemDataRole.UserRole, action)
            item.setSizeHint(QSize(0, 42)); self.results.addItem(item)
        if self.results.count(): self.results.setCurrentRow(0)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            delta = 1 if event.key() == Qt.Key.Key_Down else -1
            self.results.setCurrentRow(max(0, min(self.results.count() - 1,
                                                self.results.currentRow() + delta)))
            return
        super().keyPressEvent(event)

    def run_current(self, *_):
        item = self.results.currentItem()
        if item is None: return
        action = getattr(self.window, item.data(Qt.ItemDataRole.UserRole))
        self.accept(); QTimer.singleShot(0, action.trigger)


class HistoryDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("history_title")); self.resize(640, 480)
        root = QVBoxLayout(self); root.setContentsMargins(20, 20, 20, 20); root.setSpacing(14)
        root.addWidget(label(tr("history_title"), "section_title"))
        self.items = QListWidget(); root.addWidget(self.items, 1)
        import json
        try: entries = json.loads(window._settings.value("studio_history", "[]"))
        except (ValueError, TypeError): entries = []
        for entry in entries:
            state = tr("history_done" if entry.get("success") else "history_failed")
            item = QListWidgetItem(f"{state}  ·  {entry['time']}\n{entry.get('output') or entry.get('error', '')}")
            item.setData(Qt.ItemDataRole.UserRole, entry); item.setSizeHint(QSize(0, 65))
            self.items.addItem(item)
        empty = label(tr("history_empty")); empty.setWordWrap(True); empty.setVisible(not entries)
        root.addWidget(empty)
        row = QHBoxLayout(); clear = QPushButton(tr("history_clear"))
        def clear_history():
            window._settings.remove("studio_history"); self.items.clear(); empty.show()
        clear.clicked.connect(clear_history); row.addWidget(clear); row.addStretch()
        open_button = QPushButton(tr("history_open")); open_button.setObjectName("primary")
        row.addWidget(open_button); root.addLayout(row)
        def open_result():
            item = self.items.currentItem()
            if item is None: return
            entry = item.data(Qt.ItemDataRole.UserRole)
            if entry.get("output"):
                from pathlib import Path
                window._last_output = Path(entry["output"]); self.accept(); window._open_last_output()
        open_button.clicked.connect(open_result); self.items.itemDoubleClicked.connect(lambda _: open_result())
