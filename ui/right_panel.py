"""ui/right_panel.py — painel de ajustes: voz, velocidade, volume, grifos, livro e foco."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import HIGHLIGHT_COLORS, SPEEDS, VOICES, C
from ui.icons import icon
from ui.theme import mono_font
from ui.widgets import CollapsibleSection, MenuButton

PANEL_WIDTH = 256


def _repolish(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)


def _label(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("sectionLabel")
    return lb


def _action_button(text: str, ic: str | None = None, checkable: bool = False) -> QPushButton:
    b = QPushButton(("  " + text) if ic else text)
    b.setObjectName("ghost")
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if ic:
        b.setIcon(icon(ic, C["text_soft"]))
    return b


class RightPanel(QWidget):
    voice_changed = Signal(str)
    speed_changed = Signal(str)
    volume_changed = Signal(float)         # 0.0–1.0
    color_changed = Signal(str)            # rótulo de HIGHLIGHT_COLORS
    select_toggled = Signal(bool)
    clear_clicked = Signal()
    export_clicked = Signal()
    finished_clicked = Signal()
    toc_clicked = Signal()
    focus_clicked = Signal()
    section_toggled = Signal(str, bool)

    def __init__(self, voice: str, speed: str, volume: float, color_label: str,
                 sections: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("rightPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(PANEL_WIDTH)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Rolável: com a janela baixa o conteúdo que não cabe continua a um
        # scroll de distância, em vez de simplesmente sumir.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroll)
        body = QWidget()
        body.setObjectName("panelBody")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        # ── Voz ──────────────────────────────────────────
        lay.addWidget(_label("VOZ"))
        self._voice_names = list(VOICES.keys())
        self._voice_btn = MenuButton(self._voice_names)
        self._voice_btn.set_index(self._voice_names.index(voice))
        self._voice_btn.changed.connect(lambda i: self.voice_changed.emit(self._voice_names[i]))
        lay.addWidget(self._voice_btn)

        # ── Velocidade ───────────────────────────────────
        lay.addSpacing(6)
        lay.addWidget(_label("VELOCIDADE"))
        grid = QGridLayout()
        grid.setSpacing(5)
        self._speed_group = QButtonGroup(self)
        self._speed_group.setExclusive(True)
        for i, label in enumerate(SPEEDS):
            b = QPushButton(label)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setChecked(label == speed)
            b.clicked.connect(lambda _=False, lb=label: self.speed_changed.emit(lb))
            self._speed_group.addButton(b)
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)

        # ── Volume ───────────────────────────────────────
        lay.addSpacing(6)
        lay.addWidget(_label("VOLUME"))
        vrow = QHBoxLayout()
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(int(round(volume * 100)))
        self._vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._vol_lbl = QLabel(f"{self._vol.value()}%")
        self._vol_lbl.setObjectName("pageLabel")
        self._vol_lbl.setFont(mono_font(10, True))
        self._vol_lbl.setFixedWidth(44)
        self._vol_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._vol.valueChanged.connect(self._on_volume)
        vrow.addWidget(self._vol, 1)
        vrow.addWidget(self._vol_lbl)
        lay.addLayout(vrow)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(1)
        lay.addSpacing(6)
        lay.addWidget(sep)

        # ── Seções recolhíveis ───────────────────────────
        # Voz/velocidade/volume ficam sempre à mão porque se ajustam durante
        # a leitura; o resto se usa uma vez por sessão e começa recolhido.
        def section(title: str, default_open: bool) -> CollapsibleSection:
            sec = CollapsibleSection(title, open_=sections.get(title, default_open))
            sec.toggled_open.connect(self.section_toggled)
            lay.addWidget(sec)
            return sec

        grifos = section("Grifos", True)
        self._color_labels = list(HIGHLIGHT_COLORS.keys())
        names = [lb.split(" ", 1)[-1] for lb in self._color_labels]   # sem o emoji
        self._color_btn = MenuButton(names)
        for i, lb in enumerate(self._color_labels):
            self._color_btn.set_item_icon(i, icon("dot", HIGHLIGHT_COLORS[lb]))
        self._color_btn.set_index(self._color_labels.index(color_label))
        self._color_btn.changed.connect(lambda i: self.color_changed.emit(self._color_labels[i]))
        grifos.body_layout.addWidget(self._color_btn)

        self._btn_select = _action_button("Selecionar trecho", "pencil", checkable=True)
        self._btn_select.toggled.connect(self._on_select_toggled)
        grifos.body_layout.addWidget(self._btn_select)
        btn_clear = _action_button("Limpar página", "trash")
        btn_clear.clicked.connect(self.clear_clicked)
        grifos.body_layout.addWidget(btn_clear)
        btn_export = _action_button("Exportar grifos", "export")
        btn_export.clicked.connect(self.export_clicked)
        grifos.body_layout.addWidget(btn_export)

        livro = section("Este livro", False)
        self._btn_finished = _action_button("Marcar como lido", "check")
        self._btn_finished.clicked.connect(self.finished_clicked)
        livro.body_layout.addWidget(self._btn_finished)
        btn_toc = _action_button("Ver sumário", "list")
        btn_toc.clicked.connect(self.toc_clicked)
        livro.body_layout.addWidget(btn_toc)

        foco = section("Modo foco", False)
        self._btn_focus = _action_button("Iniciar foco", "target")
        self._btn_focus.clicked.connect(self.focus_clicked)
        foco.body_layout.addWidget(self._btn_focus)
        self._focus_lbl = QLabel("")
        self._focus_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._focus_lbl.setFont(mono_font(11, True))
        foco.body_layout.addWidget(self._focus_lbl)

        lay.addStretch(1)

    # — internos ——————————————————————————————————————————
    def _on_volume(self, v: int):
        self._vol_lbl.setText(f"{v}%")
        self.volume_changed.emit(v / 100.0)

    def _on_select_toggled(self, on: bool):
        self._btn_select.setText("  Cancelar seleção" if on else "  Selecionar trecho")
        self._btn_select.setIcon(icon("close" if on else "pencil",
                                      C["on_accent"] if on else C["text_soft"]))
        self.select_toggled.emit(on)

    # — API ——————————————————————————————————————————————
    def set_voice(self, name: str):
        self._voice_btn.set_index(self._voice_names.index(name))

    def set_select_mode(self, on: bool):
        self._btn_select.blockSignals(True)
        self._btn_select.setChecked(on)
        self._btn_select.blockSignals(False)
        self._btn_select.setText("  Cancelar seleção" if on else "  Selecionar trecho")
        self._btn_select.setIcon(icon("close" if on else "pencil",
                                      C["on_accent"] if on else C["text_soft"]))

    def set_finished(self, finished: bool):
        self._btn_finished.setText(
            "  Marcar como não lido" if finished else "  Marcar como lido")
        self._btn_finished.setIcon(icon("book" if finished else "check", C["text_soft"]))

    def set_focus_active(self, active: bool):
        self._btn_focus.setText("  Foco ativo — cancelar" if active else "  Iniciar foco")
        self._btn_focus.setObjectName("danger" if active else "ghost")
        self._btn_focus.setIcon(icon("target", C["red_text"] if active else C["text_soft"]))
        _repolish(self._btn_focus)

    def set_focus_text(self, text: str, color: str | None = None):
        self._focus_lbl.setStyleSheet(f"color: {color or C['success']};")
        self._focus_lbl.setText(text)
