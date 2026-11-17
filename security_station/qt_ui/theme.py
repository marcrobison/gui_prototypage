"""Colours and the application-wide Qt stylesheet (matches the web UI)."""

BG = "#08131d"
BG_2 = "#0d2233"
TILE = "#10263a"
TILE_2 = "#132c42"
BORDER = "#1e4565"
BORDER_HOVER = "#2f6e9c"
TEXT = "#e8f1f8"
MUTED = "#8fa9bf"
ACCENT = "#38d6f5"
ACCENT_2 = "#1d8fd8"
RED = "#ff4d4f"
AMBER = "#f5b638"
GREEN = "#3ddc84"
SEVERITY_BG = {"HIGH": "#5e1c22", "MEDIUM": "#4f3d14", "INFO": "#174a33"}
SEVERITY_FG = {"HIGH": "#ff7a7c", "MEDIUM": AMBER, "INFO": GREEN}

STYLESHEET = f"""
QWidget {{ color: {TEXT}; }}
QMainWindow, #root {{
    background: qradialgradient(cx:0.3, cy:0, radius:1.2, fx:0.3, fy:0,
                                stop:0 {BG_2}, stop:0.7 {BG});
}}
QLabel {{ background: transparent; }}

Tile {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {TILE_2}, stop:1 {TILE});
    border: 2px solid {BORDER};
    border-radius: 10px;
}}
Tile[hover="true"] {{ border-color: {BORDER_HOVER}; }}

QLabel[role="title"] {{ font-weight: bold; font-size: 10.5pt; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="warn"] {{ color: {AMBER}; font-size: 9pt; }}
QLabel[role="msg-ok"] {{ color: {GREEN}; }}
QLabel[role="msg-err"] {{ color: {RED}; }}

QToolButton#expand {{
    background: transparent; border: none; color: {MUTED}; font-size: 12pt; padding: 0 4px;
}}
QToolButton#expand:hover {{ color: {ACCENT}; }}

QPushButton[role="ctl"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #23384c, stop:1 #172a3b);
    border: 1px solid #3b5a75; border-radius: 6px; padding: 6px 10px;
    color: #cfe0ee; font-weight: 600; font-size: 9.5pt;
}}
QPushButton[role="ctl"]:hover {{ border-color: {ACCENT}; color: white; }}
QPushButton[role="ctl"][state="on"] {{ border-color: {GREEN}; color: {GREEN}; }}
QPushButton[role="ctl"][state="ringing"] {{ border-color: {AMBER}; color: {AMBER}; }}

QPushButton[role="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2f8ee8, stop:1 #1b5fb0);
    border: 1px solid #5fb1ff; border-radius: 8px; padding: 10px 12px;
    color: white; font-weight: bold; font-size: 11pt;
}}
QPushButton[role="primary"]:hover {{ background: #3a9af0; }}
QPushButton[role="primary"]:disabled {{ background: #2a5a85; color: #c0d0e0; }}

QPushButton#back {{
    background: #183149; border: 1px solid #3b5a75; border-radius: 8px;
    padding: 8px 16px; font-weight: bold; font-size: 11pt;
}}
QPushButton#back:hover {{ border-color: {ACCENT}; }}

QLineEdit {{
    background: rgba(0, 0, 0, 90); border: 2px solid #3b5a75; border-radius: 6px;
    padding: 6px 8px; font-size: 12pt; color: {TEXT};
    selection-background-color: {ACCENT_2};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QTableWidget {{
    background: rgba(0, 0, 0, 50); border: none; border-radius: 6px;
    gridline-color: transparent; font-size: 9.5pt;
}}
QHeaderView::section {{
    background: #132a3e; color: {TEXT}; font-weight: bold; border: none; padding: 3px 8px;
}}
QTableCornerButton::section {{ background: #132a3e; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2b4a66; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: #2b4a66; border-radius: 4px; min-width: 24px; }}

QComboBox {{
    background: #132a3e; border: 1px solid #3b5a75; border-radius: 6px; padding: 4px 8px;
}}
QComboBox QAbstractItemView {{ background: #132a3e; selection-background-color: {ACCENT_2}; }}

QFrame#fact {{ background: rgba(0, 0, 0, 55); border: 1px solid rgba(255, 255, 255, 18); border-radius: 8px; }}
QLabel[role="fact-label"] {{ color: {MUTED}; font-size: 9pt; }}
QLabel[role="fact-value"] {{ font-size: 15pt; font-weight: bold; }}

QDialog {{ background: {TILE}; }}
#footer {{ color: #6d8297; font-weight: 600; letter-spacing: 3px; font-size: 8.5pt; }}
"""


def app_font():
    from PySide6.QtGui import QFont
    font = QFont()
    font.setFamilies(["Noto Sans", "DejaVu Sans", "Sans Serif"])
    font.setPointSizeF(10.5)
    return font
