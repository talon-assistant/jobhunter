"""Application bootstrap: create services, build GUI, run event loop."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import dearpygui.dearpygui as dpg

from jobhunter.config import Config

log = logging.getLogger(__name__)


def main() -> None:
    """Entry point for the JobHunter application."""
    # -- Logging --
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # -- Config --
    config = Config()
    log.info("Config loaded from %s", config.path)

    # -- Data directories --
    app_dir = config.path.parent
    data_dir = app_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # -- Core services --
    from jobhunter.core.job_db import JobDB
    from jobhunter.core.resume_db import ResumeDB
    from jobhunter.core.llm_client import LLMClient
    from jobhunter.core.llm_server import LLMServerManager
    from jobhunter.core.fit_scorer import FitScorer
    from jobhunter.core.resume_selector import ResumeSelector
    from jobhunter.core.cover_letter import CoverLetterGenerator
    from jobhunter.core.scraper import Scraper

    job_db_path = config.get("data.job_db_path", "data/jobhunter.db")
    if not Path(job_db_path).is_absolute():
        job_db_path = str(app_dir / job_db_path)

    resume_db_path = config.get("data.resume_db_path", "data/resume_library.db")
    if not Path(resume_db_path).is_absolute():
        resume_db_path = str(app_dir / resume_db_path)

    job_db = JobDB(job_db_path)
    resume_db = ResumeDB(resume_db_path)

    llm_server = LLMServerManager(
        binary=config.get("llm_server.binary", "llama-server"),
        model_path=config.get("llm_server.model_path", ""),
        port=config.get("llm_server.port", 8080),
        ctx_size=config.get("llm_server.ctx_size", 8192),
        threads=config.get("llm_server.threads", 4),
        n_gpu_layers=config.get("llm_server.n_gpu_layers", 0),
        extra_args=config.get("llm_server.extra_args", []),
    )

    port = config.get("llm_server.port", 8080)
    llm_client = LLMClient(
        endpoint=config.get("llm.endpoint", f"http://localhost:{port}/v1/chat/completions"),
        health_endpoint=config.get("llm.health_endpoint", f"http://localhost:{port}/health"),
        temperature=config.get("llm.temperature", 0.3),
        max_tokens=config.get("llm.max_tokens", 2048),
        timeout=config.get("llm.timeout", 300),
    )

    scraper = Scraper(
        linkedin_profile_dir=config.get("scraping.linkedin_profile_dir", ""),
        scrape_delay=config.get("scraping.scrape_delay", 4),
        enabled_boards=config.get("scraping.enabled_boards", ["linkedin", "dice", "builtin", "glassdoor"]),
    )

    fit_scorer = FitScorer(
        llm_client,
        fast_threshold=config.get("scoring.fast_threshold", 40),
        deep_threshold=config.get("scoring.deep_threshold", 50),
        batch_size=config.get("scoring.batch_size", 2),
        jd_max_chars=config.get("scoring.jd_max_chars", 1500),
        auto_archive_below=config.get("scoring.auto_archive_below", 30),
    )

    resume_selector = ResumeSelector(llm_client, resume_db)
    cover_letter_gen = CoverLetterGenerator(
        llm_client,
        style_rules=config.get("resume.style_rules", ""),
    )

    # Resume header info
    resume_header = {
        "name": config.get("resume.name", ""),
        "email": config.get("resume.email", ""),
        "phone": config.get("resume.phone", ""),
        "location": config.get("resume.location", ""),
    }

    # Load resume text from library export (if it exists)
    library_md = config.get("data.library_md_path", "data/resumelibrary.md")
    if not Path(library_md).is_absolute():
        library_md = str(app_dir / library_md)
    resume_text = ""
    if Path(library_md).exists():
        resume_text = Path(library_md).read_text(encoding="utf-8")

    # -- GUI --
    from jobhunter.gui.dashboard import DashboardTab
    from jobhunter.gui.resume_library import ResumeLibraryTab
    from jobhunter.gui.search_urls import SearchURLsTab
    from jobhunter.gui.followups import FollowupsTab
    from jobhunter.gui.settings_panel import SettingsTab
    from jobhunter.gui.layout import build_layout, frame_callback, PRIMARY_WINDOW
    from jobhunter.gui.theme import apply_dark_theme

    dashboard = DashboardTab(
        job_db, resume_db, scraper, fit_scorer,
        resume_selector, cover_letter_gen,
        resume_text=resume_text,
        output_dir=config.get("resume.output_dir", str(Path.home() / "Documents" / "JobHunter")),
        resume_header=resume_header,
    )
    resume_library = ResumeLibraryTab(resume_db, llm_client)
    search_urls = SearchURLsTab(job_db)
    followups = FollowupsTab(job_db)
    settings = SettingsTab(config, llm_server, llm_client)

    # -- DearPyGui setup --
    dpg.create_context()
    dpg.create_viewport(
        title="JobHunter",
        width=1400,
        height=900,
        min_width=800,
        min_height=600,
    )

    apply_dark_theme()

    build_layout(
        dashboard=dashboard,
        resume_library=resume_library,
        search_urls=search_urls,
        followups=followups,
        settings=settings,
    )

    dpg.setup_dearpygui()
    dpg.set_primary_window(PRIMARY_WINDOW, True)

    # Register frame callback for background task queue
    dpg.set_frame_callback(1, lambda: None)  # init frame

    dpg.show_viewport()

    # Main loop with manual callback management
    while dpg.is_dearpygui_running():
        frame_callback()
        dpg.render_dearpygui_frame()

    # -- Cleanup --
    log.info("Shutting down...")
    llm_server.stop()
    job_db.close()
    resume_db.close()
    dpg.destroy_context()
    log.info("Goodbye.")


if __name__ == "__main__":
    main()
