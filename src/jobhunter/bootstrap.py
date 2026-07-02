#!/usr/bin/env python3
"""
JobHunter Bootstrap Script

Run this once after cloning the repo:
    python setup.py

It will:
  1. Check Python version (3.10+ required)
  2. Install project dependencies (including the jobhunter package)
  3. Install Playwright + Chromium browser
  4. Pre-download the BGE embedding model (~90MB)

Config and data directories are created automatically on first launch.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# -- Constants ---------------------------------------------------------------

MIN_PYTHON = (3, 10)
APP_DIR = Path.home() / ".jobhunter"
DATA_DIR = APP_DIR / "data"
CONFIG_PATH = APP_DIR / "config.json"

# bootstrap.py lives at src/jobhunter/bootstrap.py -- repo root is two levels up
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BGE_MODEL = "BAAI/bge-base-en-v1.5"


def _print_header(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def _print_step(n: int, total: int, msg: str) -> None:
    print(f"  [{n}/{total}] {msg}")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, printing it first."""
    print(f"    > {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)


# -- Steps -------------------------------------------------------------------

def check_python() -> bool:
    """Step 1: Verify Python version."""
    v = sys.version_info
    if (v.major, v.minor) < MIN_PYTHON:
        print(f"  ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, "
              f"found {v.major}.{v.minor}.{v.micro}")
        return False
    print(f"  Python {v.major}.{v.minor}.{v.micro} -- OK")
    return True


def install_requirements() -> bool:
    """Step 2: Install project dependencies."""
    req_file = _REPO_ROOT / "requirements.txt"
    if not req_file.exists():
        print("  ERROR: requirements.txt not found")
        return False

    print("  Installing dependencies from requirements.txt...")
    print("  (First run installs ~15 packages, may take a few minutes)")
    print()
    result = _run([
        sys.executable, "-m", "pip", "install", "--progress-bar", "on",
        "-r", str(req_file)
    ])
    if result.returncode != 0:
        return False

    # Install the project itself in editable mode
    print()
    print("  Installing jobhunter package...")
    result = _run([
        sys.executable, "-m", "pip", "install", "--progress-bar", "on",
        "-e", str(_REPO_ROOT)
    ])
    return result.returncode == 0


def install_playwright() -> bool:
    """Step 3: Install Playwright Chromium browser."""
    try:
        import playwright  # noqa: F401
        print("  Playwright package found")
    except ImportError:
        print("  ERROR: Playwright not installed (should have been in step 2)")
        return False

    print("  Installing Chromium browser for Playwright (~150MB)...")
    result = _run([sys.executable, "-m", "playwright", "install", "chromium"])
    if result.returncode != 0:
        print("  WARNING: Playwright chromium install failed.")
        print("  You can install it manually later: playwright install chromium")
        print("  LinkedIn scraping won't work without it.")
    return True


def download_embedding_model() -> bool:
    """Step 4: Pre-download the BGE embedding model (ONNX format via fastembed)."""
    print(f"  Downloading {BGE_MODEL} ONNX model (~90MB on first run)...")
    print("  (This is the fast scoring model for job matching)")
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name=BGE_MODEL)
        vecs = list(model.embed(["test"]))
        print(f"  Model loaded and verified (dim={len(vecs[0])})")
        del model
        return True
    except Exception as exc:
        print(f"  WARNING: Failed to download model: {exc}")
        print("  The model will download automatically on first use.")
        return True  # Non-fatal


# -- Main --------------------------------------------------------------------

def main() -> int:
    _print_header("JobHunter Setup")

    total = 4
    steps = [
        (1, "Checking Python version...", check_python),
        (2, "Installing project dependencies...", install_requirements),
        (3, "Setting up Playwright + Chromium...", install_playwright),
        (4, "Downloading embedding model...", download_embedding_model),
    ]

    failed = False
    for step_num, msg, func in steps:
        _print_step(step_num, total, msg)
        if not func():
            print(f"\n  FAILED at step {step_num}. Fix the issue and re-run setup.py.\n")
            failed = True
            break

    if not failed:
        _print_header("Setup Complete!")
        print("  To start JobHunter:")
        print("    python -m jobhunter")
        print()
        print(f"  Config:  {CONFIG_PATH}")
        print(f"  Data:    {DATA_DIR}")
        print()
        print("  On first launch, a setup wizard will walk you through:")
        print("    - Choosing your AI provider (Claude, OpenAI, Gemini)")
        print("    - Entering your contact info")
        print("    - Importing your resumes")
        print("    - Logging into LinkedIn")
        print("    - Setting up your first job search")
        print()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
