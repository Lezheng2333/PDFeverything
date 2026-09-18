"""共享工具函数 — 文件分类、临时文件管理、页码范围解析、进度回调约定。

注：EXT_CATEGORY_MAP 只列出真正有转换器的扩展名。之前 svg/ico 被标为 image，
但 ConverterRegistry 里没有它们的转换器，混合合并会给出"不支持的文件格式"。"""

import re
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
    """创建临时工作目录并注册清理。

    必须登记到 _temp_files，否则 cleanup_temp_files() 永远删不掉它 —— 混合合并
    每次运行都会在系统临时目录里留下用户文件的转换副本。"""
    d = Path(tempfile.gettempdir()) / f"{prefix}_{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    _temp_files.append(d)
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


# ── 页码范围解析（GUI / CLI / MCP 共用同一实现） ────────────
#
# 接受的写法（中英文标点、空白、省略号都兼容）：
#   all                  → 全部页面
#   1,3,5                → 单页列表
#   1-5                  → 区间（含两端）
#   1-5,8,10-12          → 混合
#   1–5 / 1—5 / 1~5 / 1..5 → 各种连字符写法
#
# 返回 0-based、升序、去重的序号列表；越界页码自动丢弃。
# 解析失败抛 ValueError，消息可直接展示给用户。

_RANGE_SEP = re.compile(r"[,，、;；\s]+")
_RANGE_DASH = re.compile(r"\s*(?:-|–|—|~|～|\.\.+)\s*")
_DASH_PAD = re.compile(r"\s*(?:-|–|—|~|～|\.\.+)\s*")


def parse_page_ranges(spec, total: Optional[int] = None,
                      one_based: bool = False) -> List[int]:
    """把页码范围字符串解析为 0-based 升序去重列表。

    spec: 字符串（如 "1-5,8"）或已经是 int 的序列。
    total: 若给定，越界页码被丢弃；否则保留。
    one_based: True 时输入按 1-based 解释（默认），False 时按 0-based。
    """
    if spec is None:
        return []
    if isinstance(spec, (list, tuple, set)):
        items = sorted(set(int(v) for v in spec))
        out = [v - 1 if one_based else v for v in items]
        return [p for p in out if p >= 0 and (total is None or p < total)]

    text = str(spec).strip()
    if not text:
        return []
    if text.lower() in ("all", "*", "全部", "所有"):
        return list(range(total)) if total is not None else []

    # 先去掉连字符两侧的空白，保证 "1 – 5" 与 "1-5" 等价，
    # 也避免被 _RANGE_SEP 的空白切分拆散。多个连字符（1-2-3）仍会被拒绝。
    result: set = set()
    for part in _RANGE_SEP.split(_DASH_PAD.sub(lambda m: m.group(0).strip(), text)):
        if not part:
            continue
        tokens = [t for t in _RANGE_DASH.split(part) if t and t.strip()]
        if len(tokens) == 1:
            result.add(_to_int(tokens[0], text))
        elif len(tokens) == 2:
            start, end = _to_int(tokens[0], text), _to_int(tokens[1], text)
            if end < start:
                start, end = end, start
            if total is not None:
                end = min(end, total if one_based else total + 1)
            if end - start > 100_000:
                raise ValueError(f"页码范围过大: {part}")
            result.update(range(start, end + 1))
        else:
            raise ValueError(f"无法识别的页码写法: {part}")

    out = sorted(p - 1 if one_based else p for p in result)
    return [p for p in out if p >= 0 and (total is None or p < total)]


def _to_int(token: str, original: str) -> int:
    token = token.strip()
    try:
        return int(token)
    except ValueError:
        raise ValueError(f"无法识别的页码写法: {token or original}") from None


def format_page_ranges(ordinals: List[int]) -> str:
    """把 0-based 序号列表压成紧凑的 1-based 范围字符串，如 [0,1,2,4] → "1-3, 5"。"""
    if not ordinals:
        return ""
    pages = sorted(set(ordinals))
    chunks: List[str] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        chunks.append(_range_chunk(start, prev))
        start = prev = p
    chunks.append(_range_chunk(start, prev))
    return ", ".join(chunks)


def _range_chunk(start: int, end: int) -> str:
    if start == end:
        return str(start + 1)
    return f"{start + 1}-{end + 1}"


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


def set_office_cache(result: dict) -> None:
    """Publish a probe result (used by the GUI's background probe thread)."""
    global _office_cache
    _office_cache = result


def check_office_availability(use_cache: bool = True) -> dict:
    """Cross-platform Office detection. Returns {word, powerpoint, excel: bool}.

    This shells out to `osascript` / COM with a 10 s timeout per application, so
    on a machine where the probe hangs it can block for 30 s. Callers on a UI
    thread should run it in a worker (see MainWindow._start_office_probe) or pass
    `use_cache=False` from the worker itself."""
    global _office_cache
    if use_cache and _office_cache is not None:
        return _office_cache

    import sys
    if sys.platform == "win32":
        result = _check_office_windows()
    else:
        result = _check_office_macos()
    if use_cache:
        _office_cache = result
    return result
