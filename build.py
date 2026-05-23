#!/usr/bin/env python3
"""
Build JobHunter into a standalone executable.

Usage:
    python build.py

Output:
    dist/JobHunter/         -- folder with exe + all dependencies
    dist/JobHunter.exe      -- the main executable

Requires: pip install pyinstaller
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"


def main() -> int:
    print("=" * 60)
    print("  Building JobHunter")
    print("=" * 60)

    # Check pyinstaller
    if not shutil.which("pyinstaller"):
        print("\nERROR: pyinstaller not found. Install it:")
        print("  pip install pyinstaller")
        return 1

    # Clean previous builds
    print("\n[1/3] Cleaning previous builds...")
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed {d}")

    # Run PyInstaller
    print("\n[2/3] Running PyInstaller (this takes a few minutes)...")
    spec_file = PROJECT_ROOT / "jobhunter.spec"

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec_file), "--noconfirm"],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        print("\nERROR: PyInstaller build failed.")
        return 1

    # Verify output
    print("\n[3/3] Verifying build...")
    if platform.system() == "Windows":
        exe_path = DIST_DIR / "JobHunter" / "JobHunter.exe"
    else:
        exe_path = DIST_DIR / "JobHunter" / "JobHunter"

    if not exe_path.exists():
        print(f"\nERROR: Expected executable not found at {exe_path}")
        return 1

    # Calculate size
    total_size = sum(
        f.stat().st_size for f in (DIST_DIR / "JobHunter").rglob("*") if f.is_file()
    )
    size_mb = total_size / (1024 * 1024)

    print(f"\n  Build complete!")
    print(f"  Executable: {exe_path}")
    print(f"  Total size: {size_mb:.0f} MB")
    print(f"\n  To run:")
    print(f"    {exe_path}")

    # Note about Playwright
    print(f"\n  NOTE: Playwright Chromium is NOT bundled.")
    print(f"  Users need to run 'playwright install chromium' separately,")
    print(f"  or LinkedIn scraping won't work. All other features work")
    print(f"  out of the box.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
