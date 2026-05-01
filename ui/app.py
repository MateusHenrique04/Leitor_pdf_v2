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
       Este arquivo só orquestra UI + chama os módulos.
"""

import os
import asyncio
import threading
import datetime
import shutil
import sys
import logging
import re

import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw
import customtkinter as ctk

from config import C, VOICES, SPEEDS, DEFAULT_VOICE, DEFAULT_SPEED, DEFAULT_VOLUME, PDF_RENDER_DPI
from core.pdf_renderer import PDFRenderer
from core.tts          import speak
from core.player       import Player
from core              import dictionary as dic
import data.library as lib
import data.history as hist
import data.highlights as highlights

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
ctk.set_appearance_mode("dark")


class App(ctk.CTk):
    # ──────────────────────────────────────────────────────────────────
    # INIT
    # ──────────────────────────────────────────────────────────────────

    def __init__(self):
        super().__init__()
        self.title("LECTOR")
        self.geometry("1300x820")
        self.minsize(900, 600)
        self.configure(fg_color=C["bg"])

        # Estado
        self.renderer:  PDFRenderer | None = None
        self.player     = Player()
        self.current_path: str | None = None
        self.current_page  = 0          # página sendo exibida (0-indexed)
        self.current_chunk_idx = 0      # índice da frase atual sendo lida
        self.total_pages   = 0
        self._stop         = threading.Event()
        self._voice        = VOICES[DEFAULT_VOICE]
        self._speed        = SPEEDS[DEFAULT_SPEED]
        self._dragging     = False
        self._session_start = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        self._session_secs  = 0.0
        self._timer_running = False
        self._last_tick     = 0.0
        
        self._ephemeral_highlights = []
        self._current_text = ""
        self._detected_lang: str | None = None   # idioma detectado na página atual

        # Rastreia clique vs. pan no canvas
        self._press_x = 0
        self._press_y = 0

        self.player.volume = DEFAULT_VOLUME

        # Zoom e pan da página
        self._zoom       = 2.5          # 1.0 = ajusta ao canvas, >1.0 = zoom
        self._zoom_min   = 1.0
        self._zoom_max   = 5.0
        self._pan_x      = 0            # offset de pan em pixels (imagem renderizada)
        self._pan_y      = 0
        self._pan_start  = None         # (x, y) do clique para arrastar
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

    # ── Sidebar ───────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = tk.Frame(self, bg=C["panel"], width=220)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)

        # Logo
        logo = tk.Frame(sb, bg=C["panel"])
        logo.pack(fill="x", pady=(24, 0))
        tk.Frame(logo, bg=C["red"], width=3, height=32).place(x=20, y=4)
        tk.Label(logo, text="LECTOR", font=("Georgia", 20, "bold"),
                 bg=C["panel"], fg=C["text"]).pack(padx=(30, 0), anchor="w")
        tk.Label(logo, text="pdf audiobook", font=("Courier", 8),
                 bg=C["panel"], fg=C["text_dim"]).pack(padx=(31, 0), anchor="w", pady=(2, 16))

        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x")

        # Botão adicionar
        add = tk.Label(sb, text="＋  Abrir PDF",
                       font=("Georgia", 11, "bold"),
                       bg=C["red"], fg="#fff",
                       cursor="hand2", pady=10, anchor="center")
        add.pack(fill="x", padx=16, pady=14)
        add.bind("<Button-1>", lambda _: self._open_file())
        add.bind("<Enter>",    lambda _: add.configure(bg=C["red_hot"]))
        add.bind("<Leave>",    lambda _: add.configure(bg=C["red"]))

        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x")

        # Abas de livros
        seg_btn = ctk.CTkSegmentedButton(
            sb,
            values=["Lendo", "Lidos"],
            variable=self._lib_tab_var,
            command=lambda _: self._refresh_lib(),
            fg_color=C["border"],
            selected_color=C["red"],
            selected_hover_color=C["red_hot"],
            text_color="#888",
            unselected_color=C["panel"],
            unselected_hover_color="#2E2E2E"
        )
        seg_btn.pack(fill="x", padx=16, pady=(14, 8))

        self._lib_frame = tk.Frame(sb, bg=C["panel"])
        self._lib_frame.pack(fill="both", expand=True, padx=0)

    # ── Centro: visualizador + controles ──────────────────────────────

    def _build_center(self):
        center = tk.Frame(self, bg=C["bg"])
        center.grid(row=0, column=1, sticky="nsew")
        center.grid_rowconfigure(0, weight=1)   # visualizador expande
        center.grid_rowconfigure(1, weight=0)   # controles fixos
        center.grid_columnconfigure(0, weight=1)

        # ── Visualizador de página ──
        viewer = tk.Frame(center, bg=C["bg"])
        viewer.grid(row=0, column=0, sticky="nsew")
        viewer.grid_rowconfigure(0, weight=0)  # topbar
        viewer.grid_rowconfigure(1, weight=1)  # imagem
        viewer.grid_columnconfigure(0, weight=1)

        # Topbar: nome + página + slider
        topbar = tk.Frame(viewer, bg=C["panel"])
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)

        tk.Frame(topbar, bg=C["red"], height=2).grid(
            row=0, column=0, columnspan=3, sticky="ew")

        self._title_lbl = tk.Label(
            topbar, text="Nenhum livro aberto",
            font=("Georgia", 11, "bold"),
            bg=C["panel"], fg=C["text"],
            anchor="w", padx=18, pady=7,
        )
        self._title_lbl.grid(row=1, column=0, sticky="w")

        # Botões de zoom na topbar
        zoom_row = tk.Frame(topbar, bg=C["panel"])
        zoom_row.grid(row=1, column=1, sticky="e", padx=8)

        def _zoom_btn(parent, text, cmd):
            b = tk.Label(parent, text=text,
                         font=("Courier", 11, "bold"),
                         bg=C["border"], fg=C["text"],
                         cursor="hand2", padx=8, pady=2)
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda _: cmd())
            b.bind("<Enter>",    lambda _, bb=b: bb.configure(bg="#333"))
            b.bind("<Leave>",    lambda _, bb=b: bb.configure(bg=C["border"]))
            return b

        _zoom_btn(zoom_row, "−", self._zoom_out)
        self._zoom_lbl = tk.Label(zoom_row, text="100%",
                                   font=("Courier", 9, "bold"),
                                   bg=C["panel"], fg=C["text_dim"],
                                   width=5, anchor="center")
        self._zoom_lbl.pack(side="left")
        _zoom_btn(zoom_row, "＋", self._zoom_in)
        _zoom_btn(zoom_row, "⊡", self._zoom_reset)

        self._page_lbl = tk.Label(
            topbar, text="",
            font=("Courier", 10, "bold"),
            bg=C["panel"], fg=C["red"],
            anchor="e", padx=18,
        )
        self._page_lbl.grid(row=1, column=2, sticky="e")

        self._prog_var = tk.DoubleVar(value=0)
        self._prog_slider = tk.Scale(
            topbar, variable=self._prog_var,
            from_=1, to=1, orient="horizontal",
            bg=C["panel"], troughcolor=C["border"],
            activebackground=C["red_hot"],
            highlightthickness=0, bd=0,
            showvalue=0, sliderrelief="flat",
            sliderlength=14, width=5,
            fg=C["red"],
        )
        self._prog_slider.grid(row=2, column=0, columnspan=3, sticky="ew")
        self._prog_slider.bind("<Button-1>",        lambda _: setattr(self, "_dragging", True))
        self._prog_slider.bind("<ButtonRelease-1>", self._on_seek)

        # Canvas para exibir a imagem da página
        self._canvas = tk.Canvas(
            viewer, bg="#1A1A1A",
            highlightthickness=0, bd=0,
        )
        self._canvas.grid(row=1, column=0, sticky="nsew")
        self._canvas.bind("<Configure>",     self._on_canvas_resize)
        self._canvas.bind("<MouseWheel>",     self._on_mousewheel)      # Windows
        self._canvas.bind("<Button-4>",       self._on_mousewheel)      # Linux scroll up
        self._canvas.bind("<Button-5>",       self._on_mousewheel)      # Linux scroll down
        self._canvas.bind("<ButtonPress-1>",  self._on_pan_start)
        self._canvas.bind("<B1-Motion>",      self._on_pan_move)
        self._canvas.bind("<ButtonRelease-1>",self._on_pan_end)
        self._canvas_img_ref = None

        # ── Barra de controles ──
        self._build_controls(center)

    def _build_controls(self, parent):
        bar = tk.Frame(parent, bg=C["panel"], height=130)
        bar.grid(row=1, column=0, sticky="ew")
        bar.grid_propagate(False)

        tk.Frame(bar, bg=C["red"], height=2).place(x=0, y=0, relwidth=1)

        # Transport centralizado
        t = tk.Frame(bar, bg=C["panel"])
        t.place(relx=0.5, rely=0.5, anchor="center")

        self._timer_lbl = tk.Label(
            t, text="00:00:00",
            font=("Courier", 16, "bold"),
            bg=C["panel"], fg=C["red"],
        )
        self._timer_lbl.pack(pady=(0, 8))

        btns = tk.Frame(t, bg=C["panel"])
        btns.pack()

        def _tbtn(parent, text, cmd, size=15, w=42, h=42):
            f = tk.Frame(parent, bg=C["border"], width=w, height=h, cursor="hand2")
            f.pack_propagate(False)
            lbl = tk.Label(f, text=text, font=("Georgia", size),
                           bg=C["border"], fg="#888")
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            for ww in (f, lbl):
                ww.bind("<Button-1>", lambda _, c=cmd: c())
                ww.bind("<Enter>",    lambda _, ff=f, ll=lbl: [ff.configure(bg="#2E2E2E"), ll.configure(bg="#2E2E2E")])
                ww.bind("<Leave>",    lambda _, ff=f, ll=lbl: [ff.configure(bg=C["border"]), ll.configure(bg=C["border"])])
            return f

        _tbtn(btns, "⏮", self._prev_page).pack(side="left", padx=5)
        _tbtn(btns, "◂", self._prev_chunk, size=13, w=36, h=36).pack(side="left", padx=3)

        # Play button
        self._play_frame = tk.Frame(btns, bg=C["red"], width=64, height=64, cursor="hand2")
        self._play_frame.pack(side="left", padx=10)
        self._play_frame.pack_propagate(False)
        self._play_lbl = tk.Label(self._play_frame, text="▶",
                                   font=("Georgia", 22), bg=C["red"], fg="#fff")
        self._play_lbl.place(relx=0.5, rely=0.5, anchor="center")
        for w in (self._play_frame, self._play_lbl):
            w.bind("<Button-1>", lambda _: self._toggle_play())
            w.bind("<Enter>",    lambda _: self._play_frame.configure(bg=C["red_hot"]))
            w.bind("<Leave>",    lambda _: self._play_frame.configure(bg=C["red"]))

        _tbtn(btns, "▸", self._next_chunk, size=13, w=36, h=36).pack(side="left", padx=3)
        _tbtn(btns, "⏭", self._next_page).pack(side="left", padx=5)

    # ── Painel direito ─────────────────────────────────────────────────

    def _build_right(self):
        panel = tk.Frame(self, bg=C["panel"], width=200)
        panel.grid(row=0, column=2, sticky="nsew")
        panel.grid_propagate(False)

        def _sep():
            tk.Frame(panel, bg=C["border"], height=1).pack(fill="x", padx=16, pady=(10, 0))

        def _lbl(text):
            tk.Label(panel, text=text, font=("Courier", 8, "bold"),
                     bg=C["panel"], fg=C["text_dim"]).pack(anchor="w", padx=16, pady=(10, 4))

        tk.Label(panel, text="CONTROLES", font=("Courier", 8, "bold"),
                 bg=C["panel"], fg="#303030").pack(anchor="w", padx=16, pady=(20, 4))
        tk.Frame(panel, bg=C["border"], height=1).pack(fill="x", padx=16)

        # VOZ — dropdown
        _lbl("VOZ")
        voice_names = list(VOICES.keys())
        self._voice_idx = voice_names.index(DEFAULT_VOICE)
        self._voice_popup_open = False

        vbtn = tk.Frame(panel, bg="#1C1C1C", cursor="hand2")
        vbtn.pack(fill="x", padx=16)
        self._voice_lbl = tk.Label(
            vbtn, text=voice_names[self._voice_idx],
            font=("Courier", 9), bg="#1C1C1C", fg="#B0B0B0",
            anchor="w", padx=10, pady=8, wraplength=155,
        )
        self._voice_lbl.pack(side="left", fill="x", expand=True)
        arr = tk.Label(vbtn, text="▾", font=("Courier", 11),
                       bg="#1C1C1C", fg=C["red"], padx=6)
        arr.pack(side="right")

        self._voice_popup = tk.Frame(panel, bg="#202020",
                                      highlightbackground="#333",
                                      highlightthickness=1)

        def _pick_voice(idx):
            self._voice_idx = idx
            name = voice_names[idx]
            self._voice_lbl.configure(text=name)
            self._voice = VOICES[name]
            self._voice_popup.pack_forget()
            self._voice_popup_open = False

        def _toggle_voice(e=None):
            if self._voice_popup_open:
                self._voice_popup.pack_forget()
                self._voice_popup_open = False
            else:
                for w in self._voice_popup.winfo_children():
                    w.destroy()
                for i, name in enumerate(voice_names):
                    sel = i == self._voice_idx
                    opt = tk.Label(
                        self._voice_popup,
                        text=("▸ " if sel else "   ") + name,
                        font=("Courier", 9),
                        bg="#2A2A2A" if sel else "#202020",
                        fg=C["red"] if sel else "#B0B0B0",
                        anchor="w", padx=10, pady=7,
                        cursor="hand2", wraplength=165,
                    )
                    opt.pack(fill="x")
                    opt.bind("<Button-1>", lambda e, i=i: _pick_voice(i))
                    opt.bind("<Enter>",    lambda e, o=opt: o.configure(bg="#2E2E2E"))
                    opt.bind("<Leave>",    lambda e, o=opt, i=i:
                             o.configure(bg="#2A2A2A" if i == self._voice_idx else "#202020"))
                self._voice_popup.pack(fill="x", padx=16)
                self._voice_popup_open = True

        for w in (vbtn, self._voice_lbl, arr):
            w.bind("<Button-1>", _toggle_voice)

        # VELOCIDADE — botões preset
        _sep()
        _lbl("VELOCIDADE")
        self._speed_btns: dict[str, tk.Label] = {}
        speed_grid = tk.Frame(panel, bg=C["panel"])
        speed_grid.pack(fill="x", padx=16, pady=2)

        def _pick_speed(label):
            for l, b in self._speed_btns.items():
                b.configure(bg="#1A1A1A", fg="#606060")
            self._speed_btns[label].configure(bg=C["red"], fg="#fff")
            self._speed = SPEEDS[label]

        for i, label in enumerate(SPEEDS):
            b = tk.Label(speed_grid, text=label,
                         font=("Courier", 9, "bold"),
                         bg="#1A1A1A", fg="#606060",
                         cursor="hand2", pady=6, anchor="center", width=5)
            b.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="ew")
            speed_grid.grid_columnconfigure(i % 3, weight=1)
            self._speed_btns[label] = b
            b.bind("<Button-1>", lambda e, l=label: _pick_speed(l))
        _pick_speed(DEFAULT_SPEED)

        # VOLUME — slider
        _sep()
        _lbl("VOLUME")
        vol_row = tk.Frame(panel, bg=C["panel"])
        vol_row.pack(fill="x", padx=16, pady=2)
        vol_row.grid_columnconfigure(0, weight=1)

        self._vol_lbl = tk.Label(
            vol_row, text=f"{int(DEFAULT_VOLUME*100)}%",
            font=("Courier", 12, "bold"),
            bg=C["panel"], fg=C["red"], width=5,
        )
        self._vol_lbl.grid(row=0, column=1, padx=(6, 0))

        vol_sl = tk.Scale(
            vol_row, from_=0, to=100, orient="horizontal",
            bg=C["panel"], troughcolor=C["border"],
            activebackground=C["red_hot"],
            highlightthickness=0, bd=0, showvalue=0,
            sliderrelief="flat", sliderlength=12, width=6, fg=C["red"],
            command=lambda v: (
                self._vol_lbl.configure(text=f"{int(float(v))}%"),
                setattr(self.player, "volume", float(v) / 100),
            ),
        )
        vol_sl.set(int(DEFAULT_VOLUME * 100))
        vol_sl.grid(row=0, column=0, sticky="ew")

        # GRIFOS
        _sep()
        _lbl("GRIFOS")
        
        self._highlight_color = ctk.StringVar(value="#FFDD00")
        color_options = ["#FFDD00", "#00E676", "#00E5FF", "#FF4081"]
        color_labels  = ["🟡 Amarelo", "🟢 Verde", "🔵 Ciano", "🔴 Rosa"]
        self._color_map = dict(zip(color_labels, color_options))
        
        self._color_var = ctk.StringVar(value="🟡 Amarelo")
        color_menu = ctk.CTkOptionMenu(
            panel,
            variable  = self._color_var,
            values    = color_labels,
            command   = lambda label: self._highlight_color.set(self._color_map.get(label, "#FFDD00")),
            fg_color  = C["panel"],
            button_color      = C["border"],
            button_hover_color= C["red"],
            text_color= C["text"],
        )
        color_menu.pack(pady=(4, 0), padx=16, fill="x")
        
        btn_highlight = ctk.CTkButton(
            panel,
            text     = "✏ Grifar atual",
            command  = self._highlight_manual,
            fg_color = C["red"],
            hover_color = C["red_hot"],
            text_color  = C["text"],
        )
        btn_highlight.pack(pady=(8, 0), padx=16, fill="x")
        
        btn_clear = ctk.CTkButton(
            panel,
            text     = "🗑 Limpar página",
            command  = self._clear_page_highlights,
            fg_color = C["panel"],
            hover_color = C["border"],
            text_color  = C["text_dim"],
        )
        btn_clear.pack(pady=(4, 0), padx=16, fill="x")

        # STATUS
        _sep()
        _lbl("STATUS")
        
        self._btn_mark_finished = ctk.CTkButton(
            panel,
            text="✅ Marcar Lido",
            command=self._toggle_finished,
            fg_color=C["panel"],
            hover_color=C["border"],
            text_color=C["text_dim"],
            border_width=1,
            border_color=C["border"]
        )
        self._btn_mark_finished.pack(pady=(4, 0), padx=16, fill="x")

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

    # ──────────────────────────────────────────────────────────────────
    # BIBLIOTECA
    # ──────────────────────────────────────────────────────────────────

    def _refresh_lib(self):
        for w in self._lib_frame.winfo_children():
            w.destroy()
        
        is_finished_tab = (self._lib_tab_var.get() == "Lidos")
        
        books = {p: v for p, v in lib.all_books().items() 
                 if os.path.exists(p) and v.get("finished", False) == is_finished_tab}
        
        if not books:
            tk.Label(self._lib_frame, text="Nenhum livro.",
                     font=("Courier", 8), bg=C["panel"],
                     fg=C["text_dim"]).pack(pady=10, padx=18, anchor="w")
            return
        for path in books:
            name = os.path.basename(path)
            disp = name[:25] + "…" if len(name) > 26 else name
            row  = tk.Frame(self._lib_frame, bg=C["panel"], cursor="hand2")
            row.pack(fill="x")
            dot = tk.Label(row, text="▸", font=("Courier", 9),
                           bg=C["panel"], fg=C["red"], padx=10)
            dot.pack(side="left")
            lbl = tk.Label(row, text=disp, font=("Georgia", 10),
                           bg=C["panel"], fg="#909090",
                           anchor="w", pady=7)
            lbl.pack(side="left", fill="x", expand=True)

            def _open(p=path): self._load_book(p)
            def _on(e, r=row, d=dot, l=lbl):
                r.configure(bg="#1C1C1C"); d.configure(bg="#1C1C1C"); l.configure(bg="#1C1C1C")
            def _off(e, r=row, d=dot, l=lbl):
                r.configure(bg=C["panel"]); d.configure(bg=C["panel"]); l.configure(bg=C["panel"])

            for w in (row, dot, lbl):
                w.bind("<Button-1>", lambda e, fn=_open: fn())
                w.bind("<Enter>", _on); w.bind("<Leave>", _off)

    # ──────────────────────────────────────────────────────────────────
    # CARREGAR LIVRO
    # ──────────────────────────────────────────────────────────────────

    def _open_file(self):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        lib.add(path)
        self._load_book(path)
        self._refresh_lib()

    def _load_book(self, path: str):
        # Para tudo que estava rodando
        self._stop.set()
        self.player.stop()
        if self.renderer:
            self.renderer.close()
            self.renderer = None

        self.current_path = path
        self.renderer     = PDFRenderer(path)
        self.total_pages  = self.renderer.total
        
        book_meta = lib.get(path)
        self.current_page = book_meta.get("last_page", 0)
        self.current_chunk_idx = book_meta.get("last_chunk_idx", 0)

        lib.save_total(path, self.total_pages)

        # Atualiza UI
        name = os.path.basename(path)
        self._title_lbl.configure(text=name[:50] + "…" if len(name) > 50 else name)
        self._prog_slider.configure(from_=1, to=self.total_pages)
        self._prog_var.set(self.current_page + 1)
        self._update_finished_btn()

        self._stop.clear()
        self._show_page(self.current_page)

        # Inicia o loop de leitura
        threading.Thread(target=lambda: asyncio.run(self._read_loop()),
                         daemon=True).start()

    # ──────────────────────────────────────────────────────────────────
    # EXIBIÇÃO DA PÁGINA
    # ──────────────────────────────────────────────────────────────────

    def _show_page(self, n: int):
        """Renderiza e exibe a página n no canvas."""
        if not self.renderer or not (0 <= n < self.total_pages):
            return

        self.current_page = n
        self._pan_x = self._pan_y = 0   # reseta pan ao mudar de página
        lib.save_position(self.current_path, n, self.current_chunk_idx)

        # Atualiza label e slider sem disparar seek
        self._prog_var.set(n + 1)
        self._page_lbl.configure(text=f"PÁG. {n + 1} / {self.total_pages}")

        # Renderiza em thread separada para não travar a UI
        threading.Thread(target=self._render_and_draw, args=(n,), daemon=True).start()

    def _render_and_draw(self, n: int):
        """Roda em background — renderiza a imagem e agenda o draw na UI."""
        try:
            img = self.renderer.render_page(n)
            self.after(0, lambda i=img: self._draw_image(i))
        except Exception as e:
            log.error(f"Erro ao renderizar página {n}: {e}")

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _draw_image(self, img: Image.Image):
        """Exibe a imagem PIL no canvas com os grifos, respeitando zoom e pan."""
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            self.after(100, lambda: self._draw_image(img))
            return

        self._cur_img = img   # guarda para redesenhar no zoom/pan
        iw, ih = img.size

        # Aplica Grifos Permanentes e Efêmeros em uma cópia da imagem original
        img_drawn = img.convert("RGBA")
        overlay = Image.new("RGBA", img_drawn.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        zoom_pdf = PDF_RENDER_DPI / 72.0

        # Desenha efêmeros (TTS)
        if self._ephemeral_highlights:
            for h in self._ephemeral_highlights:
                r, g, b = self._hex_to_rgb(h.get("color", "#00E5FF")) # Cor diferente para a leitura
                draw.rectangle([h["x0"]*zoom_pdf, h["y0"]*zoom_pdf, h["x1"]*zoom_pdf, h["y1"]*zoom_pdf], fill=(r, g, b, 90))

        # Desenha manuais
        if self.current_path:
            saved_h = highlights.get(self.current_path, self.current_page + 1)
            for h in saved_h:
                r, g, b = self._hex_to_rgb(h.get("color", "#FFDD00"))
                a = int(h.get("opacity", 0.35) * 255)
                draw.rectangle([h["x0"]*zoom_pdf, h["y0"]*zoom_pdf, h["x1"]*zoom_pdf, h["y1"]*zoom_pdf], fill=(r, g, b, a))

        img_drawn.alpha_composite(overlay)
        base_img = img_drawn.convert("RGB")

        # Escala base (zoom=1 → cabe na tela)
        base_scale = min(cw / iw, ch / ih)
        scale      = base_scale * self._zoom
        nw         = int(iw * scale)
        nh         = int(ih * scale)

        # Limita pan: não deixa imagem sair completamente da tela
        max_px = max(0, (nw - cw) // 2 + nw // 4)
        max_py = max(0, (nh - ch) // 2 + nh // 4)
        self._pan_x = max(-max_px, min(max_px, self._pan_x))
        self._pan_y = max(-max_py, min(max_py, self._pan_y))

        resized = base_img.resize((nw, nh), Image.LANCZOS)

        # Posição central + offset de pan
        x = (cw - nw) // 2 + self._pan_x
        y = (ch - nh) // 2 + self._pan_y

        # Recorta somente a área visível para não criar imagem gigante
        src_x  = max(0, -x)
        src_y  = max(0, -y)
        src_x2 = min(nw, src_x + cw)
        src_y2 = min(nh, src_y + ch)
        cropped = resized.crop((src_x, src_y, src_x2, src_y2))

        dest_x = max(0, x)
        dest_y = max(0, y)

        bg = Image.new("RGB", (cw, ch), (26, 26, 26))
        bg.paste(cropped, (dest_x, dest_y))

        tk_img = ImageTk.PhotoImage(bg)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=tk_img)
        self._canvas_img_ref = tk_img

        # Atualiza label de zoom
        self._zoom_lbl.configure(text=f"{int(self._zoom * 100)}%")

        # Cursor muda para indicar que pode arrastar quando com zoom
        self._canvas.configure(cursor="fleur" if self._zoom > 1.01 else "")

    # ── Zoom ──────────────────────────────────────────────────────────

    def _zoom_in(self):
        self._zoom = min(self._zoom_max, round(self._zoom + 0.25, 2))
        self._redraw()

    def _zoom_out(self):
        self._zoom = max(self._zoom_min, round(self._zoom - 0.25, 2))
        if self._zoom <= 1.0:
            self._pan_x = self._pan_y = 0
        self._redraw()

    def _zoom_reset(self):
        self._zoom  = 1.0
        self._pan_x = self._pan_y = 0
        self._redraw()

    def _on_mousewheel(self, event):
        # Windows: event.delta (+120 / -120), Linux: Button-4/5
        if event.num == 4 or event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _on_pan_start(self, event):
        self._press_x = event.x
        self._press_y = event.y
        if self._zoom > 1.01:
            self._pan_start = (event.x - self._pan_x, event.y - self._pan_y)

    def _on_pan_move(self, event):
        if self._pan_start and self._zoom > 1.01:
            self._pan_x = event.x - self._pan_start[0]
            self._pan_y = event.y - self._pan_start[1]
            self._redraw()

    def _on_pan_end(self, event):
        dx = abs(event.x - self._press_x)
        dy = abs(event.y - self._press_y)
        self._pan_start = None
        # Se o mouse não se moveu mais de 5px é um clique simples → busca palavra
        if dx <= 5 and dy <= 5:
            self._on_word_click(event.x, event.y)

    def _redraw(self):
        """Redesenha a imagem atual com zoom/pan atualizados."""
        if self._cur_img is not None:
            self._draw_image(self._cur_img)

    # ── Dicionário ────────────────────────────────────────────────────

    def _canvas_to_pdf_coords(self, cx: int, cy: int) -> tuple[float, float] | None:
        """
        Converte coordenadas do canvas (pixels de tela) para coordenadas do PDF (pontos).
        Retorna (pdf_x, pdf_y) ou None se o clique foi fora da área da imagem.
        """
        if not self._cur_img:
            return None
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        iw, ih = self._cur_img.size
        base_scale = min(cw / iw, ch / ih)
        scale      = base_scale * self._zoom
        nw = int(iw * scale)
        nh = int(ih * scale)
        # Posição do canto superior esquerdo da imagem no canvas
        img_x0 = (cw - nw) // 2 + self._pan_x
        img_y0 = (ch - nh) // 2 + self._pan_y
        # Coordenada dentro da imagem renderizada
        ix = cx - img_x0
        iy = cy - img_y0
        if not (0 <= ix < nw and 0 <= iy < nh):
            return None
        # ix/scale → pixel na imagem PIL original (renderizada a PDF_RENDER_DPI)
        # ÷ (PDF_RENDER_DPI/72) → converte pixel para ponto PDF (72 DPI)
        dpi_scale = PDF_RENDER_DPI / 72.0
        pdf_x = (ix / scale) / dpi_scale
        pdf_y = (iy / scale) / dpi_scale
        return pdf_x, pdf_y

    def _on_word_click(self, cx: int, cy: int):
        """Chamado quando o usuário clica (sem arrastar) no canvas."""
        if not self.renderer:
            return
        coords = self._canvas_to_pdf_coords(cx, cy)
        if not coords:
            return
        pdf_x, pdf_y = coords
        word = self.renderer.word_at(self.current_page, pdf_x, pdf_y)
        if not word:
            return
        # Busca em thread para não travar a UI
        threading.Thread(
            target=self._fetch_and_show,
            args=(word, cx, cy),
            daemon=True,
        ).start()

    def _fetch_and_show(self, word: str, cx: int, cy: int):
        """Roda em background: busca definição e agenda popup na UI."""
        result = dic.lookup(word, self._detected_lang)
        self.after(0, lambda: self._show_dict_popup(word, result, cx, cy))

    def _show_dict_popup(self, word: str, result: dict | None, cx: int, cy: int):
        """Exibe popup estilizado com a definição da palavra."""
        # Fecha popup anterior se existir
        if hasattr(self, "_dict_popup") and self._dict_popup and self._dict_popup.winfo_exists():
            self._dict_popup.destroy()

        popup = tk.Toplevel(self)
        self._dict_popup = popup
        popup.overrideredirect(True)   # sem barra de título
        popup.configure(bg="#1A1A1A")
        popup.attributes("-topmost", True)

        # Borda colorida
        border = tk.Frame(popup, bg=C["red"], padx=2, pady=2)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg="#1E1E1E")
        inner.pack(fill="both", expand=True)

        if result:
            lang_label = {"pt-BR": "🇧🇷 PT", "en": "🇬🇧 EN", "es": "🇪🇸 ES"}
            lang_tag = lang_label.get(result["lang"], result["lang"])

            # Header
            hdr = tk.Frame(inner, bg="#252525")
            hdr.pack(fill="x", padx=0, pady=(0, 0))

            tk.Label(hdr, text=result["word"].lower(),
                     font=("Georgia", 16, "bold"),
                     bg="#252525", fg=C["text"],
                     padx=12, pady=8, anchor="w").pack(side="left")

            tag_row = tk.Frame(hdr, bg="#252525")
            tag_row.pack(side="right", padx=10)
            tk.Label(tag_row, text=lang_tag,
                     font=("Courier", 8, "bold"),
                     bg=C["red"], fg="#fff",
                     padx=6, pady=2).pack()

            if result.get("phonetic"):
                tk.Label(inner, text=result["phonetic"],
                         font=("Courier", 9),
                         bg="#1E1E1E", fg=C["text_dim"],
                         padx=12, anchor="w").pack(fill="x")

            tk.Frame(inner, bg=C["border"], height=1).pack(fill="x", padx=10, pady=4)

            # Definições
            for meaning in result["meanings"]:
                tk.Label(inner,
                         text=meaning["part_of_speech"],
                         font=("Courier", 8, "bold italic"),
                         bg="#1E1E1E", fg=C["red"],
                         padx=12, anchor="w").pack(fill="x", pady=(4, 0))
                for i, d in enumerate(meaning["definitions"], 1):
                    tk.Label(inner,
                             text=f"  {i}. {d}",
                             font=("Georgia", 9),
                             bg="#1E1E1E", fg="#C0C0C0",
                             padx=12, pady=2,
                             anchor="w", justify="left",
                             wraplength=320).pack(fill="x")
        else:
            tk.Label(inner,
                     text=f'"{word}"',
                     font=("Georgia", 13, "bold"),
                     bg="#1E1E1E", fg=C["text"],
                     padx=12, pady=8).pack()
            tk.Label(inner,
                     text="Definição não encontrada.\nVerifique a conexão com a internet.",
                     font=("Georgia", 9),
                     bg="#1E1E1E", fg=C["text_dim"],
                     padx=12, pady=4, justify="left").pack()

        # Botão fechar
        close_row = tk.Frame(inner, bg="#1E1E1E")
        close_row.pack(fill="x", pady=(4, 6))
        close_btn = tk.Label(close_row, text="×  Fechar",
                             font=("Courier", 9, "bold"),
                             bg=C["border"], fg="#888",
                             cursor="hand2", padx=10, pady=4)
        close_btn.pack(side="right", padx=10)
        close_btn.bind("<Button-1>", lambda _: popup.destroy())
        close_btn.bind("<Enter>",    lambda _: close_btn.configure(bg="#333"))
        close_btn.bind("<Leave>",    lambda _: close_btn.configure(bg=C["border"]))

        # Posiciona o popup próximo ao clique
        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        sx = self.winfo_rootx() + cx + 15
        sy = self.winfo_rooty() + cy + 15
        # Garante que não sai da tela
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        if sx + pw > sw:
            sx = sx - pw - 30
        if sy + ph > sh:
            sy = sy - ph - 30
        popup.geometry(f"+{sx}+{sy}")

        # Fecha ao clicar fora do popup
        popup.bind("<FocusOut>", lambda _: popup.destroy() if popup.winfo_exists() else None)
        popup.focus_set()

    def _on_canvas_resize(self, _event):
        """Redesenha a página atual quando o canvas muda de tamanho."""
        if self.renderer and 0 <= self.current_page < self.total_pages:
            threading.Thread(
                target=self._render_and_draw,
                args=(self.current_page,),
                daemon=True,
            ).start()

    # ──────────────────────────────────────────────────────────────────
    # LOOP DE LEITURA (TTS + player)
    # ──────────────────────────────────────────────────────────────────

    async def _read_loop(self):
        """
        Para cada página a partir de current_page:
          1. Extrai texto
          2. Gera áudio via TTS
          3. Toca o áudio
          4. Avança para a próxima página
        """
        while not self._stop.is_set():
            page = self.current_page
            if page >= self.total_pages:
                break

            self._ephemeral_highlights = []
            # Atualiza visual da página
            self.after(0, lambda p=page: self._show_page(p))

            text = self.renderer.text_for_page(page)
            if not text:
                self.current_page += 1
                self.current_chunk_idx = 0
                continue

            # Detecta idioma da página para o dicionário
            self._detected_lang = dic.detect_lang(text[:500])

            # Divide em frases ou linhas
            chunks = [c.strip() for c in re.split(r'(?<=[.!?])\s+|\n', text) if c.strip()]
            if not chunks:
                self.current_page += 1
                self.current_chunk_idx = 0
                continue

                
            start_idx = self.current_chunk_idx
            if start_idx >= len(chunks):
                start_idx = 0

            async def get_audio(text_chunk):
                try:
                    return await speak(text_chunk, self._voice, self._speed)
                except Exception as e:
                    log.error(f"TTS erro: {e}")
                    return b""

            next_audio_task = asyncio.create_task(get_audio(chunks[start_idx]))

            for i in range(start_idx, len(chunks)):
                if self._stop.is_set():
                    break
                    
                self.current_chunk_idx = i
                self._current_text = chunks[i]
                self._highlight_ephemeral()
                
                audio = await next_audio_task
                
                if i + 1 < len(chunks):
                    next_audio_task = asyncio.create_task(get_audio(chunks[i+1]))
                
                if self._stop.is_set() or not audio:
                    break

                self.player.play(audio)

                # Aguarda terminar (respeitando pause)
                while (self.player.is_busy() or self.player.is_paused) \
                      and not self._stop.is_set():
                    await asyncio.sleep(0.02)

            if not self._stop.is_set():
                self.current_page += 1
                self.current_chunk_idx = 0
                if self.current_page >= self.total_pages and self.current_path:
                    lib.mark_finished(self.current_path, True)
                    self._update_finished_btn()
                    self._refresh_lib()

    def _restart_loop(self):
        """Para o loop atual e reinicia da página corrente."""
        self._stop.set()
        self.player.stop()
        self.after(250, self._do_restart)

    def _do_restart(self):
        self._stop.clear()
        threading.Thread(
            target=lambda: asyncio.run(self._read_loop()),
            daemon=True,
        ).start()

    # ──────────────────────────────────────────────────────────────────
    # CONTROLES DE PLAYBACK
    # ──────────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if not self.renderer:
            return
        if self.player.is_paused:
            self.player.unpause()
            self._play_lbl.configure(text="⏸")
            self._timer_running = True
            import time; self._last_tick = time.time()
        else:
            self.player.pause()
            self._play_lbl.configure(text="▶")
            self._timer_running = False
            self._save_session()

    def _next_page(self):
        if not self.renderer:
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.current_chunk_idx = 0
            self._restart_loop()

    def _prev_page(self):
        if not self.renderer:
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.current_chunk_idx = 0
            self._restart_loop()

    def _get_current_chunks(self) -> list[str]:
        """Retorna a lista de frases (chunks) da página atual."""
        if not self.renderer:
            return []
        text = self.renderer.text_for_page(self.current_page)
        if not text:
            return []
        return [c.strip() for c in re.split(r'(?<=[.!?])\s+|\n', text) if c.strip()]

    def _next_chunk(self):
        """Pula para a próxima frase. Se for a última, avança para a próxima página."""
        if not self.renderer:
            return
        chunks = self._get_current_chunks()
        if chunks and self.current_chunk_idx < len(chunks) - 1:
            self.current_chunk_idx += 1
            self._restart_loop()
        else:
            # Última frase da página — avança a página
            self._next_page()

    def _prev_chunk(self):
        """Volta para a frase anterior. Se for a primeira, volta à página anterior na última frase."""
        if not self.renderer:
            return
        if self.current_chunk_idx > 0:
            self.current_chunk_idx -= 1
            self._restart_loop()
        elif self.current_page > 0:
            # Primeira frase da página — volta à página anterior, na última frase
            self.current_page -= 1
            chunks = self._get_current_chunks()
            self.current_chunk_idx = max(0, len(chunks) - 1)
            self._restart_loop()

    def _on_seek(self, _event):
        self._dragging = False
        if not self.renderer:
            return
        target = int(self._prog_var.get()) - 1   # converte para 0-indexed
        target = max(0, min(target, self.total_pages - 1))
        self.current_page = target
        self.current_chunk_idx = 0
        self._restart_loop()

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
    # GRIFOS
    # ──────────────────────────────────────────────────────────────────

    def _highlight_ephemeral(self):
        """Atualiza o grifo de leitura atual (apenas em memória RAM/UI) e redesenha."""
        if not self.renderer or not self._current_text:
            return
        
        # Busca pequenas porções para ter mais chance de achar a linha
        lines = [l for l in self._current_text.split('\n') if len(l) > 5]
        if not lines:
            lines = [self._current_text]
            
        self._ephemeral_highlights = []
        for line in lines:
            matches = self.renderer.search_text(self.current_page, line)
            for m in matches:
                m["color"] = "#00E5FF" # Cor fixa para TTS
                self._ephemeral_highlights.append(m)
                
        self.after(0, self._redraw)

    def _highlight_manual(self):
        """Salva a posição do texto lido atualmente como grifo permanente."""
        if not self.renderer or not self.current_path or not self._ephemeral_highlights:
            return
            
        color = self._highlight_color.get()
        for h in self._ephemeral_highlights:
            highlights.add(
                book_path=self.current_path,
                page=self.current_page + 1,
                x0=h["x0"], y0=h["y0"], x1=h["x1"], y1=h["y1"],
                color=color,
                opacity=0.35
            )
        self._redraw()

    def _clear_page_highlights(self):
        """Limpa todos os grifos da página atual."""
        if not self.current_path:
            return
        highlights.clear_page(self.current_path, self.current_page + 1)
        self._redraw()

    def _toggle_finished(self):
        if not self.current_path:
            return
        is_fin = lib.is_finished(self.current_path)
        lib.mark_finished(self.current_path, not is_fin)
        self._update_finished_btn()
        self._refresh_lib()

    def _update_finished_btn(self):
        if not self.current_path or not hasattr(self, '_btn_mark_finished'):
            return
        if lib.is_finished(self.current_path):
            self._btn_mark_finished.configure(text="📖 Marcar Não Lido", text_color=C["red"])
        else:
            self._btn_mark_finished.configure(text="✅ Marcar Lido", text_color=C["text_dim"])

    # ──────────────────────────────────────────────────────────────────
    # PERSISTÊNCIA
    # ──────────────────────────────────────────────────────────────────

    def _save_session(self):
        if self.current_path:
            lib.save_position(self.current_path, self.current_page, self.current_chunk_idx)
        
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
        self._save_session()
        highlights.save_to_disk()
        self._stop.set()
        self.player.quit()
        if self.renderer:
            self.renderer.close()
        from config import TEMP_DIR
        try:
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR)
        except Exception:
            pass
        self.destroy()
        sys.exit()
