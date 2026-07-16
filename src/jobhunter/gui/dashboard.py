"""Job dashboard tab using QTableView + model/view for performance."""

from __future__ import annotations

import json
import logging
import webbrowser
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QTableView, QHeaderView,
    QSplitter, QTextEdit, QMessageBox, QAbstractItemView,
)

from jobhunter.core.cover_letter import CoverLetterGenerator
from jobhunter.core.docx_builder import build_cover_letter, build_resume
from jobhunter.core.fit_scorer import FitScorer
from jobhunter.core.job_db import JobDB
from jobhunter.core.resume_db import ResumeDB
from jobhunter.core.resume_selector import ResumeSelector
from jobhunter.core.scraper import Scraper
from jobhunter.gui.job_model import JobTableModel, JobFilterProxy
from jobhunter.gui.workers import SimpleWorker

log = logging.getLogger(__name__)

_STATUS_CHOICES = ["all", "new", "reviewing", "applied", "interviewing", "offer", "rejected", "withdrawn", "archived"]
_SOURCE_CHOICES = ["all", "linkedin", "dice", "builtin", "glassdoor", "manual", "other"]
_SCORE_CHOICES = ["Any", "30+", "50+", "60+", "70+", "80+", "90+"]


class DashboardTab(QWidget):
    """Main job dashboard with model/view table."""

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
        status_callback=None,
        template_getter=None,
    ) -> None:
        super().__init__()
        self.db = job_db
        self.resume_db = resume_db
        self.scraper = scraper
        self.scorer = fit_scorer
        self.selector = resume_selector
        self.cover_gen = cover_letter_gen
        self.resume_text = resume_text
        self.output_dir = output_dir or str(Path.home() / "Documents" / "JobHunter")
        self.header = resume_header or {}
        self._status_cb = status_callback
        # Callable so a template change in Settings applies without restart
        self._template_getter = template_getter or (lambda: "classic")
        self._workers: list[SimpleWorker] = []

        # Model
        self._model = JobTableModel(self)
        self._proxy = JobFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._build_ui()
        self.refresh()

    def _set_status(self, msg: str) -> None:
        if self._status_cb:
            self._status_cb(msg)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # -- Focus line: one calm sentence about what matters today --
        self._focus_label = QLabel("")
        self._focus_label.setWordWrap(True)
        self._focus_label.setStyleSheet(
            "padding: 6px 8px; border-radius: 4px; "
            "background-color: rgba(129, 199, 132, 0.12); color: #a5d6a7;"
        )
        layout.addWidget(self._focus_label)

        # -- Top bar: URL input + actions --
        top = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Paste a job URL...")
        self._url_input.returnPressed.connect(self._on_add_url)
        top.addWidget(self._url_input, stretch=1)

        btn_add = QPushButton("Add + Score")
        btn_add.clicked.connect(self._on_add_url)
        top.addWidget(btn_add)

        btn_search = QPushButton("Run Search")
        btn_search.setProperty("primary", True)
        btn_search.clicked.connect(self._on_run_search)
        top.addWidget(btn_search)

        btn_score = QPushButton("Score Unscored")
        btn_score.clicked.connect(self._on_score_unscored)
        top.addWidget(btn_score)

        layout.addLayout(top)

        # -- Filter bar --
        filters = QHBoxLayout()

        filters.addWidget(QLabel("Status:"))
        self._filter_status = QComboBox()
        self._filter_status.addItems(_STATUS_CHOICES)
        self._filter_status.currentTextChanged.connect(self._on_filter_change)
        filters.addWidget(self._filter_status)

        filters.addWidget(QLabel("Source:"))
        self._filter_source = QComboBox()
        self._filter_source.addItems(_SOURCE_CHOICES)
        self._filter_source.currentTextChanged.connect(self._on_filter_change)
        filters.addWidget(self._filter_source)

        filters.addWidget(QLabel("Min Score:"))
        self._filter_score = QComboBox()
        self._filter_score.addItems(_SCORE_CHOICES)
        self._filter_score.currentTextChanged.connect(self._on_filter_change)
        filters.addWidget(self._filter_score)

        self._filter_search = QLineEdit()
        self._filter_search.setPlaceholderText("Search...")
        self._filter_search.textChanged.connect(self._on_filter_change)
        filters.addWidget(self._filter_search, stretch=1)

        self._filter_archived = QCheckBox("Show Archived")
        self._filter_archived.toggled.connect(self._on_filter_change)
        filters.addWidget(self._filter_archived)

        layout.addLayout(filters)

        # -- Splitter: table + detail pane --
        splitter = QSplitter(Qt.Vertical)

        # Table
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)

        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Fixed)       # ID
        header.setSectionResizeMode(1, QHeaderView.Fixed)       # Fit
        header.resizeSection(0, 50)
        header.resizeSection(1, 50)

        self._table.selectionModel().currentRowChanged.connect(self._on_row_selected)
        splitter.addWidget(self._table)

        # Detail pane
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(4, 4, 4, 4)

        # Action buttons
        actions = QHBoxLayout()
        for label, slot in [
            ("Prepare All", self._on_prepare_all),
            ("Tailored Resume", self._on_prepare_resume),
            ("Cover Letter", self._on_prepare_letter),
            ("Open URL", self._on_open_url),
            ("Delete", self._on_delete),
        ]:
            btn = QPushButton(label)
            if label == "Delete":
                btn.setProperty("danger", True)
            btn.clicked.connect(slot)
            actions.addWidget(btn)
        actions.addStretch()

        # Status dropdown
        actions.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItems(_STATUS_CHOICES[1:])
        self._status_combo.currentTextChanged.connect(self._on_status_change)
        actions.addWidget(self._status_combo)

        detail_layout.addLayout(actions)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setMaximumHeight(200)
        detail_layout.addWidget(self._detail_text)

        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # -- Stats bar --
        self._stats_label = QLabel("")
        self._stats_label.setProperty("dim", True)
        layout.addWidget(self._stats_label)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        rows = self.db.list_applications(include_archived=True)
        self._model.set_data(rows)
        self._on_filter_change()
        self._update_stats()
        self._update_focus()

    def _update_focus(self) -> None:
        """One calm, actionable sentence — not a wall of numbers."""
        try:
            counts = self.db.get_focus_counts()
        except Exception:
            log.exception("Focus counts failed")
            self._focus_label.setVisible(False)
            return

        if counts["total"] == 0:
            self._focus_label.setText(
                "Welcome! Start by pasting a job URL above, or set up a "
                "recurring search in the Search URLs tab — the app will "
                "find and score jobs for you."
            )
            return

        pieces: list[str] = []
        if counts["offers"]:
            pieces.append(
                f"🎉 {counts['offers']} offer(s) on the table — take a moment to be proud."
            )
        if counts["overdue_followups"]:
            pieces.append(f"{counts['overdue_followups']} follow-up(s) due")
        if counts["high_fit_new"]:
            pieces.append(f"{counts['high_fit_new']} high-fit job(s) waiting for a look")
        if counts["in_flight"]:
            pieces.append(f"{counts['in_flight']} application(s) in flight")

        if pieces:
            self._focus_label.setText("Today: " + "  ·  ".join(pieces))
        else:
            found = counts["added_this_week"]
            self._focus_label.setText(
                f"Nothing urgent today — {found} job(s) found this week. "
                "Run a search when you're ready; the pipeline does the sorting."
            )

    def _on_filter_change(self, *_) -> None:
        score_str = self._filter_score.currentText()
        min_score = int(score_str.replace("+", "")) if score_str != "Any" else 0

        self._proxy.set_filters(
            status=self._filter_status.currentText(),
            source=self._filter_source.currentText(),
            min_score=min_score,
            search=self._filter_search.text(),
            show_archived=self._filter_archived.isChecked(),
        )

    def _update_stats(self) -> None:
        stats = self.db.get_stats()
        parts = [f"{s}: {c}" for s, c in sorted(stats.items())]
        total = sum(stats.values())
        self._stats_label.setText(f"Total: {total}  |  " + "  |  ".join(parts))

    # ------------------------------------------------------------------
    # Row selection
    # ------------------------------------------------------------------

    def _selected_app_id(self) -> int | None:
        idx = self._table.currentIndex()
        if not idx.isValid():
            return None
        source_idx = self._proxy.mapToSource(idx)
        return self._model.get_app_id(source_idx.row())

    def _selected_app(self) -> dict | None:
        app_id = self._selected_app_id()
        return self.db.get_application(app_id) if app_id else None

    def _on_row_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        app = self._selected_app()
        if not app:
            return

        self._status_combo.blockSignals(True)
        self._status_combo.setCurrentText(app.get("status", "new"))
        self._status_combo.blockSignals(False)

        # Build detail text
        lines = [f"<b>{app['company']} — {app['position']}</b>"]
        lines.append(f"Score: {app.get('fit_score', 0)}  |  Status: {app.get('status', '')}")

        if app.get("fit_analysis"):
            try:
                analysis = json.loads(app["fit_analysis"])
                if analysis.get("summary"):
                    lines.append(f"<br>{analysis['summary']}")
                if analysis.get("strengths"):
                    lines.append("<br><b>Strengths:</b> " + ", ".join(analysis["strengths"]))
                if analysis.get("gaps"):
                    lines.append("<b>Gaps:</b> " + ", ".join(analysis["gaps"]))
            except (json.JSONDecodeError, TypeError):
                pass

        events = self.db.get_events(app["id"])
        if events:
            lines.append("<br><b>Timeline:</b>")
            for e in events[-10:]:
                lines.append(f"  {e['event_date'][:16]}  [{e['event_type']}] {e['description']}")

        if app.get("jd_text"):
            lines.append(f"<br><b>JD:</b> {app['jd_text'][:500]}...")

        self._detail_text.setHtml("<br>".join(lines))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_status_change(self, new_status: str) -> None:
        app_id = self._selected_app_id()
        if not app_id or not new_status:
            return
        try:
            self.db.update_application(app_id, status=new_status)
            self.refresh()
            self._set_status(f"Status updated to '{new_status}'")
        except ValueError as exc:
            QMessageBox.warning(self, "Status Error", str(exc))
            self.refresh()

    def _on_open_url(self) -> None:
        app = self._selected_app()
        if app and app.get("url"):
            webbrowser.open(app["url"])

    def _on_delete(self) -> None:
        app = self._selected_app()
        if not app:
            return
        reply = QMessageBox.question(
            self, "Delete",
            f"Permanently delete {app['company']} — {app['position']}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.delete_application(app["id"])
            self.refresh()
            self._set_status("Application deleted")

    def _on_add_url(self) -> None:
        url = self._url_input.text().strip()
        if not url.startswith("http"):
            QMessageBox.warning(self, "Invalid URL", "Enter a URL starting with http")
            return

        existing = self.db.url_exists(url)
        if existing:
            QMessageBox.information(self, "Duplicate", f"Already exists as #{existing}")
            return

        self._url_input.clear()
        self._set_status("Scraping URL...")

        def do_scrape():
            try:
                posting = self.scraper.scrape_posting(url)
                if not posting:
                    raise Exception("Could not scrape job details")
                app_id = self.db.add_application(
                    company=posting.company, position=posting.position,
                    location=posting.location, source=posting.source,
                    url=posting.url, jd_text=posting.jd_text,
                )
                if self.resume_text and posting.jd_text:
                    scored = self.scorer.score_all(self.resume_text, [{
                        "company": posting.company, "position": posting.position,
                        "location": posting.location, "url": posting.url,
                        "jd_text": posting.jd_text, "source": posting.source,
                    }])
                    if scored:
                        fields = scored[0].to_db_fields()
                        # No auto-archive here — the user explicitly added this job
                        self.db.update_application(
                            app_id,
                            fit_score=fields["fit_score"],
                            fit_analysis=fields["fit_analysis"],
                            jd_embedding=fields["jd_embedding"],
                        )
                return posting
            finally:
                self.scraper.close()

        worker = SimpleWorker(do_scrape)
        worker.finished.connect(lambda r: (self.refresh(), self._set_status(f"Added: {r.company} — {r.position}")))
        worker.error.connect(lambda e: QMessageBox.warning(self, "Error", e))
        self._workers.append(worker)
        worker.start()

    def _on_run_search(self) -> None:
        urls = self.db.list_search_urls(enabled_only=True)
        if not urls:
            QMessageBox.information(self, "No URLs", "Add search URLs first")
            return

        self._set_status(f"Searching {len(urls)} URL(s)...")

        def do_search():
            try:
                jobs = self.scraper.scrape_all(urls)
                for u in urls:
                    self.db.update_search_url_scraped(u["id"])
                new_ids = []
                for j in jobs:
                    if not self.db.url_exists(j.url):
                        app_id = self.db.add_application(
                            company=j.company, position=j.position,
                            location=j.location, source=j.source,
                            url=j.url, jd_text=j.jd_text,
                        )
                        new_ids.append(app_id)
                scored, archived = self._fetch_and_score(new_ids)
                return len(new_ids), scored, archived
            finally:
                self.scraper.close()

        def on_done(result):
            new_count, scored, archived = result
            self.refresh()
            msg = f"Found {new_count} new jobs"
            if scored:
                msg += f", scored {scored}"
            if archived:
                msg += f", auto-archived {archived} low-fit"
            self._set_status(msg)

        worker = SimpleWorker(do_search)
        worker.finished.connect(on_done)
        worker.error.connect(lambda e: QMessageBox.warning(self, "Search Error", e))
        self._workers.append(worker)
        worker.start()

    def _on_score_unscored(self) -> None:
        """Fetch missing JDs and run two-phase scoring on unscored jobs."""
        if not self.resume_text:
            QMessageBox.information(
                self, "No Resume",
                "Import your resumes first (Resume Library tab) so jobs can "
                "be scored against them.",
            )
            return

        apps = self.db.list_applications(include_archived=False)
        ids = [a["id"] for a in apps if not a.get("fit_score")]
        if not ids:
            self._set_status("No unscored jobs")
            return

        self._set_status(f"Scoring {len(ids)} unscored job(s)... this can take a while")

        def do_score():
            try:
                return self._fetch_and_score(ids)
            finally:
                self.scraper.close()

        def on_done(result):
            scored, archived = result
            self.refresh()
            msg = f"Scored {scored} job(s)"
            if archived:
                msg += f", auto-archived {archived} low-fit"
            self._set_status(msg)

        worker = SimpleWorker(do_score)
        worker.finished.connect(on_done)
        worker.error.connect(lambda e: QMessageBox.warning(self, "Scoring Error", e))
        self._workers.append(worker)
        worker.start()

    def _fetch_and_score(self, app_ids: list[int]) -> tuple[int, int]:
        """Fetch missing JDs, run fast + deep scoring, auto-archive low fits.

        Runs on a worker thread. Returns (scored_count, archived_count).
        """
        if not self.resume_text or not app_ids:
            return 0, 0

        jobs: list[dict] = []
        id_by_url: dict[str, int] = {}
        for app_id in app_ids:
            app = self.db.get_application(app_id)
            if not app or not app.get("url"):
                continue
            jd = app.get("jd_text", "")
            if not jd:
                posting = self.scraper.scrape_posting(app["url"])
                if posting and posting.jd_text:
                    jd = posting.jd_text
                    self.db.update_application(app_id, jd_text=jd)
            if not jd:
                continue
            jobs.append({
                "company": app["company"], "position": app["position"],
                "location": app.get("location", ""), "url": app["url"],
                "jd_text": jd, "source": app.get("source", ""),
            })
            id_by_url[app["url"]] = app_id

        if not jobs:
            return 0, 0

        scored = self.scorer.score_all(self.resume_text, jobs)
        archived = 0
        for s in scored:
            app_id = id_by_url.get(s.url)
            if app_id is None:
                continue
            fields = s.to_db_fields()
            self.db.update_application(
                app_id,
                fit_score=fields["fit_score"],
                fit_analysis=fields["fit_analysis"],
                jd_embedding=fields["jd_embedding"],
            )
            if self.scorer.should_auto_archive(s):
                self.db.update_application(app_id, status="archived")
                archived += 1
        return len(jobs), archived

    def _on_prepare_all(self) -> None:
        self._generate_materials(resume=True, letter=True)

    def _on_prepare_resume(self) -> None:
        self._generate_materials(resume=True, letter=False)

    def _on_prepare_letter(self) -> None:
        self._generate_materials(resume=False, letter=True)

    def _generate_materials(self, *, resume: bool, letter: bool) -> None:
        app = self._selected_app()
        if not app:
            QMessageBox.information(self, "No Selection", "Select a job first")
            return

        self._set_status(f"Generating materials for {app['company']}...")
        app_id = app["id"]

        def do_generate():
            results = {}
            company = app["company"]
            position = app["position"]
            jd = app.get("jd_text", "")
            out_dir = Path(self.output_dir) / f"{company}_{position}".replace(" ", "_")

            if resume:
                selection = self.selector.select(jd, company=company, position=position)
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
                        template=self._template_getter(),
                        **self.header,
                    )
                    results["resume_path"] = str(resume_path)
                    self.selector.mark_selected(selection)

            if letter:
                selected_bullets = ""
                if resume and "resume_path" in results:
                    selected_bullets = self.selector.render_preview(selection)
                letter_text = self.cover_gen.generate(
                    resume_text=self.resume_text, jd_text=jd,
                    company=company, position=position,
                    location=app.get("location", ""),
                    fit_analysis=app.get("fit_analysis", ""),
                    selected_bullets=selected_bullets,
                )
                letter_path = build_cover_letter(
                    letter_text, output_path=out_dir / f"{company}_cover_letter.docx",
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
            self._set_status(f"Materials ready for {app['company']}")

        worker = SimpleWorker(do_generate)
        worker.finished.connect(on_done)
        worker.error.connect(lambda e: QMessageBox.warning(self, "Error", e))
        self._workers.append(worker)
        worker.start()
