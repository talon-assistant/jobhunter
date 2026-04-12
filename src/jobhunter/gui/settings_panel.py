"""Settings tab: LLM config, resume header, scraping prefs."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from jobhunter.config import Config
from jobhunter.core.llm_client import LLMClient
from jobhunter.core.llm_server import LLMServerManager
from jobhunter.gui import dialogs, layout


class SettingsTab:
    """Application settings panel."""

    def __init__(
        self,
        config: Config,
        llm_server: LLMServerManager,
        llm_client: LLMClient,
    ) -> None:
        self.config = config
        self.server = llm_server
        self.llm = llm_client

    def build(self) -> None:
        dpg.add_text("Settings", color=(137, 180, 250))
        dpg.add_separator()

        # -- LLM Server --
        with dpg.collapsing_header(label="LLM Server", default_open=True):
            dpg.add_input_text(
                tag="cfg_model_path", label="Model Path (GGUF)",
                default_value=self.config.get("llm_server.model_path", ""),
                width=500,
            )
            dpg.add_input_int(
                tag="cfg_port", label="Port",
                default_value=self.config.get("llm_server.port", 8080),
                width=100,
            )
            dpg.add_input_int(
                tag="cfg_ctx_size", label="Context Size",
                default_value=self.config.get("llm_server.ctx_size", 8192),
                width=100,
            )
            dpg.add_input_int(
                tag="cfg_threads", label="Threads",
                default_value=self.config.get("llm_server.threads", 4),
                width=100,
            )
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Start Server", callback=self._on_start_server, width=100)
                dpg.add_button(label="Stop Server", callback=self._on_stop_server, width=100)
                dpg.add_button(label="Check Health", callback=self._on_check_health, width=100)
                dpg.add_spacer(width=10)
                dpg.add_text("--", tag="server_status_text", color=(158, 158, 158))

        dpg.add_spacer(height=10)

        # -- Resume Header --
        with dpg.collapsing_header(label="Resume Header", default_open=True):
            dpg.add_input_text(
                tag="cfg_name", label="Name",
                default_value=self.config.get("resume.name", ""), width=300,
            )
            dpg.add_input_text(
                tag="cfg_email", label="Email",
                default_value=self.config.get("resume.email", ""), width=300,
            )
            dpg.add_input_text(
                tag="cfg_phone", label="Phone",
                default_value=self.config.get("resume.phone", ""), width=300,
            )
            dpg.add_input_text(
                tag="cfg_location", label="Location",
                default_value=self.config.get("resume.location", ""), width=300,
            )
            dpg.add_input_text(
                tag="cfg_output_dir", label="Output Directory",
                default_value=self.config.get("resume.output_dir", ""), width=500,
            )

        dpg.add_spacer(height=10)

        # -- Cover Letter Style --
        with dpg.collapsing_header(label="Cover Letter Style"):
            dpg.add_input_text(
                tag="cfg_style_rules", label="Style Rules",
                default_value=self.config.get("resume.style_rules", ""),
                multiline=True, height=80, width=-1,
            )

        dpg.add_spacer(height=10)

        # -- Scoring --
        with dpg.collapsing_header(label="Scoring"):
            dpg.add_input_int(
                tag="cfg_deep_threshold", label="Deep Analysis Threshold",
                default_value=self.config.get("scoring.deep_threshold", 50),
                width=100,
            )
            dpg.add_input_int(
                tag="cfg_auto_archive", label="Auto-archive Below",
                default_value=self.config.get("scoring.auto_archive_below", 30),
                width=100,
            )

        dpg.add_spacer(height=10)

        # Save button
        dpg.add_button(label="Save Settings", callback=self._on_save, width=120)

    def _on_save(self, sender=None, app_data=None, user_data=None) -> None:
        self.config.set("llm_server.model_path", dpg.get_value("cfg_model_path"))
        self.config.set("llm_server.port", dpg.get_value("cfg_port"))
        self.config.set("llm_server.ctx_size", dpg.get_value("cfg_ctx_size"))
        self.config.set("llm_server.threads", dpg.get_value("cfg_threads"))
        self.config.set("resume.name", dpg.get_value("cfg_name"))
        self.config.set("resume.email", dpg.get_value("cfg_email"))
        self.config.set("resume.phone", dpg.get_value("cfg_phone"))
        self.config.set("resume.location", dpg.get_value("cfg_location"))
        self.config.set("resume.output_dir", dpg.get_value("cfg_output_dir"))
        self.config.set("resume.style_rules", dpg.get_value("cfg_style_rules"))
        self.config.set("scoring.deep_threshold", dpg.get_value("cfg_deep_threshold"))
        self.config.set("scoring.auto_archive_below", dpg.get_value("cfg_auto_archive"))
        self.config.save()

        # Update server config
        self.server.model_path = self.config.get("llm_server.model_path", "")
        self.server.port = self.config.get("llm_server.port", 8080)
        self.server.ctx_size = self.config.get("llm_server.ctx_size", 8192)
        self.server.threads = self.config.get("llm_server.threads", 4)

        # Update LLM client endpoint
        port = self.config.get("llm_server.port", 8080)
        self.llm.endpoint = f"http://localhost:{port}/v1/chat/completions"
        self.llm.health_endpoint = f"http://localhost:{port}/health"

        layout.set_status("Settings saved")

    def _on_start_server(self, sender=None, app_data=None, user_data=None) -> None:
        self._on_save()  # Save first to pick up any changes

        if dpg.does_item_exist("server_status_text"):
            dpg.set_value("server_status_text", "Starting...")

        from jobhunter.gui.workers import BackgroundTask

        def do_start():
            self.server.start(timeout=180)

        def on_done(_):
            layout.set_llm_status("Running", ok=True)
            if dpg.does_item_exist("server_status_text"):
                dpg.set_value("server_status_text", "Running")
                dpg.configure_item("server_status_text", color=(129, 199, 132))

        def on_error(exc):
            layout.set_llm_status("Error", ok=False)
            if dpg.does_item_exist("server_status_text"):
                dpg.set_value("server_status_text", f"Error: {exc}")
                dpg.configure_item("server_status_text", color=(239, 83, 80))
            dialogs.error_dialog("Server Error", str(exc))

        BackgroundTask(do_start, on_complete=on_done, on_error=on_error).start()

    def _on_stop_server(self, sender=None, app_data=None, user_data=None) -> None:
        self.server.stop()
        layout.set_llm_status("Stopped", ok=False)
        if dpg.does_item_exist("server_status_text"):
            dpg.set_value("server_status_text", "Stopped")
            dpg.configure_item("server_status_text", color=(158, 158, 158))

    def _on_check_health(self, sender=None, app_data=None, user_data=None) -> None:
        healthy = self.llm.is_healthy()
        if healthy:
            layout.set_llm_status("Running", ok=True)
            if dpg.does_item_exist("server_status_text"):
                dpg.set_value("server_status_text", "Healthy")
                dpg.configure_item("server_status_text", color=(129, 199, 132))
        else:
            layout.set_llm_status("Not responding", ok=False)
            if dpg.does_item_exist("server_status_text"):
                dpg.set_value("server_status_text", "Not responding")
                dpg.configure_item("server_status_text", color=(239, 83, 80))
