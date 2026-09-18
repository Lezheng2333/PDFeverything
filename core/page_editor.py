"""PDF page editor — snapshot-based undo/redo on a shared fitz.Document."""

from __future__ import annotations
from pathlib import Path
from typing import Callable
import io, time, fitz, pypdf

MAX_UNDO_DEPTH = 50
# Every journal state is a full copy of the document, so the depth cap alone does
# not bound anything: 50 snapshots of a 20MB document is 1GB of RAM, and the same
# again written to disk on every save. Budget by bytes as well and always keep at
# least this many states so undo still has something to work with.
JOURNAL_MAX_BYTES = 96 * 1024 * 1024
JOURNAL_MIN_STATES = 3
# Journals live in the temp directory and are never touched again once their
# document is gone, so reclaim them by age.
JOURNAL_MAX_AGE_SECONDS = 7 * 24 * 3600


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
        self._journal_key_path = None   # pinned once a journal is adopted
        self._journal_dir = None        # resolved once, then kept stable
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
        """Directory holding this document's on-disk history journal.

        The key identifies the *document*, not a byte-exact revision of it. Two
        earlier schemes failed here: hashing (path, size, mtime_ns) meant a
        command's own output no longer matched its input, and hashing the inode
        broke the moment an in-place save replaced the file. Both left the next
        invocation with no history, so cross-session `page-undo` always reported
        "nothing to undo". The key is now recorded once in a sidecar and reused.
        """
        import tempfile

        base = Path(tempfile.gettempdir()) / "pdfeverything_journal"
        if self._journal_dir is not None:
            return self._journal_dir
        key_path = self._journal_key_path or self._path
        if key_path is None:
            self._journal_dir = base / "anonymous"
            return self._journal_dir
        resolved = Path(key_path).resolve()
        self._journal_dir = base / self._journal_identity(base, resolved)
        return self._journal_dir

    @staticmethod
    def _journal_identity(base: Path, resolved: Path) -> str:
        """Stable journal key for a document path.

        File metadata cannot provide this on its own: saving in place replaces
        the file, which changes both its inode and its mtime, so the journal that
        was just written would be orphaned the moment the edit landed. The
        identity is therefore recorded once in a tiny sidecar keyed by the
        resolved path, and every later invocation reuses it. When the sidecar is
        missing (fresh temp dir, or a first-ever edit) it is rebuilt from the
        current inode."""
        import hashlib

        ident_dir = base / "identity"
        digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:16]
        sidecar = ident_dir / f"{digest}.id"
        try:
            existing = sidecar.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        except OSError:
            pass

        try:
            st = resolved.stat()
            identity = (f"{resolved}:{st.st_ino}" if st.st_ino
                        else f"{resolved}:{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            identity = str(resolved)
        key = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
        try:
            ident_dir.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(key, encoding="utf-8")
        except OSError:
            pass
        return key

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

    @property
    def history(self) -> list:
        """[{"desc": str, "time": float}] for every recorded state."""
        return [{"desc": d, "time": t} for d, t, _ in self._journal_states]

    @property
    def history_cursor(self) -> int:
        return self._journal_cursor

    def load_journal(self) -> None:
        """Restore the persisted linear history (best effort).

        Also pins the journal key: once a session has adopted a history, every
        later :meth:`save_journal` writes back to that same journal even if the
        output went to a different path. Without the pin, saving to `-o out.pdf`
        would move `self._path` and the next write would land in a different
        journal, breaking the undo chain halfway through."""
        import json

        if self._journal_key_path is None:
            self._journal_key_path = self._path   # pin BEFORE computing the key
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
            db = (d / "history.json").stat().st_size
            for f in d.glob("state_*.pdf"):
                db += f.stat().st_size
            # Journal files are not tracked by anything: touch the directory so a
            # stale sweep can tell a live document from an abandoned one.
            if db > JOURNAL_MAX_BYTES:
                self._journal_trim(d)
        except OSError:
            pass

    def _journal_trim(self, d: Path) -> None:
        """Shrink an over-budget journal on disk, newest states first."""
        keep: list = []
        total = 0
        for name in sorted((f"state_{i:04d}.pdf" for i in range(len(self._journal_states))),
                           reverse=True):
            p = d / name
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if len(keep) < JOURNAL_MIN_STATES or total + size <= JOURNAL_MAX_BYTES:
                keep.append(name)
                total += size
            else:
                p.unlink(missing_ok=True)
        keep_set = set(keep)
        for p in d.glob("state_*.pdf"):
            if p.name not in keep_set:
                p.unlink(missing_ok=True)

    def _journal_trim_memory(self) -> None:
        """Bound the in-RAM snapshot list.

        The depth cap bounds the *count*; this bounds the *bytes*. Oldest states
        are dropped until the total fits, but never below JOURNAL_MIN_STATES so
        undo keeps working on a huge document."""
        if len(self._journal_states) <= JOURNAL_MIN_STATES:
            return
        total = sum(len(raw) for _, _, raw in self._journal_states)
        while (total > JOURNAL_MAX_BYTES
               and len(self._journal_states) > JOURNAL_MIN_STATES):
            _, _, raw = self._journal_states.pop(0)
            total -= len(raw)
            self._journal_cursor = max(0, self._journal_cursor - 1)

    def clear_journal(self) -> None:
        import shutil

        shutil.rmtree(self.journal_dir(), ignore_errors=True)

    @staticmethod
    def sweep_stale_journals(max_age_seconds: int = JOURNAL_MAX_AGE_SECONDS) -> int:
        """Delete journal directories nobody has touched in `max_age_seconds`.

        Journals are keyed per document and are never revisited once the document
        is gone, so without this they accumulate forever (one directory plus up
        to 50 full document copies each). Returns the number of directories
        removed."""
        import shutil
        import tempfile
        import time as _time

        base = Path(tempfile.gettempdir()) / "pdfeverything_journal"
        if not base.is_dir():
            return 0
        cutoff = _time.time() - max_age_seconds
        removed = 0
        try:
            entries = list(base.iterdir())
        except OSError:
            return 0
        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
                newest = max((f.stat().st_mtime for f in entry.rglob("*")),
                             default=entry.stat().st_mtime)
                if newest < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        return removed

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
        self._journal_trim_memory()

    # ── Operations ───────────────────────

    def _push_undo(self, desc: str):
        """In-process undo snapshot (kept for the GUI's live session)."""
        snap = self._snapshot()
        self._undo_stack.append((desc, snap))
        self._redo_stack.clear()
        if len(self._undo_stack) > MAX_UNDO_DEPTH:
            self._undo_stack.pop(0)
        while (len(self._undo_stack) > JOURNAL_MIN_STATES
               and sum(len(s) for _, s in self._undo_stack) > JOURNAL_MAX_BYTES):
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
        # Filter first: a stray negative ordinal used to reach reader.pages[-1],
        # which silently duplicated the LAST page instead of moving the intended
        # one (6 pages became 7) while the caller still counted 6.
        total_now = len(self._doc)
        source_ordinals = sorted({o for o in (source_ordinals or [])
                                  if 0 <= o < total_now})
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
        """Write the document out.

        Saving over the file the editor was opened from needs care: MuPDF cannot
        write to a file it still has open for reading, so the content goes to a
        temporary file first and then replaces the original. That path is what
        makes `page-undo` usable from the CLI — editing in place keeps the same
        document (and therefore the same journal), while writing to a new output
        file starts a new document with no history."""
        from .utils import ensure_output_dir

        output_path = Path(output_path)
        ensure_output_dir(output_path.parent)
        target = output_path.resolve()
        same_file = False
        if self._path is not None:
            try:
                same_file = target == Path(self._path).resolve()
            except OSError:
                same_file = False

        if not same_file:
            self._doc.save(str(output_path), garbage=4, deflate=True, clean=True)
            self._emit("saved")
            return

        import os
        import tempfile

        fd, tmp_name = tempfile.mkstemp(suffix=".pdf", dir=str(output_path.parent))
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            self._doc.save(str(tmp), garbage=4, deflate=True, clean=True)
            os.replace(tmp, output_path)     # atomic: never a half-written PDF
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
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
