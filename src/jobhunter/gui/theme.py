"""DearPyGui dark theme and color constants."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

# -- Fit score colors --
FIT_GREEN = (46, 125, 50, 255)      # >= 80
FIT_ORANGE = (239, 108, 0, 255)     # 60-79
FIT_RED = (198, 40, 40, 255)        # 1-59
FIT_GRAY = (136, 136, 136, 255)     # 0 / unscored

# -- Status colors --
STATUS_COLORS = {
    "new": (100, 181, 246, 255),
    "reviewing": (255, 213, 79, 255),
    "applied": (129, 199, 132, 255),
    "interviewing": (255, 183, 77, 255),
    "offer": (76, 175, 80, 255),
    "rejected": (239, 83, 80, 255),
    "withdrawn": (158, 158, 158, 255),
    "archived": (97, 97, 97, 255),
}

# -- Priority badge colors --
PRIORITY_STRONG = (76, 175, 80, 255)
PRIORITY_NORMAL = (200, 200, 200, 255)
PRIORITY_WEAK = (158, 158, 158, 255)

# -- General --
BG_DARK = (30, 30, 46)
BG_SURFACE = (45, 45, 65)
TEXT_PRIMARY = (205, 214, 244)
TEXT_DIM = (147, 153, 178)
ACCENT = (137, 180, 250)


def apply_dark_theme() -> int:
    """Create and bind a dark theme. Returns theme tag."""
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            # Window
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, BG_DARK)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, BG_DARK)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, BG_SURFACE)

            # Text
            dpg.add_theme_color(dpg.mvThemeCol_Text, TEXT_PRIMARY)

            # Frame/Input
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, BG_SURFACE)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (55, 55, 80))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (65, 65, 95))

            # Button
            dpg.add_theme_color(dpg.mvThemeCol_Button, (69, 71, 90))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (88, 91, 112))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, ACCENT)

            # Header (table headers, collapsible headers)
            dpg.add_theme_color(dpg.mvThemeCol_Header, BG_SURFACE)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (55, 55, 80))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (65, 65, 95))

            # Tab
            dpg.add_theme_color(dpg.mvThemeCol_Tab, BG_SURFACE)
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (65, 65, 95))
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, ACCENT)

            # Table
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, BG_SURFACE)
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBg, BG_DARK)
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, (35, 35, 52))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, (69, 71, 90))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, (49, 50, 68))

            # Scrollbar
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, BG_DARK)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (69, 71, 90))

            # Separator
            dpg.add_theme_color(dpg.mvThemeCol_Separator, (69, 71, 90))

            # Rounding
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 4)

    dpg.bind_theme(theme)
    return theme


def fit_score_color(score: int) -> tuple[int, int, int, int]:
    """Return the color tuple for a given fit score."""
    if score >= 80:
        return FIT_GREEN
    elif score >= 60:
        return FIT_ORANGE
    elif score >= 1:
        return FIT_RED
    return FIT_GRAY
