# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for JobHunter.

Build with:
    pyinstaller jobhunter.spec

Output goes to dist/JobHunter/
"""

import sys
from pathlib import Path

block_cipher = None

# Project paths
PROJECT_ROOT = Path(SPECPATH)
SRC = PROJECT_ROOT / "src" / "jobhunter"

# Collect data files
datas = [
    # Prompt templates
    (str(SRC / "prompts"), "jobhunter/prompts"),
    # Resume templates
    (str(SRC / "templates" / "*.docx"), "jobhunter/templates"),
    # Default config
    (str(SRC / "default_config.json"), "jobhunter"),
]

# Hidden imports that PyInstaller can't detect
hiddenimports = [
    # fastembed internals
    "fastembed",
    "fastembed.text",
    "fastembed.text.text_embedding",
    "fastembed.common",
    "fastembed.common.onnx_model",

    # ONNX Runtime
    "onnxruntime",
    "onnxruntime.capi",

    # PySide6 modules we use
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",

    # Optional LLM provider SDKs (imported dynamically)
    # Only included if installed -- PyInstaller skips missing ones
    "anthropic",
    "openai",
    "google.generativeai",

    # Standard lib modules sometimes missed
    "sqlite3",
    "json",
    "html",
    "html.parser",
    "urllib.parse",

    # Document extraction
    "fitz",
    "docx",
    "openpyxl",

    # Scraping
    "bs4",
    "lxml",
    "lxml.etree",
    "trafilatura",

    # Encryption
    "cryptography",
    "cryptography.fernet",
    "keyring",
    "keyring.backends",

    # Our own modules
    "jobhunter.core.llm_client",
    "jobhunter.core.embeddings",
    "jobhunter.core.job_db",
    "jobhunter.core.resume_db",
    "jobhunter.core.fit_scorer",
    "jobhunter.core.resume_selector",
    "jobhunter.core.cover_letter",
    "jobhunter.core.docx_builder",
    "jobhunter.core.doc_extractor",
    "jobhunter.core.scraper",
    "jobhunter.core.export",
    "jobhunter.core.jd_sanitizer",
    "jobhunter.core.profile_vault",
    "jobhunter.gui.theme",
    "jobhunter.gui.dashboard",
    "jobhunter.gui.resume_library",
    "jobhunter.gui.search_urls",
    "jobhunter.gui.followups",
    "jobhunter.gui.settings_panel",
    "jobhunter.gui.wizard",
    "jobhunter.gui.workers",
    "jobhunter.gui.job_model",
    "jobhunter.config",
]

# Exclude heavy packages we don't need
excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "sentence_transformers",
    "transformers",
    "tensorflow",
    "keras",
    "matplotlib",
    "scipy",
    "pandas",
    # "PIL",  # Required by fastembed
    "tkinter",
    "unittest",
    "test",
    "distutils",
    "setuptools",
    "pkg_resources",
]

a = Analysis(
    [str(SRC / "app.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JobHunter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="JobHunter",
)
