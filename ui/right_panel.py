import tkinter as tk

import customtkinter as ctk

import data.prefs as prefs
from config import FONTS, HIGHLIGHT_COLORS, SPEEDS, VOICES, C


class RightPanelMixin:
    def _build_right(self):
        panel = tk.Frame(self, bg=C["panel"], width=200)
        panel.grid(row=0, column=2, sticky="nsew")
        panel.grid_propagate(False)

        def _sep():
            tk.Frame(panel, bg=C["border"], height=1).pack(fill="x", padx=16, pady=(10, 0))

        def _lbl(text):
            tk.Label(panel, text=text, font=FONTS["label"],
                     bg=C["panel"], fg=C["text_dim"]).pack(anchor="w", padx=16, pady=(10, 4))

        tk.Label(panel, text="CONTROLES", font=FONTS["label"],
                 bg=C["panel"], fg=C["text_faint2"]).pack(anchor="w", padx=16, pady=(20, 4))
        tk.Frame(panel, bg=C["border"], height=1).pack(fill="x", padx=16)

        # VOZ — dropdown (seleção inicial vem da preferência persistida)
        _lbl("VOZ")
        voice_names = list(VOICES.keys())
        self._voice_idx = voice_names.index(self._pref_voice_name)
        self._voice_popup_open = False

        vbtn = tk.Frame(panel, bg=C["panel_alt"], cursor="hand2")
        vbtn.pack(fill="x", padx=16)
        self._voice_lbl = tk.Label(
            vbtn, text=voice_names[self._voice_idx],
            font=FONTS["mono"], bg=C["panel_alt"], fg=C["text_soft2"],
            anchor="w", padx=10, pady=8, wraplength=155,
        )
        self._voice_lbl.pack(side="left", fill="x", expand=True)
        arr = tk.Label(vbtn, text="▾", font=("Courier", 11),
                       bg=C["panel_alt"], fg=C["red"], padx=6)
        arr.pack(side="right")

        self._voice_popup = tk.Frame(panel, bg=C["panel_alt2"],
                                      highlightbackground=C["border_soft"],
                                      highlightthickness=1)

        def _pick_voice(idx):
            self._voice_idx = idx
            name = voice_names[idx]
            self._voice_lbl.configure(text=name)
            self._voice = VOICES[name]
            prefs.set("voice", name)
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
                        font=FONTS["mono"],
                        bg=C["select_bg"] if sel else C["panel_alt2"],
                        fg=C["red"] if sel else C["text_soft2"],
                        anchor="w", padx=10, pady=7,
                        cursor="hand2", wraplength=165,
                    )
                    opt.pack(fill="x")
                    opt.bind("<Button-1>", lambda e, i=i: _pick_voice(i))
                    opt.bind("<Enter>",    lambda e, o=opt: o.configure(bg=C["hover"]))
                    opt.bind("<Leave>",    lambda e, o=opt, i=i:
                             o.configure(bg=C["select_bg"] if i == self._voice_idx else C["panel_alt2"]))
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
            for _label, b in self._speed_btns.items():
                b.configure(bg=C["panel_alt"], fg=C["text_faint"])
            self._speed_btns[label].configure(bg=C["red"], fg="#fff")
            self._speed = SPEEDS[label]
            prefs.set("speed", label)

        for i, label in enumerate(SPEEDS):
            b = tk.Label(speed_grid, text=label,
                         font=FONTS["mono_bold"],
                         bg=C["panel_alt"], fg=C["text_faint"],
                         cursor="hand2", pady=6, anchor="center", width=5)
            b.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="ew")
            speed_grid.grid_columnconfigure(i % 3, weight=1)
            self._speed_btns[label] = b
            b.bind("<Button-1>", lambda e, lb=label: _pick_speed(lb))
        _pick_speed(self._pref_speed_label)

        # VOLUME — slider (valor inicial vem da preferência persistida)
        _sep()
        _lbl("VOLUME")
        vol_row = tk.Frame(panel, bg=C["panel"])
        vol_row.pack(fill="x", padx=16, pady=2)
        vol_row.grid_columnconfigure(0, weight=1)

        self._vol_lbl = tk.Label(
            vol_row, text=f"{int(self._pref_volume*100)}%",
            font=("Courier", 12, "bold"),
            bg=C["panel"], fg=C["red"], width=5,
        )
        self._vol_lbl.grid(row=0, column=1, padx=(6, 0))

        def _on_volume(v):
            self._vol_lbl.configure(text=f"{int(float(v))}%")
            self.player.volume = float(v) / 100
            prefs.set("volume", self.player.volume)

        vol_sl = tk.Scale(
            vol_row, from_=0, to=100, orient="horizontal",
            bg=C["panel"], troughcolor=C["border"],
            activebackground=C["red_hot"],
            highlightthickness=0, bd=0, showvalue=0,
            sliderrelief="flat", sliderlength=12, width=6, fg=C["red"],
            command=_on_volume,
        )
        vol_sl.set(int(self._pref_volume * 100))
        vol_sl.grid(row=0, column=0, sticky="ew")

        # GRIFOS — cores centralizadas em config.HIGHLIGHT_COLORS
        _sep()
        _lbl("GRIFOS")

        color_labels = list(HIGHLIGHT_COLORS.keys())
        self._color_map = HIGHLIGHT_COLORS

        self._color_var = ctk.StringVar(value=self._pref_highlight_label)
        self._highlight_color = ctk.StringVar(value=HIGHLIGHT_COLORS[self._pref_highlight_label])

        def _on_pick_color(label):
            self._highlight_color.set(self._color_map.get(label, HIGHLIGHT_COLORS[self._pref_highlight_label]))
            prefs.set("highlight_color_label", label)

        color_menu = ctk.CTkOptionMenu(
            panel,
            variable  = self._color_var,
            values    = color_labels,
            command   = _on_pick_color,
            fg_color  = C["panel"],
            button_color      = C["border"],
            button_hover_color= C["red"],
            text_color= C["text"],
        )
        color_menu.pack(pady=(4, 0), padx=16, fill="x")

        self._btn_select = ctk.CTkButton(
            panel,
            text        = "✏ Selecionar",
            command     = self._toggle_hl_mode,
            fg_color    = C["border"],
            hover_color = "#333",
            text_color  = C["text"],
        )
        self._btn_select.pack(pady=(8, 0), padx=16, fill="x")


        btn_clear = ctk.CTkButton(
            panel,
            text     = "🗑 Limpar página",
            command  = self._clear_page_highlights,
            fg_color = C["panel"],
            hover_color = C["border"],
            text_color  = C["text_dim"],
        )
        btn_clear.pack(pady=(4, 0), padx=16, fill="x")

        btn_export = ctk.CTkButton(
            panel,
            text        = "📤 Exportar Grifos",
            command     = self._export_highlights,
            fg_color    = C["panel"],
            hover_color = C["border"],
            text_color  = C["text_dim"],
            border_width=1,
            border_color=C["border"],
        )
        btn_export.pack(pady=(4, 0), padx=16, fill="x")

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

        _sep()
        _lbl("MODO FOCO")
        self._focus_btn = ctk.CTkButton(
            panel,
            text="🎯 Iniciar Foco",
            command=self._open_focus_dialog,
            fg_color=C["panel"],
            hover_color=C["border"],
            text_color=C["text_dim"],
            border_width=1,
            border_color=C["border"],
        )
        self._focus_btn.pack(pady=(4, 0), padx=16, fill="x")

        self._focus_lbl = tk.Label(
            panel, text="",
            font=FONTS["mono_bold"],
            bg=C["panel"], fg=C["success"],
        )
        self._focus_lbl.pack(anchor="center", pady=(4, 0))

        _sep()
        _lbl("SUMÁRIO")
        btn_toc = ctk.CTkButton(
            panel,
            text="📋 Ver Sumário",
            command=self._show_toc,
            fg_color=C["panel"],
            hover_color=C["border"],
            text_color=C["text_dim"],
            border_width=1,
            border_color=C["border"]
        )
        btn_toc.pack(pady=(4, 0), padx=16, fill="x")
