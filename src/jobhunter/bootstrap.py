#!/usr/bin/env python3
"""
JobHunter Bootstrap Script

Run this once after cloning the repo:
    python setup.py

It will:
  1. Check Python version (3.10+ required)
  2. Install CPU-only PyTorch
  3. Install all project dependencies
  4. Install Playwright + Chromium browser
  5. Pre-download the BGE embedding model (~440MB)
  6. Create config and data directories
  7. Optionally download a GGUF model (~14GB)
  8. Configure LLM model path
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

# -- Constants ---------------------------------------------------------------

MIN_PYTHON = (3, 10)
APP_DIR = Path.home() / ".jobhunter"
DATA_DIR = APP_DIR / "data"
MODELS_DIR = APP_DIR / "models"
CONFIG_PATH = APP_DIR / "config.json"

# bootstrap.py lives at src/jobhunter/bootstrap.py -- repo root is two levels up
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = Path(__file__).parent / "default_config.json"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
BGE_MODEL = "BAAI/bge-base-en-v1.5"

# Recommended GGUF model
GGUF_MODELS = {
    "gemma-4-26b-a4b-q4": {
        "name": "Gemma 4 26B-A4B Q4_K_M (recommended)",
        "url": "https://huggingface.co/bartowski/google_gemma-4-26B-A4B-it-GGUF/resolve/main/google_gemma-4-26B-A4B-it-Q4_K_M.gguf",
        "filename": "gemma-4-26B-A4B-it-Q4_K_M.gguf",
        "size_gb": 16.1,
        "ram_needed": "22 GB",
        "description": "Best quality for 32GB systems. MoE with only 3.8B active params.",
    },
    "gemma-4-12b-q4": {
        "name": "Gemma 4 12B Q4_K_M (lighter alternative)",
        "url": "https://huggingface.co/bartowski/google_gemma-4-12b-it-GGUF/resolve/main/google_gemma-4-12b-it-Q4_K_M.gguf",
        "filename": "gemma-4-12b-it-Q4_K_M.gguf",
        "size_gb": 7.4,
        "ram_needed": "12 GB",
        "description": "Good balance for 16GB systems. Dense 12B model.",
    },
}


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


def _download_with_progress(url: str, dest: Path) -> bool:
    """Download a file with a console progress bar."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JobHunter-Bootstrap/1.0"})
        with urllib.request.urlopen(req) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")

            with open(tmp, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total > 0:
                        pct = downloaded / total * 100
                        gb_done = downloaded / (1024**3)
                        gb_total = total / (1024**3)
                        bar_len = 30
                        filled = int(bar_len * downloaded / total)
                        bar = "#" * filled + "-" * (bar_len - filled)
                        print(f"\r    [{bar}] {pct:.1f}% ({gb_done:.1f}/{gb_total:.1f} GB)", end="", flush=True)
                    else:
                        gb_done = downloaded / (1024**3)
                        print(f"\r    Downloaded {gb_done:.1f} GB...", end="", flush=True)

            print()  # newline after progress bar
            tmp.rename(dest)
            return True

    except Exception as exc:
        print(f"\n  ERROR: Download failed: {exc}")
        # Clean up partial download
        tmp = dest.with_suffix(".tmp")
        if tmp.exists():
            tmp.unlink()
        return False


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

    if platform.system() == "Darwin":
        print("  Detected macOS -- installing default PyTorch (includes MPS support)")
        return _pip_install(["torch"])
    else:
        return _pip_install(["torch"], extra_args=["--index-url", TORCH_CPU_INDEX])


def install_requirements() -> bool:
    """Step 3: Install project dependencies."""
    req_file = _REPO_ROOT / "requirements.txt"
    if not req_file.exists():
        print("  ERROR: requirements.txt not found")
        return False

    print("  Installing dependencies from requirements.txt...")
    result = _run([
        sys.executable, "-m", "pip", "install", "--quiet", "-r", str(req_file)
    ])
    if result.returncode != 0:
        return False

    # Install the project itself in editable mode
    print("  Installing jobhunter package...")
    result = _run([
        sys.executable, "-m", "pip", "install", "--quiet", "-e",
        str(_REPO_ROOT)
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
    return True


def download_embedding_model() -> bool:
    """Step 5: Pre-download the BGE embedding model."""
    print(f"  Downloading {BGE_MODEL} (~440MB on first run)...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(BGE_MODEL, device="cpu")
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Created {APP_DIR}")
    print(f"  Created {DATA_DIR}")
    print(f"  Created {MODELS_DIR}")

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


def download_gguf_model() -> bool:
    """Step 7: Optionally download a GGUF model for local LLM inference."""
    print()
    print("  JobHunter uses a local GGUF model via llama-server for:")
    print("    - Deep job fit analysis")
    print("    - Resume bullet selection")
    print("    - Cover letter generation")
    print()

    # Check if any GGUF files already exist
    existing = list(MODELS_DIR.glob("*.gguf"))
    if existing:
        print(f"  Found existing model(s) in {MODELS_DIR}:")
        for f in existing:
            size_gb = f.stat().st_size / (1024**3)
            print(f"    - {f.name} ({size_gb:.1f} GB)")
        print()
        response = input("  Download another model? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            return True

    print("  Available models:\n")
    options = list(GGUF_MODELS.items())
    for i, (key, info) in enumerate(options, 1):
        print(f"    {i}. {info['name']}")
        print(f"       {info['description']}")
        print(f"       Size: {info['size_gb']:.1f} GB  |  RAM needed: {info['ram_needed']}")
        print()

    print(f"    {len(options)+1}. Skip (I'll provide my own model)")
    print(f"    {len(options)+2}. Skip (I already have a model file)")
    print()

    choice = input(f"  Choose [1-{len(options)+2}]: ").strip()
    try:
        choice_num = int(choice)
    except ValueError:
        print("  Skipped.")
        return True

    if choice_num > len(options):
        print("  Skipped.")
        return True

    key, info = options[choice_num - 1]
    dest = MODELS_DIR / info["filename"]

    if dest.exists():
        size_gb = dest.stat().st_size / (1024**3)
        print(f"  {info['filename']} already exists ({size_gb:.1f} GB) -- skipping download")
        return True

    print(f"\n  Downloading {info['name']}...")
    print(f"  Size: {info['size_gb']:.1f} GB")
    print(f"  Destination: {dest}")
    print()

    confirm = input("  This is a large download. Continue? [y/N] ").strip().lower()
    if confirm not in ("y", "yes"):
        print("  Skipped.")
        return True

    print()
    if not _download_with_progress(info["url"], dest):
        print("  Download failed. You can retry later or download manually from:")
        print(f"    {info['url']}")
        return True  # Non-fatal

    print(f"  Downloaded to {dest}")

    # Auto-set in config
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    config.setdefault("llm_server", {})["model_path"] = str(dest)
    CONFIG_PATH.write_text(json.dumps(config, indent=4), encoding="utf-8")
    print(f"  Model path saved to config")

    return True


def configure_llm() -> bool:
    """Step 8: Verify or set the LLM model path and check for llama-server."""
    # Check if model path is already configured
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    model_path = config.get("llm_server", {}).get("model_path", "")

    if model_path and Path(model_path).is_file():
        size_gb = Path(model_path).stat().st_size / (1024**3)
        print(f"  Model configured: {Path(model_path).name} ({size_gb:.1f} GB)")
    elif model_path:
        print(f"  WARNING: Configured model not found: {model_path}")
        response = input("  Enter path to a GGUF model file (or press Enter to skip): ").strip().strip('"').strip("'")
        if response:
            model_path = str(Path(response).resolve())
            config.setdefault("llm_server", {})["model_path"] = model_path
            CONFIG_PATH.write_text(json.dumps(config, indent=4), encoding="utf-8")
    else:
        # Check models directory
        existing = list(MODELS_DIR.glob("*.gguf"))
        if existing:
            # Auto-select the first one found
            model_path = str(existing[0])
            config.setdefault("llm_server", {})["model_path"] = model_path
            CONFIG_PATH.write_text(json.dumps(config, indent=4), encoding="utf-8")
            print(f"  Auto-configured model: {existing[0].name}")
        else:
            print("  No GGUF model configured.")
            print("  You can set it later in the Settings tab.")

    # Check for llama-server
    llama_bin = shutil.which("llama-server")
    if llama_bin:
        print(f"  llama-server found: {llama_bin}")
    else:
        print("  WARNING: llama-server not found in PATH.")
        print("  Download llama.cpp and ensure llama-server is accessible.")
        print("  https://github.com/ggml-org/llama.cpp/releases")
        print("  LLM features won't work without it (scoring, cover letters).")
        print("  Everything else (scraping, BGE scoring, tracking) works fine.")

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

    total = 8
    steps = [
        (1, "Checking Python version...", check_python),
        (2, "Installing CPU-only PyTorch...", install_torch_cpu),
        (3, "Installing project dependencies...", install_requirements),
        (4, "Setting up Playwright + Chromium...", install_playwright),
        (5, "Downloading embedding model...", download_embedding_model),
        (6, "Creating config and directories...", setup_config_and_dirs),
        (7, "Downloading LLM model (optional)...", download_gguf_model),
        (8, "Configuring LLM server...", configure_llm),
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
        print("  Config:  {CONFIG_PATH}")
        print(f"  Data:    {DATA_DIR}")
        print(f"  Models:  {MODELS_DIR}")
        print()
        print("  Next steps:")
        print("    1. Launch the app:  python -m jobhunter")
        print("    2. Go to Settings tab to fine-tune LLM server settings")
        print("    3. Go to Search URLs tab to add job board search URLs")
        print("    4. Go to Resume Library tab to import your resumes")
        print()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
