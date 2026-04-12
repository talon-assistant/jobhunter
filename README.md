# JobHunter

CPU-only standalone job search assistant with local LLM scoring, resume tailoring, and cover letter generation.

## Features

- **Job Dashboard** -- Scrape, track, and score job listings from LinkedIn, Dice, Built In, Glassdoor, and generic ATS pages
- **Two-Phase Scoring** -- Fast BGE embedding similarity for all jobs, deep LLM analysis for top candidates
- **Resume Library** -- Build and maintain a fabrication-proof bullet library from your existing resumes. Bulk import, deduplication, LLM-assisted refinement
- **Resume Tailoring** -- Index-based bullet selection (the LLM picks from your library, never generates fake content)
- **Cover Letters** -- LLM-generated cover letters grounded in your actual experience and the job description
- **Application Timeline** -- Track status changes, materials generated, follow-up reminders
- **XLSX Export** -- Export tracking data for unemployment reporting

## Tech Stack

| Component | Choice |
|-----------|--------|
| GUI | DearPyGui |
| LLM | Any GGUF model via llama-server (designed for Gemma 4 26B-A4B) |
| Fast Scoring | BAAI/bge-base-en-v1.5 embeddings |
| LinkedIn Scraping | Playwright (persistent login context) |
| Other Scraping | requests + BeautifulSoup + trafilatura |
| Database | SQLite |
| Documents | python-docx, openpyxl |

## Requirements

- Python 3.10+
- 16-32 GB RAM (16 GB works with sequenced operations, 32 GB is comfortable)
- llama-server (from llama.cpp) for LLM features
- A GGUF model file (recommended: Gemma 4 26B-A4B Q4_K_M)

## Quick Start

```bash
git clone https://github.com/talon-assistant/jobhunter.git
cd jobhunter
python setup.py
```

The setup script handles everything:
1. Checks Python version
2. Installs CPU-only PyTorch
3. Installs all dependencies
4. Installs Playwright + Chromium
5. Downloads the BGE embedding model (~440MB)
6. Creates config and data directories
7. Optionally configures your GGUF model path

Then launch:
```bash
python -m jobhunter
```

## Manual Install

If you prefer to install manually:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e .
playwright install chromium
python -m jobhunter
```

## Configuration

Config lives at `~/.jobhunter/config.json` (created on first run or by setup.py).

Key settings:
- **LLM Server**: model path, port, context size, threads
- **Resume Header**: your name, email, phone, location (used in generated documents)
- **Scoring Thresholds**: fast/deep thresholds, auto-archive cutoff
- **Scraping**: LinkedIn profile directory, enabled boards

All settings are configurable through the Settings tab in the app.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Architecture

```
src/jobhunter/
  core/       Backend logic (no GUI imports)
  gui/        DearPyGui views (imports core/, never imported by core/)
  prompts/    LLM prompt templates (editable text files)
```

The core modules are fully testable without the GUI. All LLM prompts are stored as plain text files in `prompts/` and can be edited without code changes.

## License

MIT
