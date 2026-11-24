"""ui/focus_dialog.py — Modo Foco: diálogo de duração e a lógica do contador."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from config import C
from ui.icons import icon
from ui.widgets import ask_yes_no

PRESETS = (15, 25, 30, 45, 60, 90)


def _fmt_remaining(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}min {s:02d}s" if m else f"{s}s"


class FocusDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modo Foco")
        self.setModal(True)
        self.setFixedWidth(360)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("accentBar")
        accent.setFixedHeight(3)
        root.addWidget(accent)

        body = QVBoxLayout()
        body.setContentsMargins(24, 20, 24, 22)
        body.setSpacing(10)
        root.addLayout(body)

        title = QLabel("Modo foco")
        title.setObjectName("dialogTitle")
        body.addWidget(title)
        info = QLabel("Durante o foco você não poderá trocar de livro nem "
                      "sair do app sem confirmar.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        body.addWidget(info)

        lbl = QLabel("DURAÇÃO")
        lbl.setObjectName("sectionLabel")
        body.addSpacing(6)
        body.addWidget(lbl)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._chips: list[tuple[QPushButton, int]] = []
        for i, mins in enumerate(PRESETS):
            b = QPushButton(f"{mins} min")
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, m=mins: self._spin.setValue(m))
            grid.addWidget(b, i // 3, i % 3)
            self._chips.append((b, mins))
        body.addLayout(grid)

        custom = QLabel("OU TEMPO PERSONALIZADO")
        custom.setObjectName("sectionLabel")
        body.addSpacing(4)
        body.addWidget(custom)
        self._spin = QSpinBox()
        self._spin.setRange(1, 600)
        self._spin.setSuffix(" min")
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.valueChanged.connect(self._sync_chips)
        body.addWidget(self._spin)
        self._spin.setValue(25)
        self._sync_chips(25)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 10, 0, 0)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        start = QPushButton("  Iniciar foco")
        start.setObjectName("primary")
        start.setIcon(icon("target", C["on_accent"]))
        start.setDefault(True)
        start.clicked.connect(self.accept)
        row.addWidget(cancel, 1)
        row.addWidget(start, 1)
        body.addLayout(row)

    def _sync_chips(self, value: int):
        for b, mins in self._chips:
            b.setChecked(mins == value)

    def minutes(self) -> int:
        return self._spin.value()


class FocusMixin:
    def _init_focus(self):
        self._focus_active = False
        self._focus_end_ts = 0.0
        self._focus_timer = QTimer(self)
        self._focus_timer.setInterval(1000)
        self._focus_timer.timeout.connect(self._focus_tick)

    def _focus_remaining(self) -> int:
        return max(0, int(self._focus_end_ts - time.time()))

    def _open_focus_dialog(self):
        if self._focus_active:
            if ask_yes_no(self, "Modo Foco ativo",
                          f"Foco em andamento — {_fmt_remaining(self._focus_remaining())} "
                          "restante.\n\nCancelar o modo foco?", warning=False):
                self._focus_cancel()
            return
        dlg = FocusDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._focus_start(dlg.minutes())

    def _focus_start(self, minutes: int):
        self._focus_active = True
        self._focus_end_ts = time.time() + minutes * 60
        self.right_panel.set_focus_active(True)
        self._focus_tick()
        self._focus_timer.start()

    def _focus_tick(self):
        if not self._alive or not self._focus_active:
            self._focus_timer.stop()
            return
        remaining = self._focus_remaining()
        if remaining == 0:
            self._focus_end_naturally()
            return
        m, s = divmod(remaining, 60)
        h, m2 = divmod(m, 60)
        self.right_panel.set_focus_text(
            f"{h}h {m2:02d}m {s:02d}s" if h else f"{m:02d}:{s:02d}")

    def _focus_end_naturally(self):
        self._focus_active = False
        self._focus_timer.stop()
        self.right_panel.set_focus_active(False)
        self.right_panel.set_focus_text("✓ Foco concluído!")
        QTimer.singleShot(5000, lambda: self.right_panel.set_focus_text(""))
        self.setWindowTitle("LER COMIGO  ✓ Foco concluído!")
        QTimer.singleShot(4000, lambda: self.setWindowTitle("LER COMIGO"))

    def _focus_cancel(self):
        self._focus_active = False
        self._focus_timer.stop()
        self.right_panel.set_focus_text("")
        self.right_panel.set_focus_active(False)

    def _focus_blocked_feedback(self):
        """Feedback rápido quando uma ação é bloqueada pelo foco."""
        self.right_panel.set_focus_text(
            f"🔒 bloqueado  ({_fmt_remaining(self._focus_remaining())})", C["red_hot"])
        QTimer.singleShot(1800, self._focus_tick)
