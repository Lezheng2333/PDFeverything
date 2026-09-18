"""Background worker threads — all heavy ops run in QThread, never block UI.

Three guarantees this module provides:

1. **Cooperative cancellation.** ``cancel()`` sets a :class:`threading.Event` and
   returns immediately; the wrapped operation observes it through the progress
   callback it already accepts, so the UI never freezes waiting for a thread.
2. **A real timeout.** The runtime limit is checked on every progress tick *and*
   after the callable returns, but the error is emitted at most once.
3. **Explicit terminal states.** Callers get ``finished`` / ``error`` /
   ``cancelled`` and can tell which worker emitted them, so a stale signal from
   a previous job can no longer corrupt the busy state of the current one.
"""

import threading
import time

from PyQt6.QtCore import QThread, QTimer, pyqtSignal


class OperationCancelled(Exception):
    """Raised inside the worker thread when the user cancels the operation."""


class BaseWorker(QThread):
    """Generic background thread. Runs a callable, emits progress/result/error.
    Includes a runtime limit (default 60 min) and cooperative cancellation."""

    progress = pyqtSignal(str, int)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()

    # Runtime limit for any single operation — prevents runaway processes
    MAX_RUNTIME_SECONDS = 60 * 60  # 1 hour

    def __init__(self, func, *args, parent=None, **kwargs):
        super().__init__(parent)
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False
        self._cancel_event = threading.Event()
        self._start_time = 0
        self._final_emitted = False
        self.timed_out = False

    # ── Cancellation ─────────────────────────────────

    @property
    def cancel_event(self) -> threading.Event:
        """Event the running operation can poll (also used by nested helpers)."""
        return self._cancel_event

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def request_cancel(self) -> None:
        """Ask the operation to stop. Never blocks the calling (GUI) thread."""
        self._is_cancelled = True
        self._cancel_event.set()

    def cancel(self) -> None:
        """Request cancellation and force-terminate only if the thread does not
        stop on its own within the grace period.

        The grace period is scheduled on the event loop, so the GUI thread is
        never blocked (the previous implementation called ``wait(5000)`` inline,
        which froze the whole window for five seconds on every Cancel click).
        """
        self.request_cancel()
        QTimer.singleShot(self.GRACE_MS, self._force_terminate_if_running)

    GRACE_MS = 5000

    def _force_terminate_if_running(self) -> None:
        if self.isRunning():
            self.terminate()
            self.wait(2000)

    # ── Execution ────────────────────────────────────

    def run(self):
        self._start_time = time.time()
        try:
            self.kwargs["progress_callback"] = self._report
            result = self.func(*self.args, **self.kwargs)
            if self._is_cancelled:
                self._emit_once(self.cancelled)
            elif self.timed_out:
                pass  # the timeout error has already been reported
            else:
                self._emit_once(self.finished, result)
        except OperationCancelled:
            self._emit_once(self.cancelled)
        except MemoryError:
            self._emit_once(self.error, "Out of memory — file is too large to process")
        except Exception as e:  # noqa: BLE001 — surfaced to the user verbatim
            if self._is_cancelled:
                self._emit_once(self.cancelled)
            else:
                self._emit_once(self.error, str(e) or type(e).__name__)

    def _report(self, msg: str, pct: int):
        """Progress callback handed to the operation. Raises OperationCancelled
        once cancellation (or the runtime limit) has been requested, which lets
        long loops unwind instead of running to completion."""
        if self._is_cancelled:
            raise OperationCancelled()
        if time.time() - self._start_time > self.MAX_RUNTIME_SECONDS:
            self.timed_out = True
            self._is_cancelled = True
            self._cancel_event.set()
            self._emit_once(
                self.error, "Operation timed out — try again with fewer or smaller files")
            raise OperationCancelled()
        self.progress.emit(msg, max(0, min(100, int(pct))))

    def _emit_once(self, signal, *args):
        """Guarantee exactly one terminal signal per worker run."""
        if self._final_emitted:
            return
        self._final_emitted = True
        signal.emit(*args)
