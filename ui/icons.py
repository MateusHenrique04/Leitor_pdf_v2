"""
ui/icons.py — ícones vetoriais (SVG) desenhados em código.

Substituem os símbolos de fonte (▶ ⏸ ⏮ …) que o Tk resolvia com fontes de
fallback diferentes e saíam com desenhos inconsistentes. Aqui todo ícone
vem do mesmo conjunto, no mesmo traço, e fica nítido em qualquer DPI.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_STROKE = ('fill="none" stroke="{c}" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round"')
_FILL = 'fill="{c}" stroke="none"'

# nome → (estilo, corpo SVG em viewBox 24×24)
_ICONS: dict[str, tuple[str, str]] = {
    "play":       (_FILL, '<polygon points="7,4 20,12 7,20"/>'),
    "pause":      (_FILL, '<rect x="6" y="4" width="4.5" height="16" rx="1.2"/>'
                          '<rect x="13.5" y="4" width="4.5" height="16" rx="1.2"/>'),
    "skip_back":  (_FILL, '<polygon points="19,5 9,12 19,19"/>'
                          '<rect x="4.5" y="5" width="2.6" height="14" rx="1.1"/>'),
    "skip_fwd":   (_FILL, '<polygon points="5,5 15,12 5,19"/>'
                          '<rect x="16.9" y="5" width="2.6" height="14" rx="1.1"/>'),
    "chev_left":  (_STROKE, '<polyline points="15,5 8,12 15,19"/>'),
    "chev_right": (_STROKE, '<polyline points="9,5 16,12 9,19"/>'),
    "chev_down":  (_STROKE, '<polyline points="6,9 12,15 18,9"/>'),
    "chev_up":    (_STROKE, '<polyline points="6,15 12,9 18,15"/>'),
    "minus":      (_STROKE, '<line x1="5" y1="12" x2="19" y2="12"/>'),
    "plus":       (_STROKE, '<line x1="5" y1="12" x2="19" y2="12"/>'
                            '<line x1="12" y1="5" x2="12" y2="19"/>'),
    "close":      (_STROKE, '<line x1="6" y1="6" x2="18" y2="18"/>'
                            '<line x1="18" y1="6" x2="6" y2="18"/>'),
    "search":     (_STROKE, '<circle cx="11" cy="11" r="7"/>'
                            '<line x1="21" y1="21" x2="16.2" y2="16.2"/>'),
    "expand":     (_STROKE, '<path d="M8 3H5a2 2 0 0 0-2 2v3"/>'
                            '<path d="M21 8V5a2 2 0 0 0-2-2h-3"/>'
                            '<path d="M3 16v3a2 2 0 0 0 2 2h3"/>'
                            '<path d="M16 21h3a2 2 0 0 0 2-2v-3"/>'),
    "trash":      (_STROKE, '<path d="M3 6h18"/>'
                            '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>'
                            '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
    "pencil":     (_STROKE, '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>'),
    "export":     (_STROKE, '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                            '<polyline points="7,10 12,15 17,10"/>'
                            '<line x1="12" y1="15" x2="12" y2="3"/>'),
    "check":      (_STROKE, '<polyline points="20,6 9,17 4,12"/>'),
    "list":       (_STROKE, '<line x1="8" y1="6" x2="21" y2="6"/>'
                            '<line x1="8" y1="12" x2="21" y2="12"/>'
                            '<line x1="8" y1="18" x2="21" y2="18"/>'
                            '<line x1="3" y1="6" x2="3.01" y2="6"/>'
                            '<line x1="3" y1="12" x2="3.01" y2="12"/>'
                            '<line x1="3" y1="18" x2="3.01" y2="18"/>'),
    "target":     (_STROKE, '<circle cx="12" cy="12" r="10"/>'
                            '<circle cx="12" cy="12" r="6"/>'
                            '<circle cx="12" cy="12" r="2"/>'),
    "book":       (_STROKE, '<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z"/>'
                            '<path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/>'),
    "arrow_up":   (_STROKE, '<line x1="12" y1="19" x2="12" y2="5"/>'
                            '<polyline points="5,12 12,5 19,12"/>'),
    "arrow_down": (_STROKE, '<line x1="12" y1="5" x2="12" y2="19"/>'
                            '<polyline points="19,12 12,19 5,12"/>'),
    "dot":        (_FILL, '<circle cx="12" cy="12" r="6"/>'),
}

_cache: dict[tuple, QIcon] = {}


def _render(name: str, color: str, px: int) -> QPixmap:
    style, body = _ICONS[name]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
           f'width="{px}" height="{px}"><g {style.format(c=color)}>{body}</g></svg>')
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
    painter.end()
    return pm


def icon(name: str, color: str = "#E8E8E8", disabled: str = "#4A4A4A") -> QIcon:
    """QIcon do conjunto, na cor pedida (e uma cor própria quando
    desabilitado). Renderizado a 96 px: o Qt reduz com suavização para
    qualquer tamanho de uso, inclusive em telas HiDPI."""
    key = (name, color, disabled)
    if key not in _cache:
        ic = QIcon()
        ic.addPixmap(_render(name, color, 96), QIcon.Mode.Normal)
        ic.addPixmap(_render(name, disabled, 96), QIcon.Mode.Disabled)
        _cache[key] = ic
    return _cache[key]
