"""Application theming: Qt stylesheets and matplotlib palette."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from app import config


class _AppStyle(QProxyStyle):
    """Fusion base style with mnemonic underlines switched off.

    Buttons label their accelerators with "&"; Fusion paints the underline all the
    time, which reads as a stray line under the first letter. The accelerator still
    works with Alt, it simply is not drawn until then.
    """

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # type: ignore[override]
        if hint == QStyle.StyleHint.SH_UnderlineShortcut:
            return 0
        return super().styleHint(hint, option, widget, returnData)


def build_stylesheet(p: dict) -> str:
    return f"""
* {{ outline: none; }}
QWidget {{
    color: {p['text']};
    font-family: "Segoe UI", "Arial";
    font-size: 9.5pt;
}}
QMainWindow, QDialog {{ background: {p['window']}; }}
QToolTip {{
    background: {p['surface']}; color: {p['text']};
    border: 1px solid {p['border_strong']}; padding: 5px 8px; border-radius: 6px;
}}
QFrame#sidebar {{ background: {p['sidebar']}; border: none; }}
QLabel#brandTitle {{ color: #ffffff; font-size: 12.5pt; font-weight: 700; }}
QLabel#brandSchool {{ color: {p['sidebar_muted']}; font-size: 7.6pt; }}
QLabel#sidebarSection {{
    color: {p['sidebar_muted']}; font-size: 7.2pt; font-weight: 700;
    letter-spacing: 1px; padding: 2px 12px;
}}
QLabel#sidebarFooter {{ color: {p['sidebar_muted']}; font-size: 7.4pt; }}
QPushButton#navButton {{
    color: {p['sidebar_text']}; background: transparent; border: none;
    text-align: left; padding: 9px 12px; border-radius: 8px; font-weight: 500;
}}
QPushButton#navButton:hover {{ background: {p['sidebar_hover']}; color: #ffffff; }}
QPushButton#navButton:checked {{ background: {p['sidebar_active']}; color: #ffffff; font-weight: 600; }}
QPushButton#navButton:checked:hover {{ background: {p['sidebar_active']}; }}
QFrame#topbar {{ background: {p['surface']}; border: none; border-bottom: 1px solid {p['border']}; }}
QLabel#pageTitle {{ font-size: 17pt; font-weight: 700; color: {p['text']}; }}
QLabel#pageSubtitle {{ color: {p['text_muted']}; font-size: 9pt; }}
QLabel#sessionBadge {{
    background: {p['primary_soft']}; color: {p['primary']}; border-radius: 12px;
    padding: 4px 12px; font-size: 8.2pt; font-weight: 600;
}}
QLabel#dateBadge {{ color: {p['text_muted']}; font-size: 8.6pt; }}
QFrame#card, QFrame#statCard {{
    background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 12px;
}}
QFrame#statCard:hover {{ border-color: {p['border_strong']}; }}
QLabel#statLabel {{ color: {p['text_muted']}; font-size: 8.4pt; font-weight: 600; }}
QLabel#statValue {{ font-size: 21pt; font-weight: 700; color: {p['text']}; }}
QLabel#statHint {{ color: {p['text_muted']}; font-size: 7.8pt; }}
QLabel#cardTitle {{ font-size: 11pt; font-weight: 700; color: {p['text']}; }}
QLabel#sectionTitle {{ font-size: 11.5pt; font-weight: 700; color: {p['text']}; }}
QLabel#muted {{ color: {p['text_muted']}; }}
QLabel#small {{ color: {p['text_muted']}; font-size: 8pt; }}
QLabel#metric {{ font-size: 13pt; font-weight: 700; }}
QLabel#emptyTitle {{ font-size: 12.5pt; font-weight: 700; color: {p['text']}; }}
QLabel#emptyText {{ color: {p['text_muted']}; }}
QLabel#badge {{
    background: {p['surface_sunken']}; border-radius: 9px; padding: 2px 9px;
    color: {p['text_muted']}; font-size: 7.8pt; font-weight: 600;
}}
QLabel[tone="success"] {{ color: {p['success']}; background: {p['success_soft']}; border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 8pt; }}
QLabel[tone="danger"] {{ color: {p['danger']}; background: {p['danger_soft']}; border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 8pt; }}
QLabel[tone="warning"] {{ color: {p['warning']}; background: {p['warning_soft']}; border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 8pt; }}
QLabel[tone="info"] {{ color: {p['info']}; background: {p['info_soft']}; border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 8pt; }}
QLabel[tone="primary"] {{ color: {p['primary']}; background: {p['primary_soft']}; border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 8pt; }}
QPushButton {{
    background: {p['surface']}; color: {p['text']};
    border: 1px solid {p['border']}; border-radius: 8px; padding: 6px 13px;
    font-weight: 500; min-height: 18px;
}}
QPushButton:hover {{ background: {p['surface_alt']}; border-color: {p['border_strong']}; }}
QPushButton:pressed {{ background: {p['surface_sunken']}; }}
QPushButton:disabled {{ color: {p['text_muted']}; background: {p['surface_sunken']}; border-color: {p['border']}; }}
QPushButton[variant="primary"] {{
    background: {p['primary']}; color: #ffffff; border: 1px solid {p['primary']};
}}
QPushButton[variant="primary"]:hover {{ background: {p['primary_hover']}; }}
QPushButton[variant="danger"] {{ background: {p['danger']}; color: #ffffff; border: 1px solid {p['danger']}; }}
QPushButton[variant="danger"]:hover {{ background: {p['danger']}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: none; color: {p['primary']}; }}
QPushButton[variant="ghost"]:hover {{ background: {p['primary_soft']}; }}
QPushButton[variant="icon"] {{ padding: 5px; border-radius: 8px; }}
QPushButton[variant="link"] {{ background: transparent; border: none; color: {p['primary']}; padding: 2px; text-align: left; }}
QPushButton#navButton[variant="sidebar"] {{ background: transparent; }}
QPushButton#navButton[variant="sidebar"]:hover {{ background: {p['sidebar_hover']}; }}
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {p['surface']}; color: {p['text']};
    border: 1px solid {p['border']}; border-radius: 8px; padding: 6px 9px;
    selection-background-color: {p['primary']}; selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {p['primary']};
}}
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {{ color: {p['text_muted']}; background: {p['surface_sunken']}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {p['danger']}; background: {p['danger_soft']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {p['surface']}; border: 1px solid {p['border']};
    selection-background-color: {p['primary_soft']}; selection-color: {p['text']};
    padding: 3px; outline: none;
}}
QDateEdit::drop-down {{ border: none; width: 20px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 9px; }}
QCheckBox, QRadioButton {{ spacing: 7px; color: {p['text']}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QTableWidget, QTableView {{
    background: {p['surface']}; alternate-background-color: {p['surface_alt']};
    border: 1px solid {p['border']}; border-radius: 10px;
    gridline-color: {p['border']};
    selection-background-color: {p['primary_soft']}; selection-color: {p['text']};
}}
QTableWidget::item, QTableView::item {{ padding: 6px 8px; border: none; }}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {p['primary_soft']}; color: {p['text']};
}}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {p['surface_alt']}; color: {p['text_muted']};
    padding: 7px 8px; border: none; border-bottom: 1px solid {p['border']};
    border-right: 1px solid {p['border']};
    font-weight: 600; font-size: 8.2pt;
}}
QHeaderView::section:last {{ border-right: none; }}
QTableCornerButton::section {{ background: {p['surface_alt']}; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border_strong']}; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {p['text_muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['border_strong']}; border-radius: 4px; min-width: 24px; }}
QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 10px; background: {p['surface']}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {p['text_muted']}; padding: 7px 15px;
    border: 1px solid transparent; border-bottom: 2px solid transparent;
    margin-right: 2px; font-weight: 500;
}}
QTabBar::tab:selected {{ color: {p['primary']}; border-bottom: 2px solid {p['primary']}; }}
QTabBar::tab:hover {{ color: {p['text']}; }}
QGroupBox {{
    background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px;
    margin-top: 12px; padding: 14px 12px 10px 12px; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; color: {p['primary']}; }}
