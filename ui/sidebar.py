"""ui/sidebar.py — barra lateral: logo, abrir PDF e biblioteca."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import C
from ui.icons import icon
from ui.widgets import ElidedLabel

SIDEBAR_WIDTH = 236


class _BookRow(QFrame):
    open_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, path: str, meta: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("bookRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._path = path

        total = meta.get("total_pages", 0)
        last = meta.get("last_page", 0)
        pct = (last / total) if total > 0 else 0.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 6, 8)
        lay.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(6)
        name = ElidedLabel(os.path.basename(path))
        name.setObjectName("bookName")
        pct_lbl = QLabel(f"{int(pct * 100)}%")
        pct_lbl.setObjectName("bookPct")
        rm = QToolButton()
        rm.setObjectName("removeBook")
        rm.setIcon(icon("close", C["text_dim"]))
        rm.setIconSize(QSize(12, 12))
        rm.setToolTip("Remover da biblioteca")
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        rm.clicked.connect(lambda: self.remove_requested.emit(self._path))
        top.addWidget(name, 1)
        top.addWidget(pct_lbl)
        top.addWidget(rm)
        lay.addLayout(top)

        bar = QProgressBar()
        bar.setObjectName("bookProgress")
        bar.setRange(0, 1000)
        bar.setValue(int(pct * 1000))
        bar.setTextVisible(False)
        lay.addWidget(bar)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self._path)


class Sidebar(QWidget):
    open_clicked = Signal()
    book_selected = Signal(str)
    book_removed = Signal(str)
    tab_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(SIDEBAR_WIDTH)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Logo
        logo = QHBoxLayout()
        logo.setContentsMargins(20, 24, 20, 18)
        logo.setSpacing(10)
        bar = QFrame()
        bar.setObjectName("accentBar")
        bar.setFixedSize(3, 34)
        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel("LER COMIGO")
        name.setObjectName("logo")
        tag = QLabel("pdf audiobook")
        tag.setObjectName("tagline")
        text.addWidget(name)
        text.addWidget(tag)
        logo.addWidget(bar)
        logo.addLayout(text)
        logo.addStretch(1)
        root.addLayout(logo)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Abrir PDF
        add = QPushButton("  Abrir PDF")
        add.setObjectName("primary")
        add.setIcon(icon("plus", C["on_accent"]))
        add.setIconSize(QSize(16, 16))
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add.setToolTip("Abrir PDF  (Ctrl+O)")
        add.clicked.connect(self.open_clicked)
        holder = QVBoxLayout()
        holder.setContentsMargins(16, 14, 16, 12)
        holder.addWidget(add)
        root.addLayout(holder)

        # Abas Lendo / Lidos (controle segmentado)
        seg = QFrame()
        seg.setObjectName("segmented")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(3, 3, 3, 3)
        seg_lay.setSpacing(2)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tabs: dict[str, QPushButton] = {}
        for label in ("Lendo", "Lidos"):
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._tab_group.addButton(b)
            seg_lay.addWidget(b, 1)
            self._tabs[label] = b
        self._tabs["Lendo"].setChecked(True)
        self._tab_group.buttonClicked.connect(lambda _b: self.tab_changed.emit())
        seg_holder = QVBoxLayout()
        seg_holder.setContentsMargins(16, 0, 16, 8)
        seg_holder.addWidget(seg)
        root.addLayout(seg_holder)

        # Lista de livros
        self._list = QWidget()
        self._list_lay = QVBoxLayout(self._list)
        self._list_lay.setContentsMargins(8, 0, 8, 12)
        self._list_lay.setSpacing(2)
        self._list_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._list)
        root.addWidget(scroll, 1)

    def current_tab(self) -> str:
        return "Lidos" if self._tabs["Lidos"].isChecked() else "Lendo"

    def set_books(self, books: list[tuple[str, dict]]):
        # Esvazia (mantém o stretch final)
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not books:
            empty = QLabel("Nenhum livro.")
            empty.setObjectName("muted")
            empty.setContentsMargins(12, 8, 0, 0)
            self._list_lay.insertWidget(0, empty)
            return
        for i, (path, meta) in enumerate(books):
            row = _BookRow(path, meta)
            row.open_requested.connect(self.book_selected)
            row.remove_requested.connect(self.book_removed)
            self._list_lay.insertWidget(i, row)
