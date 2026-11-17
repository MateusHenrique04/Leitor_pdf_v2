"""ui/transport.py — barra de controles: linha do tempo do audiolivro e transporte."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from config import C
from ui.icons import icon
from ui.theme import mono_font
from ui.widgets import ClickSlider

SEEK_RESOLUTION = 10_000


def _round_button(ic: str, size: int, tip: str, name: str = "round",
                  color: str | None = None, icon_px: int = 18) -> QPushButton:
    b = QPushButton()
    b.setObjectName(name)
    b.setFixedSize(size, size)
    b.setIcon(icon(ic, color or C["text_soft"]))
    b.setIconSize(QSize(icon_px, icon_px))
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


class TransportBar(QFrame):
    prev_page = Signal()
    prev_chunk = Signal()
    toggle_play = Signal()
    next_chunk = Signal()
    next_page = Signal()
    autoscroll_toggled = Signal(bool)
    seek_fraction = Signal(float)

    def __init__(self, autoscroll: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("transport")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("accentBar")
        accent.setFixedHeight(2)
        outer.addWidget(accent)

        body = QVBoxLayout()
        body.setContentsMargins(24, 12, 24, 12)
        body.setSpacing(10)
        outer.addLayout(body)

        # Linha do tempo: posição · barra · duração estimada. É o elemento
        # principal da barra — onde você está no livro.
        tl = QHBoxLayout()
        tl.setSpacing(12)
        self._pos = QLabel("--:--")
        self._pos.setObjectName("timeCurrent")
        self._pos.setFont(mono_font(11, True))
        self._pos.setFixedWidth(84)
        self._pos.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._seek = ClickSlider()
        self._seek.setRange(0, SEEK_RESOLUTION)
        self._seek.setEnabled(False)
        self._seek.setMaximumWidth(520)
        self._seek.committed.connect(lambda v: self.seek_fraction.emit(v / SEEK_RESOLUTION))
        self._total = QLabel("--:--")
        self._total.setObjectName("timeLabel")
        self._total.setFont(mono_font(11, True))
        self._total.setFixedWidth(84)
        tl.addStretch(1)
        tl.addWidget(self._pos)
        tl.addWidget(self._seek, 4)
        tl.addWidget(self._total)
        tl.addStretch(1)
        body.addLayout(tl)

        btns = QHBoxLayout()
        btns.setSpacing(12)
        btns.addStretch(1)
        b_prev_page = _round_button("skip_back", 42, "Página anterior  (Ctrl+←)")
        b_prev_chunk = _round_button("chev_left", 36, "Frase anterior  (←)", icon_px=16)
        self._play = _round_button("play", 64, "Reproduzir / pausar  (Espaço)",
                                   name="play", color=C["on_accent"], icon_px=26)
        b_next_chunk = _round_button("chev_right", 36, "Próxima frase  (→)", icon_px=16)
        b_next_page = _round_button("skip_fwd", 42, "Próxima página  (Ctrl+→)")
        b_prev_page.clicked.connect(self.prev_page)
        b_prev_chunk.clicked.connect(self.prev_chunk)
        self._play.clicked.connect(self.toggle_play)
        b_next_chunk.clicked.connect(self.next_chunk)
        b_next_page.clicked.connect(self.next_page)
        for w in (b_prev_page, b_prev_chunk, self._play, b_next_chunk, b_next_page):
            btns.addWidget(w)
        btns.addStretch(1)
        body.addLayout(btns)

        foot = QHBoxLayout()
        foot.setSpacing(14)
        foot.addStretch(1)
        self._autoscroll = QPushButton("Auto-scroll")
        self._autoscroll.setObjectName("autoscroll")
        self._autoscroll.setCheckable(True)
        self._autoscroll.setChecked(autoscroll)
        self._autoscroll.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autoscroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._autoscroll.setToolTip("Rola a página acompanhando a voz")
        self._autoscroll.toggled.connect(self.autoscroll_toggled)
        self._session = QLabel("sessão  00:00:00")
        self._session.setObjectName("muted")
        self._session.setFont(mono_font(9))
        foot.addWidget(self._autoscroll)
        foot.addWidget(self._session)
        foot.addStretch(1)
        body.addLayout(foot)

        # Aviso transitório (falha de TTS/rede) — some sozinho.
        self._status = QLabel("")
        self._status.setObjectName("status")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setVisible(False)
        body.addWidget(self._status)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self._status.setVisible(False))

    # — API ——————————————————————————————————————————————
    def set_playing(self, playing: bool):
        self._play.setIcon(icon("pause" if playing else "play", C["on_accent"]))

    def set_timeline(self, pos_text: str, total_text: str, fraction: float):
        self._pos.setText(pos_text)
        self._total.setText(total_text)
        if not self._seek.isSliderDown():
            self._seek.blockSignals(True)
            self._seek.setValue(int(max(0.0, min(1.0, fraction)) * SEEK_RESOLUTION))
            self._seek.blockSignals(False)

    def reset_timeline(self):
        self._pos.setText("--:--")
        self._total.setText("--:--")
        self._seek.blockSignals(True)
        self._seek.setValue(0)
        self._seek.blockSignals(False)

    def set_seek_enabled(self, enabled: bool):
        self._seek.setEnabled(enabled)

    def set_session_text(self, text: str):
        self._session.setText(text)

    def set_autoscroll(self, on: bool):
        self._autoscroll.blockSignals(True)
        self._autoscroll.setChecked(on)
        self._autoscroll.blockSignals(False)

    def show_status(self, text: str, error: bool = False, ms: int = 4000):
        color = C["red_hot"] if error else C["text_dim"]
        self._status.setStyleSheet(f"color: {color};")
        self._status.setText(text)
        self._status.setVisible(True)
        self._status_timer.start(ms)