QMenuBar {{ background: {p['surface']}; border-bottom: 1px solid {p['border']}; padding: 2px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {p['primary_soft']}; color: {p['text']}; }}
QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 6px 26px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p['primary_soft']}; }}
QMenu::separator {{ height: 1px; background: {p['border']}; margin: 4px 8px; }}
QTextBrowser, QTextEdit {{
    background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px;
    padding: 8px;
}}
QListWidget {{
    background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 4px;
}}
QListWidget::item {{ padding: 7px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {p['primary_soft']}; color: {p['text']}; }}
QProgressBar {{ background: {p['surface_sunken']}; border: none; border-radius: 5px; height: 10px; text-align: center; }}
QProgressBar::chunk {{ background: {p['primary']}; border-radius: 5px; }}
QSplitter::handle {{ background: {p['border']}; width: 1px; }}
QFrame#inset {{ background: {p['surface_alt']}; border: 1px solid {p['border']}; border-radius: 10px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#pageContent {{ background: transparent; }}
QFrame#divider {{ background: {p['border']}; max-height: 1px; min-height: 1px; border: none; }}
QFrame#toast {{
    background: {p['text']}; border-radius: 10px;
}}
QLabel#toastText {{ color: {p['surface']}; font-weight: 500; }}
QCalendarWidget QWidget {{ alternate-background-color: {p['surface_alt']}; }}
QCalendarWidget QToolButton {{ color: {p['text']}; background: transparent; }}
QCalendarWidget QAbstractItemView {{
    background: {p['surface']}; color: {p['text']};
    selection-background-color: {p['primary']}; selection-color: #ffffff;
}}
"""


def apply_theme(app: QApplication, name: str) -> dict:
    palette = config.theme_palette(name)
    app.setStyle(_AppStyle("Fusion"))
    app.setStyleSheet(build_stylesheet(palette))
    qt_palette = QPalette()
    qt_palette.setColor(QPalette.ColorRole.Window, QColor(palette["window"]))
    qt_palette.setColor(QPalette.ColorRole.WindowText, QColor(palette["text"]))
    qt_palette.setColor(QPalette.ColorRole.Base, QColor(palette["surface"]))
    qt_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(palette["surface_alt"]))
    qt_palette.setColor(QPalette.ColorRole.Text, QColor(palette["text"]))
    qt_palette.setColor(QPalette.ColorRole.Button, QColor(palette["surface"]))
    qt_palette.setColor(QPalette.ColorRole.ButtonText, QColor(palette["text"]))
    qt_palette.setColor(QPalette.ColorRole.Highlight, QColor(palette["primary"]))
    qt_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    qt_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(palette["surface"]))
    qt_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(palette["text"]))
    app.setPalette(qt_palette)
    apply_matplotlib_theme(palette)
    return palette


def apply_matplotlib_theme(p: dict) -> None:
    try:
        import matplotlib

        matplotlib.rcParams.update(
            {
                "figure.facecolor": p["surface"],
                "axes.facecolor": p["surface"],
                "savefig.facecolor": p["surface"],
                "axes.edgecolor": p["border"],
                "axes.labelcolor": p["chart_text"],
                "axes.titlecolor": p["text"],
                "text.color": p["chart_text"],
                "xtick.color": p["text_muted"],
                "ytick.color": p["text_muted"],
                "grid.color": p["chart_grid"],
                "grid.linewidth": 0.7,
                "axes.grid": True,
                "axes.spines.top": False,
                "axes.spines.right": False,
                "font.size": 8.5,
                "axes.titlesize": 10,
                "axes.titleweight": "bold",
                "legend.fontsize": 8,
                "figure.autolayout": False,
            }
        )
    except Exception:
        pass


def chart_colors(p: dict) -> list[str]:
    return config.CHART_DARK if p.get("name") == "dark" else config.CHARTS
