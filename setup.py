#!/usr/bin/env python3
"""
JobHunter Setup Script

Run this once after cloning the repo:
    python setup.py

It will:
  1. Check Python version (3.10+ required)
  2. Install CPU-only PyTorch
  3. Install all project dependencies
  4. Install Playwright + Chromium browser
  5. Pre-download the BGE embedding model (~440MB)
  6. Create config and data directories
  7. Optionally configure your GGUF model path
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# -- Constants ---------------------------------------------------------------

MIN_PYTHON = (3, 10)
APP_DIR = Path.home() / ".jobhunter"
DATA_DIR = APP_DIR / "data"
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_CONFIG = Path(__file__).parent / "src" / "jobhunter" / "default_config.json"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
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


def _pip_install(packages: list[str], extra_args: list[str] | None = None) -> bool:
    cmd = [sys.executable, "-m", "pip", "install", "--quiet"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.extend(packages)
    result = _run(cmd)
    return result.returncode == 0


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


def install_torch_cpu() -> bool:
    """Step 2: Install CPU-only PyTorch."""
    try:
        import torch
        print(f"  PyTorch {torch.__version__} already installed -- skipping")
        return True
    except ImportError:
        pass

    print("  Installing CPU-only PyTorch (this may take a few minutes)...")
    return _pip_install(["torch"], extra_args=["--index-url", TORCH_CPU_INDEX])


def install_requirements() -> bool:
    """Step 3: Install project dependencies."""
    req_file = Path(__file__).parent / "requirements.txt"
    if not req_file.exists():
        print("  ERROR: requirements.txt not found")
        return False

    print("  Installing dependencies from requirements.txt...")
    result = _run([
        sys.executable, "-m", "pip", "install", "--quiet", "-r", str(req_file)
    ])
    if result.returncode != 0:
        return False

    # Also install the project itself in editable mode
    print("  Installing jobhunter package...")
    result = _run([
        sys.executable, "-m", "pip", "install", "--quiet", "-e",
        str(Path(__file__).parent)
    ])
    return result.returncode == 0


def install_playwright() -> bool:
    """Step 4: Install Playwright Chromium browser."""
    try:
        import playwright
        print(f"  Playwright package found")
    except ImportError:
        print("  ERROR: Playwright not installed (should have been in step 3)")
        return False

    print("  Installing Chromium browser for Playwright...")
    result = _run([sys.executable, "-m", "playwright", "install", "chromium"])
    if result.returncode != 0:
        print("  WARNING: Playwright chromium install failed.")
        print("  You can install it manually later: playwright install chromium")
        print("  LinkedIn scraping won't work without it.")
        # Non-fatal -- everything else still works
    return True


def download_embedding_model() -> bool:
    """Step 5: Pre-download the BGE embedding model."""
    print(f"  Downloading {BGE_MODEL} (~440MB on first run)...")
    try:
        from sentence_transformers import SentenceTransformer
        # This triggers the download if not cached
        model = SentenceTransformer(BGE_MODEL, device="cpu")
        # Quick sanity check
        vec = model.encode("test", normalize_embeddings=True)
        print(f"  Model loaded and verified (dim={len(vec)})")
        del model
        return True
    except Exception as exc:
        print(f"  WARNING: Failed to download model: {exc}")
        print("  The model will download automatically on first use.")
        return True  # Non-fatal


def setup_config_and_dirs() -> bool:
    """Step 6: Create config and data directories."""
    # Directories
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DIR / "linkedin_profile").mkdir(parents=True, exist_ok=True)
    print(f"  Created {APP_DIR}")
    print(f"  Created {DATA_DIR}")

    # Config
    if CONFIG_PATH.exists():
        print(f"  Config already exists at {CONFIG_PATH} -- merging new keys")
        with open(DEFAULT_CONFIG, encoding="utf-8") as f:
            defaults = json.load(f)
        with open(CONFIG_PATH, encoding="utf-8") as f:
            user = json.load(f)

        merged = _deep_merge(user, defaults)
        if merged != user:
            CONFIG_PATH.write_text(json.dumps(merged, indent=4), encoding="utf-8")
            print("  Merged new config keys")
    else:
        shutil.copy2(DEFAULT_CONFIG, CONFIG_PATH)
        print(f"  Created default config at {CONFIG_PATH}")

    return True


def configure_model() -> bool:
    """Step 7: Optionally set the GGUF model path."""
    print()
    print("  JobHunter uses Gemma 4 26B-A4B (or any GGUF model) via llama-server.")
    print("  You need llama-server installed and a GGUF model file.")
    print()

    response = input("  Do you have a GGUF model file to configure now? [y/N] ").strip().lower()
    if response not in ("y", "yes"):
        print("  Skipped. You can set it later in Settings.")
        return True

    model_path = input("  Path to GGUF model file: ").strip().strip('"').strip("'")
    if not model_path:
        print("  Skipped.")
        return True

    model_path = str(Path(model_path).resolve())
    if not Path(model_path).is_file():
        print(f"  WARNING: File not found: {model_path}")
        print("  Saving anyway -- make sure the file exists before starting the server.")

    # Update config
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    config.setdefault("llm_server", {})["model_path"] = model_path
    CONFIG_PATH.write_text(json.dumps(config, indent=4), encoding="utf-8")
    print(f"  Model path saved to config")

    # Check for llama-server
    llama_bin = shutil.which("llama-server")
    if llama_bin:
        print(f"  llama-server found: {llama_bin}")
    else:
        print("  WARNING: llama-server not found in PATH.")
        print("  Download llama.cpp and ensure llama-server is in your PATH.")
        print("  LLM features (scoring, cover letters) won't work without it.")

    return True


# -- Helpers -----------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if key not in merged:
            merged[key] = value
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
    return merged


# -- Main --------------------------------------------------------------------

def main() -> int:
    _print_header("JobHunter Setup")

    total = 7
    steps = [
        (1, "Checking Python version...", check_python),
        (2, "Installing CPU-only PyTorch...", install_torch_cpu),
        (3, "Installing project dependencies...", install_requirements),
        (4, "Setting up Playwright + Chromium...", install_playwright),
        (5, "Downloading embedding model...", download_embedding_model),
        (6, "Creating config and directories...", setup_config_and_dirs),
        (7, "Configuring LLM model (optional)...", configure_model),
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
        print(f"    python -m jobhunter")
        print()
        print("  Config location:")
        print(f"    {CONFIG_PATH}")
        print()
        print("  Data directory:")
        print(f"    {DATA_DIR}")
        print()
        print("  Next steps:")
        print("    1. Launch the app:  python -m jobhunter")
        print("    2. Go to Settings tab to configure LLM server (if not done above)")
        print("    3. Go to Search URLs tab to add job board search URLs")
        print("    4. Go to Resume Library tab to import your resumes")
        print()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
