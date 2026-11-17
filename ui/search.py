"""ui/search.py — barra de busca (Ctrl+F) e a lógica de busca no documento."""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton

from config import C
from ui.icons import icon

log = logging.getLogger(__name__)

SEARCH_DEBOUNCE_MS = 250


def _small_button(ic: str, tip: str) -> QPushButton:
    b = QPushButton()
    b.setObjectName("flat")
    b.setIcon(icon(ic, C["text_soft"]))
    b.setIconSize(QSize(15, 15))
    b.setFixedSize(30, 30)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


class SearchBar(QFrame):
    text_changed = Signal(str)     # já com debounce
    navigate = Signal(int)         # +1 / −1
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 6, 10, 6)
        row.setSpacing(6)

        glass = QLabel()
        glass.setPixmap(icon("search", C["text_dim"]).pixmap(QSize(16, 16)))
        row.addWidget(glass)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("Buscar no documento…")
        self._edit.setClearButtonEnabled(True)
        row.addWidget(self._edit, 1)

        self._count = QLabel("")
        self._count.setObjectName("muted")
        self._count.setMinimumWidth(80)
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._count)

        up = _small_button("arrow_up", "Resultado anterior  (Shift+Enter)")
        down = _small_button("arrow_down", "Próximo resultado  (Enter)")
        close = _small_button("close", "Fechar  (Esc)")
        up.clicked.connect(lambda: self.navigate.emit(-1))
        down.clicked.connect(lambda: self.navigate.emit(+1))
        close.clicked.connect(self.closed)
        for b in (up, down, close):
            row.addWidget(b)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self.text_changed.emit(self._edit.text().strip()))
        self._edit.textChanged.connect(lambda _t: self._debounce.start(SEARCH_DEBOUNCE_MS))
        self._edit.returnPressed.connect(self._on_return)
        self.setVisible(False)

    def _on_return(self):
        from PySide6.QtWidgets import QApplication
        shift = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.navigate.emit(-1 if shift else +1)

    def open(self):
        self.setVisible(True)
        self._edit.setFocus()
        self._edit.selectAll()

    def close_bar(self):
        self.setVisible(False)
        self._debounce.stop()

    def has_text_focus(self) -> bool:
        return self._edit.hasFocus()

    def term(self) -> str:
        return self._edit.text().strip()

    def set_count(self, text: str):
        self._count.setText(text)


class SearchMixin:
    """Lógica da busca. Resultados: lista de {"page": int, "bbox": dict}."""

    def _init_search(self):
        self._search_results: list[dict] = []
        self._search_idx = -1
        self._search_gen = 0

    def _open_search(self):
        self.search_bar.open()

    def _close_search(self):
        self.search_bar.close_bar()
        self._search_gen += 1          # invalida qualquer varredura em andamento
        self._search_results = []
        self._search_idx = -1
        self.search_bar.set_count("")
        self._refresh_search_layer()

    def _do_search(self, term: str):
        """A página atual responde na hora; o resto do documento é varrido
        em segundo plano."""
        self._search_gen += 1
        gen = self._search_gen
        self._search_results = []
        self._search_idx = -1
        self.search_bar.set_count("")
        if not term or not self.renderer:
            self._refresh_search_layer()
            return
        here = []
        try:
            for bbox in self.renderer.search_text(self.current_page, term):
                here.append({"page": self.current_page, "bbox": bbox})
        except Exception as e:
            log.debug("Busca na página atual falhou: %s", e)
        self._search_results = here
        self._refresh_search_layer()
        threading.Thread(
            target=self._search_all_pages,
            args=(term, self.current_page, gen, self.renderer),
            daemon=True,
        ).start()

    def _search_all_pages(self, term: str, skip_page: int, gen: int, renderer):
        """Roda em background: varre as demais páginas e entrega por sinal."""
        results = []
        for p in range(renderer.total):
            if gen != self._search_gen or not self._alive:
                return
            if p == skip_page:
                continue
            try:
                hits = renderer.search_text(p, term)
            except Exception:
                hits = []
            results.extend({"page": p, "bbox": b} for b in hits)
        self.sig_search_done.emit(gen, results)

    def _on_search_done(self, gen: int, results: list):
        if gen != self._search_gen:
            return
        merged = self._search_results + results
        merged.sort(key=lambda r: (r["page"], r["bbox"]["y0"], r["bbox"]["x0"]))
        self._search_results = merged
        if not merged:
            self.search_bar.set_count("sem resultados")
            self._refresh_search_layer()
            return
        # Começa no primeiro resultado da página atual ou, se não houver,
        # no próximo à frente — sem arrancar o leitor de onde ele está
        # enquanto digita.
        start = next((i for i, r in enumerate(merged) if r["page"] >= self.current_page), 0)
        self._search_idx = start
        self._update_search_count()
        self._jump_to_search_result(start)

    def _update_search_count(self):
        n = len(self._search_results)
        self.search_bar.set_count(f"{self._search_idx + 1} / {n}" if n else "sem resultados")

    def _search_navigate(self, delta: int):
        if not self._search_results:
            return
        n = len(self._search_results)
        self._search_idx = (self._search_idx + delta) % n
        self._update_search_count()
        self._jump_to_search_result(self._search_idx)

    def _refresh_search_layer(self):
        """Pinta os resultados da página atual: o selecionado em laranja,
        os demais em amarelo."""
        rects = []
        for i, r in enumerate(self._search_results):
            if r["page"] != self.current_page:
                continue
            rects.append({
                **r["bbox"],
                "color": C["warn"] if i == self._search_idx else C["search"],
                "opacity": 0.55,
            })
        self.view.set_search_highlights(rects)

    def _jump_to_search_result(self, idx: int):
        if not self._search_results or not (0 <= idx < len(self._search_results)):
            return
        result = self._search_results[idx]
        bbox = result["bbox"]
        if result["page"] != self.current_page:
            # É navegação: troca de página e a leitura recomeça dali. O
            # foco no resultado é aplicado quando a página aparece, e o
            # auto-scroll da leitura fica quieto até o próximo comando do
            # usuário — senão ele puxava a tela de volta para o topo.
            self._pending_focus_y = (bbox["y0"] + bbox["y1"]) / 2.0
            self.current_page = result["page"]
            self.current_chunk_idx = 0
            self._restart_loop()
            self._follow_suppressed = True
        else:
            self._refresh_search_layer()
            self.view.focus_rect(bbox)
