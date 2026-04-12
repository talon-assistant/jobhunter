"""Threading helpers for DearPyGui background operations.

DearPyGui is NOT thread-safe for widget creation, but ``dpg.set_value()``
is safe for updating existing widgets.  Long operations run in background
threads and push results to a shared queue that the main render loop drains.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)

# Shared queue for cross-thread callbacks
_callback_queue: queue.Queue[tuple[Callable, tuple]] = queue.Queue()


def schedule_main_thread(fn: Callable, *args: Any) -> None:
    """Schedule ``fn(*args)`` to run on the next DPG frame (main thread)."""
    _callback_queue.put((fn, args))


def drain_callback_queue() -> None:
    """Process all pending callbacks. Call this every frame from the DPG render loop."""
    while True:
        try:
            fn, args = _callback_queue.get_nowait()
            try:
                fn(*args)
            except Exception:
                log.exception("Error in main-thread callback %s", fn.__name__)
        except queue.Empty:
            break


class BackgroundTask:
    """Run a callable in a background thread with completion callbacks.

    Usage::

        def do_work():
            time.sleep(5)
            return {"result": 42}

        def on_done(result):
            dpg.set_value("status", f"Done: {result}")

        BackgroundTask(do_work, on_complete=on_done, on_error=show_error).start()
    """

    def __init__(
        self,
        target: Callable[..., Any],
        *,
        args: tuple = (),
        on_complete: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        name: str = "",
    ) -> None:
        self.target = target
        self.args = args
        self.on_complete = on_complete
        self.on_error = on_error
        self._thread: threading.Thread | None = None
        self._name = name or target.__name__

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"bg-{self._name}", daemon=True
        )
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        try:
            result = self.target(*self.args)
            if self.on_complete:
                schedule_main_thread(self.on_complete, result)
        except Exception as exc:
            log.exception("Background task '%s' failed", self._name)
            if self.on_error:
                schedule_main_thread(self.on_error, exc)


class TaskTracker:
    """Track multiple background tasks for status display."""

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}

    def submit(
        self,
        name: str,
        target: Callable,
        *,
        args: tuple = (),
        on_complete: Callable | None = None,
        on_error: Callable | None = None,
    ) -> BackgroundTask:
        task = BackgroundTask(
            target, args=args, on_complete=on_complete,
            on_error=on_error, name=name,
        )
        self._tasks[name] = task
        task.start()
        return task

    def is_busy(self) -> bool:
        return any(t.is_alive() for t in self._tasks.values())

    def active_task_names(self) -> list[str]:
        return [name for name, t in self._tasks.items() if t.is_alive()]
