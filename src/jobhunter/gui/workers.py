"""Background workers for PySide6.

Uses QThread + signals for thread-safe GUI updates.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal, QObject

log = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Signals emitted by background workers."""

    finished = Signal(object)   # result
    error = Signal(str)         # error message
    progress = Signal(int, str) # (percent, message)


class BackgroundWorker(QThread):
    """Run a callable in a background thread with completion signals.

    Usage::

        def do_work(progress_callback):
            progress_callback(50, "Halfway...")
            return {"result": 42}

        worker = BackgroundWorker(do_work)
        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(on_error)
        worker.start()
    """

    def __init__(
        self,
        target: Callable,
        *args: Any,
        name: str = "",
    ) -> None:
        super().__init__()
        self.target = target
        self.args = args
        self.signals = WorkerSignals()
        self._name = name or target.__name__

    def run(self) -> None:
        try:
            result = self.target(*self.args, progress_callback=self._emit_progress)
            self.signals.finished.emit(result)
        except Exception as exc:
            log.exception("Worker '%s' failed", self._name)
            self.signals.error.emit(f"{exc}\n{traceback.format_exc()}")

    def _emit_progress(self, percent: int, message: str = "") -> None:
        self.signals.progress.emit(percent, message)


class SimpleWorker(QThread):
    """Simpler worker that doesn't pass a progress callback.

    For quick operations that don't need progress reporting.
    """

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, target: Callable, *args: Any) -> None:
        super().__init__()
        self.target = target
        self.args = args

    def run(self) -> None:
        try:
            result = self.target(*self.args)
            self.finished.emit(result)
        except Exception as exc:
            log.exception("SimpleWorker failed")
            self.error.emit(str(exc))
