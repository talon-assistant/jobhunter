"""Manage a local llama-server subprocess for CPU-only inference."""

from __future__ import annotations

import json
import logging
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)


class LLMServerError(Exception):
    pass


class LLMServerManager:
    """Start, monitor, and stop a ``llama-server`` process."""

    def __init__(
        self,
        binary: str = "llama-server",
        model_path: str = "",
        port: int = 8080,
        ctx_size: int = 8192,
        threads: int = 4,
        n_gpu_layers: int = 0,
        extra_args: list[str] | None = None,
    ) -> None:
        self.binary = binary
        self.model_path = model_path
        self.port = port
        self.ctx_size = ctx_size
        self.threads = threads
        self.n_gpu_layers = n_gpu_layers
        self.extra_args = extra_args or []
        self._process: subprocess.Popen | None = None
        self._status = "stopped"  # stopped | starting | running | error

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def status(self) -> str:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status == "running"

    def start(self, *, timeout: int = 120) -> None:
        """Start llama-server and wait until it responds to health checks."""
        if self._process and self._process.poll() is None:
            log.info("llama-server already running (pid %d)", self._process.pid)
            return

        binary_path = shutil.which(self.binary)
        if not binary_path:
            raise LLMServerError(
                f"Cannot find '{self.binary}' in PATH. "
                "Download llama.cpp and ensure llama-server is accessible."
            )

        if not self.model_path or not Path(self.model_path).is_file():
            raise LLMServerError(
                f"Model file not found: {self.model_path}. "
                "Set llm_server.model_path in settings."
            )

        cmd = [
            binary_path,
            "--model", self.model_path,
            "--port", str(self.port),
            "--host", "127.0.0.1",
            "--ctx-size", str(self.ctx_size),
            "--threads", str(self.threads),
            "--n-gpu-layers", str(self.n_gpu_layers),
        ]

        # Gemma 4 thinking mode control
        cmd.extend([
            "--chat-template-kwargs",
            json.dumps({"enable_thinking": False}),
        ])

        cmd.extend(self.extra_args)

        log.info("Starting llama-server: %s", " ".join(cmd))
        self._status = "starting"

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            self._status = "error"
            raise LLMServerError(f"Failed to start llama-server: {exc}") from exc

        # Poll health endpoint until ready
        health_url = f"http://127.0.0.1:{self.port}/health"
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            # Check process is still alive
            if self._process.poll() is not None:
                stdout = self._process.stdout.read() if self._process.stdout else ""
                self._status = "error"
                raise LLMServerError(
                    f"llama-server exited with code {self._process.returncode}:\n{stdout[-2000:]}"
                )

            try:
                r = requests.get(health_url, timeout=3)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("status") in ("ok", "no slot available"):
                        self._status = "running"
                        log.info("llama-server ready (pid %d)", self._process.pid)
                        return
            except (requests.ConnectionError, requests.Timeout, ValueError):
                pass

            time.sleep(2)

        self._status = "error"
        self.stop()
        raise LLMServerError(f"llama-server did not become ready within {timeout}s")

    def stop(self, *, timeout: int = 10) -> None:
        """Gracefully stop the llama-server process."""
        if not self._process:
            self._status = "stopped"
            return

        if self._process.poll() is not None:
            self._status = "stopped"
            self._process = None
            return

        log.info("Stopping llama-server (pid %d)...", self._process.pid)

        try:
            self._process.terminate()
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.warning("llama-server did not stop gracefully, killing")
            self._process.kill()
            self._process.wait(timeout=5)

        self._status = "stopped"
        self._process = None
        log.info("llama-server stopped")

    def restart(self) -> None:
        """Stop and re-start the server."""
        self.stop()
        self.start()

    def read_log(self, max_lines: int = 50) -> str:
        """Read recent stdout/stderr from the server process."""
        if not self._process or not self._process.stdout:
            return ""
        # Non-blocking read isn't straightforward with Popen;
        # for now return empty string. Full log capture would need
        # a separate reader thread.
        return ""
