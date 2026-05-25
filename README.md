# JobHunter

Job search assistant with AI-powered scoring, resume tailoring, and cover letter generation.

## Download

**Windows**: Grab the latest release from [Releases](https://github.com/talon-assistant/jobhunter/releases) — extract the zip and run `JobHunter.exe`. No Python required.

A setup wizard walks you through provider selection, resume import, and LinkedIn login on first launch.

## Features

- **Job Dashboard** — Scrape, track, and score job listings from LinkedIn, Dice, Built In, Glassdoor, and generic ATS pages
- **Two-Phase Scoring** — Fast BGE embedding similarity for all jobs, deep LLM analysis for top candidates
- **Resume Library** — Build a fabrication-proof bullet library from your existing resumes. Bulk import, deduplication, LLM-assisted refinement
- **Resume Tailoring** — Index-based bullet selection (the AI picks from your library, never generates fake content)
- **ATS-Friendly Templates** — 4 built-in resume templates (Classic, Modern, Executive, Compact) optimized for ATS parsing and human readability
- **Cover Letters** — AI-generated cover letters grounded in your actual experience and the job description
- **Application Timeline** — Track status changes, materials generated, follow-up reminders
- **XLSX Export** — Export tracking data for unemployment reporting

## AI Providers

JobHunter uses AI for scoring jobs, tailoring resumes, and writing cover letters. You choose your provider during setup:

| Provider | API Key Needed | Cost | Notes |
|----------|---------------|------|-------|
| **Claude CLI** (recommended) | No | Uses your existing Claude plan | Requires [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed |
| **Anthropic API** | Yes | ~$0.01-0.05 per job scored | Direct API, fast |
| **OpenAI API** | Yes | ~$0.01-0.05 per job scored | GPT-4o or other models |
| **Google Gemini API** | Yes | Free tier available | Gemini models |
| **Local / OpenAI-compatible** | Varies | Free if self-hosted | Ollama, llama-server, etc. |

**Cost note**: API-based providers charge per token. Scoring a batch of 50 jobs typically costs $0.50-2.00 depending on the provider and model. Cover letters and resume tailoring cost a few cents each. Claude CLI uses your existing Claude subscription with no additional API charges.

API keys are stored in your OS keyring (Windows Credential Manager / macOS Keychain), not in config files.

## Tech Stack

| Component | Choice |
|-----------|--------|
| GUI | PySide6 (Qt) with model/view architecture |
| AI | Claude CLI, Anthropic, OpenAI, Gemini, or any OpenAI-compatible endpoint |
| Fast Scoring | BAAI/bge-base-en-v1.5 via fastembed (ONNX Runtime) |
| LinkedIn Scraping | Playwright (persistent login context, encrypted at rest) |
| Other Scraping | requests + BeautifulSoup + trafilatura |
| Database | SQLite |
| Documents | python-docx, openpyxl |

## Quick Start (from source)

```bash
git clone https://github.com/talon-assistant/jobhunter.git
cd jobhunter
python setup.py
python -m jobhunter
```

The setup script installs dependencies, Playwright, and the BGE embedding model (~90MB). On first launch, a wizard walks you through:

1. Choosing your AI provider
2. Entering your contact info
3. Importing your resumes
4. Logging into LinkedIn
5. Setting up your first job search

## Manual Install

```bash
pip install -e .
playwright install chromium
python -m jobhunter
```

## Configuration

All settings are configurable through the **Settings tab** in the app. No config files to edit.

- **AI Provider**: provider, model, API key (stored in OS keyring)
- **Resume Header**: name, email, phone, location
- **Resume Template**: Classic, Modern, Executive, or Compact
- **Scoring Thresholds**: fast/deep thresholds, auto-archive cutoff
- **Cover Letter Style**: tone and formatting rules
- **Scraping**: enabled boards, delays

## Building the Executable

```bash
pip install pyinstaller
python build.py
```

Output: `dist/JobHunter/JobHunter.exe` (~470MB). To create a Windows installer, open `installer.iss` in [Inno Setup](https://jrsoftware.org/isinfo.php).

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

73 tests covering the LLM client, job database, resume database, scoring, document generation, and extraction.

## Architecture

```
src/jobhunter/
  core/        Backend logic (no GUI imports)
  gui/         PySide6 views (imports core/, never imported by core/)
  prompts/     LLM prompt templates (editable text files)
  templates/   ATS-friendly DOCX resume templates
```

The core modules are fully testable without the GUI. All LLM prompts are stored as plain text files in `prompts/` and can be edited without code changes.

## License

MIT
