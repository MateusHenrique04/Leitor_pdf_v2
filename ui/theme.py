"""
ui/theme.py — folha de estilo (QSS) do app, gerada a partir de config.C.

Toda cor vem de config.C (única fonte de verdade). Para mudar o visual,
edite lá ou aqui — nenhum widget define cor própria.
"""
from PySide6.QtGui import QFont

from config import MONO_FONT_FAMILIES, UI_FONT_FAMILIES, C


def app_font() -> QFont:
    font = QFont()
    font.setFamilies(UI_FONT_FAMILIES)
    font.setPointSizeF(10.0)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def mono_font(point_size: float = 10.0, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FONT_FAMILIES)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(point_size)
    font.setBold(bold)
    return font


def build_qss() -> str:
    c = C
    return f"""
* {{
    color: {c['text']};
    outline: none;
}}
QMainWindow, QDialog, QWidget#root {{ background: {c['bg']}; }}
QWidget#sidebar, QWidget#rightPanel, QFrame#topbar, QFrame#transport,
QFrame#searchBar, QWidget#panelBody {{ background: {c['panel']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#panelBody {{ background: {c['panel']}; }}

QLabel {{ background: transparent; }}
QLabel#muted, QLabel#timeLabel {{ color: {c['text_dim']}; }}
QLabel#logo {{ font-size: 21px; font-weight: 700; }}
QLabel#tagline {{ color: {c['text_dim']}; font-size: 11px; }}
QLabel#sectionLabel {{ color: {c['text_dim']}; font-size: 10px; font-weight: 700; }}
QLabel#bookTitle {{ font-size: 13px; font-weight: 600; }}
QLabel#pageLabel {{ color: {c['red_text']}; font-weight: 600; }}
QLabel#status {{ color: {c['red_hot']}; font-size: 11px; }}
QLabel#timeCurrent {{ font-weight: 600; }}
QLabel#dialogTitle {{ font-size: 16px; font-weight: 700; }}
QLabel#langTag {{
    background: {c['red']}; color: {c['on_accent']};
    border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;
}}
QFrame#accentBar {{ background: {c['red']}; }}
QFrame#separator {{ background: {c['border']}; }}

QPushButton, QToolButton {{
    background: {c['border']}; border: none; border-radius: 7px;
    padding: 7px 12px; color: {c['text']};
}}
QPushButton:hover, QToolButton:hover {{ background: {c['hover']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {c['border_soft']}; }}
QPushButton:disabled {{ color: {c['text_dim']}; background: {c['panel_alt']}; }}
QPushButton#primary {{
    background: {c['red']}; color: {c['on_accent']}; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {c['red_hot']}; }}
QPushButton#ghost {{
    background: transparent; color: {c['text_soft']};
    border: 1px solid {c['border_soft']};
}}
QPushButton#ghost:hover {{ background: {c['panel_alt']}; }}
QPushButton#ghost:checked {{
    background: {c['red']}; color: {c['on_accent']}; border-color: {c['red']};
}}
QPushButton#danger {{
    background: {c['red_deep']}; color: {c['red_text']};
    border: 1px solid {c['red']};
}}
QPushButton#flat, QToolButton#flat {{
    background: transparent; color: {c['text_soft']}; padding: 6px 8px;
}}
QPushButton#flat:hover, QToolButton#flat:hover {{ background: {c['panel_alt3']}; }}
QPushButton#flat:checked, QToolButton#flat:checked {{
    background: {c['red_deep']}; color: {c['red_text']};
}}
QPushButton#round {{ border-radius: 21px; padding: 0; background: {c['panel_alt3']}; }}
QPushButton#round:hover {{ background: {c['hover']}; }}
QPushButton#play {{ border-radius: 32px; padding: 0; background: {c['red']}; }}
QPushButton#play:hover {{ background: {c['red_hot']}; }}
QPushButton#chip {{
    background: {c['panel_alt']}; color: {c['text_dim']};
    padding: 6px 0; font-weight: 600;
}}
QPushButton#chip:hover {{ background: {c['panel_alt3']}; color: {c['text']}; }}
QPushButton#chip:checked {{ background: {c['red']}; color: {c['on_accent']}; }}
QPushButton#autoscroll {{
    background: transparent; color: {c['text_dim']}; font-size: 11px;
    padding: 4px 10px; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QPushButton#autoscroll:checked {{ color: {c['success']}; border-color: {c['success']}; }}
QPushButton#menuButton {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']};
    text-align: left; padding: 8px 30px 8px 12px; color: {c['text_soft']};
}}
QPushButton#menuButton:hover {{ background: {c['panel_alt3']}; }}

QFrame#segmented {{ background: {c['border']}; border-radius: 8px; }}
QPushButton#seg {{
    background: transparent; color: {c['text_dim']}; border-radius: 6px;
    padding: 6px 0; font-weight: 600;
}}
QPushButton#seg:hover {{ color: {c['text']}; }}
QPushButton#seg:checked {{ background: {c['red']}; color: {c['on_accent']}; }}

QToolButton#sectionHeader {{
    background: transparent; color: {c['text_dim']}; font-size: 10px;
    font-weight: 700; text-align: left; padding: 9px 4px; border-radius: 4px;
}}
QToolButton#sectionHeader:hover {{ color: {c['text']}; }}

QFrame#bookRow {{ background: transparent; border-radius: 8px; }}
QFrame#bookRow:hover {{ background: {c['panel_alt']}; }}
QLabel#bookName {{ color: {c['text_soft']}; font-size: 12px; }}
QLabel#bookPct {{ color: {c['text_dim']}; font-size: 10px; }}
QToolButton#removeBook {{
    background: transparent; color: {c['text_dim']}; padding: 2px; border-radius: 4px;
}}
QToolButton#removeBook:hover {{ background: {c['red_deep']}; }}
QProgressBar#bookProgress {{
    background: {c['border']}; border: none; border-radius: 1px;
    max-height: 3px; min-height: 3px; text-align: center;
}}
QProgressBar#bookProgress::chunk {{ background: {c['red']}; border-radius: 1px; }}

QLineEdit, QSpinBox {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']};
    border-radius: 7px; padding: 7px 10px; selection-background-color: {c['red']};
    selection-color: {c['on_accent']};
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {c['red']}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QSlider::groove:horizontal {{
    height: 4px; background: {c['border_soft']}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {c['red']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {c['text']}; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: {c['red_hot']}; }}
QSlider::handle:horizontal:disabled {{ background: {c['text_dim']}; }}
QSlider::sub-page:horizontal:disabled {{ background: {c['border_soft']}; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {c['border_soft']}; min-height: 36px; border-radius: 4px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['text_dim']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {c['border_soft']}; min-width: 36px; border-radius: 4px; margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {c['text_dim']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QGraphicsView {{ background: {c['canvas_bg']}; border: none; }}

QMenu {{
    background: {c['panel_alt2']}; border: 1px solid {c['border_soft']};
    border-radius: 8px; padding: 5px;
}}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {c['hover']}; }}
QMenu::item:checked {{ color: {c['red_text']}; }}
QToolTip {{
    background: {c['panel_alt3']}; color: {c['text']};
    border: 1px solid {c['border_soft']}; padding: 4px 8px;
}}

QTreeWidget {{
    background: {c['bg']}; border: none; show-decoration-selected: 1;
}}
QTreeWidget::item {{ padding: 6px 4px; border-radius: 5px; }}
QTreeWidget::item:hover {{ background: {c['panel_alt']}; }}
QTreeWidget::item:selected {{ background: {c['select_bg']}; color: {c['text']}; }}

QFrame#dictPopup {{
    background: {c['panel_alt2']}; border: 1px solid {c['border_soft']};
    border-top: 3px solid {c['red']}; border-radius: 10px;
}}
QFrame#dictHeader {{ background: {c['panel_alt3']}; border-radius: 8px; }}
QLabel#dictWord {{ font-size: 20px; font-weight: 700; }}
QLabel#dictPos {{ color: {c['red_text']}; font-size: 11px; font-weight: 700; }}
QLabel#dictDef {{ color: {c['text_soft']}; }}

QMessageBox {{ background: {c['panel_alt']}; }}
"""


def dark_palette():
    """Paleta escura para o que o QSS não cobre (caixas de mensagem, menus
    nativos, seleção de texto). Combina com o Fusion, que respeita paletas."""
    from PySide6.QtGui import QColor, QPalette
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: C["bg"],
        QPalette.ColorRole.WindowText: C["text"],
        QPalette.ColorRole.Base: C["panel_alt"],
        QPalette.ColorRole.AlternateBase: C["panel"],
        QPalette.ColorRole.Text: C["text"],
        QPalette.ColorRole.Button: C["border"],
        QPalette.ColorRole.ButtonText: C["text"],
        QPalette.ColorRole.ToolTipBase: C["panel_alt3"],
        QPalette.ColorRole.ToolTipText: C["text"],
        QPalette.ColorRole.Highlight: C["red"],
        QPalette.ColorRole.HighlightedText: C["on_accent"],
        QPalette.ColorRole.PlaceholderText: C["text_dim"],
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    return p
