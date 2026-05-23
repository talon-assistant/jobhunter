"""First-run setup wizard (PySide6).

Guides the user through:
  1. LLM provider selection + test
  2. Personal info (name, email, phone, location)
  3. Resume import (drop files, extract bullets, review)
  4. LinkedIn login (opens visible browser for manual login)
  5. First search URL generation
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QRadioButton, QButtonGroup,
    QFileDialog, QListWidget, QListWidgetItem, QTextEdit,
    QMessageBox, QProgressBar, QGroupBox, QFormLayout,
)

from jobhunter.config import Config
from jobhunter.core.llm_client import LLMClient
from jobhunter.gui.workers import SimpleWorker

log = logging.getLogger(__name__)


class SetupWizard(QWizard):
    """First-run setup wizard."""

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._llm_client: LLMClient | None = None
        self._workers: list[SimpleWorker] = []

        self.setWindowTitle("JobHunter Setup")
        self.setMinimumSize(700, 500)
        self.setWizardStyle(QWizard.ModernStyle)

        self.addPage(WelcomePage())
        self.addPage(ProviderPage(config))
        self.addPage(PersonalInfoPage(config))
        self.addPage(ResumeImportPage(config))
        self.addPage(LinkedInLoginPage(config))
        self.addPage(FirstSearchPage(config))
        self.addPage(FinishPage())

    def get_llm_client(self) -> LLMClient | None:
        """Return the configured LLM client after wizard completes."""
        return self._llm_client


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
            "<li>Logging into LinkedIn for job scraping</li>"
            "<li>Setting up your first job search</li>"
            "</ol>"
            "<p>This takes about 5-10 minutes. You can change everything later in Settings.</p>"
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
             "Uses your installed Claude Code. No API key needed, uses your existing plan."),
            ("anthropic", "Anthropic API",
             "Direct API access to Claude. Requires an API key from console.anthropic.com."),
            ("openai", "OpenAI API",
             "Use GPT-4o or other OpenAI models. Requires an API key from platform.openai.com."),
            ("gemini", "Google Gemini API",
             "Use Gemini models. Requires an API key from aistudio.google.com."),
            ("openai-compatible", "Other / Local Server",
             "Any OpenAI-compatible endpoint (llama-server, Ollama, etc.)"),
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

        # API key input
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

        # Endpoint input (for openai-compatible)
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
            self._test_label.setText("✓ Claude CLI found" if has_cli else "✗ Install Claude Code first")

    def _on_test(self) -> None:
        provider = self._selected_provider()
        client = LLMClient(
            provider=provider,
            api_key=self._api_key.text().strip(),
            endpoint=self._endpoint.text().strip(),
        )
        try:
            client.generate_text("Reply: OK", max_tokens=10)
            self._test_label.setText("✓ Connected!")
            self._test_label.setStyleSheet("color: #81c784;")
        except Exception as exc:
            self._test_label.setText(f"✗ {exc}")
            self._test_label.setStyleSheet("color: #ef5350;")

    def validatePage(self) -> bool:
        provider = self._selected_provider()
        api_key = self._api_key.text().strip()

        self.config.set("llm.provider", provider)
        self.config.save()

        # Save API key to keyring
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
            "Drop in your existing resume files. We'll extract bullet points to build "
            "your resume library. You can review and edit everything after setup."
        )

        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        btn_browse = QPushButton("Browse for Resume Files")
        btn_browse.setProperty("primary", True)
        btn_browse.clicked.connect(self._on_browse)
        btn_row.addWidget(btn_browse)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._file_list = QListWidget()
        layout.addWidget(self._file_list)

        self._status = QLabel("No files selected yet. You can also skip this and import later from the Resume Library tab.")
        self._status.setProperty("dim", True)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

    def _on_browse(self) -> None:
        from jobhunter.core.doc_extractor import supported_extensions
        ext_filter = "Resume Files (" + " ".join(f"*{e}" for e in supported_extensions()) + ")"
        files, _ = QFileDialog.getOpenFileNames(self, "Select Resume Files", "", ext_filter)
        for f in files:
            name = Path(f).name
            # Avoid duplicates
            existing = [self._file_list.item(i).data(Qt.UserRole) for i in range(self._file_list.count())]
            if f not in existing:
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, f)
                self._file_list.addItem(item)

        count = self._file_list.count()
        self._status.setText(f"{count} file(s) selected. They'll be processed after setup completes.")

    def get_files(self) -> list[str]:
        """Return list of file paths selected by the user."""
        return [
            self._file_list.item(i).data(Qt.UserRole)
            for i in range(self._file_list.count())
        ]


class LinkedInLoginPage(QWizardPage):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setTitle("LinkedIn Login")
        self.setSubTitle(
            "Click the button below to open a browser window. "
            "Log into LinkedIn manually — your session will be saved securely for future scraping."
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
        self._status.setText("Opening browser... Log in to LinkedIn, then close the browser when done.")
        self._btn_login.setEnabled(False)

        try:
            from playwright.sync_api import sync_playwright
            from jobhunter.core.profile_vault import ProfileVault

            vault = ProfileVault(Path.home() / ".jobhunter")
            profile_dir = str(vault.unlock())

            pw = sync_playwright().start()
            browser = pw.chromium.launch_persistent_context(
                profile_dir,
                headless=False,  # Visible browser for user login
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.new_page()
            page.goto("https://www.linkedin.com/login")

            # Wait for user to close the browser
            try:
                browser.pages[0].wait_for_event("close", timeout=300000)
            except Exception:
                pass

            try:
                browser.close()
            except Exception:
                pass
            pw.stop()

            vault.lock()
            self._status.setText("✓ LinkedIn session saved and encrypted!")
            self._status.setStyleSheet("color: #81c784;")
        except Exception as exc:
            self._status.setText(f"Login failed: {exc}")
            self._status.setStyleSheet("color: #ef5350;")
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
        self._title.setPlaceholderText("e.g., Security Engineer, Product Manager, Data Analyst")
        layout.addRow("Job Title:", self._title)

        self._search_location = QLineEdit()
        self._search_location.setPlaceholderText("e.g., Remote, New York, San Francisco")
        layout.addRow("Location:", self._search_location)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(120)
        layout.addRow("Preview:", self._preview)

        btn_gen = QPushButton("Generate Search URLs")
        btn_gen.clicked.connect(self._on_generate)
        layout.addRow("", btn_gen)

        note = QLabel("You can also paste search URLs manually in the Search URLs tab later.")
        note.setProperty("dim", True)
        note.setWordWrap(True)
        layout.addRow("", note)

    def _on_generate(self) -> None:
        title = self._title.text().strip()
        loc = self._search_location.text().strip()
        if not title:
            return

        title_encoded = title.replace(" ", "%20")
        loc_encoded = loc.replace(" ", "%20") if loc else ""

        urls = []
        urls.append(("linkedin", f"https://www.linkedin.com/jobs/search/?keywords={title_encoded}&location={loc_encoded}"))
        urls.append(("dice", f"https://www.dice.com/jobs?q={title_encoded}&location={loc_encoded}"))
        urls.append(("builtin", f"https://builtin.com/jobs?search={title_encoded}&location={loc_encoded}"))

        preview_lines = [f"[{board}] {url}" for board, url in urls]
        self._preview.setPlainText("\n".join(preview_lines))
        self._generated_urls = urls

    def get_generated_urls(self) -> list[tuple[str, str]]:
        """Return list of (board, url) tuples."""
        return getattr(self, "_generated_urls", [])


class FinishPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("All Set!")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "<h2>Setup complete</h2>"
            "<p>JobHunter is ready to use. Here's what you can do next:</p>"
            "<ul>"
            "<li><b>Dashboard</b> — Click 'Run Search' to find jobs</li>"
            "<li><b>Resume Library</b> — Review and edit your imported bullets</li>"
            "<li><b>Settings</b> — Fine-tune your preferences anytime</li>"
            "</ul>"
            "<p>Click Finish to start using JobHunter.</p>"
        ))
        layout.addStretch()
