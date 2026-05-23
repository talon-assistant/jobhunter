"""Resume library tab: section browser, bullet editor, import, quick-add (PySide6)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QTextEdit, QComboBox,
    QSpinBox, QFileDialog, QMessageBox, QInputDialog, QGroupBox,
)

from jobhunter.core.doc_extractor import extract_text, supported_extensions
from jobhunter.core.llm_client import LLMClient, LLMError
from jobhunter.core.resume_db import ResumeDB
from jobhunter.gui.workers import SimpleWorker

log = logging.getLogger(__name__)

_REFINE_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "bullet_refine.txt"
_EXTRACT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract_bullets.txt"


class ResumeLibraryTab(QWidget):
    """Interactive resume bullet library manager."""

    def __init__(
        self,
        resume_db: ResumeDB,
        llm_client: LLMClient | None = None,
        *,
        status_callback=None,
    ) -> None:
        super().__init__()
        self.db = resume_db
        self.llm = llm_client
        self._status_cb = status_callback
        self._selected_section = ""
        self._selected_bullet_id: int | None = None
        self._workers: list[SimpleWorker] = []

        self._refine_prompt = ""
        self._extract_prompt = ""
        if _REFINE_PROMPT_PATH.exists():
            self._refine_prompt = _REFINE_PROMPT_PATH.read_text(encoding="utf-8")
        if _EXTRACT_PROMPT_PATH.exists():
            self._extract_prompt = _EXTRACT_PROMPT_PATH.read_text(encoding="utf-8")

        self._build_ui()
        self._refresh_sections()

    def _set_status(self, msg: str) -> None:
        if self._status_cb:
            self._status_cb(msg)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # -- Left: section browser --
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        heading = QLabel("Sections")
        heading.setProperty("heading", True)
        left_layout.addWidget(heading)

        self._section_list = QListWidget()
        self._section_list.currentItemChanged.connect(self._on_section_click)
        left_layout.addWidget(self._section_list)

        btn_add_section = QPushButton("+ Add Section")
        btn_add_section.clicked.connect(self._on_add_section)
        left_layout.addWidget(btn_add_section)

        # Cap controls
        cap_group = QGroupBox("Section Cap")
        cap_layout = QHBoxLayout(cap_group)
        self._cap_spin = QSpinBox()
        self._cap_spin.setRange(0, 20)
        self._cap_spin.setValue(4)
        self._cap_spin.valueChanged.connect(self._on_cap_change)
        cap_layout.addWidget(QLabel("Max bullets:"))
        cap_layout.addWidget(self._cap_spin)
        left_layout.addWidget(cap_group)

        splitter.addWidget(left)

        # -- Right: bullet list + editor --
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._bullets_heading = QLabel("Bullets")
        self._bullets_heading.setProperty("heading", True)
        right_layout.addWidget(self._bullets_heading)

        self._bullet_list = QListWidget()
        self._bullet_list.currentItemChanged.connect(self._on_bullet_click)
        right_layout.addWidget(self._bullet_list, stretch=1)

        # Edit area
        edit_group = QGroupBox("Edit Bullet")
        edit_layout = QVBoxLayout(edit_group)
        self._edit_text = QTextEdit()
        self._edit_text.setMaximumHeight(80)
        edit_layout.addWidget(self._edit_text)

        edit_buttons = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._on_save_edit)
        edit_buttons.addWidget(btn_save)

        btn_delete = QPushButton("Delete")
        btn_delete.setProperty("danger", True)
        btn_delete.clicked.connect(self._on_delete_bullet)
        edit_buttons.addWidget(btn_delete)

        edit_buttons.addWidget(QLabel("Priority:"))
        self._priority_combo = QComboBox()
        self._priority_combo.addItems(["strong", "normal", "weak"])
        self._priority_combo.setCurrentText("normal")
        self._priority_combo.currentTextChanged.connect(self._on_set_priority)
        edit_buttons.addWidget(self._priority_combo)
        edit_buttons.addStretch()

        edit_layout.addLayout(edit_buttons)
        right_layout.addWidget(edit_group)

        # Quick add bar
        quick_group = QGroupBox("Add Bullets")
        quick_layout = QVBoxLayout(quick_group)
        quick_input_row = QHBoxLayout()
        self._quick_input = QLineEdit()
        self._quick_input.setPlaceholderText("Type a rough note or accomplishment...")
        self._quick_input.returnPressed.connect(self._on_quick_add_raw)
        quick_input_row.addWidget(self._quick_input, stretch=1)

        btn_raw = QPushButton("Add Raw")
        btn_raw.clicked.connect(self._on_quick_add_raw)
        quick_input_row.addWidget(btn_raw)

        btn_refine = QPushButton("Refine + Add")
        btn_refine.setProperty("primary", True)
        btn_refine.clicked.connect(self._on_quick_add_refine)
        quick_input_row.addWidget(btn_refine)

        quick_layout.addLayout(quick_input_row)

        import_row = QHBoxLayout()
        btn_import = QPushButton("Import Resume File(s)")
        btn_import.clicked.connect(self._on_import_files)
        import_row.addWidget(btn_import)

        btn_export = QPushButton("Export Markdown")
        btn_export.clicked.connect(self._on_export_md)
        import_row.addWidget(btn_export)

        self._stats_label = QLabel("")
        self._stats_label.setProperty("dim", True)
        import_row.addWidget(self._stats_label)
        import_row.addStretch()

        quick_layout.addLayout(import_row)
        right_layout.addWidget(quick_group)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Section browser
    # ------------------------------------------------------------------

    def _refresh_sections(self) -> None:
        self._section_list.clear()
        sections = self.db.get_sections()
        for section in sections:
            count = len(self.db.list_bullets(section=section))
            item = QListWidgetItem(f"{section} ({count})")
            item.setData(Qt.UserRole, section)
            self._section_list.addItem(item)
        self._update_stats()

    def _on_section_click(self, current: QListWidgetItem | None, previous) -> None:
        if not current:
            return
        self._selected_section = current.data(Qt.UserRole)
        self._bullets_heading.setText(f"Bullets — {self._selected_section}")
        cap = self.db.get_section_cap(self._selected_section)
        self._cap_spin.blockSignals(True)
        self._cap_spin.setValue(cap)
        self._cap_spin.blockSignals(False)
        self._refresh_bullets()

    def _on_add_section(self) -> None:
        name, ok = QInputDialog.getText(self, "New Section", "Section name:")
        if ok and name.strip():
            self._selected_section = name.strip()
            self._bullets_heading.setText(f"Bullets — {self._selected_section}")
            self._refresh_sections()
            self._refresh_bullets()

    def _on_cap_change(self, value: int) -> None:
        if self._selected_section:
            self.db.set_section_cap(self._selected_section, value)

    # ------------------------------------------------------------------
    # Bullet list
    # ------------------------------------------------------------------

    def _refresh_bullets(self) -> None:
        self._bullet_list.clear()
        if not self._selected_section:
            return

        bullets = self.db.list_bullets(section=self._selected_section)
        for b in bullets:
            priority = b.get("priority", "normal")
            times = b.get("times_selected", 0)
            indicator = {"strong": "★", "normal": "●", "weak": "○"}.get(priority, "●")
            label = f"{indicator} {b['text'][:120]}{'...' if len(b['text']) > 120 else ''}  ({times}x)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, b["bullet_id"])
            self._bullet_list.addItem(item)
        self._update_stats()

    def _on_bullet_click(self, current: QListWidgetItem | None, previous) -> None:
        if not current:
            return
        bid = current.data(Qt.UserRole)
        self._selected_bullet_id = bid
        b = self.db.get_bullet(bid)
        if b:
            self._edit_text.setPlainText(b["text"])
            self._priority_combo.setCurrentText(b.get("priority", "normal"))

    def _on_save_edit(self) -> None:
        if self._selected_bullet_id:
            text = self._edit_text.toPlainText().strip()
            if text:
                self.db.update_bullet(self._selected_bullet_id, text=text)
                self._refresh_bullets()
                self._set_status("Bullet updated")

    def _on_delete_bullet(self) -> None:
        if not self._selected_bullet_id:
            return
        b = self.db.get_bullet(self._selected_bullet_id)
        if not b:
            return
        reply = QMessageBox.question(
            self, "Delete Bullet",
            f"Delete this bullet?\n\n{b['text'][:100]}...",
        )
        if reply == QMessageBox.Yes:
            self.db.delete_bullet(self._selected_bullet_id)
            self._selected_bullet_id = None
            self._refresh_bullets()
            self._refresh_sections()
            self._set_status("Bullet deleted")

    def _on_set_priority(self, priority: str) -> None:
        if self._selected_bullet_id and priority:
            self.db.update_bullet(self._selected_bullet_id, priority=priority)
            self._refresh_bullets()

    # ------------------------------------------------------------------
    # Quick add
    # ------------------------------------------------------------------

    def _on_quick_add_raw(self) -> None:
        text = self._quick_input.text().strip()
        if not text:
            return
        if not self._selected_section:
            QMessageBox.warning(self, "No Section", "Select a section first")
            return

        dupes = self.db.find_duplicates(text, threshold=0.92)
        if dupes:
            reply = QMessageBox.question(
                self, "Possible Duplicate",
                f"Similar bullet found ({dupes[0][1]:.0%} match):\n\n"
                f"{dupes[0][0]['text'][:150]}\n\nAdd anyway?",
            )
            if reply != QMessageBox.Yes:
                return

        self.db.add_bullet(self._selected_section, text, source_file="manual")
        self._quick_input.clear()
        self._refresh_bullets()
        self._refresh_sections()
        self._set_status("Bullet added")

    def _on_quick_add_refine(self) -> None:
        text = self._quick_input.text().strip()
        if not text:
            return
        if not self._selected_section:
            QMessageBox.warning(self, "No Section", "Select a section first")
            return
        if not self.llm:
            QMessageBox.warning(self, "No LLM", "Configure an LLM provider first")
            return

        self._set_status("Refining bullet...")

        def do_refine():
            prompt = self._refine_prompt.replace("{{NOTE}}", text)
            prompt = prompt.replace("{{CONTEXT}}", self._selected_section)
            return self.llm.generate_text(prompt, system_prompt="You are a resume writing expert.")

        def on_done(refined):
            refined = refined.strip()
            reply = QMessageBox.question(
                self, "Review Refined Bullet",
                f"Original:\n{text}\n\nRefined:\n{refined}\n\nAccept the refined version?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Yes:
                self.db.add_bullet(self._selected_section, refined, source_file="llm_refined")
            elif reply == QMessageBox.No:
                self.db.add_bullet(self._selected_section, text, source_file="manual")
            else:
                return
            self._quick_input.clear()
            self._refresh_bullets()
            self._refresh_sections()
            self._set_status("Bullet added")

        worker = SimpleWorker(do_refine)
        worker.finished.connect(on_done)
        worker.error.connect(lambda e: QMessageBox.warning(self, "Error", e))
        self._workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # File import
    # ------------------------------------------------------------------

    def _on_import_files(self) -> None:
        ext_filter = "Resume Files (" + " ".join(f"*{e}" for e in supported_extensions()) + ")"
        files, _ = QFileDialog.getOpenFileNames(self, "Import Resume Files", "", ext_filter)
        if not files:
            return

        self._set_status(f"Importing {len(files)} file(s)...")

        def do_import():
            count = 0
            for fpath in files:
                text = extract_text(fpath)
                if not text:
                    continue
                filename = Path(fpath).name
                if self.llm:
                    try:
                        prompt = self._extract_prompt.replace("{{DOCUMENT}}", text[:8000])
                        prompt = prompt.replace("{{FILENAME}}", filename)
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
                                        self.db.add_bullet(section, bullet, role=role_name, source_file=filename)
                                        count += 1
                    except LLMError:
                        log.exception("LLM extraction failed for %s", filename)
                else:
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith(("- ", "* ", "o ")):
                            bullet = line.lstrip("-*o ").strip()
                            if bullet and len(bullet) > 15:
                                dupes = self.db.find_duplicates(bullet, threshold=0.92)
                                if not dupes:
                                    section = self._selected_section or "experience"
                                    self.db.add_bullet(section, bullet, source_file=filename)
                                    count += 1
            return count

        def on_done(count):
            self._refresh_sections()
            self._refresh_bullets()
            self._set_status(f"Imported {count} new bullets")
            QMessageBox.information(self, "Import Complete", f"Added {count} new bullets")

        worker = SimpleWorker(do_import)
        worker.finished.connect(on_done)
        worker.error.connect(lambda e: QMessageBox.warning(self, "Error", e))
        self._workers.append(worker)
        worker.start()

    def _on_export_md(self) -> None:
        from jobhunter.config import _APP_DIR
        out_path = _APP_DIR / "data" / "resumelibrary.md"
        self.db.export_markdown(out_path)
        self._set_status(f"Exported to {out_path}")
        QMessageBox.information(self, "Export Complete", f"Saved to:\n{out_path}")

    def _update_stats(self) -> None:
        total = self.db.total_bullets()
        sections = len(self.db.get_sections())
        self._stats_label.setText(f"Library: {total} bullets across {sections} sections")
