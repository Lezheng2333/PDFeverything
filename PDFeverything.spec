# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — 将 PDFeverything 封装为 macOS .app 应用。
用法: pyinstaller PDFeverything.spec --noconfirm --clean
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = Path(SPECPATH)

# ── 收集 data files ──────────────────────────────────────

datas = []
for mod in ('fitz', 'PIL'):
    try:
        datas += collect_data_files(mod)
    except Exception:
        pass

# Bundle PNG for QIcon.setWindowIcon (handles alpha correctly for Dock)
datas.append((str(PROJECT_ROOT / 'resources' / 'app_icon.png'), 'resources'))

# ── 隐藏导入 ─────────────────────────────────────────────

hiddenimports = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.sip",
    "pypdf",
    "pypdf.generic",
    "pypdf.filters",
    "pikepdf",
    "pikepdf._core",
    "pikepdf.models",
    "fitz",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.PdfImagePlugin",
    "docx",
    "docx.document",
    "docx.table",
    "docx.text",
    "pptx",
    "pptx.slide",
    "pptx.shapes",
    "openpyxl",
    "openpyxl.worksheet",
    "openpyxl.reader",
    "mcp", "mcp.server",
    "tempfile",
    "subprocess",
    "shutil",
    "uuid",
]

# ── 排除 ─────────────────────────────────────────────────

excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "scipy",
    "pandas",
    "jedi",
    "IPython",
    "notebook",
    "sphinx",
    "pytest",
    "setuptools",
    "pip",
]

# ── 构建 ─────────────────────────────────────────────────

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# onedir 模式：瘦 EXE + COLLECT 收集依赖
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDFeverything",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "resources" / "app_icon.icns"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PDFeverything",
)

app = BUNDLE(
    coll,
    name="PDFeverything.app",
    icon=str(PROJECT_ROOT / "resources" / "app_icon.icns"),
    bundle_identifier="com.pdfeverything.app",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
        "CFBundleName": "PDFeverything",
        "CFBundleDisplayName": "PDFeverything",
        "CFBundleShortVersionString": "1.3.12",
        "CFBundleVersion": "1.3.12",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "PDF Document",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "CFBundleTypeExtensions": ["pdf"],
                "LSItemContentTypes": ["com.adobe.pdf"],
            },
        ],
        "NSAppleEventsUsageDescription": "PDFeverything needs to open PDF files.",
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "© 2026 PDFeverything",
    },
)
