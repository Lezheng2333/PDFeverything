"""PDF page editor — snapshot-based undo/redo on a shared fitz.Document."""

from __future__ import annotations
from pathlib import Path
from typing import Callable
import io, time, fitz, pypdf

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
        self._journal_states: list[tuple[str, float, bytes]] = []
        self._journal_cursor: int = 0
        self._listeners: list[Callable[[str], None]] = []

    # ── Queries ──────────────────────────
    @property
    def page_count(self) -> int: return len(self._doc)
    def page_rotation(self, idx: int) -> int:
        return self._doc[idx].rotation if 0 <= idx < len(self._doc) else 0
    @property
    def undo_stack_desc(self) -> list[str]:
        return [desc for desc, _ in reversed(self._undo_stack)]

    # ── Document handle ──────────────────
    @property
    def doc(self):
        """The live fitz.Document. Undo/redo replace this object, so callers that
        keep their own reference (the reader widget) must read it back through
        this property instead of caching the old handle."""
        return self._doc

    def attach(self, doc) -> None:
        """Point the editor at a different fitz.Document (used by revert)."""
        self._doc = doc
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._emit("changed")

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
        """Swap the document for the snapshot's content.

        NOTE: this closes the previous fitz.Document and binds a new one, so any
        caller holding its own reference must re-read :attr:`doc` afterwards —
        the old object is dead."""
        try:
            self._doc.close()
        except Exception:
            pass
        self._doc = fitz.open(stream=raw, filetype="pdf")

    # ── On-disk journal (makes CLI page-undo/redo meaningful) ──

    def journal_dir(self) -> Path:
        """Directory holding this document's on-disk undo journal."""
        import hashlib
        import tempfile

        base = Path(tempfile.gettempdir()) / "pdfeverything_journal"
        if self._path is None:
            return base / "anonymous"
        try:
            st = Path(self._path).stat()
            # Nanosecond mtime: with 1-second resolution two edits made in the
            # same second produced the same key and clobbered each other's journal.
            fingerprint = (f"{Path(self._path).resolve()}:{st.st_size}:"
                           f"{st.st_mtime_ns}")
        except OSError:
            fingerprint = str(self._path)
        key = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]
        return base / key

    # ── Journal state (linear history with a cursor) ──
    #
    # The in-memory undo/redo stacks only make sense inside one process. The CLI
    # runs every command as a separate process, so the history is persisted as a
    # linear list of document states plus a cursor:
    #
    #     states[0]            — the file as it was opened (never mutated)
    #     states[1..cursor]    — every successive operation's result
    #     states[cursor+1..]   — redoable (undone) states
    #
    # Undo moves the cursor back, redo moves it forward, and a new operation
    # truncates everything after the cursor.

    def journal_dir(self) -> Path:
        """Directory holding this document's on-disk history journal."""
        import hashlib
        import tempfile

        base = Path(tempfile.gettempdir()) / "pdfeverything_journal"
        if self._path is None:
            return base / "anonymous"
        try:
            st = Path(self._path).stat()
            # Nanosecond mtime: 1-second resolution made two edits made in the
            # same second share a key and clobber each other's journal.
            fingerprint = (f"{Path(self._path).resolve()}:{st.st_size}:"
                           f"{st.st_mtime_ns}")
        except OSError:
            fingerprint = str(self._path)
        key = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]
        return base / key

    @property
    def history(self) -> list:
        """[{"desc": str, "time": float}] for every recorded state."""
        return [{"desc": d, "time": t} for d, t, _ in self._journal_states]

    @property
    def history_cursor(self) -> int:
        return self._journal_cursor

    def load_journal(self) -> None:
        """Restore the persisted linear history (best effort)."""
        import json

        d = self.journal_dir()
        meta_file = d / "history.json"
        if not meta_file.exists():
            return
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        states = []
        for item in meta.get("states", []) or []:
            blob = d / item.get("blob", "")
            if blob.exists():
                states.append((item.get("desc", ""), item.get("time", 0.0),
                               blob.read_bytes()))
        if not states:
            return
        self._journal_states = states
        self._journal_cursor = max(0, min(int(meta.get("cursor", 0)), len(states) - 1))

    def save_journal(self) -> None:
        """Persist the linear history to disk."""
        import json

        d = self.journal_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
            # Drop blobs that are no longer referenced (truncated redo branch).
            keep = {f"state_{i:04d}.pdf" for i in range(len(self._journal_states))}
            for old in d.glob("state_*.pdf"):
                if old.name not in keep:
                    old.unlink(missing_ok=True)
            meta = {"cursor": self._journal_cursor, "states": []}
            for i, (desc, ts, raw) in enumerate(self._journal_states):
                name = f"state_{i:04d}.pdf"
                (d / name).write_bytes(raw)
                meta["states"].append({"desc": desc, "time": ts, "blob": name})
            (d / "history.json").write_text(json.dumps(meta), encoding="utf-8")
        except OSError:
            pass

    def clear_journal(self) -> None:
        import shutil

        shutil.rmtree(self.journal_dir(), ignore_errors=True)

    def _journal_init(self) -> None:
        """Seed state 0 with the document as it is *before* any mutation, so the
        first operation is undoable too. Must be called before the mutation."""
        if self._journal_states:
            return
        try:
            raw = self._snapshot()
        except Exception:
            return
        self._journal_states = [("初始状态", time.time(), raw)]
        self._journal_cursor = 0

    def _journal_record(self, desc: str) -> None:
        """Push the current document as the newest state and truncate redo."""
        try:
            raw = self._snapshot()
        except Exception:
            return
        # NOTE: _journal_init() must have run BEFORE the mutation — seeding it
        # here would record the already-modified document as the "initial state",
        # making the first operation impossible to undo.
        del self._journal_states[self._journal_cursor + 1:]
        self._journal_states.append((desc, time.time(), raw))
        self._journal_cursor = len(self._journal_states) - 1
        if len(self._journal_states) > MAX_UNDO_DEPTH:
            self._journal_states.pop(0)
            self._journal_cursor = max(0, self._journal_cursor - 1)

    # ── Operations ───────────────────────

    def _push_undo(self, desc: str):
        """In-process undo snapshot (kept for the GUI's live session)."""
        snap = self._snapshot()
        self._undo_stack.append((desc, snap))
        self._redo_stack.clear()
        if len(self._undo_stack) > MAX_UNDO_DEPTH:
            self._undo_stack.pop(0)
        self._emit("changed")

    def delete_pages(self, ordinals: list[int]):
        if not ordinals: return
        self._journal_init()
        self._push_undo(f"删除 {len(ordinals)} 页")
        for o in sorted(ordinals, reverse=True):
            if 0 <= o < len(self._doc):
                self._doc.delete_page(o)
        self._journal_record(f"删除 {len(ordinals)} 页")
        self._emit("changed")

    def rotate_pages(self, ordinals: list[int], degrees: int):
        if degrees not in (90, 180, 270) or not ordinals: return
        self._journal_init()
        self._push_undo(f"旋转 {len(ordinals)} 页")
        for o in ordinals:
            if 0 <= o < len(self._doc):
                p = self._doc[o]
                p.set_rotation((p.rotation + degrees) % 360)
        self._journal_record(f"旋转 {len(ordinals)} 页 {degrees}°")
        self._emit("changed")

    def move_pages(self, source_ordinals: list[int], target: int):
        if not source_ordinals: return
        self._journal_init()
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
        self._journal_record(f"移动 {len(source_ordinals)} 页")
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
        """Revert to the previous recorded state. Returns its description."""
        if len(self._journal_states) > 1 and self._journal_cursor > 0:
            current = self._journal_states[self._journal_cursor][0]
            self._journal_cursor -= 1
            self._restore_snapshot(self._journal_states[self._journal_cursor][2])
            self._emit("changed")
            return current or "上一次操作"
        if not self._undo_stack:
            return None
        desc, snap = self._undo_stack.pop()
        cur = self._snapshot()
        self._redo_stack.append((desc, cur))
        self._restore_snapshot(snap)
        self._emit("changed")
        return desc

    def redo(self) -> str | None:
        """Re-apply the next recorded state. Returns its description."""
        if self._journal_cursor + 1 < len(self._journal_states):
            self._journal_cursor += 1
            desc = self._journal_states[self._journal_cursor][0]
            self._restore_snapshot(self._journal_states[self._journal_cursor][2])
            self._emit("changed")
            return desc or "重做"
        if not self._redo_stack:
            return None
        desc, snap = self._redo_stack.pop()
        cur = self._snapshot()
        self._undo_stack.append((desc, cur))
        self._restore_snapshot(snap)
        self._emit("changed")
        return desc

    def can_undo(self) -> bool:
        return (len(self._journal_states) > 1 and self._journal_cursor > 0) \
            or len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return self._journal_cursor + 1 < len(self._journal_states) \
            or len(self._redo_stack) > 0

    # ── Save / Close ─────────────────────
    def save(self, output_path: Path):
        # garbage/clean force MuPDF to rebuild the page tree: without them a
        # document that had pages deleted still serialises the stale page objects
        # and the output keeps the original page count.
        self._doc.save(str(output_path), garbage=4, deflate=True, clean=True)
        self._emit("saved")

    def close(self):
        if self._doc and self._own_doc:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None

    def _require_doc(self):
        if self._doc is None:
            raise RuntimeError("编辑器已关闭 (editor closed)")
        return self._doc
