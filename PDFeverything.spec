# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — 将 PDFeverything 封装为 macOS .app 应用。
用法: pyinstaller PDFeverything.spec --noconfirm --clean
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = Path(SPECPATH)

# ── 可移植性参数（由 build_macos.py 注入，也可手动设置）──────────────
#
# PDFE_MIN_MACOS:  bundle 声明并保证的最低 macOS 版本。必须 >= 所有随包
#                二进制（Python / Qt / 第三方扩展）各自要求的版本，否则
#                dyld 会在旧系统上拒绝加载 —— 2.0.1 的 "macOS 26 打不开"
#                就是这么来的（plist 写 11.0，实际 libpython 要 26.0、
#                Homebrew OpenSSL 要 27.0）。
# PDFE_TARGET_ARCH: "arm64"（Apple 芯片原生）或 "universal2"。
# PDFE_CODESIGN_IDENTITY: 留空 = ad-hoc 签名；"Developer ID Application: ..."
#                配合 build_macos.py --notarize 才能免 Gatekeeper 拦截。
VERSION = "2.0.2"
MIN_MACOS = os.environ.get("PDFE_MIN_MACOS", "13.0")
TARGET_ARCH = os.environ.get("PDFE_TARGET_ARCH", "arm64")
CODESIGN_IDENTITY = os.environ.get("PDFE_CODESIGN_IDENTITY") or None
ENTITLEMENTS = PROJECT_ROOT / "resources" / "macos_entitlements.plist"
# Only advertise arm64 priority when that is the arch we actually built.
ARCH_PLIST = ({"LSArchitecturePriority": ["arm64"]}
              if TARGET_ARCH == "arm64" else {})

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
    "PyQt6.QtPrintSupport",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.sip",
    "pypdf",
    "pypdf.generic",
    "pypdf.filters",
    "cryptography",
    "cryptography.hazmat.primitives.ciphers",
    "cryptography.hazmat.backends.openssl",
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
    # Qt owns the native event loop; Apple Event argv emulation delays CLI/MCP
    # startup and may abort when no WindowServer connection is available.
    argv_emulation=False,
    target_arch=TARGET_ARCH,
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=str(ENTITLEMENTS) if CODESIGN_IDENTITY else None,
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
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
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
        # Must match the newest deployment target among every bundled Mach-O.
        # build_macos.py audits this after the build and fails on a mismatch.
        "LSMinimumSystemVersion": MIN_MACOS,
        "LSApplicationCategoryType": "public.app-category.productivity",
        **ARCH_PLIST,
        "NSHumanReadableCopyright": "© 2026 PDFeverything",
    },
)
