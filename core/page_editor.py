"""PDF page editor — command-pattern undo/redo for page-level operations.

All mutations go through commands that support undo(). The editor maintains
a history stack (max 50 entries) and emits change events for GUI refresh.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import fitz
import pypdf


MAX_UNDO_DEPTH = 50


# ═══════════ Snapshot / State ═══════════

@dataclass
class PageSnapshot:
    """Lightweight snapshot of page order and rotations for undo."""
    indices: list[int]             # original page indices in display order
    rotations: dict[int, int]      # page_ordinal -> rotation (0/90/180/270)


# ═══════════ Command Pattern ═══════════

class Command(ABC):
    """A reversible page-level operation."""

    desc: str  # human-readable description for UI

    @abstractmethod
    def execute(self, editor: "PdfPageEditor") -> None:
        ...

    @abstractmethod
    def undo(self, editor: "PdfPageEditor") -> None:
        ...


class DeleteCommand(Command):
    def __init__(self, removed: dict[int, bytes]):
        self.removed = removed  # {ordinal: page_pdf_bytes}
        self.desc = f"删除 {len(removed)} 页"

    def execute(self, e: PdfPageEditor) -> None:
        e._rebuild_doc(keep=set(e._indices) - set(self.removed.keys()))

    def undo(self, e: PdfPageEditor) -> None:
        # Re-insert removed pages at their original positions
        new_order = list(e._indices)
        for ordinal in sorted(self.removed.keys()):
            idx = min(ordinal, len(new_order))
            new_order.insert(idx, ordinal)
        # Rebuild doc with all pages back
        all_bytes = dict(e._original_pages)
        e._indices = new_order
        e._rebuild_doc(indices=new_order, page_bytes=all_bytes)


class RotateCommand(Command):
    def __init__(self, rotations: dict[int, tuple[int, int]]):
        # ordinal -> (old_rotation, new_rotation)
        self.rotations = rotations
        self.desc = f"旋转 {len(rotations)} 页"

    def execute(self, e: PdfPageEditor) -> None:
        for ordinal, (_, new_rot) in self.rotations.items():
            idx = e._indices.index(ordinal)
            e._doc[idx].set_rotation(new_rot)

    def undo(self, e: PdfPageEditor) -> None:
        for ordinal, (old_rot, _) in self.rotations.items():
            idx = e._indices.index(ordinal)
            e._doc[idx].set_rotation(old_rot)


class MoveCommand(Command):
    def __init__(self, old_indices: list[int], new_indices: list[int]):
        self.old_indices = list(old_indices)
        self.new_indices = list(new_indices)
        moved = [i for i in old_indices if i not in new_indices or
                 old_indices.index(i) != new_indices.index(i)]
        self.desc = f"移动 {len(moved)} 页"

    def execute(self, e: PdfPageEditor) -> None:
        e._indices = list(self.new_indices)

    def undo(self, e: PdfPageEditor) -> None:
        e._indices = list(self.old_indices)


# ═══════════ Main Editor ═══════════

class PdfPageEditor:
    """Edits PDF pages in-memory via PyMuPDF + pypdf snapshotting.
    All mutations are reversible (Cmd+Z / Cmd+Shift+Z).
    Emits change callbacks for GUI synchronization."""

    def __init__(self, input_path: Path):
        self._path = input_path
        self._doc: fitz.Document = fitz.open(input_path)
        self._indices = list(range(len(self._doc)))
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._listeners: list[Callable[[str], None]] = []

        # Cache original page bytes for undo delete
        self._original_pages: dict[int, bytes] = {}
        for i in range(len(self._doc)):
            self._original_pages[i] = self._doc[i].get_pixmap(
                matrix=fitz.Matrix(0.2, 0.2)).samples[:0]  # placeholder
        # Build actual page byte cache lazily
        self._page_bytes_cache: dict[int, bytes] = {}

    # ── Properties ─────────────────────────────────

    @property
    def page_count(self) -> int:
        return len(self._indices)

    @property
    def page_order(self) -> list[int]:
        """Current display order (original ordinal indices)."""
        return list(self._indices)

    def page_rotation(self, display_index: int) -> int:
        """Rotation of the page at the given display position."""
        if 0 <= display_index < len(self._indices):
            return self._doc[self._indices[display_index]].rotation
        return 0

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def undo_stack_desc(self) -> list[str]:
        return [c.desc for c in reversed(self._undo_stack)]

    @property
    def redo_stack_desc(self) -> list[str]:
        return [c.desc for c in self._redo_stack]

    # ── Listeners ─────────────────────────────────

    def on_change(self, callback: Callable[[str], None]):
        self._listeners.append(callback)

    def _emit(self, event: str):
        for cb in self._listeners:
            try: cb(event)
            except Exception: pass

    # ── Internal ─────────────────────────────────

    def _page_bytes(self, ordinal: int) -> bytes:
        """Extract a single page as PDF bytes (for rebuild)."""
        if ordinal not in self._page_bytes_cache:
            writer = pypdf.PdfWriter()
            reader = pypdf.PdfReader(self._path)
            if ordinal < len(reader.pages):
                writer.add_page(reader.pages[ordinal])
                import io
                buf = io.BytesIO()
                writer.write(buf)
                self._page_bytes_cache[ordinal] = buf.getvalue()
        return self._page_bytes_cache.get(ordinal, b"")

    def _rebuild_doc(self, indices: list[int] = None,
                     keep: set = None, page_bytes: dict = None):
        """Rebuild fitz document from page order. Used by undo/redo."""
        if indices is not None:
            order = indices
        elif keep is not None:
            order = [i for i in self._indices if i in keep]
        else:
            order = self._indices

        source = self._page_bytes_cache if page_bytes is None else page_bytes
        writer = pypdf.PdfWriter()
        reader = pypdf.PdfReader(self._path)
        for ordinal in order:
            if ordinal in source:
                writer.add_page(pypdf.PdfReader(
                    __import__("io").BytesIO(source[ordinal])).pages[0])
            elif ordinal < len(reader.pages):
                writer.add_page(reader.pages[ordinal])

        import io, tempfile
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)

        self._doc.close()
        self._doc = fitz.open(stream=buf.read(), filetype="pdf")
        self._indices = list(range(len(self._doc)))

    def _execute(self, cmd: Command):
        cmd.execute(self)
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        if len(self._undo_stack) > MAX_UNDO_DEPTH:
            self._undo_stack.pop(0)
        self._emit("changed")

    # ── Page Operations ──────────────────────────

    def delete_pages(self, ordinals: list[int]):
        """Delete pages by their current display ordinal (0-based).
        ordinals are converted to internal doc indices for undo snapshots."""
        internal = [self._indices[o] for o in ordinals if 0 <= o < len(self._indices)]
        if not internal:
            return
        # Ensure page bytes are cached
        for o in internal:
            self._page_bytes(o)
        removed = {o: self._page_bytes_cache.get(o, b"") for o in internal}
        cmd = DeleteCommand(removed)
        self._execute(cmd)

    def rotate_pages(self, ordinals: list[int], degrees: int):
        """Rotate pages at current display ordinals."""
        if degrees not in (90, 180, 270):
            raise ValueError(f"旋转角度必须是 90/180/270")
        rotations = {}
        for o in ordinals:
            if 0 <= o < len(self._indices):
                idx = self._indices[o]
                old = self._doc[idx].rotation
                new = (old + degrees) % 360
                rotations[idx] = (old, new)
        if rotations:
            cmd = RotateCommand(rotations)
            self._execute(cmd)

    def move_pages(self, source_ordinals: list[int], target: int):
        """Move source pages (display ordinals) to before target ordinal."""
        old = list(self._indices)
        moved = [self._indices[s] for s in sorted(source_ordinals, reverse=True)
                 if 0 <= s < len(self._indices)]
        if not moved:
            return
        for s in sorted(source_ordinals, reverse=True):
            if 0 <= s < len(self._indices):
                del self._indices[s]
        target = max(0, min(target, len(self._indices)))
        for m in reversed(moved):
            self._indices.insert(target, m)
        cmd = MoveCommand(old, list(self._indices))
        # Reset stacks to treat this as atomic (execute_and_capture already done)
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        if len(self._undo_stack) > MAX_UNDO_DEPTH:
            self._undo_stack.pop(0)
        self._rebuild_doc(indices=self._indices)
        self._emit("changed")

    def extract_pages(self, ordinals: list[int], output_path: Path) -> Path:
        """Export selected display ordinals to a new PDF file."""
        internal = [self._indices[o] for o in ordinals if 0 <= o < len(self._indices)]
        if not internal:
            raise ValueError("没有选中页面")
        writer = pypdf.PdfWriter()
        reader = pypdf.PdfReader(self._path)
        for o in internal:
            if o < len(reader.pages):
                writer.add_page(reader.pages[o])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ── Undo / Redo ──────────────────────────────

    def undo(self) -> str | None:
        if not self._undo_stack:
            return None
        cmd = self._undo_stack.pop()
        cmd.undo(self)
        self._redo_stack.append(cmd)
        self._emit("changed")
        return cmd.desc

    def redo(self) -> str | None:
        if not self._redo_stack:
            return None
        cmd = self._redo_stack.pop()
        cmd.execute(self)
        self._undo_stack.append(cmd)
        self._emit("changed")
        return cmd.desc

    def history(self) -> list[str]:
        return [c.desc for c in self._undo_stack]

    # ── Save ─────────────────────────────────────

    def save(self, output_path: Path):
        """Save current state to a new PDF file."""
        self._doc.save(str(output_path))
        self._emit("saved")

    def close(self):
        if self._doc:
            self._doc.close()
            self._doc = None
