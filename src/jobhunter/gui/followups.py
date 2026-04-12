"""Follow-ups/reminders tab."""

from __future__ import annotations

from datetime import date, timedelta

import dearpygui.dearpygui as dpg

from jobhunter.core.job_db import JobDB
from jobhunter.gui import layout
from jobhunter.gui.theme import FIT_ORANGE, FIT_RED


class FollowupsTab:
    """Show overdue and upcoming follow-up reminders."""

    def __init__(self, job_db: JobDB) -> None:
        self.db = job_db

    def build(self) -> None:
        dpg.add_text("Follow-up Reminders", color=(137, 180, 250))
        dpg.add_separator()

        with dpg.group(horizontal=True):
            dpg.add_button(label="Refresh", callback=self._refresh, width=80)
            dpg.add_spacer(width=10)
            dpg.add_button(label="Set Follow-up", callback=self._on_set_followup, width=120)

        dpg.add_spacer(height=10)

        # Overdue section
        dpg.add_text("OVERDUE", color=FIT_RED)
        with dpg.child_window(tag="overdue_list", height=200):
            pass

        dpg.add_spacer(height=10)

        # Upcoming section
        dpg.add_text("UPCOMING (next 7 days)", color=FIT_ORANGE)
        with dpg.child_window(tag="upcoming_list", height=200):
            pass

        self._refresh()

    def _refresh(self, sender=None, app_data=None, user_data=None) -> None:
        # Overdue
        self._clear_list("overdue_list")
        overdue = self.db.get_overdue_followups()
        if not overdue:
            dpg.add_text("No overdue follow-ups", parent="overdue_list", color=(158, 158, 158))
        else:
            for app in overdue:
                days = (date.today() - date.fromisoformat(app["follow_up_date"])).days
                with dpg.group(horizontal=True, parent="overdue_list"):
                    dpg.add_text(f"[{days}d overdue]", color=FIT_RED)
                    dpg.add_text(f"{app['company']} - {app['position']}")
                    dpg.add_text(f"(due: {app['follow_up_date']})", color=(158, 158, 158))
                    dpg.add_button(
                        label="Clear", width=50,
                        callback=self._on_clear_followup,
                        user_data=app["id"],
                    )

        # Upcoming
        self._clear_list("upcoming_list")
        upcoming = self.db.get_upcoming_followups(days=7)
        if not upcoming:
            dpg.add_text("No upcoming follow-ups", parent="upcoming_list", color=(158, 158, 158))
        else:
            for app in upcoming:
                days = (date.fromisoformat(app["follow_up_date"]) - date.today()).days
                with dpg.group(horizontal=True, parent="upcoming_list"):
                    dpg.add_text(f"[in {days}d]", color=FIT_ORANGE)
                    dpg.add_text(f"{app['company']} - {app['position']}")
                    dpg.add_text(f"(due: {app['follow_up_date']})", color=(158, 158, 158))

    def _on_set_followup(self, sender=None, app_data=None, user_data=None) -> None:
        tag = "set_followup_dialog"

        def _do_set():
            app_id_str = dpg.get_value("followup_app_id").strip()
            days_str = dpg.get_value("followup_days").strip()
            try:
                app_id = int(app_id_str)
                days = int(days_str) if days_str else 3
            except ValueError:
                return

            due = (date.today() + timedelta(days=days)).isoformat()
            self.db.update_application(app_id, follow_up_date=due)
            self.db.add_event(app_id, "note", f"Follow-up set for {due}")
            dpg.delete_item(tag)
            self._refresh()
            layout.set_status(f"Follow-up set for {due}")

        with dpg.window(label="Set Follow-up", modal=True, tag=tag, width=300, height=150):
            dpg.add_input_text(tag="followup_app_id", hint="Application ID", width=-1)
            dpg.add_input_text(tag="followup_days", hint="Days from now (default: 3)", width=-1)
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Set", callback=_do_set, width=60)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(tag), width=60)

    def _on_clear_followup(self, sender, app_data, user_data) -> None:
        self.db.update_application(user_data, follow_up_date=None)
        self._refresh()
        layout.set_status("Follow-up cleared")

    @staticmethod
    def _clear_list(tag: str) -> None:
        if dpg.does_item_exist(tag):
            children = dpg.get_item_children(tag, 1) or []
            for child in children:
                dpg.delete_item(child)
