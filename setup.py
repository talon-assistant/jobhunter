#!/usr/bin/env python3
"""JobHunter setup -- run: python setup.py"""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    bootstrap = Path(__file__).parent / "src" / "jobhunter" / "bootstrap.py"
    sys.exit(subprocess.call([sys.executable, str(bootstrap)]))
