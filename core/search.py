"""PDF 全文搜索 — GUI / CLI / MCP 共用同一实现。

设计要点：
- 用 PyMuPDF 的 ``search_for`` 拿到命中矩形，同时返回页码、四角坐标与上下文，
  这样 GUI 可以在页面位图上精确高亮，CLI/MCP 也能得到结构化结果。
- 命中上下文由 ``page.get_text()`` 的平坦文本还原，遇到跨行/跨页命中也能给出
  可读片段。
- 大小写不敏感、可选整词匹配；不依赖正则，避免用户输入的特殊字符引发异常。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .utils import check_input

MAX_HITS_DEFAULT = 500
CONTEXT_CHARS = 40


@dataclass
class SearchHit:
    """一次命中。rect 为 PDF 坐标（点），可直接用于渲染时缩放。"""

    page: int                      # 0-based 页码
    rect: tuple                    # (x0, y0, x1, y1)
    text: str = ""                 # 实际匹配到的文字
    context: str = ""              # 周边上下文片段

    def as_dict(self) -> dict:
        return {
            "page": self.page + 1,
            "rect": [round(v, 2) for v in self.rect],
            "text": self.text,
            "context": self.context,
        }


@dataclass
class SearchResult:
    """搜索结果集合。"""

    query: str
    total_pages: int
    hits: List[SearchHit] = field(default_factory=list)
    truncated: bool = False

    @property
    def count(self) -> int:
        return len(self.hits)

    def pages_with_hits(self) -> List[int]:
        seen = []
        for h in self.hits:
            if h.page not in seen:
                seen.append(h.page)
        return seen

    def as_dict(self) -> dict:
        return {
            "success": True,
            "query": self.query,
            "matches": self.count,
            "pages": [p + 1 for p in self.pages_with_hits()],
            "truncated": self.truncated,
            "results": [h.as_dict() for h in self.hits],
        }


def _fold(text: str) -> str:
    """NFKC 归一 + 大小写折叠，让全角/半角、连字等写法都能互相命中。"""
    import unicodedata
    return unicodedata.normalize("NFKC", text or "").casefold()


def _query_variants(query: str) -> List[str]:
    """PyMuPDF 的 search_for 是字面匹配，这里补上常见写法差异。"""
    variants = [query]
    folded = _fold(query)
    for candidate in (folded, query.lower(), query.upper(), query.capitalize()):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def search_pdf(
    input_path: Path,
    query: str,
    *,
    case_sensitive: bool = False,
    whole_word: bool = False,
    pages: Optional[List[int]] = None,
    max_hits: int = MAX_HITS_DEFAULT,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> SearchResult:
    """在 PDF 中搜索文本。

    参数：
        input_path: PDF 路径
        query:      搜索词（空字符串返回空结果）
        pages:      限定 0-based 页码列表；None 表示全部页面
        max_hits:   命中上限，超过则截断并置 truncated=True
    """
    import fitz

    check_input(input_path)
    query = (query or "").strip()
    if not query:
        return SearchResult(query="", total_pages=0)

    doc = fitz.open(input_path)
    try:
        if doc.needs_pass:
            raise ValueError("PDF 受密码保护，无法搜索")
        total = len(doc)
        targets = list(range(total)) if pages is None else [
            p for p in pages if 0 <= p < total
        ]
        # PyMuPDF 的 search_for 会丢弃单字符查询，这里统一交给它处理，
        # 但把「整词匹配」在文本层面自行过滤，保证行为可预期。
        result = SearchResult(query=query, total_pages=total)
        step = max(1, len(targets))
        for i, pno in enumerate(targets):
            if progress_callback:
                progress_callback(f"搜索中 ({i + 1}/{len(targets)})",
                                  int((i + 1) / step * 100))
            page = doc[pno]
            if case_sensitive:
                # MuPDF's search_for is case-insensitive; a case-sensitive search
                # therefore has to read the matched glyphs back and filter them.
                matched = _search_case_sensitive(page, query)
            else:
                matched = []
                for variant in _query_variants(query):
                    try:
                        matched = page.search_for(variant, quads=False)
                    except Exception:
                        matched = []
                    if matched:
                        break
            rects = matched
            if not rects:
                continue
            flat = None
            for rect in rects:
                if len(result.hits) >= max_hits:
                    result.truncated = True
                    return result
                if flat is None:
                    try:
                        flat = page.get_text("text")
                    except Exception:
                        flat = ""
                hit_text = _text_in_rect(page, rect) or query
                if whole_word and not _is_whole_word(page, rect, query):
                    continue
                result.hits.append(SearchHit(
                    page=pno,
                    rect=(rect.x0, rect.y0, rect.x1, rect.y1),
                    text=hit_text,
                    context=_context_for(flat, hit_text),
                ))
        return result
    finally:
        doc.close()


def highlight_rects(input_path: Path, query: str, page: int,
                    page_rect) -> List:
    """返回某一页上所有命中的矩形（已换算到页面坐标），供渲染高亮使用。"""
    import fitz

    doc = fitz.open(input_path)
    try:
        if page < 0 or page >= len(doc):
            return []
        rects = doc[page].search_for(query or "", quads=False)
        return [fitz.Rect(r) for r in rects]
    except Exception:
        return []
    finally:
        doc.close()


# ── 内部工具 ────────────────────────────────────────────────

def _search_case_sensitive(page, query: str) -> list:
    """Filter MuPDF's case-insensitive hits down to exact matches."""
    try:
        raw = page.search_for(query, quads=False)
    except Exception:
        return []
    keep = []
    for rect in raw:
        hit_text = _text_in_rect(page, rect)
        if hit_text == query or query in hit_text:
            keep.append(rect)
    return keep


