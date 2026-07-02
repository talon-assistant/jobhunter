"""Application bootstrap: create services, build PySide6 GUI, run event loop."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QStatusBar
from PySide6.QtCore import Qt

from jobhunter.config import Config

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle("JobHunter")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # -- Status bar --
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        # -- Build services --
        self._build_services()

        # -- Tab widget --
        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._build_tabs()

    def _status(self, msg: str) -> None:
        self._status_bar.showMessage(msg, 5000)

    def _build_services(self) -> None:
        from jobhunter.core.job_db import JobDB
        from jobhunter.core.resume_db import ResumeDB
        from jobhunter.core.llm_client import LLMClient
        from jobhunter.core.fit_scorer import FitScorer
        from jobhunter.core.resume_selector import ResumeSelector
        from jobhunter.core.cover_letter import CoverLetterGenerator
        from jobhunter.core.scraper import Scraper

        app_dir = self.config.path.parent
        data_dir = app_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # DB paths
        job_db_path = self.config.get("data.job_db_path", "data/jobhunter.db")
        if not Path(job_db_path).is_absolute():
            job_db_path = str(app_dir / job_db_path)
        resume_db_path = self.config.get("data.resume_db_path", "data/resume_library.db")
        if not Path(resume_db_path).is_absolute():
            resume_db_path = str(app_dir / resume_db_path)

        self.job_db = JobDB(job_db_path)
        self.resume_db = ResumeDB(resume_db_path)

        # LLM client
        provider = self.config.get("llm.provider", "claude-cli")
        api_key = self._load_api_key(provider)
        self.llm_client = LLMClient(
            provider=provider,
            api_key=api_key,
            model=self.config.get("llm.model", ""),
            endpoint=self.config.get("llm.endpoint", ""),
            temperature=self.config.get("llm.temperature", 0.3),
            max_tokens=self.config.get("llm.max_tokens", 4096),
            timeout=self.config.get("llm.timeout", 300),
        )

        self.scraper = Scraper(
            linkedin_profile_dir=self.config.get("scraping.linkedin_profile_dir", ""),
            scrape_delay=self.config.get("scraping.scrape_delay", 4),
            enabled_boards=self.config.get("scraping.enabled_boards", []),
        )

        self.fit_scorer = FitScorer(
            self.llm_client,
            deep_threshold=self.config.get("scoring.deep_threshold", 50),
            batch_size=self.config.get("scoring.batch_size", 2),
            jd_max_chars=self.config.get("scoring.jd_max_chars", 1500),
            auto_archive_below=self.config.get("scoring.auto_archive_below", 30),
        )

        self.resume_selector = ResumeSelector(self.llm_client, self.resume_db)
        self.cover_letter_gen = CoverLetterGenerator(
            self.llm_client,
            style_rules=self.config.get("resume.style_rules", ""),
        )

        # Resume text
        library_md = self.config.get("data.library_md_path", "data/resumelibrary.md")
        if not Path(library_md).is_absolute():
            library_md = str(app_dir / library_md)
        self.resume_text = ""
        if Path(library_md).exists():
            self.resume_text = Path(library_md).read_text(encoding="utf-8")

        self.resume_header = {
            "name": self.config.get("resume.name", ""),
            "email": self.config.get("resume.email", ""),
            "phone": self.config.get("resume.phone", ""),
            "location": self.config.get("resume.location", ""),
        }

    def _build_tabs(self) -> None:
        from jobhunter.gui.dashboard import DashboardTab
        from jobhunter.gui.resume_library import ResumeLibraryTab
        from jobhunter.gui.search_urls import SearchURLsTab
        from jobhunter.gui.followups import FollowupsTab
        from jobhunter.gui.settings_panel import SettingsTab

        dashboard = DashboardTab(
            self.job_db, self.resume_db, self.scraper,
            self.fit_scorer, self.resume_selector, self.cover_letter_gen,
            resume_text=self.resume_text,
            output_dir=self.config.get("resume.output_dir", ""),
            resume_header=self.resume_header,
            status_callback=self._status,
        )
        self._tabs.addTab(dashboard, "Dashboard")

        resume_lib = ResumeLibraryTab(
            self.resume_db, self.llm_client,
            status_callback=self._status,
        )
        self._tabs.addTab(resume_lib, "Resume Library")

        search_urls = SearchURLsTab(self.job_db, status_callback=self._status)
        self._tabs.addTab(search_urls, "Search URLs")

        followups = FollowupsTab(self.job_db, status_callback=self._status)
        self._tabs.addTab(followups, "Follow-ups")

        settings = SettingsTab(
            self.config, self.llm_client,
            status_callback=self._status,
        )
        self._tabs.addTab(settings, "Settings")

    @staticmethod
    def _load_api_key(provider: str) -> str:
        try:
            import keyring
            return keyring.get_password("jobhunter", f"api_key_{provider}") or ""
        except Exception:
            return ""

    def closeEvent(self, event) -> None:
        self.job_db.close()
        self.resume_db.close()
        event.accept()


def main() -> None:
    """Entry point for the JobHunter application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config = Config()
    log.info("Config loaded from %s", config.path)

    app = QApplication(sys.argv)

    # Apply dark theme
    from jobhunter.gui.theme import DARK_STYLESHEET
    app.setStyleSheet(DARK_STYLESHEET)

    # First-run wizard
    if not config.get("setup_complete", False):
        from jobhunter.gui.wizard import SetupWizard
        wizard = SetupWizard(config)
        result = wizard.exec()
        if result == 1:  # QDialog.DialogCode.Accepted
            # Process wizard results
            _process_wizard_results(config, wizard)
            config.set("setup_complete", True)
            config.save()
        else:
            # User cancelled wizard — still launch app but note incomplete setup
            log.info("Wizard cancelled, launching with defaults")

    # Main window
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


def _process_wizard_results(config: Config, wizard) -> None:
    """Process results from the setup wizard after it completes."""
    from jobhunter.core.job_db import JobDB
    from jobhunter.core.resume_db import ResumeDB
    from jobhunter.gui.wizard import BulletReviewPage, FirstSearchPage

    app_dir = config.path.parent

    pages = [wizard.page(pid) for pid in wizard.pageIds()]

    # Save reviewed bullets to resume DB
    for page in pages:
        if isinstance(page, BulletReviewPage):
            bullets = page.get_bullets()
            if bullets:
                resume_db_path = config.get("data.resume_db_path", "data/resume_library.db")
                if not Path(resume_db_path).is_absolute():
                    resume_db_path = str(app_dir / resume_db_path)
                rdb = ResumeDB(resume_db_path)
                for b in bullets:
                    rdb.add_bullet(
                        b["section"], b["text"],
                        role=b.get("role", ""),
                        source_file=b.get("source", "wizard"),
                        priority=b.get("priority", "normal"),
                    )
                rdb.close()
                log.info("Saved %d bullets from wizard", len(bullets))

    # Add generated search URLs
    for page in pages:
        if isinstance(page, FirstSearchPage):
            urls = page.get_generated_urls()
            if urls:
                job_db_path = config.get("data.job_db_path", "data/jobhunter.db")
                if not Path(job_db_path).is_absolute():
                    job_db_path = str(app_dir / job_db_path)
                db = JobDB(job_db_path)
                for board, url in urls:
                    db.add_search_url(board, url)
                db.close()
                log.info("Saved %d search URLs from wizard", len(urls))


if __name__ == "__main__":
    main()
