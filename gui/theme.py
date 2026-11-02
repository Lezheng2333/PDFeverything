"""The Studio design system. Native Qt widgets, no runtime assets or web views."""

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPalette


def colors(dark=False):
    return ({"bg": "#101c17", "surface": "#192a22", "text": "#e7f0e8",
             "muted": "#a1b4a7", "border": "#344b3d", "accent": "#b9dda8",
             "tint": "#263d2e", "on_accent": "#173323", "hover": "#22392c"}
            if dark else
            {"bg": "#f3f5ef", "surface": "#ffffff", "text": "#21372c",
             "muted": "#728176", "border": "#dde5da", "accent": "#286344",
             "tint": "#eaf2e5", "on_accent": "#ffffff", "hover": "#f0f5ec"})


def file_icon(label="PDF", color="#286344", size=40):
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    pix.setDevicePixelRatio(2)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QColor(color); bg.setAlpha(24)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(bg)
    p.drawRoundedRect(QRectF(0, 0, size, size), 10, 10)
    p.setPen(QColor(color))
    p.setFont(QFont("Arial", max(8, size // 4), QFont.Weight.Bold))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, label)
    p.end()
    return QIcon(pix)


def stylesheet(dark=False):
    c = colors(dark)
    return f"""
    QWidget {{ color:{c['text']}; font-family:'SF Pro Text','PingFang SC','Microsoft YaHei','Arial'; font-size:13px; }}
    QMainWindow, QDialog {{ background:{c['bg']}; }}
    QWidget#app_central, QWidget#workspace, QWidget#tool_library {{ background:{c['bg']}; }}
    QLabel {{ background:transparent; }}
    QLabel#brand {{ font-size:20px; font-weight:700; letter-spacing:-0.7px; }}
    QLabel#brand_mark {{ background:{c['accent']}; color:{c['on_accent']}; border-radius:12px; font-size:22px; font-weight:700; }}
    QLabel#edition {{ color:{c['muted']}; font-size:10px; letter-spacing:2px; }}
    QLabel#muted, QLabel#file_list_summary {{ color:{c['muted']}; font-size:12px; }}
    QLabel#section_title {{ font-size:19px; font-weight:600; }}
    QLabel#eyebrow {{ color:{c['accent']}; font-size:10px; font-weight:700; letter-spacing:2px; }}
    QLabel#metric {{ font-size:28px; font-weight:600; }}
    QWidget#card, QGroupBox {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:14px; }}
    QGroupBox {{ margin-top:12px; padding:20px 14px 14px; font-weight:600; }}
    QGroupBox::title {{ subcontrol-origin:margin; left:18px; padding:0 5px; color:{c['muted']}; }}
    QGroupBox#merge_card {{ margin:0; padding:0; }}
    QGroupBox#quick_tools {{ margin-top:8px; padding:0; }}
    QPushButton, QToolButton {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; padding:8px 13px; font-weight:500; }}
    QPushButton:hover, QToolButton:hover {{ background:{c['hover']}; border-color:{c['accent']}; }}
    QPushButton:pressed {{ background:{c['tint']}; }}
    QPushButton:checked, QToolButton:checked {{ background:{c['tint']}; color:{c['accent']}; border-color:{c['accent']}; }}
    QPushButton:disabled {{ color:{c['muted']}; background:{c['bg']}; border-color:{c['border']}; }}
    QPushButton:focus, QToolButton:focus {{ border:1px solid {c['accent']}; }}
    QPushButton#primary {{ background:{c['accent']}; color:{c['on_accent']}; border:none; font-weight:600; padding:12px 18px; }}
    QPushButton#primary:hover {{ background:{'#c9e9ba' if dark else '#1d5135'}; }}
    QPushButton#primary:disabled {{ background:{c['border']}; color:{c['muted']}; }}
    QPushButton#quiet {{ background:transparent; border:none; color:{c['muted']}; }}
    QPushButton#quiet:hover {{ background:{c['tint']}; color:{c['accent']}; }}
    QPushButton#command {{ background:{c['surface']}; color:{c['muted']}; text-align:left; padding:10px 16px; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; padding:8px 10px; selection-background-color:{c['accent']}; }}
    QLineEdit:focus, QTextEdit:focus {{ border-color:{c['accent']}; }}
    QTabWidget::pane {{ border:none; background:transparent; }}
    QTabBar::tab {{ background:transparent; color:{c['muted']}; padding:12px 23px; margin:0 8px 8px 0; border-radius:9px; font-size:13px; }}
    QTabBar::tab:selected {{ background:{c['accent']}; color:{c['on_accent']}; font-weight:600; }}
    QTabBar::tab:hover:!selected {{ background:{c['tint']}; }}
    QScrollArea {{ border:none; background:transparent; }}
    QScrollBar:vertical {{ background:transparent; width:7px; margin:3px; }}
    QScrollBar::handle:vertical {{ background:{c['border']}; border-radius:3px; min-height:30px; }}
    QScrollBar:horizontal {{ background:transparent; height:7px; }}
    QScrollBar::handle:horizontal {{ background:{c['border']}; border-radius:3px; min-width:30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
    QListWidget, QTreeWidget {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:12px; outline:none; padding:6px; }}
    QListWidget::item, QTreeWidget::item {{ padding:8px; border-radius:7px; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{ background:{c['tint']}; color:{c['accent']}; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background:{c['hover']}; }}
    QSplitter::handle {{ background:transparent; width:16px; }}
    QProgressBar {{ background:{c['border']}; border:none; border-radius:3px; height:6px; max-height:6px; color:transparent; }}
    QProgressBar::chunk {{ background:{c['accent']}; border-radius:3px; }}
    QMenuBar {{ background:{c['bg']}; }}
    QMenu {{ background:{c['surface']}; border:1px solid {c['border']}; padding:6px; }}
    QMenu::item {{ padding:7px 24px; border-radius:4px; }}
    QMenu::item:selected {{ background:{c['tint']}; color:{c['accent']}; }}
    QToolTip {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; padding:5px 9px; }}
    QWidget#reader_toolbar, QWidget#edit_toolbar, QWidget#reader_sidebar {{ background:{c['surface']}; border:1px solid {c['border']}; }}
    QWidget#reader_toolbar QPushButton, QWidget#edit_toolbar QPushButton {{ padding:6px 9px; }}
    QWidget#reader_sidebar QTreeWidget, QWidget#reader_sidebar QListWidget {{ border:none; }}
    QWidget#search_bar {{ background:{c['surface']}; }}
    QPushButton#tool_card {{ text-align:left; padding:16px; font-size:14px; font-weight:600; border-radius:12px; }}
    QCheckBox {{ spacing:7px; }}
    QDialogButtonBox QPushButton {{ min-width:70px; }}
    """


def apply_theme(app, dark=False):
    c = colors(dark)
    palette = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "bg"),
                      (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.Base, "surface"),
                      (QPalette.ColorRole.AlternateBase, "bg"),
                      (QPalette.ColorRole.Text, "text"),
                      (QPalette.ColorRole.Button, "surface"),
                      (QPalette.ColorRole.ButtonText, "text"),
                      (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.HighlightedText, "on_accent")):
        palette.setColor(role, QColor(c[key]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(dark))
