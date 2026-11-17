"""
ui/app.py — janela principal (PySide6).

Layout:
  ┌──────────┬─────────────────────────┬──────────┐
  │ SIDEBAR  │ TOPO (título, zoom)     │  PAINEL  │
  │ biblioteca│ ───────────────────────│ ajustes  │
  │          │   PÁGINA (PageView)     │ (rolável)│
  │          │ ───────────────────────│          │
  │          │   TRANSPORTE            │          │
  └──────────┴─────────────────────────┴──────────┘

Regra: lógica de negócio fica em core/ e data/. Este arquivo orquestra a UI e
chama os módulos, usando mixins (um por assunto, como antes).

Threads: a leitura (TTS), a abertura de PDF, a busca e o dicionário rodam em
threads de fundo. Elas NUNCA tocam em widgets — só emitem os sinais `sig_*`
abaixo, que o Qt entrega na thread da interface.
"""
import datetime
import logging
import os
import shutil
import threading
import time

from PySide6.QtCore import QByteArray, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import data.highlights as highlights
import data.history as hist
import data.library as lib
import data.prefs as prefs
from config import (
    DEFAULT_HIGHLIGHT_LABEL,
    DEFAULT_SPEED,
    DEFAULT_VOICE,
    DEFAULT_VOLUME,
    GEOMETRY_FILE,
    HIGHLIGHT_COLORS,
    SPEEDS,
    VOICES,
)
from core.duration import BookTimeline
from core.generation import GenerationGuard
from core.pdf_renderer import PDFOpenError, PDFRenderer
from core.player import Player
from ui.dict_popup import DictPopupMixin
from ui.focus_dialog import FocusMixin
from ui.highlights_mixin import HighlightsMixin
from ui.page_view import PageView
from ui.reading import ReadingMixin
from ui.right_panel import RightPanel
from ui.search import SearchBar, SearchMixin
from ui.sidebar import Sidebar
from ui.toc_window import TocMixin
from ui.topbar import TopBar
from ui.transport import TransportBar
from ui.widgets import ask_yes_no

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# O zoom da versão Tk (padrão 2,5) tinha outra base de cálculo; usar a mesma
# chave abriria o app com a página enorme. A nova guarda em chave própria.
_ZOOM_PREF = "zoom_qt"