def _text_in_rect(page, rect) -> str:
    """取命中矩形内的文字（用于展示与整词判断）。"""
    try:
        text = page.get_text("text", clip=rect).strip()
    except Exception:
        return ""
    return " ".join(text.split())


def _is_whole_word(page, rect, query: str) -> bool:
    """判断命中是否为整词。

    命中的矩形只覆盖查询本身（"alp" 在 "alphabetic" 中同样返回 "alp"），
    因此必须在命中所在的**整行**文本上做前后字符检查。中文等无空格语言直接视为整词。
    """
    import re

    if not query:
        return False
    if any(ord(c) > 0x2E80 for c in query):
        return True
    try:
        line = page.get_text("text", clip=_line_clip(page, rect))
    except Exception:
        line = ""
    if not line:
        return False
    pattern = r"(?<![0-9A-Za-z_])" + re.escape(query) + r"(?![0-9A-Za-z_])"
    return re.search(pattern, line, re.IGNORECASE) is not None


def _line_clip(page, rect):
    """命中所在的整行矩形（用于整词判断取上下文）。"""
    import fitz

    x0 = 0.0
    x1 = page.rect.width
    height = max(1.0, rect.y1 - rect.y0)
    return fitz.Rect(x0, rect.y0 - height * 0.5, x1, rect.y1 + height * 0.5)


def _context_for(flat: str, needle: str) -> str:
    """从扁平文本里截取命中周围的片段。"""
    if not flat or not needle:
        return ""
    idx = flat.lower().find(needle.lower())
    if idx < 0:
        # 跨行命中：把换行折叠后再找一次
        collapsed = " ".join(flat.split())
        idx = collapsed.lower().find(needle.lower())
        if idx < 0:
            return ""
        flat = collapsed
    start = max(0, idx - CONTEXT_CHARS)
    end = min(len(flat), idx + len(needle) + CONTEXT_CHARS)
    snippet = " ".join(flat[start:end].split())
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(flat) else "")


# ── 目录 / 书签 ─────────────────────────────────────────────

@dataclass
class OutlineEntry:
    """PDF 目录（书签）中的一项。level 从 0 开始表示嵌套深度。"""

    title: str
    page: int          # 0-based；-1 表示目标无法解析
    level: int = 0
    bold: bool = False
    children: List["OutlineEntry"] = field(default_factory=list)

    def flatten(self) -> List["OutlineEntry"]:
        out = [self]
        for child in self.children:
            out.extend(child.flatten())
        return out

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "page": self.page + 1 if self.page >= 0 else None,
            "level": self.level,
            "children": [c.as_dict() for c in self.children],
        }


def get_outline(input_path: Path) -> List[OutlineEntry]:
    """读取 PDF 目录树。没有书签时返回空列表。"""
    import fitz

    check_input(input_path)
    doc = fitz.open(input_path)
    try:
        raw = doc.get_toc(simple=False) or []
        if not raw:
            return []
        entries: List[OutlineEntry] = []
        stack: List[OutlineEntry] = []
        for item in raw:
            level = int(item[0]) if item else 1
            title = str(item[1]) if len(item) > 1 else ""
            page = int(item[2]) - 1 if len(item) > 2 else -1
            detail = item[3] if len(item) > 3 and isinstance(item[3], dict) else {}
            entry = OutlineEntry(title=title, page=page,
                                 level=max(0, level - 1),
                                 bold=bool(detail.get("bold", False)))
            while stack and stack[-1].level >= entry.level:
                stack.pop()
            if stack:
                stack[-1].children.append(entry)
            else:
                entries.append(entry)
            stack.append(entry)
        return entries
    except Exception:
        return []
    finally:
        doc.close()
