"""Search URL manager tab."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from jobhunter.core.job_db import JobDB
from jobhunter.core.scraper import detect_board
from jobhunter.gui import dialogs, layout


_BOARD_CHOICES = ["linkedin", "dice", "builtin", "glassdoor", "other"]


class SearchURLsTab:
    """Manage configured search URLs per board."""

    def __init__(self, job_db: JobDB) -> None:
        self.db = job_db

    def build(self) -> None:
        dpg.add_text("Manage Search URLs", color=(137, 180, 250))
        dpg.add_separator()

        # Add URL bar
        with dpg.group(horizontal=True):
            dpg.add_combo(
                _BOARD_CHOICES, tag="url_board_combo",
                default_value="linkedin", width=100,
            )
            dpg.add_input_text(
                tag="url_add_input", hint="Paste search URL...", width=500,
            )
            dpg.add_input_text(
                tag="url_label_input", hint="Label (optional)", width=150,
            )
            dpg.add_button(label="Add", callback=self._on_add, width=50)

        dpg.add_spacer(height=10)

        # URL list
        with dpg.child_window(tag="url_list_container"):
            with dpg.group(tag="url_list"):
                pass

        self._refresh()

    def _refresh(self) -> None:
        if not dpg.does_item_exist("url_list"):
            return

        children = dpg.get_item_children("url_list", 1) or []
        for child in children:
            dpg.delete_item(child)

        urls = self.db.list_search_urls()
        if not urls:
            dpg.add_text("No search URLs configured", parent="url_list", color=(158, 158, 158))
            return

        for entry in urls:
            uid = entry["id"]
            enabled = bool(entry.get("enabled", 1))
            board = entry.get("board", "other")
            url = entry.get("url", "")
            label = entry.get("label", "")
            last = entry.get("last_scraped", "never")

            with dpg.group(horizontal=True, parent="url_list"):
                dpg.add_checkbox(
                    default_value=enabled,
                    callback=self._on_toggle,
                    user_data=uid,
                )
                dpg.add_text(f"[{board}]", color=(137, 180, 250))
                display = label if label else (url[:80] + "..." if len(url) > 80 else url)
                dpg.add_text(display)
                dpg.add_text(f"(last: {last or 'never'})", color=(158, 158, 158))
                dpg.add_button(label="Del", callback=self._on_delete, user_data=uid, width=35)

    def _on_add(self, sender=None, app_data=None, user_data=None) -> None:
        url = dpg.get_value("url_add_input").strip()
        if not url.startswith("http"):
            dialogs.error_dialog("Invalid URL", "URL must start with http")
            return

        board = dpg.get_value("url_board_combo")
        # Auto-detect board from URL
        detected = detect_board(url)
        if detected != "other":
            board = detected

        label = dpg.get_value("url_label_input").strip()
        self.db.add_search_url(board, url, label)
        dpg.set_value("url_add_input", "")
        dpg.set_value("url_label_input", "")
        self._refresh()
        layout.set_status(f"Search URL added ({board})")

    def _on_toggle(self, sender, app_data, user_data) -> None:
        self.db.toggle_search_url(user_data, app_data)

    def _on_delete(self, sender, app_data, user_data) -> None:
        dialogs.confirm_dialog(
            "Delete URL",
            "Remove this search URL?",
            on_confirm=lambda: self._do_delete(user_data),
        )

    def _do_delete(self, uid: int) -> None:
        self.db.delete_search_url(uid)
        self._refresh()
        layout.set_status("Search URL removed")
