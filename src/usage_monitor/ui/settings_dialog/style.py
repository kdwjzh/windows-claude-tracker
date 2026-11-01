"""設定視窗的 Qt 樣式表（顏色全部來自 theme.DialogPalette）。"""

from __future__ import annotations

from usage_monitor.core.i18n import Lang
from usage_monitor.ui.theme import (
    DIALOG_FONT_FAMILIES_ZH,
    DIALOG_FONT_WEIGHT,
    FONT_FAMILIES,
    DialogPalette,
)


def font_families(lang: Lang) -> list[str]:
    return DIALOG_FONT_FAMILIES_ZH if lang is Lang.ZH_TW else FONT_FAMILIES


def stylesheet(p: DialogPalette, lang: Lang) -> str:
    families = ", ".join(f'"{f}"' for f in font_families(lang))
    bold = DIALOG_FONT_WEIGHT
    return f"""
    QWidget#settingsRoot {{ background: {p.window}; }}
    QWidget {{
        font-family: {families}; font-size: 14px; font-weight: {bold}; color: {p.text};
    }}
    QLabel {{ background: transparent; }}

    QListWidget#nav {{ background: transparent; border: none; outline: none; }}
    QListWidget#nav::item {{
        padding: 9px 14px; margin: 2px 0; border-radius: 6px;
        border-left: 3px solid transparent;
    }}
    QListWidget#nav::item:selected {{
        background: {p.nav_selected}; color: {p.text}; border-left: 3px solid {p.accent};
    }}
    QListWidget#nav::item:hover:!selected {{ background: {p.nav_selected}; }}

    QScrollArea {{ background: transparent; border: none; }}
    QWidget#page {{ background: transparent; }}
    QLabel#pageTitle {{ font-size: 28px; }}
    QLabel#section {{ font-size: 14px; padding-top: 14px; }}

    QWidget#card {{
        background: {p.card}; border: 1px solid {p.card_border}; border-radius: 6px;
    }}
    QLabel#cardTitle {{ font-size: 14px; }}
    QLabel#cardSubtitle {{ font-size: 12px; color: {p.text_secondary}; }}
    QLabel#statusOk {{ font-size: 12px; color: {p.ok_text}; }}
    QLabel#statusError {{ font-size: 12px; color: {p.error_text}; }}
    QLabel#switchLabel, QLabel#valueLabel {{ color: {p.text}; }}
    QLabel#hotkeyBox {{
        background: {p.control}; border: 1px solid {p.control_border}; border-radius: 4px;
        padding: 5px 12px;
    }}

    QComboBox, QPushButton {{
        background: {p.control}; border: 1px solid {p.control_border}; border-radius: 4px;
        padding: 6px 12px; min-height: 20px;
    }}
    QPushButton:hover, QComboBox:hover {{ border-color: {p.accent}; }}
    QComboBox QAbstractItemView {{
        background: {p.card}; border: 1px solid {p.control_border};
        selection-background-color: {p.nav_selected}; selection-color: {p.text};
    }}

    QSlider::groove:horizontal {{
        height: 4px; background: {p.control_border}; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: {p.accent}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    }}
    """
