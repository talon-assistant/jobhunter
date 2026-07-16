"""Bullet Coach dialog: turn plain-language work stories into resume bullets.

The flow is built for the blank-page moment: the user describes what they
did in their own words, the AI drafts bullets WITHOUT inventing numbers
(placeholders + questions instead), and instant rule-based feedback guides
editing until each bullet is strong enough to keep.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QListWidget, QListWidgetItem, QComboBox, QMessageBox,
    QInputDialog, QGroupBox, QSplitter, QWidget,
)

from jobhunter.core.bullet_coach import check_bullet, draft_bullets, improve_bullet
from jobhunter.core.llm_client import LLMClient
from jobhunter.core.resume_db import ResumeDB
from jobhunter.gui.workers import SimpleWorker

log = logging.getLogger(__name__)

_DEFAULT_SECTIONS = ["experience", "skills", "summary", "projects", "education", "certifications"]


class BulletCoachDialog(QDialog):
    """Describe → draft → polish → add to library."""

    def __init__(
        self,
        resume_db: ResumeDB,
        llm_client: LLMClient | None,
        *,
        default_section: str = "experience",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.db = resume_db
        self.llm = llm_client
        self._workers: list[SimpleWorker] = []
        self._drafts: list[dict] = []  # {"text": str, "questions": [str]}

        self.setWindowTitle("Bullet Coach")
        self.setMinimumSize(860, 620)
        self._build_ui(default_section)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self, default_section: str) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Tell me what you did in your own words — messy is fine. "
            "I'll draft resume bullets from it. I never make up numbers: "
            "where a metric would help, you'll see a [placeholder] and a "
            "question instead."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # -- Input area --
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Your role/title (optional):"))
        self._role_input = QLineEdit()
        self._role_input.setPlaceholderText("e.g., SOC Manager at a fintech")
        input_row.addWidget(self._role_input, stretch=1)
        layout.addLayout(input_row)

        self._description = QTextEdit()
        self._description.setPlaceholderText(
            "Example: I ran the security operations team for about three years. "
            "We built some automation for phishing triage that meant the "
            "analysts didn't have to look at every alert by hand anymore, and "
            "our response times got a lot better. I also did the vendor "
            "reviews and ran the on-call rotation..."
        )
        self._description.setMaximumHeight(110)
        layout.addWidget(self._description)

        draft_row = QHBoxLayout()
        self._btn_draft = QPushButton("Draft Bullets with AI")
        self._btn_draft.setProperty("primary", True)
        self._btn_draft.clicked.connect(self._on_draft)
        draft_row.addWidget(self._btn_draft)
        self._draft_status = QLabel("")
        self._draft_status.setProperty("dim", True)
        draft_row.addWidget(self._draft_status)
        draft_row.addStretch()
        layout.addLayout(draft_row)

        # -- Results: drafts list + editor side by side --
        splitter = QSplitter(Qt.Horizontal)

        drafts_box = QGroupBox("Drafts (check the ones to keep)")
        drafts_layout = QVBoxLayout(drafts_box)
        self._draft_list = QListWidget()
        self._draft_list.currentItemChanged.connect(self._on_draft_selected)
        drafts_layout.addWidget(self._draft_list)
        splitter.addWidget(drafts_box)

        editor_box = QGroupBox("Polish")
        editor_layout = QVBoxLayout(editor_box)

        self._editor = QTextEdit()
        self._editor.setMaximumHeight(80)
        self._editor.setPlaceholderText("Select a draft to edit it here...")
        self._editor.textChanged.connect(self._on_editor_changed)
        editor_layout.addWidget(self._editor)

        self._feedback = QLabel("")
        self._feedback.setWordWrap(True)
        self._feedback.setProperty("dim", True)
        editor_layout.addWidget(self._feedback)

        self._questions = QLabel("")
        self._questions.setWordWrap(True)
        self._questions.setStyleSheet("color: #ffb74d;")
        editor_layout.addWidget(self._questions)

        editor_btns = QHBoxLayout()
        btn_apply = QPushButton("Apply Edit")
        btn_apply.clicked.connect(self._on_apply_edit)
        editor_btns.addWidget(btn_apply)

        self._btn_improve = QPushButton("Improve with AI")
        self._btn_improve.clicked.connect(self._on_improve)
        editor_btns.addWidget(self._btn_improve)
        editor_btns.addStretch()
        editor_layout.addLayout(editor_btns)
        editor_layout.addStretch()

        splitter.addWidget(editor_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

        # -- Bottom: add to library --
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Add to section:"))
        self._section_combo = QComboBox()
        self._section_combo.setEditable(True)
        sections = list(dict.fromkeys(self.db.get_sections() + _DEFAULT_SECTIONS))
        self._section_combo.addItems(sections)
        self._section_combo.setCurrentText(default_section)
        bottom.addWidget(self._section_combo)

        self._btn_add = QPushButton("Add Checked to Library")
        self._btn_add.setProperty("primary", True)
        self._btn_add.clicked.connect(self._on_add_checked)
        bottom.addWidget(self._btn_add)

        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    # Drafting
    # ------------------------------------------------------------------

    def _on_draft(self) -> None:
        description = self._description.toPlainText().strip()
        if len(description) < 20:
            QMessageBox.information(
                self, "Tell Me More",
                "Give me a sentence or two about what you did — even rough "
                "notes are enough to start.",
            )
            return
        if not self.llm:
            QMessageBox.warning(
                self, "No AI Provider",
                "Configure an AI provider in Settings to use drafting.\n\n"
                "You can still write bullets by hand and get instant "
                "feedback in the Polish box.",
            )
            return

        role = self._role_input.text().strip()
        section = self._section_combo.currentText().strip() or "experience"

        self._btn_draft.setEnabled(False)
        self._draft_status.setText("Drafting... (a few seconds)")

        def do_draft():
            return draft_bullets(self.llm, description, role=role, section=section)

        def on_done(drafts):
            self._btn_draft.setEnabled(True)
            if not drafts:
                self._draft_status.setText(
                    "No drafts came back — try adding a little more detail."
                )
                return
            self._draft_status.setText(
                f"{len(drafts)} draft(s). Click one to polish it; orange "
                "questions show where a real number would help."
            )
            self._drafts.extend(drafts)
            self._refresh_drafts(select_last_added=len(drafts))

        def on_error(err):
            self._btn_draft.setEnabled(True)
            self._draft_status.setText("")
            QMessageBox.warning(self, "Drafting Failed", str(err))

        worker = SimpleWorker(do_draft)
        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _refresh_drafts(self, select_last_added: int = 0) -> None:
        previously_checked = {
            self._draft_list.item(i).data(Qt.UserRole)
            for i in range(self._draft_list.count())
            if self._draft_list.item(i).checkState() == Qt.Checked
        }
        self._draft_list.clear()
        for idx, draft in enumerate(self._drafts):
            needs_input = "❓ " if draft["questions"] or "[" in draft["text"] else ""
            item = QListWidgetItem(f"{needs_input}{draft['text']}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            new_default = idx >= len(self._drafts) - select_last_added
            item.setCheckState(
                Qt.Checked if (idx in previously_checked or new_default) else Qt.Unchecked
            )
            item.setData(Qt.UserRole, idx)
            self._draft_list.addItem(item)

    # ------------------------------------------------------------------
    # Polishing
    # ------------------------------------------------------------------

    def _current_draft_index(self) -> int | None:
        item = self._draft_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_draft_selected(self, current, previous) -> None:
        idx = current.data(Qt.UserRole) if current else None
        if idx is None or idx >= len(self._drafts):
            return
        draft = self._drafts[idx]
        self._editor.blockSignals(True)
        self._editor.setPlainText(draft["text"])
        self._editor.blockSignals(False)
        self._update_feedback(draft["text"])
        if draft["questions"]:
            self._questions.setText(
                "To fill in the blanks: " + "  •  ".join(draft["questions"])
            )
        else:
            self._questions.setText("")

    def _on_editor_changed(self) -> None:
        self._update_feedback(self._editor.toPlainText())

    def _update_feedback(self, text: str) -> None:
        checks = check_bullet(text)
        if not checks:
            self._feedback.setText("")
            return
        lines = []
        for c in checks:
            mark = "✓" if c.ok else "•"
            lines.append(f"{mark} {c.message}")
        self._feedback.setText("\n".join(lines))
        issues = [c for c in checks if not c.ok]
        self._feedback.setStyleSheet(
            "color: #81c784;" if not issues else "color: #cccccc;"
        )

    def _on_apply_edit(self) -> None:
        idx = self._current_draft_index()
        text = self._editor.toPlainText().strip()
        if not text:
            return
        if idx is None:
            # Nothing selected: treat the editor as a hand-written draft
            self._drafts.append({"text": text, "questions": []})
            self._refresh_drafts(select_last_added=1)
            return
        self._drafts[idx]["text"] = text
        # Placeholders resolved? Clear the stored questions.
        if "[" not in text:
            self._drafts[idx]["questions"] = []
            self._questions.setText("")
        self._refresh_drafts()

    def _on_improve(self) -> None:
        text = self._editor.toPlainText().strip()
        if not text:
            return
        if not self.llm:
            QMessageBox.warning(self, "No AI Provider", "Configure an AI provider in Settings first.")
            return

        role = self._role_input.text().strip()
        self._btn_improve.setEnabled(False)

        def do_improve():
            return improve_bullet(self.llm, text, role=role)

        def on_done(result):
            self._btn_improve.setEnabled(True)
            variants = result.get("variants", [])
            if not variants:
                QMessageBox.information(self, "No Suggestions", "The AI had nothing better — that's a good sign.")
                return
            options = [f"[{v['style']}] {v['text']}" for v in variants]
            choice, ok = QInputDialog.getItem(
                self, "Pick a Version",
                "Three takes on your bullet — pick one or press Cancel to keep yours:",
                options, 0, False,
            )
            if ok and choice:
                picked = variants[options.index(choice)]["text"]
                self._editor.setPlainText(picked)
                self._on_apply_edit()

        def on_error(err):
            self._btn_improve.setEnabled(True)
            QMessageBox.warning(self, "Improve Failed", str(err))

        worker = SimpleWorker(do_improve)
        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # Adding to the library
    # ------------------------------------------------------------------

    def _on_add_checked(self) -> None:
        section = self._section_combo.currentText().strip()
        if not section:
            QMessageBox.warning(self, "No Section", "Pick or type a section name first.")
            return

        checked = [
            self._drafts[self._draft_list.item(i).data(Qt.UserRole)]
            for i in range(self._draft_list.count())
            if self._draft_list.item(i).checkState() == Qt.Checked
        ]
        if not checked:
            QMessageBox.information(self, "Nothing Checked", "Check at least one draft to add.")
            return

        unresolved = [d for d in checked if "[" in d["text"]]
        if unresolved:
            reply = QMessageBox.question(
                self, "Placeholders Remain",
                f"{len(unresolved)} bullet(s) still have [placeholders] "
                "waiting for your real numbers. Add them anyway?\n\n"
                "(You can fill them in later from the Resume Library.)",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        added = 0
        skipped = 0
        for draft in checked:
            if self.db.find_duplicates(draft["text"], threshold=0.92):
                skipped += 1
                continue
            self.db.add_bullet(section, draft["text"], source_file="bullet_coach")
            added += 1

        msg = f"Added {added} bullet(s) to '{section}'."
        if skipped:
            msg += f" Skipped {skipped} that were already in your library."
        QMessageBox.information(self, "Done", msg)

        # Remove the added drafts so the list reflects what's left
        added_texts = {d["text"] for d in checked}
        self._drafts = [d for d in self._drafts if d["text"] not in added_texts]
        self._refresh_drafts()
        self._editor.clear()
        self._questions.setText("")
