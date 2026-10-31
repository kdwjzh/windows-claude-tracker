"""設定視窗的 Qt 樣式表（顏色全部來自 theme.DialogPalette）。"""

from __future__ import annotations

from usage_monitor.ui.theme import FONT_FAMILIES, DialogPalette


def stylesheet(p: DialogPalette) -> str:
    families = ", ".join(f'"{f}"' for f in FONT_FAMILIES)
    return f"""
    QWidget#settingsRoot {{ background: {p.window}; }}
    QWidget {{ font-family: {families}; font-size: 14px; color: {p.text}; }}
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
    QLabel#pageTitle {{ font-size: 28px; font-weight: 600; }}
    QLabel#section {{ font-size: 14px; font-weight: 600; padding-top: 14px; }}

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
