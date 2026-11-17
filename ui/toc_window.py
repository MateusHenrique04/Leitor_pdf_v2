"""ui/toc_window.py — sumário (TOC) do PDF."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from config import C


class TocDialog(QDialog):
    page_chosen = Signal(int)   # página, base 1

    def __init__(self, parent, toc: list[tuple[int, str, int]]):
        super().__init__(parent)
        self.setWindowTitle("Sumário")
        self.resize(440, 580)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("accentBar")
        accent.setFixedHeight(3)
        root.addWidget(accent)
        title = QLabel("Sumário")
        title.setObjectName("dialogTitle")
        title.setContentsMargins(20, 16, 20, 10)
        root.addWidget(title)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setColumnCount(2)
        tree.setIndentation(18)
        tree.setRootIsDecorated(True)
        tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        # O PDF entrega uma lista plana (nível, título, página); a árvore é
        # montada pelos níveis, e um nível "pulado" cai no pai mais próximo.
        stack: list[tuple[int, QTreeWidgetItem]] = []
        bold = QFont()
        bold.setBold(True)
        for level, text, page in toc:
            item = QTreeWidgetItem([text, str(page)])
            item.setData(0, Qt.ItemDataRole.UserRole, page)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setForeground(1, QBrush(QColor(C["text_dim"])))
            if level == 1:
                item.setFont(0, bold)
                item.setForeground(0, QBrush(QColor(C["red_text"])))
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                tree.addTopLevelItem(item)
            stack.append((level, item))
        tree.expandAll()
        tree.itemClicked.connect(self._on_click)
        root.addWidget(tree, 1)

    def _on_click(self, item: QTreeWidgetItem, _col: int):
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page:
            self.page_chosen.emit(int(page))
            self.accept()


class TocMixin:
    def _show_toc(self):
        """Abre o sumário embutido no PDF (via PyMuPDF)."""
        if not self.renderer:
            QMessageBox.information(self, "Sumário", "Nenhum livro aberto.")
            return
        toc = self.renderer.get_toc()
        if not toc:
            QMessageBox.information(
                self, "Sumário",
                "Este PDF não possui sumário embutido. "
                "Tente um PDF com marcadores/bookmarks.")
            return
        dlg = TocDialog(self, toc)
        dlg.page_chosen.connect(self._goto_page_from_toc)
        dlg.exec()

    def _goto_page_from_toc(self, page_1based: int):
        self.current_page = max(0, min(page_1based - 1, self.total_pages - 1))
        self.current_chunk_idx = 0
        self._follow_suppressed = False
        self._restart_loop()
