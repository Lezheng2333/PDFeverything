"""共享工具函数 — 文件分类、临时文件管理、进度回调约定。"""

import os
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

# ── 临时文件追踪 ──────────────────────────────────────────

_temp_files: List[Path] = []


def temp_pdf_path(prefix: str = "pdfeverything") -> Path:
    """在系统临时目录生成唯一的 PDF 文件路径，并注册为待清理。"""
    tmp = Path(tempfile.gettempdir()) / f"{prefix}_{uuid.uuid4().hex[:8]}.pdf"
    _temp_files.append(tmp)
    return tmp


def temp_dir(prefix: str = "pdfeverything") -> Path:
    """创建临时工作目录并注册清理。"""
    d = Path(tempfile.gettempdir()) / f"{prefix}_{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def register_temp(*paths: Path) -> None:
    """手动注册需要清理的临时路径。"""
    _temp_files.extend(paths)


def cleanup_temp_files() -> None:
    """删除所有注册的临时文件/目录。忽略权限错误。"""
    import shutil

    for p in _temp_files:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except OSError:
            pass
    _temp_files.clear()


# ── 文件检查与分类 ────────────────────────────────────────


def check_input(path: Path) -> Path:
    """检查文件是否存在，不存在则抛出 FileNotFoundError。"""
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return path


def ensure_output_dir(path: Path) -> Path:
    """确保输出目录存在。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


# 文件扩展名 → 类型映射
EXT_CATEGORY_MAP = {
    # PDF
    "pdf": "pdf",
    # 图片
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "bmp": "image", "tiff": "image", "tif": "image", "webp": "image",
    "svg": "image", "ico": "image",
    # Word
    "docx": "word", "doc": "word", "rtf": "word",
    # PowerPoint
    "pptx": "powerpoint", "ppt": "powerpoint",
    # Excel
    "xlsx": "excel", "xls": "excel", "csv": "text",
    # 文本
    "txt": "text", "md": "text", "log": "text", "py": "text",
    "json": "text", "xml": "text", "html": "text", "htm": "text",
    "yaml": "text", "yml": "text", "ini": "text", "cfg": "text",
    "sh": "text", "bat": "text", "ps1": "text",
}


def get_file_category(path: Path) -> str:
    """根据扩展名返回文件类别：pdf / image / word / powerpoint / excel / text / unknown。"""
    ext = path.suffix.lstrip(".").lower()
    return EXT_CATEGORY_MAP.get(ext, "unknown")


def filter_by_category(paths: List[Path], category: str) -> List[Path]:
    """从路径列表中筛选指定类别的文件。"""
    return [p for p in paths if get_file_category(p) == category]


def format_bytes(size: int) -> str:
    """人类可读的文件大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ── 文本编码检测 ──────────────────────────────────────────


def read_text_file(path: Path) -> str:
    """读取文本文件，自动尝试常见编码。"""
    encodings = ["utf-8", "utf-16", "gbk", "gb2312", "shift_jis", "latin-1"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 最后尝试忽略错误
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


# ── Office 可用性检测（跨平台） ────────────────────────────

_office_cache: Optional[dict] = None


def _check_office_macos() -> dict:
    """Detect Office on macOS via AppleScript."""
    import subprocess
    apps = {"word": "Microsoft Word", "powerpoint": "Microsoft PowerPoint",
            "excel": "Microsoft Excel"}
    result = {}
    for key, name in apps.items():
        try:
            r = subprocess.run(
                ["osascript", "-e", f'tell application "{name}" to get version'],
                capture_output=True, text=True, timeout=10,
            )
            result[key] = r.returncode == 0
        except Exception:
            result[key] = False
    return result


def _check_office_windows() -> dict:
    """Detect Office on Windows via COM."""
    result = {"word": False, "powerpoint": False, "excel": False}
    try:
        import win32com.client
        for prog_id, key in [("Word.Application", "word"),
                              ("PowerPoint.Application", "powerpoint"),
                              ("Excel.Application", "excel")]:
            try:
                app = win32com.client.Dispatch(prog_id)
                ver = app.Version  # noqa: F841 — probe that it works
                app.Quit()
                result[key] = True
            except Exception:
                result[key] = False
    except ImportError:
        pass  # pywin32 not installed
    return result


def check_office_availability() -> dict:
    """Cross-platform Office detection. Returns {word, powerpoint, excel: bool}."""
    global _office_cache
    if _office_cache is not None:
        return _office_cache

    import sys
    if sys.platform == "win32":
        _office_cache = _check_office_windows()
    else:
        _office_cache = _check_office_macos()
    return _office_cache
