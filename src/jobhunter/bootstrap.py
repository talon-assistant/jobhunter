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
  5. Download and install llama-server (from llama.cpp)
  6. Pre-download the BGE embedding model (~440MB)
  7. Create config and data directories
  8. Optionally download a GGUF model (~14GB)
  9. Configure LLM server paths
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
BIN_DIR = APP_DIR / "bin"
CONFIG_PATH = APP_DIR / "config.json"

# bootstrap.py lives at src/jobhunter/bootstrap.py -- repo root is two levels up
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = Path(__file__).parent / "default_config.json"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
BGE_MODEL = "BAAI/bge-base-en-v1.5"
LLAMA_CPP_RELEASE_TAG = "b8762"

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
    cmd = [sys.executable, "-m", "pip", "install", "--progress-bar", "on"]
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

    print("  Installing CPU-only PyTorch...")
    print("  (This is ~2GB and may take several minutes on slow connections)")
    print()

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
    """Step 4: Install Playwright Chromium browser."""
    try:
        import playwright
        print(f"  Playwright package found")
    except ImportError:
        print("  ERROR: Playwright not installed (should have been in step 3)")
        return False

    print("  Installing Chromium browser for Playwright (~150MB)...")
    result = _run([sys.executable, "-m", "playwright", "install", "chromium"])
    if result.returncode != 0:
        print("  WARNING: Playwright chromium install failed.")
        print("  You can install it manually later: playwright install chromium")
        print("  LinkedIn scraping won't work without it.")
    return True


def install_llama_server() -> bool:
    """Step 5: Download and install llama-server binary."""
    # Check if already in PATH
    existing = shutil.which("llama-server")
    if existing:
        print(f"  llama-server already available: {existing}")
        return True

    # Check if already in our bin dir
    if platform.system() == "Windows":
        local_bin = BIN_DIR / "llama-server.exe"
    else:
        local_bin = BIN_DIR / "llama-server"

    if local_bin.exists():
        print(f"  llama-server already installed: {local_bin}")
        _add_to_path(BIN_DIR)
        return True

    # Determine platform and download URL
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        asset_name = f"llama-{LLAMA_CPP_RELEASE_TAG}-bin-win-cpu-x64.zip"
    elif system == "Darwin":
        if machine in ("arm64", "aarch64"):
            asset_name = f"llama-{LLAMA_CPP_RELEASE_TAG}-bin-macos-arm64.zip"
        else:
            asset_name = f"llama-{LLAMA_CPP_RELEASE_TAG}-bin-macos-x64.zip"
    elif system == "Linux":
        asset_name = f"llama-{LLAMA_CPP_RELEASE_TAG}-bin-linux-x64.zip"
    else:
        print(f"  WARNING: Unsupported platform '{system}'. Install llama-server manually.")
        return True  # Non-fatal

    url = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_RELEASE_TAG}/{asset_name}"

    print(f"  Downloading llama-server ({system} {machine})...")
    print(f"  From: {url}")
    print()

    # Download to temp file
    zip_path = BIN_DIR / asset_name
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    if not _download_with_progress(url, zip_path):
        print("  WARNING: Failed to download llama-server.")
        print("  You can install it manually from:")
        print("    https://github.com/ggml-org/llama.cpp/releases")
        return True  # Non-fatal

    # Extract everything -- llama-server needs companion DLLs/dylibs
    # (ggml-base.dll, ggml-cpu.dll, llama.dll, etc.)
    print("  Extracting...")
    import zipfile
    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            # Extract all files, flattening any subdirectory into BIN_DIR
            for member in zf.namelist():
                # Skip directories
                if member.endswith("/"):
                    continue
                basename = Path(member).name
                if not basename:
                    continue
                data = zf.read(member)
                dest = BIN_DIR / basename
                dest.write_bytes(data)

            # Set executable permissions on Unix
            if system != "Windows":
                for f in BIN_DIR.iterdir():
                    if f.is_file() and not f.suffix:
                        f.chmod(0o755)

            print(f"  Extracted {len(zf.namelist())} files to {BIN_DIR}")
    except Exception as exc:
        print(f"  WARNING: Failed to extract: {exc}")
        return True  # Non-fatal
    finally:
        try:
            zip_path.unlink()
        except Exception:
            pass

    _add_to_path(BIN_DIR)

    # Verify
    if shutil.which("llama-server"):
        print("  llama-server is now available in PATH")
    else:
        print(f"  llama-server installed to {BIN_DIR}")
        print(f"  NOTE: You may need to add {BIN_DIR} to your system PATH,")
        print(f"  or restart your terminal for the PATH change to take effect.")

    return True


def _add_to_path(bin_dir: Path) -> None:
    """Add a directory to the current process PATH."""
    bin_str = str(bin_dir)
    current_path = os.environ.get("PATH", "")
    if bin_str not in current_path:
        os.environ["PATH"] = bin_str + os.pathsep + current_path


def download_embedding_model() -> bool:
    """Pre-download the BGE embedding model (ONNX format via fastembed)."""
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
    """Step 9: Verify or set the LLM model path and check for llama-server."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    # -- llama-server binary --
    llama_bin = shutil.which("llama-server")
    if llama_bin:
        print(f"  llama-server: {llama_bin}")
        # Save the resolved path so the app doesn't depend on PATH
        config.setdefault("llm_server", {})["binary"] = llama_bin
    else:
        # Check our bin dir directly
        if platform.system() == "Windows":
            local = BIN_DIR / "llama-server.exe"
        else:
            local = BIN_DIR / "llama-server"
        if local.exists():
            print(f"  llama-server: {local}")
            config.setdefault("llm_server", {})["binary"] = str(local)
        else:
            print("  WARNING: llama-server not found.")
            print("  LLM features won't work without it.")
            print("  Everything else (scraping, BGE scoring, tracking) works fine.")

    # -- GGUF model --
    model_path = config.get("llm_server", {}).get("model_path", "")

    if model_path and Path(model_path).is_file():
        size_gb = Path(model_path).stat().st_size / (1024**3)
        print(f"  Model: {Path(model_path).name} ({size_gb:.1f} GB)")
    elif model_path:
        print(f"  WARNING: Configured model not found: {model_path}")
        response = input("  Enter path to a GGUF model file (or press Enter to skip): ").strip().strip('"').strip("'")
        if response:
            model_path = str(Path(response).resolve())
            config.setdefault("llm_server", {})["model_path"] = model_path
    else:
        existing = list(MODELS_DIR.glob("*.gguf"))
        if existing:
            model_path = str(existing[0])
            config.setdefault("llm_server", {})["model_path"] = model_path
            print(f"  Auto-configured model: {existing[0].name}")
        else:
            print("  No GGUF model configured.")
            print("  You can set it later in the Settings tab.")

    CONFIG_PATH.write_text(json.dumps(config, indent=4), encoding="utf-8")
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
        print(f"    python -m jobhunter")
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
