"""Resume library tab: section browser, bullet editor, import, quick-add."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import dearpygui.dearpygui as dpg

from jobhunter.core.doc_extractor import extract_text, supported_extensions
from jobhunter.core.llm_client import LLMClient, LLMError
from jobhunter.core.resume_db import ResumeDB
from jobhunter.gui import dialogs, layout
from jobhunter.gui.theme import PRIORITY_NORMAL, PRIORITY_STRONG, PRIORITY_WEAK
from jobhunter.gui.workers import BackgroundTask

log = logging.getLogger(__name__)

_REFINE_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "bullet_refine.txt"
_EXTRACT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract_bullets.txt"


class ResumeLibraryTab:
    """Interactive resume bullet library manager."""

    def __init__(
        self,
        resume_db: ResumeDB,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.db = resume_db
        self.llm = llm_client
        self._selected_section: str = ""
        self._selected_bullet_id: int | None = None
        self._refine_prompt = ""
        self._extract_prompt = ""
        if _REFINE_PROMPT_PATH.exists():
            self._refine_prompt = _REFINE_PROMPT_PATH.read_text(encoding="utf-8")
        if _EXTRACT_PROMPT_PATH.exists():
            self._extract_prompt = _EXTRACT_PROMPT_PATH.read_text(encoding="utf-8")

    def build(self) -> None:
        """Build the resume library UI."""
        with dpg.group(horizontal=True):
            # -- Left pane: section browser --
            with dpg.child_window(width=220, tag="lib_sections_pane"):
                dpg.add_text("Sections", color=(137, 180, 250))
                dpg.add_separator()
                dpg.add_button(label="+ Add Section", callback=self._on_add_section, width=-1)
                dpg.add_spacer(height=5)
                # Section list placeholder
                with dpg.group(tag="section_list"):
                    pass

            dpg.add_spacer(width=5)

            # -- Right pane: bullet list --
            with dpg.child_window(tag="lib_bullets_pane"):
                dpg.add_text("Bullets", tag="bullets_header", color=(137, 180, 250))
                dpg.add_separator()

                # Bullet list
                with dpg.child_window(tag="bullet_list_container", height=-180):
                    with dpg.group(tag="bullet_list"):
                        pass

                dpg.add_separator()

                # -- Edit area --
                dpg.add_text("Edit Bullet:", tag="edit_label", show=False)
                dpg.add_input_text(
                    tag="bullet_edit_text", multiline=True, height=60,
                    show=False, width=-1,
                )
                with dpg.group(horizontal=True, tag="edit_buttons", show=False):
                    dpg.add_button(label="Save", callback=self._on_save_edit, width=60)
                    dpg.add_button(label="Cancel", callback=self._on_cancel_edit, width=60)
                    dpg.add_spacer(width=20)
                    dpg.add_combo(
                        ["strong", "normal", "weak"], tag="priority_combo",
                        default_value="normal", width=80,
                    )
                    dpg.add_button(label="Set Priority", callback=self._on_set_priority, width=90)

                dpg.add_separator()

                # -- Bottom bar --
                with dpg.group(horizontal=True):
                    dpg.add_input_text(
                        tag="quick_add_input", hint="Quick add: type a rough note...",
                        width=400,
                    )
                    dpg.add_button(label="Add Raw", callback=self._on_quick_add_raw, width=70)
                    dpg.add_button(label="Refine + Add", callback=self._on_quick_add_refine, width=90)
                    dpg.add_spacer(width=10)
                    dpg.add_button(label="Import File(s)", callback=self._on_import_files, width=100)
                    dpg.add_button(label="Export MD", callback=self._on_export_md, width=80)

                # Stats
                dpg.add_text("", tag="lib_stats")

        # File dialog (hidden)
        with dpg.file_dialog(
            tag="import_file_dialog",
            directory_selector=False,
            show=False,
            callback=self._on_file_selected,
            width=600, height=400,
        ):
            for ext in supported_extensions():
                dpg.add_file_extension(f"*{ext}")
            dpg.add_file_extension(".*")

        self._refresh_sections()
        self._update_stats()

    # ------------------------------------------------------------------
    # Section browser
    # ------------------------------------------------------------------

    def _refresh_sections(self) -> None:
        """Rebuild the section list."""
        if not dpg.does_item_exist("section_list"):
            return

        children = dpg.get_item_children("section_list", 1) or []
        for child in children:
            dpg.delete_item(child)

        sections = self.db.get_sections()
        for section in sections:
            count = len(self.db.list_bullets(section=section))
            cap = self.db.get_section_cap(section)
            with dpg.group(horizontal=True, parent="section_list"):
                dpg.add_selectable(
                    label=f"{section} ({count})",
                    callback=self._on_section_click,
                    user_data=section,
                    width=150,
                )
                dpg.add_input_int(
                    default_value=cap, width=45, min_value=0, max_value=20,
                    callback=self._on_cap_change, user_data=section,
                )

    def _on_section_click(self, sender, app_data, user_data) -> None:
        self._selected_section = user_data
        if dpg.does_item_exist("bullets_header"):
            dpg.set_value("bullets_header", f"Bullets - {user_data}")
        self._refresh_bullets()

    def _on_cap_change(self, sender, app_data, user_data) -> None:
        """User changed the bullet cap for a section."""
        section = user_data
        cap = app_data
        self.db.set_section_cap(section, cap)

    def _on_add_section(self, sender=None, app_data=None, user_data=None) -> None:
        tag = "add_section_dialog"

        def _do_add():
            name = dpg.get_value("new_section_name").strip()
            if name:
                # Adding a section is just adding a bullet to it
                # For now, just select it as the target for new bullets
                self._selected_section = name
                if dpg.does_item_exist("bullets_header"):
                    dpg.set_value("bullets_header", f"Bullets - {name}")
                self._refresh_bullets()
            dpg.delete_item(tag)

        with dpg.window(label="New Section", modal=True, tag=tag, width=300, height=120):
            dpg.add_input_text(tag="new_section_name", hint="Section name...")
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Add", callback=_do_add, width=60)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(tag), width=60)

    # ------------------------------------------------------------------
    # Bullet list
    # ------------------------------------------------------------------

    def _refresh_bullets(self) -> None:
        """Rebuild the bullet list for the selected section."""
        if not dpg.does_item_exist("bullet_list"):
            return

        children = dpg.get_item_children("bullet_list", 1) or []
        for child in children:
            dpg.delete_item(child)

        if not self._selected_section:
            dpg.add_text("Select a section", parent="bullet_list", color=(158, 158, 158))
            return

        bullets = self.db.list_bullets(section=self._selected_section)
        if not bullets:
            dpg.add_text("No bullets in this section", parent="bullet_list", color=(158, 158, 158))
            return

        for b in bullets:
            bid = b["bullet_id"]
            priority = b.get("priority", "normal")
            times = b.get("times_selected", 0)

            # Priority indicator
            indicator = {"strong": "[S]", "normal": "[N]", "weak": "[W]"}.get(priority, "[N]")
            color = {"strong": PRIORITY_STRONG, "normal": PRIORITY_NORMAL, "weak": PRIORITY_WEAK}.get(priority, PRIORITY_NORMAL)

            with dpg.group(horizontal=True, parent="bullet_list"):
                dpg.add_text(indicator, color=color)
                dpg.add_selectable(
                    label=f"{b['text'][:100]}{'...' if len(b['text']) > 100 else ''}",
                    callback=self._on_bullet_click,
                    user_data=bid,
                    width=-120,
                )
                dpg.add_text(f"({times}x)", color=(158, 158, 158))
                dpg.add_button(label="Edit", callback=self._on_edit_bullet, user_data=bid, width=40)
                dpg.add_button(label="Del", callback=self._on_delete_bullet, user_data=bid, width=35)

        self._update_stats()

    def _on_bullet_click(self, sender, app_data, user_data) -> None:
        self._selected_bullet_id = user_data
        b = self.db.get_bullet(user_data)
        if b:
            # Show full text in edit area (read-only until Edit clicked)
            dpg.set_value("bullet_edit_text", b["text"])
            dpg.show_item("edit_label")
            dpg.show_item("bullet_edit_text")
            dpg.show_item("edit_buttons")
            dpg.set_value("priority_combo", b.get("priority", "normal"))

    def _on_edit_bullet(self, sender, app_data, user_data) -> None:
        self._selected_bullet_id = user_data
        b = self.db.get_bullet(user_data)
        if b:
            dpg.set_value("bullet_edit_text", b["text"])
            dpg.show_item("edit_label")
            dpg.show_item("bullet_edit_text")
            dpg.show_item("edit_buttons")
            dpg.set_value("priority_combo", b.get("priority", "normal"))

    def _on_save_edit(self, sender=None, app_data=None, user_data=None) -> None:
        if self._selected_bullet_id:
            new_text = dpg.get_value("bullet_edit_text").strip()
            if new_text:
                self.db.update_bullet(self._selected_bullet_id, text=new_text)
                self._refresh_bullets()
                layout.set_status("Bullet updated")

    def _on_cancel_edit(self, sender=None, app_data=None, user_data=None) -> None:
        dpg.hide_item("edit_label")
        dpg.hide_item("bullet_edit_text")
        dpg.hide_item("edit_buttons")
        self._selected_bullet_id = None

    def _on_set_priority(self, sender=None, app_data=None, user_data=None) -> None:
        if self._selected_bullet_id:
            priority = dpg.get_value("priority_combo")
            self.db.update_bullet(self._selected_bullet_id, priority=priority)
            self._refresh_bullets()

    def _on_delete_bullet(self, sender, app_data, user_data) -> None:
        bid = user_data
        b = self.db.get_bullet(bid)
        if not b:
            return
        dialogs.confirm_dialog(
            "Delete Bullet",
            f"Delete this bullet?\n\n{b['text'][:100]}...",
            on_confirm=lambda: self._do_delete_bullet(bid),
        )

    def _do_delete_bullet(self, bid: int) -> None:
        self.db.delete_bullet(bid)
        self._refresh_bullets()
        layout.set_status("Bullet deleted")

    # ------------------------------------------------------------------
    # Quick add
    # ------------------------------------------------------------------

    def _on_quick_add_raw(self, sender=None, app_data=None, user_data=None) -> None:
        """Add a bullet exactly as typed."""
        text = dpg.get_value("quick_add_input").strip()
        if not text:
            return
        if not self._selected_section:
            dialogs.error_dialog("No Section", "Select a section first")
            return

        # Check for duplicates
        dupes = self.db.find_duplicates(text, threshold=0.92)
        if dupes:
            existing = dupes[0][0]
            dialogs.info_dialog(
                "Possible Duplicate",
                f"Similar bullet found (similarity: {dupes[0][1]:.0%}):\n\n{existing['text'][:150]}",
            )
            return

        self.db.add_bullet(self._selected_section, text, source_file="manual")
        dpg.set_value("quick_add_input", "")
        self._refresh_bullets()
        self._refresh_sections()
        layout.set_status("Bullet added")

    def _on_quick_add_refine(self, sender=None, app_data=None, user_data=None) -> None:
        """Refine a rough note via LLM, then add with approval."""
        text = dpg.get_value("quick_add_input").strip()
        if not text:
            return
        if not self._selected_section:
            dialogs.error_dialog("No Section", "Select a section first")
            return
        if not self.llm:
            dialogs.error_dialog("No LLM", "LLM server is not running. Add the bullet raw instead.")
            return

        layout.set_status("Refining bullet via LLM...")

        def do_refine():
            prompt = self._refine_prompt.replace("{{NOTE}}", text)
            prompt = prompt.replace("{{CONTEXT}}", self._selected_section)
            return self.llm.generate_text(prompt, system_prompt="You are a resume writing expert.")

        def on_done(refined):
            # Show refined text for approval
            self._show_refine_approval(text, refined.strip())

        BackgroundTask(
            do_refine, on_complete=on_done,
            on_error=lambda e: dialogs.error_dialog("Refine Error", str(e)),
        ).start()

    def _show_refine_approval(self, original: str, refined: str) -> None:
        tag = "refine_approval"

        def _accept():
            self.db.add_bullet(self._selected_section, refined, source_file="llm_refined")
            dpg.set_value("quick_add_input", "")
            self._refresh_bullets()
            self._refresh_sections()
            dpg.delete_item(tag)
            layout.set_status("Refined bullet added")

        def _use_original():
            self.db.add_bullet(self._selected_section, original, source_file="manual")
            dpg.set_value("quick_add_input", "")
            self._refresh_bullets()
            self._refresh_sections()
            dpg.delete_item(tag)
            layout.set_status("Original bullet added")

        with dpg.window(label="Review Refined Bullet", modal=True, tag=tag, width=600, height=250):
            dpg.add_text("Original:", color=(158, 158, 158))
            dpg.add_text(original, wrap=570)
            dpg.add_spacer(height=5)
            dpg.add_text("Refined:", color=(137, 180, 250))
            dpg.add_input_text(
                tag="refined_text_edit", default_value=refined,
                multiline=True, height=60, width=-1,
            )
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Accept Refined", callback=_accept, width=120)
                dpg.add_button(label="Use Original", callback=_use_original, width=100)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(tag), width=60)

    # ------------------------------------------------------------------
    # File import
    # ------------------------------------------------------------------

    def _on_import_files(self, sender=None, app_data=None, user_data=None) -> None:
        dpg.show_item("import_file_dialog")

    def _on_file_selected(self, sender, app_data, user_data=None) -> None:
        if not app_data or "selections" not in app_data:
            return

        files = list(app_data["selections"].values())
        if not files:
            return

        layout.set_status(f"Importing {len(files)} file(s)...")

        def do_import():
            results = []
            for fpath in files:
                text = extract_text(fpath)
                if not text:
                    continue

                filename = Path(fpath).name

                if self.llm:
                    # Use LLM to extract structured bullets
                    prompt = self._extract_prompt.replace("{{DOCUMENT}}", text[:8000])
                    prompt = prompt.replace("{{FILENAME}}", filename)
                    try:
                        result = self.llm.generate_json(
                            prompt,
                            {"type": "object", "properties": {"roles": {"type": "array"}}},
                            system_prompt="You are a resume parser. Extract bullets exactly as written.",
                        )
                        roles = result.get("roles", []) if isinstance(result, dict) else []
                        for role in roles:
                            section = role.get("section", "experience")
                            role_name = role.get("role", "")
                            for bullet in role.get("bullets", []):
                                bullet = bullet.strip()
                                if bullet and len(bullet) > 10:
                                    dupes = self.db.find_duplicates(bullet, threshold=0.92)
                                    if not dupes:
                                        self.db.add_bullet(
                                            section, bullet,
                                            role=role_name,
                                            source_file=filename,
                                        )
                                        results.append(bullet)
                    except LLMError:
                        log.exception("LLM extraction failed for %s", filename)
                else:
                    # Simple line-based extraction without LLM
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith(("- ", "* ", "o ")):
                            bullet = line.lstrip("-*o ").strip()
                            if bullet and len(bullet) > 15:
                                dupes = self.db.find_duplicates(bullet, threshold=0.92)
                                if not dupes:
                                    section = self._selected_section or "experience"
                                    self.db.add_bullet(section, bullet, source_file=filename)
                                    results.append(bullet)

            return results

        def on_done(results):
            self._refresh_sections()
            self._refresh_bullets()
            self._update_stats()
            layout.set_status(f"Imported {len(results)} new bullets")
            if results:
                dialogs.info_dialog("Import Complete", f"Added {len(results)} new bullets to library")

        BackgroundTask(
            do_import, on_complete=on_done,
            on_error=lambda e: dialogs.error_dialog("Import Error", str(e)),
        ).start()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export_md(self, sender=None, app_data=None, user_data=None) -> None:
        from jobhunter.config import _APP_DIR
        out_path = _APP_DIR / "data" / "resumelibrary.md"
        self.db.export_markdown(out_path)
        layout.set_status(f"Library exported to {out_path}")
        dialogs.info_dialog("Export Complete", f"Saved to:\n{out_path}")

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _update_stats(self) -> None:
        total = self.db.total_bullets()
        sections = len(self.db.get_sections())
        if dpg.does_item_exist("lib_stats"):
            dpg.set_value("lib_stats", f"Library: {total} bullets across {sections} sections")
