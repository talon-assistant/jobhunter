"""Main window layout: tab bar, status bar, frame loop."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from jobhunter.gui.workers import drain_callback_queue

if TYPE_CHECKING:
    from jobhunter.gui.dashboard import DashboardTab
    from jobhunter.gui.followups import FollowupsTab
    from jobhunter.gui.resume_library import ResumeLibraryTab
    from jobhunter.gui.search_urls import SearchURLsTab
    from jobhunter.gui.settings_panel import SettingsTab

log = logging.getLogger(__name__)

# Tags for stable references
PRIMARY_WINDOW = "primary_window"
TAB_BAR = "main_tab_bar"
STATUS_TEXT = "status_text"
LLM_STATUS = "llm_status"


def build_layout(
    *,
    dashboard: DashboardTab,
    resume_library: ResumeLibraryTab,
    search_urls: SearchURLsTab,
    followups: FollowupsTab,
    settings: SettingsTab,
) -> None:
    """Build the main application window and wire all tabs."""

    with dpg.window(tag=PRIMARY_WINDOW):
        # Tab bar
        with dpg.tab_bar(tag=TAB_BAR):
            with dpg.tab(label="Dashboard"):
                dashboard.build()

            with dpg.tab(label="Resume Library"):
                resume_library.build()

            with dpg.tab(label="Search URLs"):
                search_urls.build()

            with dpg.tab(label="Follow-ups"):
                followups.build()

            with dpg.tab(label="Settings"):
                settings.build()

        # Status bar at bottom
        dpg.add_separator()
        with dpg.group(horizontal=True):
            dpg.add_text("Ready", tag=STATUS_TEXT)
            dpg.add_spacer(width=20)
            dpg.add_text("LLM: --", tag=LLM_STATUS, color=(158, 158, 158))


def set_status(text: str) -> None:
    """Update the status bar text."""
    if dpg.does_item_exist(STATUS_TEXT):
        dpg.set_value(STATUS_TEXT, text)


def set_llm_status(text: str, *, ok: bool = True) -> None:
    """Update the LLM status indicator."""
    if dpg.does_item_exist(LLM_STATUS):
        dpg.set_value(LLM_STATUS, f"LLM: {text}")
        color = (129, 199, 132) if ok else (239, 83, 80)
        dpg.configure_item(LLM_STATUS, color=color)


def frame_callback() -> None:
    """Called every frame to process background task results."""
    drain_callback_queue()
