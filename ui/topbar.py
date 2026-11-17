"""ui/topbar.py — barra superior: título, página, zoom, modo leitura e slider de páginas."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from config import C
from ui.icons import icon
from ui.widgets import ClickSlider


def _tool_button(ic: str, tip: str) -> QPushButton:
    b = QPushButton()
    b.setObjectName("flat")
    b.setIcon(icon(ic, C["text_soft"]))
    b.setIconSize(QSize(16, 16))
    b.setFixedSize(32, 30)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


class TopBar(QFrame):
    zoom_in = Signal()
    zoom_out = Signal()
    toggle_fit = Signal()
    toggle_reading = Signal()
    page_committed = Signal(int)   # número da página, base 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topbar")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("accentBar")
        bar.setFixedHeight(2)
        outer.addWidget(bar)

        row = QHBoxLayout()
        row.setContentsMargins(18, 8, 14, 6)
        row.setSpacing(6)
        outer.addLayout(row)

        self._title = QLabel("Nenhum livro aberto")
        self._title.setObjectName("bookTitle")
        row.addWidget(self._title, 1)

        self._btn_out = _tool_button("minus", "Diminuir zoom  (−)")
        self._btn_out.clicked.connect(self.zoom_out)
        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setObjectName("muted")
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_lbl.setFixedWidth(46)
        self._btn_in = _tool_button("plus", "Aumentar zoom  (+)")
        self._btn_in.clicked.connect(self.zoom_in)

        self._fit_btn = QPushButton("LARGURA")
        self._fit_btn.setObjectName("flat")
        self._fit_btn.setToolTip("Alternar ajuste: largura ⇄ página inteira")
        self._fit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._fit_btn.clicked.connect(self.toggle_fit)

        self._reading_btn = _tool_button("expand", "Modo leitura  (Tab)")
        self._reading_btn.setCheckable(True)
        self._reading_btn.clicked.connect(self.toggle_reading)

        self._page_lbl = QLabel("")
        self._page_lbl.setObjectName("pageLabel")

        for w in (self._btn_out, self._zoom_lbl, self._btn_in, self._fit_btn,
                  self._reading_btn):
            row.addWidget(w)
        row.addSpacing(10)
        row.addWidget(self._page_lbl)

        self._slider = ClickSlider()
        self._slider.setRange(1, 1)
        self._slider.setEnabled(False)
        self._slider.committed.connect(self.page_committed)
        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(18, 0, 18, 8)
        slider_row.addWidget(self._slider)
        outer.addLayout(slider_row)

    # — API ——————————————————————————————————————————————
    def set_title(self, text: str):
        self._title.setText(text)

    def set_page(self, page_1based: int, total: int):
        self._page_lbl.setText(f"PÁG. {page_1based} / {total}" if total else "")
        if not self._slider.isSliderDown():
            self._slider.blockSignals(True)
            self._slider.setValue(page_1based)
            self._slider.blockSignals(False)

    def clear_page(self):
        self._page_lbl.setText("")
        self._slider.setEnabled(False)

    def set_page_range(self, total: int):
        self._slider.setEnabled(total > 1)
        self._slider.setRange(1, max(1, total))

    def set_zoom_text(self, zoom: float):
        self._zoom_lbl.setText(f"{int(round(zoom * 100))}%")

    def set_fit_text(self, mode: str):
        self._fit_btn.setText("LARGURA" if mode == "largura" else "PÁGINA")

    def set_reading_active(self, active: bool):
        self._reading_btn.setChecked(active)
        self._reading_btn.setIcon(
            icon("expand", C["red_text"] if active else C["text_soft"]))
