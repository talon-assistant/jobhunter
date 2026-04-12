#!/usr/bin/env python3
"""
JobHunter setup.

When run directly (python setup.py): launches the bootstrap installer.
When invoked by pip/setuptools: does nothing (pyproject.toml handles it).
"""
import sys

if __name__ == "__main__" and len(sys.argv) == 1:
    # User ran: python setup.py  (no arguments)
    import subprocess
    from pathlib import Path

    bootstrap = Path(__file__).parent / "src" / "jobhunter" / "bootstrap.py"
    sys.exit(subprocess.call([sys.executable, str(bootstrap)]))
else:
    # pip/setuptools invoked us with arguments like egg_info, bdist_wheel, etc.
    # Defer entirely to pyproject.toml build-backend.
    try:
        from setuptools import setup
        setup()
    except ImportError:
        pass
