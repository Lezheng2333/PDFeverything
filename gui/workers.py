"""后台工作线程 — 所有耗时操作通过 QThread 执行，不阻塞 UI。"""

from PyQt6.QtCore import QThread, pyqtSignal


class BaseWorker(QThread):
    """通用后台 Worker：执行任意可调用对象并发射进度/结果/错误信号。"""

    progress = pyqtSignal(str, int)   # (状态消息, 百分比 0-100)
    finished = pyqtSignal(object)     # 结果对象
    error = pyqtSignal(str)           # 错误消息

    def __init__(self, func, *args, parent=None, **kwargs):
        super().__init__(parent)
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def cancel(self):
        """请求取消（子类应在循环中检查此标志）。"""
        self._is_cancelled = True

    def run(self):
        try:
            self.kwargs["progress_callback"] = self._on_progress
            result = self.func(*self.args, **self.kwargs)
            if not self._is_cancelled:
                self.finished.emit(result)
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))

    def _on_progress(self, msg: str, pct: int):
        if not self._is_cancelled:
            self.progress.emit(msg, pct)
