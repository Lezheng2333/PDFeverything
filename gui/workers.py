"""Background worker threads — all heavy ops run in QThread, never block UI."""

import time

from PyQt6.QtCore import QThread, pyqtSignal


class BaseWorker(QThread):
    """Generic background thread. Runs a callable, emits progress/result/error.
    Includes safety timeout (60 min) and graceful shutdown."""

    progress = pyqtSignal(str, int)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    # Hard timeout for any operation — prevents runaway processes
    MAX_RUNTIME_SECONDS = 60 * 60  # 1 hour

    def __init__(self, func, *args, parent=None, **kwargs):
        super().__init__(parent)
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False
        self._start_time = 0

    def cancel(self):
        """Request cancellation. Forced after 5s grace."""
        self._is_cancelled = True
        # Schedule force-terminate if it doesn't stop
        QThread.quit(self)  # gentle request
        self.wait(5000)      # 5s grace
        if self.isRunning():
            self.terminate()  # force kill
            self.wait(2000)

    def run(self):
        self._start_time = time.time()
        try:
            self.kwargs["progress_callback"] = self._on_progress
            result = self.func(*self.args, **self.kwargs)
            if not self._is_cancelled:
                self.finished.emit(result)
        except MemoryError:
            if not self._is_cancelled:
                self.error.emit("Out of memory — file is too large to process")
        except Exception as e:
            if not self._is_cancelled:
                msg = str(e) if str(e) else type(e).__name__
                self.error.emit(msg)

    def _on_progress(self, msg: str, pct: int):
        # Clamp percentage and check runtime timeout
        pct = max(0, min(100, pct))
        elapsed = time.time() - self._start_time
        if elapsed > self.MAX_RUNTIME_SECONDS:
            self._is_cancelled = True
            self.error.emit("Operation timed out (>60 min). Please try with fewer/smaller files.")
            return
        if not self._is_cancelled:
            self.progress.emit(msg, pct)
