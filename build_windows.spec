# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — Windows  onefile 模式
=========================================
用法: pyinstaller build_windows.spec --noconfirm --clean
输出: dist/PDFeverything.exe  (单个文件，可直接分发)
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = Path(SPECPATH)

datas = []
for mod in ('fitz', 'PIL'):
    try:
        datas += collect_data_files(mod)
    except Exception:
        pass

hiddenimports = [
    "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets", "PyQt6.sip",
    "pypdf", "pypdf.generic", "pypdf.filters",
    "pikepdf", "pikepdf._core", "pikepdf.models",
    "fitz",
    "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.PdfImagePlugin",
    "docx", "docx.document", "docx.table", "docx.text",
    "pptx", "pptx.slide", "pptx.shapes",
    "openpyxl", "openpyxl.worksheet", "openpyxl.reader",
    "tempfile", "subprocess", "shutil", "uuid",
]

excludes = [
    "tkinter", "matplotlib", "numpy", "scipy", "pandas",
    "jedi", "IPython", "notebook", "sphinx", "pytest",
    "setuptools", "pip", "lib2to3", "multiprocessing",
]

# ── onefile: 所有文件塞进单个 exe ──────────────────────

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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,         # ← 内嵌所有 dll/pyd（onefile 关键）
    a.datas,            # ← 内嵌所有数据文件
    [],
    name="PDFeverything",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "resources" / "app_icon.ico"),
)
