"""
ui/app.py — janela principal.

Layout:
  ┌──────────┬─────────────────────────┬──────────┐
  │ SIDEBAR  │   VISUALIZADOR PDF      │  PAINEL  │
  │  220px   │   (imagem da página)    │  200px   │
  │          │                         │          │
  │          ├─────────────────────────┤          │
  │          │   CONTROLES (140px)     │          │
  └──────────┴─────────────────────────┴──────────┘

Regra: lógica de negócio fica em core/ e data/.
       Este arquivo orquestra UI + chama os módulos, usando mixins.
"""

import datetime
import logging
import os
import shutil
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk

import data.highlights as highlights
import data.history as hist
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
    C,
)
from core.player import Player
from ui.controls import ControlsMixin
from ui.dict_popup import DictPopupMixin
from ui.focus_dialog import FocusMixin
from ui.highlights_mixin import HighlightsMixin
from ui.right_panel import RightPanelMixin

# Import dos mixins
from ui.sidebar import SidebarMixin
from ui.toc_window import TocMixin
from ui.viewer import ViewerMixin

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
ctk.set_appearance_mode("dark")


class App(SidebarMixin, ViewerMixin, ControlsMixin, RightPanelMixin, HighlightsMixin, DictPopupMixin, TocMixin, FocusMixin, ctk.CTk):
    # ──────────────────────────────────────────────────────────────────
    # INIT
    # ──────────────────────────────────────────────────────────────────

    def __init__(self):
        super().__init__()
        self.title("LECTOR")
        self.minsize(900, 600)
        self.configure(fg_color=C["bg"])
        self._geo_file = GEOMETRY_FILE
        if self._geo_file.exists():
            try:
                self.geometry(self._geo_file.read_text().strip())
            except Exception:
                self.geometry("1300x820")
        else:
            self.geometry("1300x820")

        # Preferências persistidas (voz, velocidade, volume, zoom,
        # auto-scroll, cor de grifo) — antes resetavam para os padrões de
        # config.py a cada abertura do app; agora seguem o usuário entre
        # sessões (ver data/prefs.py).
        _p = prefs.get_all()

        self._pref_voice_name = _p.get("voice") or DEFAULT_VOICE
        if self._pref_voice_name not in VOICES:
            self._pref_voice_name = DEFAULT_VOICE

        self._pref_speed_label = _p.get("speed") or DEFAULT_SPEED
        if self._pref_speed_label not in SPEEDS:
            self._pref_speed_label = DEFAULT_SPEED

        _volume = _p.get("volume")
        self._pref_volume = DEFAULT_VOLUME if _volume is None else max(0.0, min(1.0, _volume))

        self._pref_highlight_label = _p.get("highlight_color_label") or DEFAULT_HIGHLIGHT_LABEL
        if self._pref_highlight_label not in HIGHLIGHT_COLORS:
            self._pref_highlight_label = DEFAULT_HIGHLIGHT_LABEL

        _zoom = _p.get("zoom")
        self._pref_zoom = 2.5 if _zoom is None else max(1.0, min(5.0, _zoom))

        _autoscroll = _p.get("autoscroll")
        self._pref_autoscroll = True if _autoscroll is None else bool(_autoscroll)

        # Estado
        self.renderer = None
        self.player     = Player()
        self.current_path: str | None = None
        self.current_page  = 0          # página sendo exibida (0-indexed)
        self.current_chunk_idx = 0      # índice da frase atual sendo lida
        self.total_pages   = 0
        self._stop         = threading.Event()
        self._voice        = VOICES[self._pref_voice_name]
        self._speed        = SPEEDS[self._pref_speed_label]
        self._dragging     = False
        self._session_start = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        self._session_secs  = 0.0
        self._timer_running = False
        self._last_tick     = 0.0

        self._ephemeral_highlights = []
        self._current_text = ""
        self._detected_lang: str | None = None
        self._state_lock = threading.Lock()   # protege current_chunk_idx entre threads
        self._autoscroll_enabled: bool = self._pref_autoscroll   # scroll automático ligado/desligado
        self._alive = True                        # False após _quit — impede callbacks órfãos

        # Modo foco
        self._focus_active  = False   # True quando o modo foco está ligado
        self._focus_end_ts  = 0.0     # timestamp (time.time()) em que o foco termina
        self._focus_tick_id = None    # id do .after() do countdown

        # Rastreia clique vs. pan no canvas
        self._press_x = 0
        self._press_y = 0

        # Modo seleção manual de grifo
        self._hl_mode       = False   # True quando o usuário ativou seleção
        self._sel_start_pdf = None    # (pdf_x, pdf_y) início da seleção
        self._sel_rect_id   = None    # id do retângulo desenhado no canvas

        self.player.volume = self._pref_volume

        # Zoom e pan da página
        self._zoom       = self._pref_zoom   # 1.0 = ajusta ao canvas, >1.0 = zoom
        self._zoom_min   = 1.0
        self._zoom_max   = 5.0
        self._pan_x      = 0            # offset de pan em pixels (imagem renderizada)
        self._pan_y      = 0
        self._pan_start  = None         # (x, y) do clique para arrastar
        self._pan_pending_top = False   # True logo após abrir/trocar de página — ver _show_page
        self._cur_img    = None         # PIL Image da página atual (para redesenhar)
        
        self._lib_tab_var = ctk.StringVar(value="Lendo")

        self._build()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._quit)
        self._refresh_lib()
        self._tick_timer()

    # ──────────────────────────────────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_center()
        self._build_right()

    # ──────────────────────────────────────────────────────────────────
    # ATALHOS
    # ──────────────────────────────────────────────────────────────────

    def _bind_keys(self):
        self.bind("<space>",         lambda _: self._toggle_play())
        # Setas: pula frases
        self.bind("<Right>",         lambda _: self._next_chunk())
        self.bind("<Left>",          lambda _: self._prev_chunk())
        # Ctrl + setas: pula páginas
        self.bind("<Control-Right>", lambda _: self._next_page())
        self.bind("<Control-Left>",  lambda _: self._prev_page())
        # Busca
        self.bind("<Control-f>",     lambda _: self._open_search())
        self.bind("<Control-F>",     lambda _: self._open_search())
        # Modo foco
        self.bind("<Control-Shift-F>", lambda _: self._open_focus_dialog())
        # Abrir arquivo
        self.bind("<Control-o>",     lambda _: self._open_file())
        self.bind("<Control-O>",     lambda _: self._open_file())
        # Zoom (+ / - / reset) — antes só existiam botões na topbar
        self.bind("<plus>",          lambda _: self._zoom_in())
        self.bind("<equal>",         lambda _: self._zoom_in())   # "+" sem Shift em teclado US
        self.bind("<KP_Add>",        lambda _: self._zoom_in())
        self.bind("<minus>",         lambda _: self._zoom_out())
        self.bind("<KP_Subtract>",   lambda _: self._zoom_out())
        self.bind("<Control-0>",     lambda _: self._zoom_reset())
        # Esc universal — fecha o que estiver aberto (popup de dicionário,
        # barra de busca); cada Toplevel modal (foco, sumário, popup) tem
        # seu próprio bind de Esc além deste.
        self.bind("<Escape>",        lambda _: self._on_escape())

    def _on_escape(self):
        """Fecha, em ordem de prioridade, o que estiver aberto na janela
        principal quando o usuário aperta Esc."""
        if getattr(self, "_dict_popup", None) is not None:
            try:
                if self._dict_popup.winfo_exists():
                    self._dict_popup.destroy()
                    return
            except Exception:
                pass
        if hasattr(self, "_search_bar") and self._search_bar.winfo_ismapped():
            self._close_search()

    # ──────────────────────────────────────────────────────────────────
    # CRONÔMETRO
    # ──────────────────────────────────────────────────────────────────

    def _tick_timer(self):
        import time
        if self._timer_running:
            now = time.time()
            self._session_secs += now - self._last_tick
            self._last_tick     = now
        m, s = divmod(int(self._session_secs), 60)
        h, m = divmod(m, 60)
        self._timer_lbl.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.after(1000, self._tick_timer)

    # ──────────────────────────────────────────────────────────────────
    # PERSISTÊNCIA
    # ──────────────────────────────────────────────────────────────────

    def _save_session(self):
        if self.current_path:
            with self._state_lock:
                _chunk = self.current_chunk_idx
            import data.library as lib
            lib.save_position(self.current_path, self.current_page, _chunk)
        
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

    # ──────────────────────────────────────────────────────────────────
    # ENCERRAMENTO
    # ──────────────────────────────────────────────────────────────────

    def _quit(self):
        if self._focus_active:
            import time
            remaining = max(0, int(self._focus_end_ts - time.time()))
            m, s = divmod(remaining, 60)
            time_str = f"{m}min {s:02d}s" if m else f"{s}s"
            ok = messagebox.askyesno(
                "Modo Foco ativo",
                f"O modo foco ainda tem {time_str} restante.\n\n"
                "Deseja sair mesmo assim?",
                icon="warning",
            )
            if not ok:
                return
        self._alive = False
        self._stop.set()
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
            self._geo_file.write_text(self.geometry())
        except Exception:
            pass
        self.destroy()
        sys.exit()