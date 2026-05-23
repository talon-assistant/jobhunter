"""Settings tab (PySide6) — all config via GUI."""

from __future__ import annotations

import shutil

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QFormLayout, QTextEdit,
    QSpinBox, QMessageBox,
)

from jobhunter.config import Config
from jobhunter.core.llm_client import LLMClient


class SettingsTab(QWidget):
    def __init__(
        self,
        config: Config,
        llm_client: LLMClient,
        *,
        status_callback=None,
        on_provider_change=None,
    ) -> None:
        super().__init__()
        self.config = config
        self.llm = llm_client
        self._status_cb = status_callback
        self._on_provider_change = on_provider_change
        self._build_ui()

    def _set_status(self, msg: str) -> None:
        if self._status_cb:
            self._status_cb(msg)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        heading = QLabel("Settings")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        # -- LLM Provider --
        llm_group = QGroupBox("LLM Provider")
        llm_layout = QFormLayout(llm_group)

        self._provider_combo = QComboBox()
        self._provider_combo.addItems(LLMClient.PROVIDERS)
        self._provider_combo.setCurrentText(self.config.get("llm.provider", "claude-cli"))
        self._provider_combo.currentTextChanged.connect(self._on_provider_ui_change)
        llm_layout.addRow("Provider:", self._provider_combo)

        self._api_key_input = QLineEdit()
        self._api_key_input.setPlaceholderText("API key (stored in OS keyring)")
        self._api_key_input.setEchoMode(QLineEdit.Password)
        llm_layout.addRow("API Key:", self._api_key_input)

        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("Model name (leave blank for default)")
        self._model_input.setText(self.config.get("llm.model", ""))
        llm_layout.addRow("Model:", self._model_input)

        self._endpoint_input = QLineEdit()
        self._endpoint_input.setPlaceholderText("Only for openai-compatible")
        self._endpoint_input.setText(self.config.get("llm.endpoint", ""))
        llm_layout.addRow("Endpoint:", self._endpoint_input)

        test_row = QHBoxLayout()
        btn_test = QPushButton("Test Connection")
        btn_test.clicked.connect(self._on_test_connection)
        test_row.addWidget(btn_test)
        self._test_result = QLabel("")
        test_row.addWidget(self._test_result)
        test_row.addStretch()
        llm_layout.addRow("", test_row)

        # Load API key from keyring
        self._load_api_key()
        self._on_provider_ui_change(self._provider_combo.currentText())

        layout.addWidget(llm_group)

        # -- Resume Header --
        resume_group = QGroupBox("Resume Header")
        resume_layout = QFormLayout(resume_group)

        self._name = QLineEdit(self.config.get("resume.name", ""))
        resume_layout.addRow("Name:", self._name)
        self._email = QLineEdit(self.config.get("resume.email", ""))
        resume_layout.addRow("Email:", self._email)
        self._phone = QLineEdit(self.config.get("resume.phone", ""))
        resume_layout.addRow("Phone:", self._phone)
        self._location = QLineEdit(self.config.get("resume.location", ""))
        resume_layout.addRow("Location:", self._location)
        self._output_dir = QLineEdit(self.config.get("resume.output_dir", ""))
        self._output_dir.setPlaceholderText("Output directory for generated documents")
        resume_layout.addRow("Output Dir:", self._output_dir)

        layout.addWidget(resume_group)

        # -- Cover Letter Style --
        style_group = QGroupBox("Cover Letter Style Rules")
        style_layout = QVBoxLayout(style_group)
        self._style_rules = QTextEdit()
        self._style_rules.setPlainText(self.config.get("resume.style_rules", ""))
        self._style_rules.setMaximumHeight(80)
        style_layout.addWidget(self._style_rules)
        layout.addWidget(style_group)

        # -- Scoring --
        score_group = QGroupBox("Scoring")
        score_layout = QFormLayout(score_group)

        self._deep_threshold = QSpinBox()
        self._deep_threshold.setRange(0, 100)
        self._deep_threshold.setValue(self.config.get("scoring.deep_threshold", 50))
        score_layout.addRow("Deep Analysis Threshold:", self._deep_threshold)

        self._auto_archive = QSpinBox()
        self._auto_archive.setRange(0, 100)
        self._auto_archive.setValue(self.config.get("scoring.auto_archive_below", 30))
        score_layout.addRow("Auto-archive Below:", self._auto_archive)

        layout.addWidget(score_group)

        # -- Save --
        btn_save = QPushButton("Save Settings")
        btn_save.setProperty("primary", True)
        btn_save.clicked.connect(self._on_save)
        layout.addWidget(btn_save)

        layout.addStretch()

    def _on_provider_ui_change(self, provider: str) -> None:
        """Show/hide fields based on provider."""
        needs_key = provider in ("anthropic", "openai", "gemini")
        needs_endpoint = provider == "openai-compatible"

        self._api_key_input.setVisible(needs_key or needs_endpoint)
        self._endpoint_input.setVisible(needs_endpoint)

        # Show CLI status for claude-cli
        if provider == "claude-cli":
            has_cli = shutil.which("claude") is not None
            self._test_result.setText("✓ Claude CLI found" if has_cli else "✗ Claude CLI not found")
            self._test_result.setStyleSheet(
                "color: #81c784;" if has_cli else "color: #ef5350;"
            )

    def _on_test_connection(self) -> None:
        provider = self._provider_combo.currentText()
        api_key = self._api_key_input.text().strip()
        model = self._model_input.text().strip()
        endpoint = self._endpoint_input.text().strip()

        test_client = LLMClient(
            provider=provider, api_key=api_key,
            model=model, endpoint=endpoint,
        )

        try:
            result = test_client.generate_text(
                "Reply with exactly: OK",
                system_prompt="Reply with exactly one word: OK",
                max_tokens=10,
            )
            self._test_result.setText(f"✓ Connected ({provider})")
            self._test_result.setStyleSheet("color: #81c784;")
        except Exception as exc:
            self._test_result.setText(f"✗ {exc}")
            self._test_result.setStyleSheet("color: #ef5350;")

    def _on_save(self) -> None:
        provider = self._provider_combo.currentText()
        self.config.set("llm.provider", provider)
        self.config.set("llm.model", self._model_input.text().strip())
        self.config.set("llm.endpoint", self._endpoint_input.text().strip())
        self.config.set("resume.name", self._name.text())
        self.config.set("resume.email", self._email.text())
        self.config.set("resume.phone", self._phone.text())
        self.config.set("resume.location", self._location.text())
        self.config.set("resume.output_dir", self._output_dir.text())
        self.config.set("resume.style_rules", self._style_rules.toPlainText())
        self.config.set("scoring.deep_threshold", self._deep_threshold.value())
        self.config.set("scoring.auto_archive_below", self._auto_archive.value())
        self.config.save()

        # Save API key to OS keyring
        api_key = self._api_key_input.text().strip()
        if api_key:
            self._save_api_key(provider, api_key)

        # Update the live LLM client
        self.llm.provider = provider
        self.llm.api_key = api_key or self._load_api_key_value(provider)
        self.llm.model = self._model_input.text().strip() or LLMClient._default_model(provider)
        self.llm.endpoint = self._endpoint_input.text().strip()

        if self._on_provider_change:
            self._on_provider_change()

        self._set_status("Settings saved")

    # ------------------------------------------------------------------
    # Keyring helpers
    # ------------------------------------------------------------------

    def _load_api_key(self) -> None:
        provider = self._provider_combo.currentText()
        key = self._load_api_key_value(provider)
        if key:
            self._api_key_input.setText(key)

    @staticmethod
    def _load_api_key_value(provider: str) -> str:
        try:
            import keyring
            return keyring.get_password("jobhunter", f"api_key_{provider}") or ""
        except Exception:
            return ""

    @staticmethod
    def _save_api_key(provider: str, key: str) -> None:
        try:
            import keyring
            keyring.set_password("jobhunter", f"api_key_{provider}", key)
        except Exception:
            pass  # Keyring unavailable, key stays in memory only
