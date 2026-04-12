"""Modal dialogs for DearPyGui: confirm, error, progress."""

from __future__ import annotations

from typing import Callable

import dearpygui.dearpygui as dpg


def confirm_dialog(
    title: str,
    message: str,
    on_confirm: Callable[[], None],
    *,
    confirm_label: str = "Yes",
    cancel_label: str = "Cancel",
) -> None:
    """Show a modal confirmation dialog."""
    tag = f"confirm_{id(on_confirm)}"

    def _on_confirm():
        on_confirm()
        dpg.delete_item(tag)

    def _on_cancel():
        dpg.delete_item(tag)

    with dpg.window(
        label=title, modal=True, tag=tag,
        no_resize=True, no_move=False,
        width=400, height=150,
    ):
        dpg.add_text(message, wrap=380)
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True):
            dpg.add_button(label=confirm_label, callback=_on_confirm, width=80)
            dpg.add_button(label=cancel_label, callback=_on_cancel, width=80)


def error_dialog(title: str, message: str) -> None:
    """Show a modal error dialog."""
    tag = f"error_{hash(message)}"

    def _close():
        dpg.delete_item(tag)

    with dpg.window(
        label=title, modal=True, tag=tag,
        no_resize=True, width=450, height=180,
    ):
        dpg.add_text(message, wrap=420, color=(239, 83, 80))
        dpg.add_spacer(height=10)
        dpg.add_button(label="OK", callback=_close, width=60)


def info_dialog(title: str, message: str) -> None:
    """Show a modal info dialog."""
    tag = f"info_{hash(message)}"

    def _close():
        dpg.delete_item(tag)

    with dpg.window(
        label=title, modal=True, tag=tag,
        no_resize=True, width=450, height=180,
    ):
        dpg.add_text(message, wrap=420)
        dpg.add_spacer(height=10)
        dpg.add_button(label="OK", callback=_close, width=60)


class ProgressDialog:
    """A modal dialog with a progress bar and status text."""

    def __init__(self, title: str) -> None:
        self.tag = f"progress_{hash(title)}"
        self._bar_tag = f"{self.tag}_bar"
        self._text_tag = f"{self.tag}_text"

        with dpg.window(
            label=title, modal=True, tag=self.tag,
            no_resize=True, no_close=True,
            width=400, height=120,
        ):
            dpg.add_text("Starting...", tag=self._text_tag)
            dpg.add_progress_bar(
                tag=self._bar_tag, default_value=0.0, width=-1
            )

    def update(self, progress: float, message: str = "") -> None:
        """Update progress (0.0 to 1.0) and optional message."""
        if dpg.does_item_exist(self._bar_tag):
            dpg.set_value(self._bar_tag, progress)
        if message and dpg.does_item_exist(self._text_tag):
            dpg.set_value(self._text_tag, message)

    def close(self) -> None:
        if dpg.does_item_exist(self.tag):
            dpg.delete_item(self.tag)
