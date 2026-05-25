"""Multi-board job scraper: Playwright for LinkedIn, requests+BS4 for others.

All scraped job descriptions are run through jd_sanitizer before being
returned, stripping prompt injections before they ever reach the DB or LLM.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


@dataclass
class ScrapedJob:
    """A single scraped job listing."""

    company: str
    position: str
    location: str
    url: str
    jd_text: str
    source: str  # linkedin, dice, builtin, glassdoor, manual


def detect_board(url: str) -> str:
    """Determine which job board a URL belongs to."""
    host = urlparse(url).hostname or ""
    host = host.lower().replace("www.", "")
    if "linkedin.com" in host:
        return "linkedin"
    if "dice.com" in host:
        return "dice"
    if "builtin.com" in host:
        return "builtin"
    if "glassdoor.com" in host:
        return "glassdoor"
    return "other"


def clean_search_url(url: str) -> str:
    """Strip ephemeral params that change between sessions."""
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    # LinkedIn ephemeral params
    for key in ("start", "trk", "currentJobId", "origin", "refId", "trackingId"):
        params.pop(key, None)
    cleaned_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=cleaned_query))


class Scraper:
    """Scrape job listings from multiple boards."""

    def __init__(
        self,
        *,
        linkedin_profile_dir: str = "",
        scrape_delay: float = 4.0,
        enabled_boards: list[str] | None = None,
        vault_dir: str = "",
    ) -> None:
        self.linkedin_profile_dir = linkedin_profile_dir
        self.scrape_delay = scrape_delay
        self.enabled_boards = enabled_boards or ["linkedin", "dice", "builtin", "glassdoor"]

        # Profile vault for encrypted LinkedIn session storage
        from jobhunter.core.profile_vault import ProfileVault
        vdir = vault_dir or str(Path.home() / ".jobhunter")
        self._vault = ProfileVault(vdir)

    def scrape_url(self, url: str) -> list[ScrapedJob]:
        """Scrape a single URL and return job listings."""
        board = detect_board(url)

        if board == "linkedin":
            return self._scrape_linkedin(url)
        elif board == "dice":
            return self._scrape_dice(url)
        elif board == "builtin":
            return self._scrape_builtin(url)
        elif board == "glassdoor":
            return self._scrape_generic(url, source="glassdoor")
        else:
            return self._scrape_generic(url, source="other")

    def scrape_all(self, search_urls: list[dict]) -> list[ScrapedJob]:
        """Scrape all configured search URLs.

        Each entry should have 'url' and 'board' keys.
        """
        all_jobs: list[ScrapedJob] = []

        # Group by board type: LinkedIn uses Playwright, others use requests
        linkedin_urls = [u for u in search_urls if u.get("board") == "linkedin"]
        other_urls = [u for u in search_urls if u.get("board") != "linkedin"]

        # Scrape non-LinkedIn first (lightweight, no browser needed)
        for entry in other_urls:
            board = entry.get("board", "other")
            if board not in self.enabled_boards:
                continue
            try:
                jobs = self.scrape_url(entry["url"])
                all_jobs.extend(jobs)
                log.info("Scraped %d jobs from %s (%s)", len(jobs), entry["url"][:60], board)
            except Exception:
                log.exception("Failed to scrape %s", entry["url"][:80])

        # Scrape LinkedIn (uses Playwright, heavier)
        if linkedin_urls and "linkedin" in self.enabled_boards:
            try:
                for entry in linkedin_urls:
                    jobs = self._scrape_linkedin(entry["url"])
                    all_jobs.extend(jobs)
                    log.info("Scraped %d jobs from LinkedIn", len(jobs))
            except Exception:
                log.exception("Failed to scrape LinkedIn")
            finally:
                self._close_playwright()

        return all_jobs

    def scrape_posting(self, url: str) -> ScrapedJob | None:
        """Scrape a single job posting page for its details.

        The returned JD text is sanitized to strip prompt injections.
        """
        board = detect_board(url)

        if board == "linkedin":
            job = self._scrape_linkedin_posting(url)
        else:
            try:
                resp = requests.get(url, timeout=15, headers=_HEADERS)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")
                job = _extract_posting_metadata(soup, url, source=board)
            except Exception:
                log.exception("Failed to scrape posting: %s", url[:80])
                return None

        if job and job.jd_text:
            job = _sanitize_job(job)

        return job

    # ------------------------------------------------------------------
    # Dice (requests + BS4)
    # ------------------------------------------------------------------

    def _scrape_dice(self, url: str) -> list[ScrapedJob]:
        """Scrape Dice search results."""
        jobs: list[ScrapedJob] = []
        try:
            resp = requests.get(url, timeout=15, headers=_HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Dice uses search-card elements
            cards = soup.select("a.card-title-link, a[data-cy='card-title-link']")
            for card in cards[:25]:
                title = card.get_text(strip=True)
                href = card.get("href", "")
                if href and not href.startswith("http"):
                    href = f"https://www.dice.com{href}"

                # Try to get company and location from sibling elements
                parent = card.find_parent("div", class_=re.compile("card"))
                company = ""
                location = ""
                if parent:
                    company_el = parent.select_one("[data-cy='search-result-company-name'], .card-company a")
                    if company_el:
                        company = company_el.get_text(strip=True)
                    loc_el = parent.select_one("[data-cy='search-result-location'], .card-posted-date-location")
                    if loc_el:
                        location = loc_el.get_text(strip=True)

                if title and href:
                    jobs.append(ScrapedJob(
                        company=company, position=title, location=location,
                        url=href, jd_text="", source="dice",
                    ))
        except Exception:
            log.exception("Failed to scrape Dice")
        return jobs

    # ------------------------------------------------------------------
    # Built In (requests + BS4)
    # ------------------------------------------------------------------

    def _scrape_builtin(self, url: str) -> list[ScrapedJob]:
        """Scrape Built In search results."""
        jobs: list[ScrapedJob] = []
        try:
            resp = requests.get(url, timeout=15, headers=_HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("[data-id='job-card'], .job-card, article")
            for card in cards[:25]:
                title_el = card.select_one("h2 a, .job-title a, a[data-testid='job-title']")
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = f"https://builtin.com{href}"

                company_el = card.select_one(".company-name, [data-testid='company-name']")
                company = company_el.get_text(strip=True) if company_el else ""

                loc_el = card.select_one(".job-location, [data-testid='job-location']")
                location = loc_el.get_text(strip=True) if loc_el else ""

                if title and href:
                    jobs.append(ScrapedJob(
                        company=company, position=title, location=location,
                        url=href, jd_text="", source="builtin",
                    ))
        except Exception:
            log.exception("Failed to scrape Built In")
        return jobs

    # ------------------------------------------------------------------
    # Generic / trafilatura
    # ------------------------------------------------------------------

    def _scrape_generic(self, url: str, source: str = "other") -> list[ScrapedJob]:
        """Scrape a generic job page using trafilatura for content extraction."""
        try:
            resp = requests.get(url, timeout=15, headers=_HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            posting = _extract_posting_metadata(soup, url, source=source)
            if posting:
                return [posting]
        except Exception:
            log.exception("Failed to scrape generic URL")
        return []

    # ------------------------------------------------------------------
    # LinkedIn (Playwright)
    # ------------------------------------------------------------------

    _playwright = None
    _browser = None

    def _get_playwright_browser(self):
        """Lazy-init Playwright with persistent context for LinkedIn."""
        if self._browser:
            return self._browser

        # Ensure browsers are in a user-writable location (not inside _internal/)
        import os
        if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
            from pathlib import Path
            cache_dir = str(Path.home() / ".jobhunter" / "playwright-browsers")
            os.makedirs(cache_dir, exist_ok=True)
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = cache_dir

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()

        # Decrypt the LinkedIn profile from the vault (or use a fresh dir)
        if self._vault.is_available:
            profile_dir = str(self._vault.unlock())
            log.info("Using encrypted profile vault")
        elif self.linkedin_profile_dir:
            profile_dir = self.linkedin_profile_dir
        else:
            profile_dir = str(Path.home() / ".jobhunter" / "linkedin_profile")
            Path(profile_dir).mkdir(parents=True, exist_ok=True)

        self._browser = self._playwright.chromium.launch_persistent_context(
            profile_dir,
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        # Anti-detection
        self._browser.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return self._browser

    def _close_playwright(self) -> None:
        """Close Playwright browser and re-encrypt profile to vault."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        # Re-encrypt the profile back to the vault
        if self._vault.is_available:
            try:
                self._vault.lock()
            except Exception:
                log.exception("Failed to re-encrypt LinkedIn profile")

    def _scrape_linkedin(self, url: str) -> list[ScrapedJob]:
        """Scrape LinkedIn job search results."""
        jobs: list[ScrapedJob] = []
        try:
            browser = self._get_playwright_browser()
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(self.scrape_delay)

            # Parse job cards
            cards = page.query_selector_all("div[data-job-id], li.jobs-search-results__list-item")
            for card in cards[:25]:
                try:
                    title_el = card.query_selector("a.job-card-list__title, a.job-card-container__link")
                    if not title_el:
                        continue

                    title = (title_el.inner_text() or "").strip()
                    href = title_el.get_attribute("href") or ""
                    if href and not href.startswith("http"):
                        href = f"https://www.linkedin.com{href}"

                    company_el = card.query_selector(".job-card-container__primary-description, .artdeco-entity-lockup__subtitle")
                    company = (company_el.inner_text() or "").strip() if company_el else ""

                    loc_el = card.query_selector(".job-card-container__metadata-item, .artdeco-entity-lockup__caption")
                    location = (loc_el.inner_text() or "").strip() if loc_el else ""

                    if title and href:
                        # Clean URL
                        href = clean_search_url(href.split("?")[0])
                        jobs.append(ScrapedJob(
                            company=company, position=title, location=location,
                            url=href, jd_text="", source="linkedin",
                        ))
                except Exception:
                    continue

            page.close()
        except Exception:
            log.exception("Failed to scrape LinkedIn search results")
        return jobs

    def _scrape_linkedin_posting(self, url: str) -> ScrapedJob | None:
        """Scrape a single LinkedIn job posting for its full description."""
        try:
            browser = self._get_playwright_browser()
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(self.scrape_delay)

            title_el = page.query_selector("h1.t-24, h1.job-details-jobs-unified-top-card__job-title")
            title = (title_el.inner_text() or "").strip() if title_el else ""

            company_el = page.query_selector("a.app-aware-link[href*='/company/'], .job-details-jobs-unified-top-card__company-name")
            company = (company_el.inner_text() or "").strip() if company_el else ""

            loc_el = page.query_selector(".job-details-jobs-unified-top-card__bullet, span.t-black--light")
            location = (loc_el.inner_text() or "").strip() if loc_el else ""

            jd_el = page.query_selector("div.jobs-description__content, div.jobs-box__html-content")
            jd_text = (jd_el.inner_text() or "").strip() if jd_el else ""

            page.close()

            if title:
                return ScrapedJob(
                    company=company, position=title, location=location,
                    url=url, jd_text=jd_text[:10000], source="linkedin",
                )
        except Exception:
            log.exception("Failed to scrape LinkedIn posting")
        finally:
            self._close_playwright()
        return None


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _extract_posting_metadata(
    soup: BeautifulSoup, url: str, source: str = "other"
) -> ScrapedJob | None:
    """Extract job metadata from a generic posting page."""
    # Title: og:title -> h1 -> page title
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title:
        title = og_title.get("content", "")
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # Company: og:site_name -> common selectors
    company = ""
    og_site = soup.find("meta", property="og:site_name")
    if og_site:
        company = og_site.get("content", "")
    if not company:
        for sel in (".company-name", "[data-testid='company-name']", ".employer-name"):
            el = soup.select_one(sel)
            if el:
                company = el.get_text(strip=True)
                break

    # Location
    location = ""
    for sel in (".location", "[data-testid*='location']", ".job-location"):
        el = soup.select_one(sel)
        if el:
            location = el.get_text(strip=True)
            break

    # Body text
    body = soup.find("body")
    jd_text = body.get_text(separator="\n", strip=True)[:10000] if body else ""

    if not title:
        return None

    return ScrapedJob(
        company=company, position=title, location=location,
        url=url, jd_text=jd_text, source=source,
    )


def _sanitize_job(job: ScrapedJob) -> ScrapedJob:
    """Run a scraped job's description through the sanitizer."""
    from jobhunter.core.jd_sanitizer import sanitize

    context = f"{job.position} at {job.company}" if job.position else ""
    result = sanitize(job.jd_text, job_context=context)

    if result.is_suspicious:
        log.warning(
            "Sanitized JD for %s - %s: %s",
            job.company, job.position, result.summary,
        )

    job.jd_text = result.clean_text
    return job
