"""PDF page editor — snapshot-based undo/redo on a shared fitz.Document."""

from __future__ import annotations
from pathlib import Path
from typing import Callable
import io, fitz, pypdf

MAX_UNDO_DEPTH = 50


class PdfPageEditor:
    """Operates on a shared fitz.Document. Before every mutation, the current
    state is snapshotted to the undo stack. Undo restores from the snapshot."""

    def __init__(self, doc_or_path, path: Path = None):
        if isinstance(doc_or_path, fitz.Document):
            self._doc = doc_or_path
            self._path = path
            self._own_doc = False
        else:
            self._path = doc_or_path
            self._doc = fitz.open(doc_or_path)
            self._own_doc = True
        self._undo_stack: list[tuple[str, bytes]] = []
        self._redo_stack: list[tuple[str, bytes]] = []
        self._listeners: list[Callable[[str], None]] = []

    # ── Queries ──────────────────────────
    @property
    def page_count(self) -> int: return len(self._doc)
    def page_rotation(self, idx: int) -> int:
        return self._doc[idx].rotation if 0 <= idx < len(self._doc) else 0
    def can_undo(self) -> bool: return len(self._undo_stack) > 0
    def can_redo(self) -> bool: return len(self._redo_stack) > 0
    @property
    def undo_stack_desc(self) -> list[str]:
        return [desc for desc, _ in reversed(self._undo_stack)]

    # ── Observer ─────────────────────────
    def on_change(self, cb): self._listeners.append(cb)
    def _emit(self, event: str):
        for cb in self._listeners:
            try: cb(event)
            except Exception: pass

    # ── Snapshots ────────────────────────
    def _snapshot(self) -> bytes:
        buf = io.BytesIO(); self._doc.save(buf); return buf.getvalue()

    def _restore_snapshot(self, raw: bytes):
        """Replace self._doc with the snapshot content, preserving the shared reference."""
        self._doc.close()
        buf = io.BytesIO(raw)
        self._doc = fitz.open(stream=buf.read(), filetype="pdf")

    def _push_undo(self, desc: str):
        snap = self._snapshot()
        self._undo_stack.append((desc, snap))
        self._redo_stack.clear()
        if len(self._undo_stack) > MAX_UNDO_DEPTH:
            self._undo_stack.pop(0)
        self._emit("changed")

    # ── Operations ───────────────────────
    def delete_pages(self, ordinals: list[int]):
        if not ordinals: return
        self._push_undo(f"删除 {len(ordinals)} 页")
        for o in sorted(ordinals, reverse=True):
            if 0 <= o < len(self._doc):
                self._doc.delete_page(o)
        self._emit("changed")

    def rotate_pages(self, ordinals: list[int], degrees: int):
        if degrees not in (90, 180, 270) or not ordinals: return
        self._push_undo(f"旋转 {len(ordinals)} 页")
        for o in ordinals:
            if 0 <= o < len(self._doc):
                p = self._doc[o]
                p.set_rotation((p.rotation + degrees) % 360)
        self._emit("changed")

    def move_pages(self, source_ordinals: list[int], target: int):
        if not source_ordinals: return
        self._push_undo(f"移动 {len(source_ordinals)} 页")
        # Reorder pages in the doc
        total = len(self._doc)
        keep = [i for i in range(total) if i not in source_ordinals]
        target = max(0, min(target, len(keep)))
        new_order = keep[:target] + source_ordinals + keep[target:]
        # Rebuild doc in new order
        writer = pypdf.PdfWriter()
        buf = io.BytesIO(); self._doc.save(buf)
        reader = pypdf.PdfReader(io.BytesIO(buf.getvalue()))
        for idx in new_order:
            if idx < len(reader.pages):
                writer.add_page(reader.pages[idx])
        buf2 = io.BytesIO(); writer.write(buf2)
        self._doc.close()
        self._doc = fitz.open(stream=buf2.getvalue(), filetype="pdf")
        self._emit("changed")

    def extract_pages(self, ordinals: list[int], output_path: Path) -> Path:
        if not ordinals: raise ValueError("no pages selected")
        writer = pypdf.PdfWriter()
        buf = io.BytesIO(); self._doc.save(buf)
        reader = pypdf.PdfReader(io.BytesIO(buf.getvalue()))
        for o in ordinals:
            if 0 <= o < len(reader.pages):
                writer.add_page(reader.pages[o])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ── Undo / Redo ──────────────────────
    def undo(self) -> str | None:
        if not self._undo_stack: return None
        desc, snap = self._undo_stack.pop()
        cur = self._snapshot()
        self._redo_stack.append((desc, cur))
        self._restore_snapshot(snap)
        self._emit("changed")
        return desc

    def redo(self) -> str | None:
        if not self._redo_stack: return None
        desc, snap = self._redo_stack.pop()
        cur = self._snapshot()
        self._undo_stack.append((desc, cur))
        self._restore_snapshot(snap)
        self._emit("changed")
        return desc

    # ── Save / Close ─────────────────────
    def save(self, output_path: Path):
        self._doc.save(str(output_path))
        self._emit("saved")

    def close(self):
        if self._doc and self._own_doc:
            self._doc.close()
        self._doc = None
