"""The Studio design system. Native Qt widgets, no runtime assets or web views."""

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPalette


# Three complete color schemes. Each one has a light and a dark variant with the
# same keys, so every surface can be switched without special-casing widgets.
PALETTES = {
    "forest": {
        "light": {"bg": "#f3f5ef", "surface": "#ffffff", "text": "#21372c",
                  "muted": "#6b7a6f", "border": "#dde5da", "accent": "#286344",
                  "tint": "#eaf2e5", "on_accent": "#ffffff", "hover": "#f0f5ec",
                  "accent_hover": "#1d5135", "hero": "#203f2e",
                  "hero_text": "#edf4e5", "hero_muted": "#bad4ac"},
        "dark": {"bg": "#101c17", "surface": "#192a22", "text": "#e7f0e8",
                 "muted": "#a1b4a7", "border": "#344b3d", "accent": "#b9dda8",
                 "tint": "#263d2e", "on_accent": "#173323", "hover": "#22392c",
                 "accent_hover": "#c9e9ba", "hero": "#203f2e",
                 "hero_text": "#edf4e5", "hero_muted": "#bad4ac"},
    },
    "cherry": {
        "light": {"bg": "#fbf6f5", "surface": "#ffffff", "text": "#3a2326",
                  "muted": "#7d666a", "border": "#ecd9da", "accent": "#a63d4a",
                  "tint": "#f9e9eb", "on_accent": "#ffffff", "hover": "#fdf1f2",
                  "accent_hover": "#8c2f3b", "hero": "#4a2328",
                  "hero_text": "#fff1f2", "hero_muted": "#e7b8bd"},
        "dark": {"bg": "#1b1214", "surface": "#271a1d", "text": "#f6e8ea",
                 "muted": "#b99ba0", "border": "#4a3035", "accent": "#f0a6b0",
                 "tint": "#3b2428", "on_accent": "#3a1118", "hover": "#2e1c20",
                 "accent_hover": "#ffc2ca", "hero": "#3a1a1f",
                 "hero_text": "#fff1f2", "hero_muted": "#d9a0a7"},
    },
    "florence": {
        "light": {"bg": "#f3f7fa", "surface": "#ffffff", "text": "#1d2f3b",
                  "muted": "#617686", "border": "#d8e4ec", "accent": "#2b5d7d",
                  "tint": "#e8f2f8", "on_accent": "#ffffff", "hover": "#f0f7fb",
                  "accent_hover": "#234c68", "hero": "#1e3448",
                  "hero_text": "#eef6fb", "hero_muted": "#b5cbda"},
        "dark": {"bg": "#0f1921", "surface": "#172630", "text": "#e8f1f7",
                 "muted": "#9fb4c3", "border": "#2e4656", "accent": "#8fc4e8",
                 "tint": "#20333f", "on_accent": "#11293a", "hover": "#1a2b37",
                 "accent_hover": "#b7ddf8", "hero": "#162a3a",
                 "hero_text": "#eef6fb", "hero_muted": "#a8c0d1"},
    },
}

SCHEMES = tuple(PALETTES)
DEFAULT_SCHEME = "forest"

_DARK = False
_SCHEME = DEFAULT_SCHEME


def normalize_scheme(scheme):
    return scheme if scheme in PALETTES else DEFAULT_SCHEME


def set_active(dark=False, scheme=None):
    """Remember the active pair so paint code and late-created widgets agree."""
    global _DARK, _SCHEME
    _DARK = bool(dark)
    _SCHEME = normalize_scheme(scheme if scheme is not None else _SCHEME)


def current_scheme():
    return _SCHEME


def current_dark():
    return _DARK


def colors(dark=None, scheme=None):
    """Return the palette for the requested (or currently active) theme."""
    use_dark = _DARK if dark is None else bool(dark)
    use_scheme = normalize_scheme(scheme if scheme is not None else _SCHEME)
    return dict(PALETTES[use_scheme]["dark" if use_dark else "light"])


def file_icon(label="PDF", color=None, size=40):
    if color is None:
        color = colors()["accent"]
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


def stylesheet(dark=False, scheme=None):
    c = colors(dark, scheme)
    return f"""
    QWidget {{ color:{c['text']}; font-family:'SF Pro Text','PingFang SC','Microsoft YaHei','Arial'; font-size:13px; }}
    QMainWindow, QDialog {{ background:{c['bg']}; }}
    QWidget#app_central, QWidget#workspace, QWidget#tool_library {{ background:{c['bg']}; }}
    QLabel {{ background:transparent; }}
    QLabel#brand {{ font-size:20px; font-weight:700; letter-spacing:-0.7px; }}
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
    QPushButton#primary:hover {{ background:{c['accent_hover']}; }}
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


def apply_theme(app, dark=False, scheme=None):
    set_active(dark, scheme)
    c = colors(dark, scheme)
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
    app.setStyleSheet(stylesheet(dark, scheme))