class App(ReadingMixin, HighlightsMixin, SearchMixin, DictPopupMixin,
          TocMixin, FocusMixin, QMainWindow):
    # Threads de fundo → interface
    sig_show_page = Signal(int)
    sig_follow = Signal()
    sig_status = Signal(str, bool)
    sig_book_opened = Signal(str, object, int)
    sig_book_failed = Signal(str, str, int)
    sig_dict = Signal(str, object, object)
    sig_lib_changed = Signal()
    sig_search_done = Signal(int, list)

    # ──────────────────────────────────────────────────────────────
    # INIT
    # ──────────────────────────────────────────────────────────────

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LECTOR")
        self.setMinimumSize(1000, 640)
        self._geo_file = GEOMETRY_FILE
        self._restore_geometry()

        # Preferências persistidas (ver data/prefs.py)
        p = prefs.get_all()
        self._pref_voice_name = p.get("voice") or DEFAULT_VOICE
        if self._pref_voice_name not in VOICES:
            self._pref_voice_name = DEFAULT_VOICE
        self._pref_speed_label = p.get("speed") or DEFAULT_SPEED
        if self._pref_speed_label not in SPEEDS:
            self._pref_speed_label = DEFAULT_SPEED
        volume = p.get("volume")
        self._pref_volume = DEFAULT_VOLUME if volume is None else max(0.0, min(1.0, volume))
        self._pref_highlight_label = p.get("highlight_color_label") or DEFAULT_HIGHLIGHT_LABEL
        if self._pref_highlight_label not in HIGHLIGHT_COLORS:
            self._pref_highlight_label = DEFAULT_HIGHLIGHT_LABEL
        zoom = p.get(_ZOOM_PREF)
        self._pref_zoom = 1.0 if zoom is None else max(1.0, min(5.0, float(zoom)))
        autoscroll = p.get("autoscroll")
        self._pref_autoscroll = True if autoscroll is None else bool(autoscroll)
        fit = p.get("fit_mode")
        self._pref_fit_mode = fit if fit in ("largura", "pagina") else "largura"
        sections = p.get("panel_sections")
        self._pref_panel_sections = sections if isinstance(sections, dict) else {}
        self._reading_mode = bool(p.get("reading_mode"))

        # Estado do livro / leitura
        self.renderer = None
        self.player = Player()
        self.current_path: str | None = None
        self.current_page = 0
        self.current_chunk_idx = 0
        self.total_pages = 0
        # Token de geração do loop de leitura: só a execução mais recente
        # escreve estado e toca áudio (ver core/generation.py).
        self._read_gen = GenerationGuard()
        self._voice = VOICES[self._pref_voice_name]
        self._speed = SPEEDS[self._pref_speed_label]
        self._session_start = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        self._session_secs = 0.0
        self._timer_running = False
        self._last_tick = 0.0

        self._ephemeral_highlights: list[dict] = []   # fundo do trecho lido
        self._word_highlights: list[dict] = []        # palavra falada agora
        self._current_text = ""
        self._timeline = None
        self._reading_pos: tuple | None = None
        self._anchor_seconds = 0.0
        self._detected_lang: str | None = None
        self._state_lock = threading.Lock()
        self._autoscroll_enabled = self._pref_autoscroll
        self._follow_suppressed = False     # True logo após pular para um resultado de busca
        self._pending_focus_y: float | None = None
        self._open_token = 0
        self._alive = True                  # False após o fechamento — impede callbacks órfãos
        self._hl_mode = False
        self._highlight_color_hex = HIGHLIGHT_COLORS[self._pref_highlight_label]
        self._dict_popup = None

        self.player.volume = self._pref_volume
        self._init_search()
        self._init_focus()

        self._build()
        self._connect()
        self._apply_reading_mode()
        self._setup_shortcuts()
        self._refresh_lib()

        # Relógio da janela: cronômetro da sessão e barra de tempo.
        self._clock = QTimer(self)
        self._clock.setInterval(250)
        self._clock.timeout.connect(self._tick_timer)
        self._clock.start()
        # Volume vira preferência só depois que o slider para (evita gravar
        # o arquivo a cada pixel arrastado).
        self._volume_save = QTimer(self)
        self._volume_save.setSingleShot(True)
        self._volume_save.setInterval(400)
        self._volume_save.timeout.connect(
            lambda: prefs.set_value("volume", self.player.volume))

    # ──────────────────────────────────────────────────────────────
    # BUILD
    # ──────────────────────────────────────────────────────────────

    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.sidebar = Sidebar()
        center = QWidget()
        col = QVBoxLayout(center)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.topbar = TopBar()
        self.search_bar = SearchBar()
        self.view = PageView()
        self.view.restore(self._pref_zoom, self._pref_fit_mode)
        self.transport = TransportBar(self._autoscroll_enabled)
        col.addWidget(self.topbar)
        col.addWidget(self.search_bar)
        col.addWidget(self.view, 1)
        col.addWidget(self.transport)
        self.right_panel = RightPanel(
            self._pref_voice_name, self._pref_speed_label, self._pref_volume,
            self._pref_highlight_label, self._pref_panel_sections)

        row.addWidget(self.sidebar)
        row.addWidget(center, 1)
        row.addWidget(self.right_panel)

        self.view.set_selection_color(self._highlight_color_hex)
        self.topbar.set_zoom_text(self.view.zoom)
        self.topbar.set_fit_text(self.view.fit_mode)

    def _connect(self):
        # Threads de fundo → UI
        self.sig_show_page.connect(self._show_page)
        self.sig_follow.connect(self._follow_highlight)
        self.sig_status.connect(lambda text, err: self.transport.show_status(text, err))
        self.sig_book_opened.connect(self._on_book_opened)
        self.sig_book_failed.connect(self._on_book_open_failed)
        self.sig_dict.connect(self._show_dict_popup)
        self.sig_search_done.connect(self._on_search_done)
        self.sig_lib_changed.connect(self._on_lib_changed)

        # Biblioteca
        self.sidebar.open_clicked.connect(self._open_file)
        self.sidebar.book_selected.connect(self._load_book)
        self.sidebar.book_removed.connect(self._remove_book)
        self.sidebar.tab_changed.connect(self._refresh_lib)

        # Topo
        self.topbar.zoom_in.connect(self.view.zoom_in)
        self.topbar.zoom_out.connect(self.view.zoom_out)
        self.topbar.toggle_fit.connect(self._toggle_fit)
        self.topbar.toggle_reading.connect(self._toggle_reading_mode)
        self.topbar.page_committed.connect(self._on_page_seek)

        # Página
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.clicked.connect(self._on_word_click)
        self.view.right_clicked.connect(self._on_right_click)
        self.view.selected.connect(self._on_selection)
        self.view.page_step.connect(self._on_page_step)

        # Busca
        self.search_bar.text_changed.connect(self._do_search)
        self.search_bar.navigate.connect(self._search_navigate)
        self.search_bar.closed.connect(self._close_search)

        # Transporte
        self.transport.prev_page.connect(self._prev_page)
        self.transport.prev_chunk.connect(self._prev_chunk)
        self.transport.toggle_play.connect(self._toggle_play)
        self.transport.next_chunk.connect(self._next_chunk)
        self.transport.next_page.connect(self._next_page)
        self.transport.autoscroll_toggled.connect(self._on_autoscroll_toggled)
        self.transport.seek_fraction.connect(self._on_time_seek)

        # Painel de ajustes
        rp = self.right_panel
        rp.voice_changed.connect(self._on_voice_changed)
        rp.speed_changed.connect(self._on_speed_changed)
        rp.volume_changed.connect(self._on_volume_changed)
        rp.color_changed.connect(self._on_color_changed)
        rp.select_toggled.connect(self._set_hl_mode)
        rp.clear_clicked.connect(self._clear_page_highlights)
        rp.export_clicked.connect(self._export_highlights)
        rp.finished_clicked.connect(self._toggle_finished)
        rp.toc_clicked.connect(self._show_toc)
        rp.focus_clicked.connect(self._open_focus_dialog)
        rp.section_toggled.connect(self._on_section_toggle)

    # ──────────────────────────────────────────────────────────────
    # ATALHOS
    # ──────────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        def sc(seq, fn):
            QShortcut(QKeySequence(seq), self, activated=fn)

        sc("Ctrl+F", self._open_search)
        sc("Ctrl+O", self._open_file)
        sc("Ctrl+0", self._zoom_reset)
        sc("Ctrl+Shift+F", self._open_focus_dialog)
        sc("Tab", self._on_tab)
        sc("Esc", self._on_escape)

    def keyPressEvent(self, event):
        """Teclas de leitura. Chegam aqui só quando nenhum campo de texto as
        consumiu — então digitar na busca não pula frases nem muda o zoom."""
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key.Key_Space and not ctrl:
            self._toggle_play()
        elif key == Qt.Key.Key_Right:
            self._next_page() if ctrl else self._next_chunk()
        elif key == Qt.Key.Key_Left:
            self._prev_page() if ctrl else self._prev_chunk()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.view.zoom_in()
        elif key == Qt.Key.Key_Minus:
            self.view.zoom_out()
        else:
            super().keyPressEvent(event)

    def _on_tab(self):
        """Tab alterna o modo leitura — menos dentro de um campo de texto,
        onde continua sendo navegação entre campos."""
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QSpinBox)):
            w.focusNextPrevChild(True)
            return
        self._toggle_reading_mode()

    def _on_escape(self):
        if self.search_bar.isVisible():
            self._close_search()

    # ──────────────────────────────────────────────────────────────
    # PREFERÊNCIAS / AJUSTES
    # ──────────────────────────────────────────────────────────────

    def _on_voice_changed(self, name: str):
        self._pref_voice_name = name
        self._voice = VOICES[name]
        prefs.set_value("voice", name)
        # O ritmo aprendido era o da voz anterior; recomeça do padrão.
        if self._timeline is not None:
            self._timeline.reset_calibration()

    def _on_speed_changed(self, label: str):
        self._pref_speed_label = label
        self._speed = SPEEDS[label]
        prefs.set_value("speed", label)
        # A duração estimada do livro depende da velocidade escolhida.
        if self._timeline is not None:
            self._timeline.speed_pct = self._speed
            self._refresh_timeline()

    def _on_volume_changed(self, volume: float):
        self.player.volume = volume
        self._volume_save.start()

    def _on_color_changed(self, label: str):
        self._pref_highlight_label = label
        self._highlight_color_hex = HIGHLIGHT_COLORS[label]
        self.view.set_selection_color(self._highlight_color_hex)
        prefs.set_value("highlight_color_label", label)

    def _on_section_toggle(self, title: str, open_: bool):
        state = dict(self._pref_panel_sections)
        state[title] = open_
        self._pref_panel_sections = state
        prefs.set_value("panel_sections", state)

    # ──────────────────────────────────────────────────────────────
    # VISUALIZADOR (zoom, modo leitura, página)
    # ──────────────────────────────────────────────────────────────

    def _on_zoom_changed(self, zoom: float):
        self.topbar.set_zoom_text(zoom)
        prefs.set_value(_ZOOM_PREF, zoom)

    def _zoom_reset(self):
        self.view.reset_view()
        self.topbar.set_zoom_text(self.view.zoom)
        prefs.set_value(_ZOOM_PREF, self.view.zoom)

    def _toggle_fit(self):
        mode = "pagina" if self.view.fit_mode == "largura" else "largura"
        self.view.set_fit_mode(mode)
        prefs.set_value("fit_mode", mode)
        self.topbar.set_fit_text(mode)
        self._on_zoom_changed(self.view.zoom)

    def _toggle_reading_mode(self):
        """Esconde/mostra os painéis laterais — a página ganha toda a largura."""
        self._reading_mode = not self._reading_mode
        prefs.set_value("reading_mode", self._reading_mode)
        self._apply_reading_mode()

    def _apply_reading_mode(self):
        self.sidebar.setVisible(not self._reading_mode)
        self.right_panel.setVisible(not self._reading_mode)
        self.topbar.set_reading_active(self._reading_mode)

    def _show_page(self, n: int):
        """Mostra a página n (thread da UI). Chamado pelo loop de leitura via
        sig_show_page e ignorado se a leitura já passou para outra página."""
        if not self.renderer or not (0 <= n < self.total_pages) or n != self.current_page:
            return
        self._ephemeral_highlights = []
        self._word_highlights = []
        if self.current_path:
            lib.save_position(self.current_path, n, self.current_chunk_idx)
        self.topbar.set_page(n + 1, self.total_pages)
        focus_y, self._pending_focus_y = self._pending_focus_y, None
        self.view.show_page(self.renderer, n, focus_y)
        self.view.set_chunk_highlights([])
        self.view.set_word_highlights([])
        self._refresh_saved_highlights()
        self._refresh_search_layer()

    # ──────────────────────────────────────────────────────────────
    # CRONÔMETRO
    # ──────────────────────────────────────────────────────────────

    def _tick_timer(self):
        if self._timer_running:
            now = time.time()
            self._session_secs += now - self._last_tick
            self._last_tick = now
        m, s = divmod(int(self._session_secs), 60)
        h, m = divmod(m, 60)
        self.transport.set_session_text(f"sessão  {h:02d}:{m:02d}:{s:02d}")
        self._refresh_timeline()

    # ──────────────────────────────────────────────────────────────
    # BIBLIOTECA
    # ──────────────────────────────────────────────────────────────

    def _refresh_lib(self):
        want_finished = self.sidebar.current_tab() == "Lidos"
        books = [(p, v) for p, v in lib.all_books().items()
                 if os.path.exists(p) and v.get("finished", False) == want_finished]
        self.sidebar.set_books(books)

    def _on_lib_changed(self):
        self._update_finished_btn()
        self._refresh_lib()

    def _remove_book(self, path: str):
        name = os.path.basename(path)
        if not ask_yes_no(self, "Remover livro",
                          f'Remover "{name}" da biblioteca?\n\nO arquivo PDF não será apagado.'):
            return
        if self.current_path == path:
            self._close_current_book()
        lib.remove(path)
        highlights.clear_book(path)
        self._refresh_lib()

    def _close_current_book(self):
        """Para tudo e deixa a tela sem livro."""
        self._stop_read_loop()
        self.player.stop()
        if self.renderer:
            self.renderer.close()
            self.renderer = None
        self.current_path = None
        self._timeline = None
        self._reading_pos = None
        self._anchor_seconds = 0.0
        self._search_gen += 1
        self._search_results = []
        self._search_idx = -1
        self.transport.set_seek_enabled(False)
        self.transport.reset_timeline()
        self.topbar.set_title("Nenhum livro aberto")
        self.topbar.clear_page()
        self.view.clear()

    def _open_file(self):
        if self._focus_active:
            self._focus_blocked_feedback()
            return
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf)")
        if not path:
            return
        lib.add(path)
        self._load_book(path)
        self._refresh_lib()

    def _load_book(self, path: str):
        """
        Troca de livro. Abrir um PDF pode ser lento em livros grandes (varre
        todas as páginas para detectar cabeçalho/rodapé), então roda numa
        thread de fundo e nunca trava a UI. `current_path` nunca aponta para
        um livro que falhou ao abrir.
        """
        if self._focus_active and path != self.current_path:
            self._focus_blocked_feedback()
            return
        self._close_current_book()
        self._open_token += 1
        name = os.path.basename(path)
        self.topbar.set_title(f"Abrindo {name[:50] + '…' if len(name) > 50 else name}…")
        threading.Thread(
            target=self._open_book_bg, args=(path, self._open_token), daemon=True,
        ).start()

    def _open_book_bg(self, path: str, token: int):
        try:
            renderer = PDFRenderer(path)
        except PDFOpenError as e:
            log.warning("Não foi possível abrir %r: %s", path, e)
            if self._alive:
                self.sig_book_failed.emit(path, str(e), token)
            return
        except Exception as e:
            log.error("Erro inesperado ao abrir %r: %s", path, e)
            if self._alive:
                self.sig_book_failed.emit(path, str(e), token)
            return
        if self._alive:
            self.sig_book_opened.emit(path, renderer, token)
        else:
            renderer.close()

    def _on_book_open_failed(self, path: str, error_msg: str, token: int):
        if token != self._open_token:
            return
        self.topbar.set_title("Nenhum livro aberto")
        QMessageBox.critical(
            self, "Não foi possível abrir o PDF",
            f'Não foi possível abrir "{os.path.basename(path)}".\n\n{error_msg}')

    def _on_book_opened(self, path: str, renderer: PDFRenderer, token: int):
        if token != self._open_token or not self._alive:
            renderer.close()    # o usuário já abriu outro livro nesse meio tempo
            return
        self.current_path = path
        self.renderer = renderer
        self.total_pages = renderer.total

        meta = lib.get(path)
        self.current_page = min(meta.get("last_page", 0), max(0, self.total_pages - 1))
        self.current_chunk_idx = meta.get("last_chunk_idx", 0)
        self._word_cursor_page = None
        self._follow_suppressed = False
        self._pending_focus_y = None
        lib.save_total(path, self.total_pages)

        # Linha do tempo do audiolivro (page_lengths vem de graça da varredura
        # que o PDFRenderer já faz ao abrir o arquivo).
        self._timeline = BookTimeline(renderer.page_lengths, speed_pct=self._speed)
        self._reading_pos = None
        self._publish_position()
        self.transport.set_seek_enabled(self._timeline.total_chars > 0)

        name = os.path.basename(path)
        self.topbar.set_title(name[:50] + "…" if len(name) > 50 else name)
        self.topbar.set_page_range(self.total_pages)
        self._update_finished_btn()

        self._show_page(self.current_page)
        self._start_read_loop()

    def _toggle_finished(self):
        if not self.current_path:
            return
        lib.mark_finished(self.current_path, not lib.is_finished(self.current_path))
        self._update_finished_btn()
        self._refresh_lib()

    def _update_finished_btn(self):
        if self.current_path:
            self.right_panel.set_finished(lib.is_finished(self.current_path))

    # ──────────────────────────────────────────────────────────────
    # PERSISTÊNCIA / ENCERRAMENTO
    # ──────────────────────────────────────────────────────────────

    def _save_session(self):
        if self.current_path:
            with self._state_lock:
                chunk = self.current_chunk_idx
            lib.save_position(self.current_path, self.current_page, chunk)

        if self._session_secs < 1 or not self.current_path:
            return
        m, s = divmod(int(self._session_secs), 60)
        h, m = divmod(m, 60)
        hist.add_session(
            self._session_start,
            f"{h:02d}h {m:02d}m {s:02d}s",
            self._session_secs,
            os.path.basename(self.current_path),
        )

    def _restore_geometry(self):
        self.resize(1300, 820)
        try:
            if self._geo_file.exists():
                raw = self._geo_file.read_text().strip()
                # Formato novo: "qt:<hex>". O arquivo da versão Tk guardava
                # "LxA+X+Y" — nesse caso só se usa o tamanho padrão.
                if raw.startswith("qt:"):
                    self.restoreGeometry(QByteArray.fromHex(raw[3:].encode("ascii")))
        except Exception as e:
            log.debug("Geometria não restaurada: %s", e)

    def closeEvent(self, event):
        if self._focus_active:
            if not ask_yes_no(
                self, "Modo Foco ativo",
                f"O modo foco ainda tem {self._focus_remaining() // 60}min "
                f"{self._focus_remaining() % 60:02d}s restante.\n\n"
                "Deseja sair mesmo assim?"):
                event.ignore()
                return
        self._alive = False
        self._stop_read_loop()
        self._save_session()
        highlights.save_to_disk()
        self.player.quit()
        if self.renderer:
            self.renderer.close()
        from config import TEMP_DIR
        try:
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR)
        except Exception:
            pass
        try:
            self._geo_file.write_text("qt:" + bytes(self.saveGeometry().toHex()).decode("ascii"))
        except Exception:
            pass
        event.accept()


__all__ = ["App"]
