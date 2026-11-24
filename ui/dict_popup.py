"""ui/dict_popup.py — popup do dicionário (clique numa palavra do PDF)."""
from __future__ import annotations

import threading

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import C
from core import dictionary as dic
from ui.theme import mono_font

_LANG_TAG = {"pt-BR": "PT-BR", "en": "EN", "es": "ES"}


class DictPopup(QFrame):
    """Popup sem moldura que fecha sozinho ao clicar fora ou apertar Esc
    (comportamento nativo de Qt.Popup — não precisa de FocusOut manual).
    Definições longas rolam dentro de uma altura máxima."""

    def __init__(self, parent, word: str, result: dict | None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        # Janela transparente (cantos arredondados); o fundo é pintado em
        # paintEvent, sem depender de QSS (que não pintava o fundo aqui).
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 8, 4, 8)
        outer.setSpacing(4)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 8, 10, 4)
        lay.setSpacing(4)

        network_error = bool(result and result.get("_network_error"))
        if network_error:
            lay.addWidget(self._title(f'"{word}"'))
            lay.addWidget(self._muted("Sem conexão com a internet.\n"
                                      "Verifique sua rede e tente novamente."))
        elif result:
            hdr = QFrame()
            hdr.setObjectName("dictHeader")
            hrow = QHBoxLayout(hdr)
            hrow.setContentsMargins(12, 8, 10, 8)
            hrow.addWidget(self._title(result["word"].lower()), 1)
            tag = QLabel(_LANG_TAG.get(result["lang"], result["lang"]))
            tag.setObjectName("langTag")
            hrow.addWidget(tag, 0, Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(hdr)
            if result.get("phonetic"):
                ph = self._muted(result["phonetic"])
                ph.setFont(mono_font(10))
                lay.addWidget(ph)
            for meaning in result["meanings"]:
                pos = QLabel(meaning["part_of_speech"])
                pos.setObjectName("dictPos")
                pos.setContentsMargins(2, 8, 0, 0)
                lay.addWidget(pos)
                for i, d in enumerate(meaning["definitions"], 1):
                    lb = QLabel(f"{i}.  {d}")
                    lb.setObjectName("dictDef")
                    lb.setWordWrap(True)
                    lb.setContentsMargins(6, 0, 0, 0)
                    lay.addWidget(lb)
        else:
            lay.addWidget(self._title(f'"{word}"'))
            lay.addWidget(self._muted("Definição não encontrada."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        hint = self._muted("Esc para fechar")
        hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        hint.setContentsMargins(0, 0, 10, 0)
        outer.addWidget(hint)

        self.setFixedWidth(360)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        content.setFixedWidth(340)
        content.adjustSize()
        height = min(content.sizeHint().height() + 46, int(screen.height() * 0.7))
        self.setFixedHeight(max(120, height))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        p.fillPath(path, QColor(C["panel_alt2"]))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 3), QColor(C["red"]))
        p.restore()
        p.setPen(QPen(QColor(C["border_soft"]), 1))
        p.drawPath(path)

    @staticmethod
    def _title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("dictWord")
        return lb

    @staticmethod
    def _muted(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("muted")
        lb.setWordWrap(True)
        return lb

    def show_near(self, global_pos: QPoint):
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x, y = global_pos.x() + 15, global_pos.y() + 15
        if x + self.width() > area.right():
            x = global_pos.x() - self.width() - 15
        if y + self.height() > area.bottom():
            y = max(area.top() + 8, area.bottom() - self.height() - 10)
        self.move(max(area.left() + 4, x), y)
        self.show()


class DictPopupMixin:
    def _on_word_click(self, x: float, y: float, global_pos: QPoint):
        """Clique (sem arrastar) numa palavra da página."""
        if not self.renderer:
            return
        threading.Thread(
            target=self._fetch_and_show,
            args=(self.renderer, self.current_page, x, y, global_pos),
            daemon=True,
        ).start()

    def _fetch_and_show(self, renderer, page: int, x: float, y: float, global_pos: QPoint):
        """Background: acha a palavra, busca a definição e entrega por sinal."""
        try:
            word = renderer.word_at(page, x, y)
        except Exception:
            word = None
        if not word:
            return
        result = dic.lookup(word, self._detected_lang)
        if self._alive:
            self.sig_dict.emit(word, result, global_pos)

    def _show_dict_popup(self, word: str, result, global_pos: QPoint):
        if getattr(self, "_dict_popup", None) is not None:
            try:
                self._dict_popup.close()
            except RuntimeError:
                pass   # já destruído pelo Qt
        popup = DictPopup(self, word, result)
        self._dict_popup = popup
        popup.show_near(global_pos)
