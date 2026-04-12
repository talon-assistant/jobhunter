"""Job dashboard tab: table, filters, detail pane, actions."""

from __future__ import annotations

import json
import logging
import webbrowser
from pathlib import Path
from typing import Any

import dearpygui.dearpygui as dpg

from jobhunter.core.cover_letter import CoverLetterGenerator
from jobhunter.core.docx_builder import build_cover_letter, build_resume
from jobhunter.core.fit_scorer import FitScorer
from jobhunter.core.job_db import JobDB
from jobhunter.core.resume_db import ResumeDB
from jobhunter.core.resume_selector import ResumeSelector
from jobhunter.core.scraper import Scraper
from jobhunter.gui import dialogs, layout
from jobhunter.gui.theme import fit_score_color
from jobhunter.gui.workers import BackgroundTask

log = logging.getLogger(__name__)

_STATUS_CHOICES = ["all", "new", "reviewing", "applied", "interviewing", "offer", "rejected", "withdrawn", "archived"]
_SOURCE_CHOICES = ["all", "linkedin", "dice", "builtin", "glassdoor", "manual", "other"]
_SCORE_CHOICES = ["Any", "30+", "50+", "60+", "70+", "80+", "90+"]


class DashboardTab:
    """The main job dashboard view."""

    def __init__(
        self,
        job_db: JobDB,
        resume_db: ResumeDB,
        scraper: Scraper,
        fit_scorer: FitScorer,
        resume_selector: ResumeSelector,
        cover_letter_gen: CoverLetterGenerator,
        *,
        resume_text: str = "",
        output_dir: str = "",
        resume_header: dict[str, str] | None = None,
    ) -> None:
        self.db = job_db
        self.resume_db = resume_db
        self.scraper = scraper
        self.scorer = fit_scorer
        self.selector = resume_selector
        self.cover_gen = cover_letter_gen
        self.resume_text = resume_text
        self.output_dir = output_dir or str(Path.home() / "Documents" / "JobHunter")
        self.header = resume_header or {}
        self._rows: list[dict] = []
        self._selected_app_id: int | None = None

    def build(self) -> None:
        """Build the dashboard UI."""
        # -- URL drop-in bar --
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                tag="url_input", hint="Paste a job URL...", width=500
            )
            dpg.add_button(label="Add + Score", callback=self._on_add_url)
            dpg.add_spacer(width=20)
            dpg.add_button(label="Run Search", callback=self._on_run_search)

        dpg.add_spacer(height=5)

        # -- Filter bar --
        with dpg.group(horizontal=True):
            dpg.add_text("Status:")
            dpg.add_combo(
                _STATUS_CHOICES, tag="filter_status", default_value="all",
                width=120, callback=self._on_filter_change,
            )
            dpg.add_spacer(width=10)
            dpg.add_text("Source:")
            dpg.add_combo(
                _SOURCE_CHOICES, tag="filter_source", default_value="all",
                width=120, callback=self._on_filter_change,
            )
            dpg.add_spacer(width=10)
            dpg.add_text("Min Score:")
            dpg.add_combo(
                _SCORE_CHOICES, tag="filter_score", default_value="Any",
                width=80, callback=self._on_filter_change,
            )
            dpg.add_spacer(width=10)
            dpg.add_input_text(
                tag="filter_search", hint="Search...",
                width=200, callback=self._on_filter_change,
            )
            dpg.add_spacer(width=10)
            dpg.add_checkbox(
                label="Show Archived", tag="filter_archived",
                default_value=False, callback=self._on_filter_change,
            )

        dpg.add_spacer(height=5)
        dpg.add_separator()

        # -- Job table --
        with dpg.child_window(tag="table_container", height=-200):
            self._build_table()

        # -- Detail pane --
        dpg.add_separator()
        with dpg.child_window(tag="detail_pane", height=-30):
            dpg.add_text("Select a job to view details", tag="detail_text", wrap=0)
            dpg.add_input_text(
                tag="detail_notes", multiline=True, height=60,
                hint="Notes...", show=False, callback=self._on_notes_change,
            )
            dpg.add_text("", tag="detail_timeline", wrap=0, show=False)

        # -- Stats bar --
        with dpg.group(horizontal=True):
            dpg.add_text("", tag="stats_text")

        # Initial load
        self.refresh()

    def refresh(self) -> None:
        """Reload data from DB and rebuild the table."""
        filters = self._get_filters()
        self._rows = self.db.list_applications(**filters)
        self._rebuild_table()
        self._update_stats()

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _build_table(self) -> None:
        with dpg.table(
            tag="job_table",
            header_row=True,
            resizable=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            row_background=True,
            scrollY=True,
            policy=dpg.mvTable_SizingStretchProp,
        ):
            dpg.add_table_column(label="ID", width_fixed=True, init_width_or_weight=50)
            dpg.add_table_column(label="Fit", width_fixed=True, init_width_or_weight=50)
            dpg.add_table_column(label="Company", init_width_or_weight=150)
            dpg.add_table_column(label="Position", init_width_or_weight=200)
            dpg.add_table_column(label="Location", init_width_or_weight=120)
            dpg.add_table_column(label="Source", width_fixed=True, init_width_or_weight=80)
            dpg.add_table_column(label="Found", width_fixed=True, init_width_or_weight=90)
            dpg.add_table_column(label="Status", width_fixed=True, init_width_or_weight=110)
            dpg.add_table_column(label="Actions", width_fixed=True, init_width_or_weight=280)

    def _rebuild_table(self) -> None:
        """Clear and repopulate all table rows."""
        # Delete existing rows
        children = dpg.get_item_children("job_table", 1) or []
        for child in children:
            dpg.delete_item(child)

        for app in self._rows:
            app_id = app["id"]
            row_tag = f"row_{app_id}"

            with dpg.table_row(parent="job_table", tag=row_tag):
                # ID
                dpg.add_text(str(app_id))

                # Fit score (colored)
                score = app.get("fit_score", 0)
                dpg.add_text(
                    str(score) if score else "--",
                    color=fit_score_color(score),
                )

                # Company (clickable to show detail)
                dpg.add_selectable(
                    label=app.get("company", ""),
                    callback=self._on_row_click,
                    user_data=app_id,
                )

                # Position
                dpg.add_text(app.get("position", ""))

                # Location
                dpg.add_text(app.get("location", ""))

                # Source
                dpg.add_text(app.get("source", ""))

                # Date found
                dpg.add_text(app.get("date_found", ""))

                # Status dropdown
                status_tag = f"status_{app_id}"
                current_status = app.get("status", "new")
                dpg.add_combo(
                    _STATUS_CHOICES[1:],  # exclude "all"
                    tag=status_tag,
                    default_value=current_status,
                    width=100,
                    callback=self._on_status_change,
                    user_data=app_id,
                )

                # Action buttons
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="All", width=40,
                        callback=self._on_prepare_all, user_data=app_id,
                    )
                    dpg.add_button(
                        label="Resume", width=55,
                        callback=self._on_prepare_resume, user_data=app_id,
                    )
                    dpg.add_button(
                        label="Letter", width=50,
                        callback=self._on_prepare_letter, user_data=app_id,
                    )
                    dpg.add_button(
                        label="Open", width=42,
                        callback=self._on_open_url, user_data=app_id,
                    )
                    dpg.add_button(
                        label="Del", width=35,
                        callback=self._on_delete, user_data=app_id,
                    )

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def _get_filters(self) -> dict[str, Any]:
        status = dpg.get_value("filter_status") if dpg.does_item_exist("filter_status") else "all"
        source = dpg.get_value("filter_source") if dpg.does_item_exist("filter_source") else "all"
        score_str = dpg.get_value("filter_score") if dpg.does_item_exist("filter_score") else "Any"
        search = dpg.get_value("filter_search") if dpg.does_item_exist("filter_search") else ""
        archived = dpg.get_value("filter_archived") if dpg.does_item_exist("filter_archived") else False

        min_score = 0
        if score_str != "Any":
            min_score = int(score_str.replace("+", ""))

        filters: dict[str, Any] = {
            "min_score": min_score,
            "search": search,
            "include_archived": archived,
        }
        if status != "all":
            filters["status"] = status
        if source != "all":
            filters["source"] = source
        return filters

    def _on_filter_change(self, sender=None, app_data=None, user_data=None) -> None:
        self.refresh()

    # ------------------------------------------------------------------
    # Row actions
    # ------------------------------------------------------------------

    def _on_row_click(self, sender, app_data, user_data) -> None:
        app_id = user_data
        self._selected_app_id = app_id
        self._show_detail(app_id)

    def _on_status_change(self, sender, app_data, user_data) -> None:
        app_id = user_data
        new_status = app_data
        try:
            self.db.update_application(app_id, status=new_status)
            layout.set_status(f"Status updated to '{new_status}'")
        except ValueError as exc:
            dialogs.error_dialog("Status Error", str(exc))
            self.refresh()

    def _on_open_url(self, sender, app_data, user_data) -> None:
        app = self.db.get_application(user_data)
        if app and app.get("url"):
            webbrowser.open(app["url"])

    def _on_delete(self, sender, app_data, user_data) -> None:
        app_id = user_data
        app = self.db.get_application(app_id)
        if not app:
            return
        dialogs.confirm_dialog(
            "Delete Application",
            f"Permanently delete {app['company']} - {app['position']}?",
            on_confirm=lambda: self._do_delete(app_id),
        )

    def _do_delete(self, app_id: int) -> None:
        self.db.delete_application(app_id)
        self.refresh()
        layout.set_status("Application deleted")

    # ------------------------------------------------------------------
    # URL add + search
    # ------------------------------------------------------------------

    def _on_add_url(self, sender=None, app_data=None, user_data=None) -> None:
        url = dpg.get_value("url_input").strip()
        if not url.startswith("http"):
            dialogs.error_dialog("Invalid URL", "Please enter a valid URL starting with http")
            return

        existing = self.db.url_exists(url)
        if existing:
            dialogs.info_dialog("Duplicate", f"This URL already exists as application #{existing}")
            return

        layout.set_status("Scraping URL...")
        dpg.set_value("url_input", "")

        def do_scrape():
            posting = self.scraper.scrape_posting(url)
            if not posting:
                raise Exception("Could not scrape job details from URL")
            return posting

        def on_done(posting):
            app_id = self.db.add_application(
                company=posting.company,
                position=posting.position,
                location=posting.location,
                source=posting.source,
                url=posting.url,
                jd_text=posting.jd_text,
            )
            # Quick BGE score
            if self.resume_text and posting.jd_text:
                scored = self.scorer.score_fast(self.resume_text, [{
                    "company": posting.company, "position": posting.position,
                    "location": posting.location, "url": posting.url,
                    "jd_text": posting.jd_text, "source": posting.source,
                }])
                if scored:
                    self.db.update_application(
                        app_id,
                        fit_score=scored[0].fit_score,
                        fit_analysis=json.dumps({"fast_score": scored[0].fast_score}),
                    )
            self.refresh()
            layout.set_status(f"Added: {posting.company} - {posting.position}")

        BackgroundTask(do_scrape, on_complete=on_done, on_error=lambda e: dialogs.error_dialog("Scrape Error", str(e))).start()

    def _on_run_search(self, sender=None, app_data=None, user_data=None) -> None:
        search_urls = self.db.list_search_urls(enabled_only=True)
        if not search_urls:
            dialogs.info_dialog("No URLs", "Add search URLs in the Search URLs tab first")
            return

        layout.set_status(f"Searching {len(search_urls)} URL(s)...")

        def do_search():
            jobs = self.scraper.scrape_all(search_urls)
            # Deduplicate against existing
            new_jobs = []
            for j in jobs:
                if not self.db.url_exists(j.url):
                    new_jobs.append(j)

            # Add to DB
            for j in new_jobs:
                self.db.add_application(
                    company=j.company, position=j.position,
                    location=j.location, source=j.source,
                    url=j.url, jd_text=j.jd_text,
                )

            # Fast score all new jobs
            if self.resume_text and new_jobs:
                job_dicts = [{"company": j.company, "position": j.position,
                              "location": j.location, "url": j.url,
                              "jd_text": j.jd_text, "source": j.source}
                             for j in new_jobs]
                scored = self.scorer.score_fast(self.resume_text, job_dicts)
                for s in scored:
                    existing = self.db.url_exists(s.url)
                    if existing:
                        self.db.update_application(existing, fit_score=s.fit_score)

            return len(new_jobs)

        def on_done(count):
            self.refresh()
            layout.set_status(f"Search complete: {count} new jobs found")

        BackgroundTask(do_search, on_complete=on_done, on_error=lambda e: dialogs.error_dialog("Search Error", str(e))).start()

    # ------------------------------------------------------------------
    # Material generation
    # ------------------------------------------------------------------

    def _on_prepare_all(self, sender, app_data, user_data) -> None:
        self._generate_materials(user_data, resume=True, letter=True)

    def _on_prepare_resume(self, sender, app_data, user_data) -> None:
        self._generate_materials(user_data, resume=True, letter=False)

    def _on_prepare_letter(self, sender, app_data, user_data) -> None:
        self._generate_materials(user_data, resume=False, letter=True)

    def _generate_materials(self, app_id: int, *, resume: bool, letter: bool) -> None:
        app = self.db.get_application(app_id)
        if not app:
            return

        layout.set_status(f"Generating materials for {app['company']}...")

        def do_generate():
            results = {}
            company = app["company"]
            position = app["position"]
            jd = app.get("jd_text", "")
            out_dir = Path(self.output_dir) / f"{company}_{position}".replace(" ", "_")

            if resume:
                selection = self.selector.select(
                    jd, company=company, position=position
                )
                # Build sections dict from selection
                sections: dict[str, list[str]] = {}
                for section_name, bullet_ids in selection.picks.items():
                    bullets = []
                    for bid in bullet_ids:
                        b = self.resume_db.get_bullet(bid)
                        if b:
                            bullets.append(b["text"])
                    if bullets:
                        sections[section_name] = bullets

                if sections:
                    resume_path = build_resume(
                        sections, output_path=out_dir / f"{company}_resume.docx",
                        **self.header,
                    )
                    results["resume_path"] = str(resume_path)
                    self.selector.mark_selected(selection)

                    # Save preview markdown
                    preview = self.selector.render_preview(selection)
                    (out_dir / "resume_preview.md").write_text(preview, encoding="utf-8")

            if letter:
                selected_bullets = ""
                if resume and "resume_path" in results:
                    # Use already selected bullets as context
                    selected_bullets = self.selector.render_preview(selection)

                letter_text = self.cover_gen.generate(
                    resume_text=self.resume_text,
                    jd_text=jd,
                    company=company,
                    position=position,
                    location=app.get("location", ""),
                    fit_analysis=app.get("fit_analysis", ""),
                    selected_bullets=selected_bullets,
                )
                letter_path = build_cover_letter(
                    letter_text,
                    output_path=out_dir / f"{company}_cover_letter.docx",
                    **self.header,
                )
                results["cover_letter_path"] = str(letter_path)

            return results

        def on_done(results):
            updates = {}
            if "resume_path" in results:
                updates["resume_path"] = results["resume_path"]
            if "cover_letter_path" in results:
                updates["cover_letter_path"] = results["cover_letter_path"]
            if updates:
                self.db.update_application(app_id, **updates)
                self.db.add_event(app_id, "materials", f"Generated: {', '.join(updates.keys())}")
            self.refresh()
            layout.set_status(f"Materials ready for {app['company']}")

        BackgroundTask(
            do_generate, on_complete=on_done,
            on_error=lambda e: dialogs.error_dialog("Generation Error", str(e)),
            name=f"materials_{app_id}",
        ).start()

    # ------------------------------------------------------------------
    # Detail pane
    # ------------------------------------------------------------------

    def _show_detail(self, app_id: int) -> None:
        app = self.db.get_application(app_id)
        if not app:
            return

        # Fit analysis
        detail_parts = [f"## {app['company']} - {app['position']}"]
        detail_parts.append(f"Score: {app.get('fit_score', 0)}  |  Status: {app.get('status', 'new')}")

        if app.get("fit_analysis"):
            try:
                analysis = json.loads(app["fit_analysis"])
                if analysis.get("summary"):
                    detail_parts.append(f"\n{analysis['summary']}")
                if analysis.get("strengths"):
                    detail_parts.append("\nStrengths: " + ", ".join(analysis["strengths"]))
                if analysis.get("gaps"):
                    detail_parts.append("Gaps: " + ", ".join(analysis["gaps"]))
            except (json.JSONDecodeError, TypeError):
                pass

        if app.get("jd_text"):
            detail_parts.append(f"\n--- JD Excerpt ---\n{app['jd_text'][:800]}...")

        dpg.set_value("detail_text", "\n".join(detail_parts))

        # Notes
        dpg.set_value("detail_notes", app.get("notes", ""))
        dpg.show_item("detail_notes")

        # Timeline
        events = self.db.get_events(app_id)
        if events:
            timeline = "\n".join(
                f"  {e['event_date'][:16]}  [{e['event_type']}] {e['description']}"
                for e in events
            )
            dpg.set_value("detail_timeline", f"\n--- Timeline ---\n{timeline}")
            dpg.show_item("detail_timeline")

    def _on_notes_change(self, sender, app_data, user_data) -> None:
        if self._selected_app_id:
            self.db.update_application(self._selected_app_id, notes=app_data)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _update_stats(self) -> None:
        stats = self.db.get_stats()
        parts = [f"{status}: {count}" for status, count in sorted(stats.items())]
        total = sum(stats.values())
        text = f"Total: {total}  |  " + "  |  ".join(parts)
        if dpg.does_item_exist("stats_text"):
            dpg.set_value("stats_text", text)
