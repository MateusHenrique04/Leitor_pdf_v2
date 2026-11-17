"""
ui/widgets.py — componentes reutilizáveis da interface Qt.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from config import C
from ui.icons import icon


class ClickSlider(QSlider):
    """Slider horizontal em que um clique na barra pula direto para o ponto
    clicado (o QSlider padrão só avança uma "página" por vez) e que avisa
    `committed` só quando o usuário solta — arrastar não dispara um seek a
    cada pixel, e o valor mexido por código (a leitura andando) nunca
    dispara nada."""

    committed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _value_at(self, x: float) -> int:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        style = self.style()
        groove = style.subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        handle = style.subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        span = max(1, groove.width() - handle.width())
        pos = int(x) - groove.x() - handle.width() // 2
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), max(0, min(span, pos)), span)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setSliderDown(True)
            self.setValue(self._value_at(event.position().x()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self.setValue(self._value_at(event.position().x()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.isSliderDown():
            self.setSliderDown(False)
            self.committed.emit(self.value())
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class ElidedLabel(QLabel):
    """QLabel que corta o texto com "…" quando não cabe, em vez de forçar a
    largura do painel. O texto completo vai para a dica (tooltip)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (API do Qt)
        self._full = text
        self.setToolTip(text)
        self._elide()

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(10, self.width()))
        QLabel.setText(self, shown)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class MenuButton(QPushButton):
    """Botão que abre um menu de opções exclusivas (substitui o dropdown
    feito à mão com Frame+Label). Mostra a opção atual e um chevron."""

    changed = Signal(int)

    def __init__(self, items: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("menuButton")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu = QMenu(self)
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self._actions: list[QAction] = []
        self._chev = icon("chev_down", C["red_text"]).pixmap(QSize(14, 14))
        for i, label in enumerate(items):
            act = self._menu.addAction(str(label))
            act.setCheckable(True)
            self._group.addAction(act)
            act.triggered.connect(lambda _=False, idx=i: self.set_index(idx, emit=True))
            self._actions.append(act)
        self._index = -1
        self.clicked.connect(self._open_menu)

    def set_item_icon(self, idx: int, ic) -> None:
        self._actions[idx].setIcon(ic)

    def index(self) -> int:
        return self._index

    def set_index(self, idx: int, emit: bool = False) -> None:
        if not (0 <= idx < len(self._actions)):
            return
        self._index = idx
        self._actions[idx].setChecked(True)
        self.setText(self._actions[idx].text())
        if emit:
            self.changed.emit(idx)

    def _open_menu(self):
        self._menu.setMinimumWidth(self.width())
        self._menu.exec(self.mapToGlobal(QPoint(0, self.height() + 3)))

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        dpr = self._chev.devicePixelRatio() or 1.0
        w, h = self._chev.width() / dpr, self._chev.height() / dpr
        p.drawPixmap(int(self.width() - w - 10), int((self.height() - h) / 2), self._chev)
        p.end()


class _SectionHeader(QWidget):
    """Cabeçalho clicável: título à esquerda, chevron à direita."""

    clicked = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sectionHeaderBar")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 9, 2, 9)
        self._label = QLabel(text.upper())
        self._label.setObjectName("sectionLabel")
        self._chev = QLabel()
        row.addWidget(self._label, 1)
        row.addWidget(self._chev, 0)

    def set_open(self, open_: bool):
        self._chev.setPixmap(
            icon("chev_up" if open_ else "chev_down", C["text_dim"]).pixmap(QSize(14, 14)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class CollapsibleSection(QWidget):
    """Seção com título clicável que recolhe/expande o conteúdo."""

    toggled_open = Signal(str, bool)

    def __init__(self, title: str, *, open_: bool = False, parent=None):
        super().__init__(parent)
        self._title = title
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._header = _SectionHeader(title)
        self._header.clicked.connect(self.toggle)
        lay.addWidget(self._header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 2, 0, 8)
        self.body_layout.setSpacing(6)
        lay.addWidget(self.body)
        self._open = open_
        self._sync()

    def is_open(self) -> bool:
        return self._open

    def toggle(self):
        self._open = not self._open
        self._sync()
        self.toggled_open.emit(self._title, self._open)

    def _sync(self):
        self.body.setVisible(self._open)
        self._header.set_open(self._open)


def ask_yes_no(parent, title: str, text: str, *, warning: bool = True) -> bool:
    """Pergunta Sim/Não em português (o padrão do Qt sai em inglês)."""
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(
        QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Question,
        title, text, QMessageBox.StandardButton.NoButton, parent)
    yes = box.addButton("Sim", QMessageBox.ButtonRole.YesRole)
    no = box.addButton("Não", QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes
