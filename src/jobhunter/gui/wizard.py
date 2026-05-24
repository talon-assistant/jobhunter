"""First-run setup wizard (PySide6).

Guides the user through:
  1. LLM provider selection + test
  2. Personal info (name, email, phone, location)
  3. Resume import (browse files, remove files, or import existing library)
  4. Interactive bullet review (dedup, edit, delete, set priority)
  5. LinkedIn login (opens visible browser, installs Chromium if needed)
  6. First search URL generation
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QRadioButton, QButtonGroup,
    QFileDialog, QListWidget, QListWidgetItem, QTextEdit,
    QMessageBox, QProgressBar, QGroupBox, QFormLayout, QSpinBox,
    QSplitter, QApplication,
)

from jobhunter.config import Config
from jobhunter.core.llm_client import LLMClient
from jobhunter.gui.workers import BackgroundWorker, SimpleWorker

log = logging.getLogger(__name__)


class SetupWizard(QWizard):
    """First-run setup wizard."""

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._workers: list[SimpleWorker] = []

        self.setWindowTitle("JobHunter Setup")
        self.setMinimumSize(800, 600)
        self.setWizardStyle(QWizard.ModernStyle)

        self.addPage(WelcomePage())
        self.addPage(ProviderPage(config))
        self.addPage(PersonalInfoPage(config))
        self._import_page = ResumeImportPage(config)
        self.addPage(self._import_page)
        self._review_page = BulletReviewPage(config)
        self.addPage(self._review_page)
        self.addPage(LinkedInLoginPage(config))
        self.addPage(FirstSearchPage(config))
        self.addPage(FinishPage())


class WelcomePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Welcome to JobHunter")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "<h2>Let's get you set up</h2>"
            "<p>This wizard will walk you through:</p>"
            "<ol>"
            "<li>Choosing your AI provider (Claude, OpenAI, Gemini, etc.)</li>"
            "<li>Entering your contact info for resumes and cover letters</li>"
            "<li>Importing your existing resumes to build a bullet library</li>"
            "<li>Reviewing and organizing your resume bullets</li>"
            "<li>Logging into LinkedIn for job scraping</li>"
            "<li>Setting up your first job search</li>"
            "</ol>"
            "<p>This takes about 10-15 minutes. You can change everything later in Settings.</p>"
        ))
        layout.addStretch()


class ProviderPage(QWizardPage):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setTitle("Choose AI Provider")
        self.setSubTitle("Select which AI service to use for scoring, cover letters, and resume tailoring.")

        layout = QVBoxLayout(self)

        self._group = QButtonGroup(self)
        providers = [
            ("claude-cli", "Claude CLI (Recommended)",
             "Uses your installed Claude Code. No API key needed."),
            ("anthropic", "Anthropic API",
             "Direct API access to Claude. Requires an API key from console.anthropic.com."),
            ("openai", "OpenAI API",
             "Use GPT-4o or other OpenAI models. Requires an API key from platform.openai.com."),
            ("gemini", "Google Gemini API",
             "Use Gemini models. Requires an API key from aistudio.google.com."),
            ("openai-compatible", "Other / Local Server",
             "Any OpenAI-compatible endpoint (Ollama, llama-server, etc.)"),
        ]

        current = config.get("llm.provider", "claude-cli")
        for i, (key, name, desc) in enumerate(providers):
            radio = QRadioButton(f"{name}\n{desc}")
            radio.setProperty("provider_key", key)
            if key == current:
                radio.setChecked(True)
            self._group.addButton(radio, i)
            layout.addWidget(radio)

        layout.addSpacing(10)

        key_group = QGroupBox("API Key")
        key_layout = QHBoxLayout(key_group)
        self._api_key = QLineEdit()
        self._api_key.setPlaceholderText("Paste your API key here")
        self._api_key.setEchoMode(QLineEdit.Password)
        key_layout.addWidget(self._api_key)

        btn_test = QPushButton("Test")
        btn_test.clicked.connect(self._on_test)
        key_layout.addWidget(btn_test)

        self._test_label = QLabel("")
        key_layout.addWidget(self._test_label)
        layout.addWidget(key_group)

        self._endpoint_group = QGroupBox("Endpoint URL")
        ep_layout = QHBoxLayout(self._endpoint_group)
        self._endpoint = QLineEdit()
        self._endpoint.setPlaceholderText("http://localhost:8080/v1/chat/completions")
        ep_layout.addWidget(self._endpoint)
        layout.addWidget(self._endpoint_group)

        self._group.buttonClicked.connect(self._on_provider_change)
        self._on_provider_change()
        layout.addStretch()

    def _selected_provider(self) -> str:
        btn = self._group.checkedButton()
        return btn.property("provider_key") if btn else "claude-cli"

    def _on_provider_change(self, *_) -> None:
        provider = self._selected_provider()
        needs_key = provider in ("anthropic", "openai", "gemini", "openai-compatible")
        self._api_key.parentWidget().setVisible(needs_key)
        self._endpoint_group.setVisible(provider == "openai-compatible")

        if provider == "claude-cli":
            has_cli = shutil.which("claude") is not None
            self._test_label.setText("Claude CLI found" if has_cli else "Claude CLI not found — install Claude Code first")
            self._test_label.setStyleSheet("color: #81c784;" if has_cli else "color: #ef5350;")

    def _on_test(self) -> None:
        provider = self._selected_provider()
        client = LLMClient(
            provider=provider,
            api_key=self._api_key.text().strip(),
            endpoint=self._endpoint.text().strip(),
        )
        try:
            client.generate_text("Reply: OK", max_tokens=10)
            self._test_label.setText("Connected!")
            self._test_label.setStyleSheet("color: #81c784;")
        except Exception as exc:
            self._test_label.setText(str(exc)[:80])
            self._test_label.setStyleSheet("color: #ef5350;")

    def validatePage(self) -> bool:
        provider = self._selected_provider()
        api_key = self._api_key.text().strip()
        self.config.set("llm.provider", provider)
        self.config.save()
        if api_key:
            try:
                import keyring
                keyring.set_password("jobhunter", f"api_key_{provider}", api_key)
            except Exception:
                pass
        return True


class PersonalInfoPage(QWizardPage):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setTitle("Your Information")
        self.setSubTitle("This appears on generated resumes and cover letters.")

        layout = QFormLayout(self)
        self._name = QLineEdit(config.get("resume.name", ""))
        self._name.setPlaceholderText("Your full name")
        layout.addRow("Name:", self._name)
        self._email = QLineEdit(config.get("resume.email", ""))
        layout.addRow("Email:", self._email)
        self._phone = QLineEdit(config.get("resume.phone", ""))
        layout.addRow("Phone:", self._phone)
        self._location = QLineEdit(config.get("resume.location", ""))
        self._location.setPlaceholderText("e.g., Columbus, OH")
        layout.addRow("Location:", self._location)

    def validatePage(self) -> bool:
        self.config.set("resume.name", self._name.text())
        self.config.set("resume.email", self._email.text())
        self.config.set("resume.phone", self._phone.text())
        self.config.set("resume.location", self._location.text())
        self.config.save()
        return True


class ResumeImportPage(QWizardPage):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setTitle("Import Your Resumes")
        self.setSubTitle(
            "Add your resume files to extract bullet points. You can also import "
            "an existing bullet library markdown if you have one."
        )

        layout = QVBoxLayout(self)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_browse = QPushButton("Browse for Resume Files")
        btn_browse.setProperty("primary", True)
        btn_browse.clicked.connect(self._on_browse)
        btn_row.addWidget(btn_browse)

        btn_remove = QPushButton("Remove Selected")
        btn_remove.setProperty("danger", True)
        btn_remove.clicked.connect(self._on_remove)
        btn_row.addWidget(btn_remove)

        btn_row.addStretch()

        btn_library = QPushButton("Import Existing Library (.md)")
        btn_library.clicked.connect(self._on_import_library)
        btn_row.addWidget(btn_library)

        layout.addLayout(btn_row)

        # File list
        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self._file_list)

        self._status = QLabel(
            "No files selected yet. You can also skip this and import later "
            "from the Resume Library tab."
        )
        self._status.setProperty("dim", True)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._library_path: str = ""

    def _on_browse(self) -> None:
        from jobhunter.core.doc_extractor import supported_extensions
        ext_filter = "Resume Files (" + " ".join(f"*{e}" for e in supported_extensions()) + ")"
        files, _ = QFileDialog.getOpenFileNames(self, "Select Resume Files", "", ext_filter)
        for f in files:
            existing = [
                self._file_list.item(i).data(Qt.UserRole)
                for i in range(self._file_list.count())
            ]
            if f not in existing:
                item = QListWidgetItem(Path(f).name)
                item.setData(Qt.UserRole, f)
                self._file_list.addItem(item)
        self._update_status()

    def _on_remove(self) -> None:
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))
        self._update_status()

    def _on_import_library(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Bullet Library", "", "Markdown Files (*.md);;All Files (*)"
        )
        if path:
            self._library_path = path
            # Add it to the list with a special marker
            item = QListWidgetItem(f"[LIBRARY] {Path(path).name}")
            item.setData(Qt.UserRole, f"library:{path}")
            self._file_list.addItem(item)
            self._update_status()

    def _update_status(self) -> None:
        count = self._file_list.count()
        if count:
            self._status.setText(
                f"{count} file(s) selected. Click Next to extract and review bullets."
            )
        else:
            self._status.setText(
                "No files selected. You can skip this and import later."
            )

    def get_files(self) -> list[str]:
        """Return list of resume file paths (not library imports)."""
        files = []
        for i in range(self._file_list.count()):
            path = self._file_list.item(i).data(Qt.UserRole)
            if not path.startswith("library:"):
                files.append(path)
        return files

    def get_library_path(self) -> str:
        """Return the library markdown path if one was selected."""
        for i in range(self._file_list.count()):
            path = self._file_list.item(i).data(Qt.UserRole)
            if path.startswith("library:"):
                return path[len("library:"):]
        return ""


class BulletReviewPage(QWizardPage):
    """Interactive bullet review: dedup, edit, delete, set priority."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setTitle("Review Your Bullets")
        self.setSubTitle(
            "We extracted these bullets from your resumes. "
            "Review, edit, delete duplicates, and set priorities."
        )
        self._bullets: list[dict] = []  # {section, role, text, source, priority}
        self._workers: list[SimpleWorker] = []

        layout = QVBoxLayout(self)

        # Progress bar (for extraction)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)

        # Splitter: bullet list + edit pane
        splitter = QSplitter(Qt.Horizontal)

        # Left: bullet list
        left = QVBoxLayout()
        left_widget = QGroupBox("Extracted Bullets")
        left_inner = QVBoxLayout(left_widget)

        self._bullet_list = QListWidget()
        self._bullet_list.currentItemChanged.connect(self._on_bullet_selected)
        left_inner.addWidget(self._bullet_list)

        list_btns = QHBoxLayout()
        btn_delete = QPushButton("Delete Selected")
        btn_delete.setProperty("danger", True)
        btn_delete.clicked.connect(self._on_delete)
        list_btns.addWidget(btn_delete)

        btn_dedup = QPushButton("Auto-Remove Duplicates")
        btn_dedup.clicked.connect(self._on_dedup)
        list_btns.addWidget(btn_dedup)

        self._count_label = QLabel("0 bullets")
        self._count_label.setProperty("dim", True)
        list_btns.addWidget(self._count_label)
        list_btns.addStretch()

        left_inner.addLayout(list_btns)
        splitter.addWidget(left_widget)

        # Right: edit pane
        right_widget = QGroupBox("Edit Bullet")
        right_layout = QVBoxLayout(right_widget)

        right_layout.addWidget(QLabel("Section:"))
        self._edit_section = QLineEdit()
        right_layout.addWidget(self._edit_section)

        right_layout.addWidget(QLabel("Role:"))
        self._edit_role = QLineEdit()
        right_layout.addWidget(self._edit_role)

        right_layout.addWidget(QLabel("Text:"))
        self._edit_text = QTextEdit()
        self._edit_text.setMaximumHeight(100)
        right_layout.addWidget(self._edit_text)

        right_layout.addWidget(QLabel("Priority:"))
        self._edit_priority = QComboBox()
        self._edit_priority.addItems(["strong", "normal", "weak"])
        right_layout.addWidget(self._edit_priority)

        right_layout.addWidget(QLabel("Source:"))
        self._edit_source = QLabel("")
        self._edit_source.setProperty("dim", True)
        right_layout.addWidget(self._edit_source)

        btn_save = QPushButton("Save Changes")
        btn_save.setProperty("primary", True)
        btn_save.clicked.connect(self._on_save_edit)
        right_layout.addWidget(btn_save)

        right_layout.addStretch()
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def initializePage(self) -> None:
        """Called when the page is shown — extract bullets from files."""
        wizard = self.wizard()
        import_page = None
        for pid in wizard.pageIds():
            page = wizard.page(pid)
            if isinstance(page, ResumeImportPage):
                import_page = page
                break

        if not import_page:
            return

        files = import_page.get_files()
        library_path = import_page.get_library_path()

        if not files and not library_path:
            self._bullet_list.clear()
            self._bullet_list.addItem(
                QListWidgetItem("No files to import. Click Next to continue.")
            )
            return

        self._progress.setVisible(True)
        self._progress_label.setVisible(True)
        self._progress.setValue(0)
        self._progress.setMaximum(100)
        self._progress_label.setText("Preparing extraction...")
        self._bullet_list.clear()
        self._bullets = []

        self._llm_available = False
        self._llm_error_msg = ""

        def do_extract(progress_callback):
            extracted = []

            done = 0

            # Import existing library first
            if library_path:
                progress_callback(0, f"Importing library: {Path(library_path).name}")
                extracted.extend(self._parse_library_md(library_path))
                done += 1

            if not files:
                return extracted

            # Extract from resume files
            from jobhunter.core.doc_extractor import extract_text

            # Test LLM availability before starting
            provider = self.config.get("llm.provider", "claude-cli")
            api_key = ""
            try:
                import keyring
                api_key = keyring.get_password("jobhunter", f"api_key_{provider}") or ""
            except Exception:
                pass

            llm = None
            extract_prompt = ""
            prompt_path = Path(__file__).parent.parent / "prompts" / "extract_bullets.txt"
            if prompt_path.exists():
                extract_prompt = prompt_path.read_text(encoding="utf-8")

            try:
                llm = LLMClient(provider=provider, api_key=api_key)
                if not llm.is_healthy():
                    self._llm_error_msg = f"LLM provider '{provider}' is not available. Using smart text extraction instead."
                    llm = None
                else:
                    self._llm_available = True
            except Exception as exc:
                self._llm_error_msg = f"LLM not available ({exc}). Using smart text extraction instead."
                llm = None

            if not llm:
                progress_callback(0, self._llm_error_msg)

            for idx, fpath in enumerate(files):
                filename = Path(fpath).name
                method = "LLM" if llm else "text"
                pct = int((done + idx) / (len(files) + done) * 100)
                progress_callback(
                    pct,
                    f"[{idx+1}/{len(files)}] Extracting ({method}): {filename}"
                )

                text = extract_text(fpath)
                if not text:
                    progress_callback(
                        pct,
                        f"[{idx+1}/{len(files)}] Skipped (no text): {filename}"
                    )
                    continue

                if llm and extract_prompt:
                    try:
                        prompt = extract_prompt.replace("{{DOCUMENT}}", text[:8000])
                        prompt = prompt.replace("{{FILENAME}}", filename)
                        result = llm.generate_json(
                            prompt,
                            {"type": "object", "properties": {"roles": {"type": "array"}}},
                            system_prompt="Extract bullets exactly as written.",
                        )
                        roles = result.get("roles", []) if isinstance(result, dict) else []
                        for role in roles:
                            for bullet in role.get("bullets", []):
                                bullet = bullet.strip()
                                if bullet and len(bullet) > 10:
                                    extracted.append({
                                        "section": role.get("section", "experience"),
                                        "role": role.get("role", ""),
                                        "text": bullet,
                                        "source": filename,
                                        "priority": "normal",
                                    })
                    except Exception as exc:
                        log.exception("LLM extraction failed for %s", filename)
                        progress_callback(
                            pct,
                            f"[{idx+1}/{len(files)}] LLM failed for {filename}, using text extraction..."
                        )
                        extracted.extend(self._smart_extract(text, filename))
                else:
                    extracted.extend(self._smart_extract(text, filename))

            return extracted

        def on_done(extracted):
            self._bullets = extracted
            self._refresh_list()
            self._progress.setVisible(False)
            if extracted:
                msg = f"Extracted {len(extracted)} bullets from {len(files)} file(s)."
                if self._llm_error_msg:
                    msg += f"\n{self._llm_error_msg}"
                self._progress_label.setText(msg)
                self._progress_label.setStyleSheet("color: #81c784;")
            else:
                msg = "No bullets extracted."
                if self._llm_error_msg:
                    msg += f"\n{self._llm_error_msg}"
                msg += "\nTry configuring an LLM provider in the previous step, or add bullets manually later."
                self._progress_label.setText(msg)
                self._progress_label.setStyleSheet("color: #ef5350;")
            self._progress_label.setWordWrap(True)

        def on_error(err):
            self._progress.setVisible(False)
            self._progress_label.setVisible(True)
            self._progress_label.setText(f"Extraction error:\n{err}")
            self._progress_label.setStyleSheet("color: #ef5350;")
            self._progress_label.setWordWrap(True)

        def on_progress(pct, msg):
            self._progress.setValue(pct)
            self._progress_label.setText(msg)

        worker = BackgroundWorker(do_extract)
        worker._name = "bullet_extract"
        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(on_progress)
        self._workers.append(worker)
        worker.start()

    @staticmethod
    def _smart_extract(text: str, filename: str) -> list[dict]:
        """Extract bullet-like lines from resume text without an LLM.

        Handles multiple formats:
        - Markdown bullets (- , * )
        - Unicode bullets (bullet, arrow, diamond, etc.)
        - Lines that start with action verbs (Led, Built, Managed, etc.)
        - Numbered list items
        """
        import re

        ACTION_VERBS = {
            "led", "managed", "built", "developed", "designed", "implemented",
            "created", "launched", "directed", "established", "delivered",
            "reduced", "increased", "improved", "achieved", "negotiated",
            "orchestrated", "spearheaded", "transformed", "streamlined",
            "automated", "architected", "deployed", "migrated", "consolidated",
            "mentored", "trained", "supervised", "coordinated", "executed",
            "analyzed", "optimized", "secured", "maintained", "administered",
            "oversaw", "pioneered", "introduced", "resolved", "eliminated",
        }

        # Patterns that indicate a bullet point
        BULLET_PREFIXES = re.compile(
            r"^(?:"
            r"[-*•◦▪▸►➤→‣⁃]\s+"          # Common bullet chars
            r"|\d+[.)]\s+"                  # Numbered lists: 1. or 1)
            r"|[a-z][.)]\s+"               # Lettered lists: a. or a)
            r")"
        )

        bullets = []
        lines = text.splitlines()

        for line in lines:
            stripped = line.strip()
            if not stripped or len(stripped) < 15:
                continue

            # Skip likely headers (all caps, very short, or no lowercase)
            if stripped.isupper() and len(stripped) < 60:
                continue
            # Skip contact info patterns
            if "@" in stripped and len(stripped) < 80:
                continue
            if re.match(r"^\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", stripped):
                continue
            # Skip dates-only lines
            if re.match(r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", stripped):
                if len(stripped) < 40:
                    continue

            is_bullet = False
            clean_text = stripped

            # Check for bullet prefix
            m = BULLET_PREFIXES.match(stripped)
            if m:
                is_bullet = True
                clean_text = stripped[m.end():].strip()

            # Check for action verb start (common in resume bullets)
            if not is_bullet:
                first_word = stripped.split()[0].rstrip(",:;").lower()
                if first_word in ACTION_VERBS:
                    is_bullet = True
                    clean_text = stripped

            if is_bullet and len(clean_text) >= 15 and len(clean_text) <= 500:
                bullets.append({
                    "section": "experience",
                    "role": "",
                    "text": clean_text,
                    "source": filename,
                    "priority": "normal",
                })

        return bullets

    @staticmethod
    def _parse_library_md(path: str) -> list[dict]:
        """Parse a resumelibrary.md file into bullet dicts."""
        text = Path(path).read_text(encoding="utf-8")
        bullets = []
        current_section = ""
        current_role = ""

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                current_section = stripped[3:].strip()
                current_role = ""
            elif stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("- "):
                current_role = stripped.strip("*").strip()
            elif stripped.startswith("- ") and current_section:
                bullet = stripped[2:].strip()
                if bullet:
                    bullets.append({
                        "section": current_section,
                        "role": current_role,
                        "text": bullet,
                        "source": Path(path).name,
                        "priority": "normal",
                    })
        return bullets

    def _refresh_list(self) -> None:
        self._bullet_list.clear()
        for i, b in enumerate(self._bullets):
            indicator = {"strong": "★", "normal": "●", "weak": "○"}.get(b["priority"], "●")
            label = f"{indicator} [{b['section']}] {b['text'][:100]}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, i)
            self._bullet_list.addItem(item)
        self._count_label.setText(f"{len(self._bullets)} bullets")

    def _on_bullet_selected(self, current, previous) -> None:
        if not current:
            return
        idx = current.data(Qt.UserRole)
        if idx is None or idx >= len(self._bullets):
            return
        b = self._bullets[idx]
        self._edit_section.setText(b["section"])
        self._edit_role.setText(b["role"])
        self._edit_text.setPlainText(b["text"])
        self._edit_priority.setCurrentText(b["priority"])
        self._edit_source.setText(f"Source: {b['source']}")

    def _on_save_edit(self) -> None:
        current = self._bullet_list.currentItem()
        if not current:
            return
        idx = current.data(Qt.UserRole)
        if idx is None or idx >= len(self._bullets):
            return
        self._bullets[idx]["section"] = self._edit_section.text().strip()
        self._bullets[idx]["role"] = self._edit_role.text().strip()
        self._bullets[idx]["text"] = self._edit_text.toPlainText().strip()
        self._bullets[idx]["priority"] = self._edit_priority.currentText()
        self._refresh_list()

    def _on_delete(self) -> None:
        selected = self._bullet_list.selectedItems()
        if not selected:
            return
        indices = sorted([item.data(Qt.UserRole) for item in selected], reverse=True)
        for idx in indices:
            if idx is not None and idx < len(self._bullets):
                self._bullets.pop(idx)
        self._refresh_list()

    def _on_dedup(self) -> None:
        """Remove near-duplicate bullets using simple text similarity."""
        if len(self._bullets) < 2:
            return

        # Simple dedup: normalize and compare
        seen: dict[str, int] = {}
        to_remove: list[int] = []

        for i, b in enumerate(self._bullets):
            # Normalize: lowercase, strip punctuation, collapse whitespace
            normalized = " ".join(b["text"].lower().split())
            # Check for exact or near matches
            found_dupe = False
            for existing_norm, existing_idx in seen.items():
                if normalized == existing_norm:
                    to_remove.append(i)
                    found_dupe = True
                    break
                # Simple substring check for very similar bullets
                shorter, longer = sorted([normalized, existing_norm], key=len)
                if len(shorter) > 20 and shorter in longer:
                    to_remove.append(i)
                    found_dupe = True
                    break
            if not found_dupe:
                seen[normalized] = i

        if not to_remove:
            QMessageBox.information(self, "No Duplicates", "No duplicate bullets found.")
            return

        reply = QMessageBox.question(
            self, "Remove Duplicates",
            f"Found {len(to_remove)} duplicate(s). Remove them?",
        )
        if reply == QMessageBox.Yes:
            for idx in sorted(to_remove, reverse=True):
                self._bullets.pop(idx)
            self._refresh_list()

    def get_bullets(self) -> list[dict]:
        """Return the reviewed bullet list."""
        return list(self._bullets)


class LinkedInLoginPage(QWizardPage):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setTitle("LinkedIn Login")
        self.setSubTitle(
            "Click the button below to open a browser window. "
            "Log into LinkedIn manually — your session will be saved securely."
        )

        layout = QVBoxLayout(self)

        self._btn_login = QPushButton("Open LinkedIn Login")
        self._btn_login.setProperty("primary", True)
        self._btn_login.clicked.connect(self._on_login)
        layout.addWidget(self._btn_login)

        self._status = QLabel(
            "This step is optional. If you skip it, you can log in later or "
            "use other job boards (Dice, Built In) without login."
        )
        self._status.setWordWrap(True)
        self._status.setProperty("dim", True)
        layout.addWidget(self._status)
        layout.addStretch()

    def _on_login(self) -> None:
        self._btn_login.setEnabled(False)
        self._status.setText("Checking for Chromium browser...")
        QApplication.processEvents()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._status.setText("Playwright not installed. Skipping LinkedIn login.")
            self._status.setStyleSheet("color: #ef5350;")
            self._btn_login.setEnabled(True)
            return

        # Check if Chromium is installed by trying to launch
        chromium_ok = False
        pw = sync_playwright().start()
        try:
            test_browser = pw.chromium.launch(headless=True)
            test_browser.close()
            chromium_ok = True
        except Exception:
            pw.stop()

            # Chromium not installed — offer to download
            reply = QMessageBox.question(
                self, "Install Chromium",
                "Playwright Chromium browser is not installed.\n\n"
                "Download it now? (~150MB)\n\n"
                "This is needed for LinkedIn scraping.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self._status.setText("Skipped. You can install Chromium later.")
                self._btn_login.setEnabled(True)
                return

            self._status.setText("Downloading Chromium... this may take a minute.")
            QApplication.processEvents()

            # Use playwright's Python API to install, not subprocess
            # (subprocess doesn't work in PyInstaller bundles)
            try:
                from playwright._impl._driver import compute_driver_executable
                driver_exec = compute_driver_executable()
                result = subprocess.run(
                    [str(driver_exec), "install", "chromium"],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    self._status.setText(
                        f"Failed to install Chromium.\n{result.stderr[:200]}\n"
                        "You can try manually: playwright install chromium"
                    )
                    self._status.setStyleSheet("color: #ef5350;")
                    self._btn_login.setEnabled(True)
                    return
                chromium_ok = True
            except Exception as exc:
                self._status.setText(f"Failed to install Chromium: {exc}")
                self._status.setStyleSheet("color: #ef5350;")
                self._btn_login.setEnabled(True)
                return

            pw = sync_playwright().start()

        if not chromium_ok:
            self._btn_login.setEnabled(True)
            return

        # Now do the actual login
        self._status.setText(
            "Opening browser...\n"
            "Log in to LinkedIn, then CLOSE THE BROWSER WINDOW when done."
        )
        QApplication.processEvents()

        try:
            from jobhunter.core.profile_vault import ProfileVault
            vault = ProfileVault(Path.home() / ".jobhunter")
            profile_dir = str(vault.unlock())

            browser = pw.chromium.launch_persistent_context(
                profile_dir,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.new_page()
            page.goto("https://www.linkedin.com/login")

            # Wait for ALL pages to close (user closes the browser window)
            while len(browser.pages) > 0:
                try:
                    browser.pages[-1].wait_for_event("close", timeout=300000)
                except Exception:
                    break

            try:
                browser.close()
            except Exception:
                pass
            pw.stop()

            vault.lock()
            self._status.setText("LinkedIn session saved and encrypted!")
            self._status.setStyleSheet("color: #81c784;")
        except Exception as exc:
            self._status.setText(f"Login failed: {exc}")
            self._status.setStyleSheet("color: #ef5350;")
            try:
                pw.stop()
            except Exception:
                pass
        finally:
            self._btn_login.setEnabled(True)


class FirstSearchPage(QWizardPage):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setTitle("Your First Job Search")
        self.setSubTitle(
            "Enter a job title and location to generate search URLs for multiple boards."
        )

        layout = QFormLayout(self)

        self._title = QLineEdit()
        self._title.setPlaceholderText("e.g., Security Engineer, Product Manager")
        layout.addRow("Job Title:", self._title)

        self._search_location = QLineEdit()
        self._search_location.setPlaceholderText("e.g., Remote, New York")
        layout.addRow("Location:", self._search_location)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(120)
        layout.addRow("Preview:", self._preview)

        btn_gen = QPushButton("Generate Search URLs")
        btn_gen.clicked.connect(self._on_generate)
        layout.addRow("", btn_gen)

        note = QLabel("You can also paste URLs manually in the Search URLs tab later.")
        note.setProperty("dim", True)
        note.setWordWrap(True)
        layout.addRow("", note)

        self._generated_urls: list[tuple[str, str]] = []

    def _on_generate(self) -> None:
        title = self._title.text().strip()
        loc = self._search_location.text().strip()
        if not title:
            return

        title_encoded = title.replace(" ", "%20")
        loc_encoded = loc.replace(" ", "%20") if loc else ""

        self._generated_urls = [
            ("linkedin", f"https://www.linkedin.com/jobs/search/?keywords={title_encoded}&location={loc_encoded}"),
            ("dice", f"https://www.dice.com/jobs?q={title_encoded}&location={loc_encoded}"),
            ("builtin", f"https://builtin.com/jobs?search={title_encoded}&location={loc_encoded}"),
        ]

        lines = [f"[{board}] {url}" for board, url in self._generated_urls]
        self._preview.setPlainText("\n".join(lines))

    def get_generated_urls(self) -> list[tuple[str, str]]:
        return list(self._generated_urls)


class FinishPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("All Set!")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "<h2>Setup complete</h2>"
            "<p>JobHunter is ready to use:</p>"
            "<ul>"
            "<li><b>Dashboard</b> — Click 'Run Search' to find jobs</li>"
            "<li><b>Resume Library</b> — Review and edit your bullet library</li>"
            "<li><b>Settings</b> — Fine-tune your preferences anytime</li>"
            "</ul>"
            "<p>Click Finish to start.</p>"
        ))
        layout.addStretch()
