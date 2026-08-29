import tkinter as tk
from tkinter import messagebox

from config import FONTS, C
from ui.widgets import flat_button


class FocusMixin:
    def _open_focus_dialog(self):
        """Abre o diálogo para configurar e iniciar o modo foco."""
        if self._focus_active:
            # Já ativo: pergunta se quer cancelar
            import time
            remaining = max(0, int(self._focus_end_ts - time.time()))
            m, s = divmod(remaining, 60)
            time_str = f"{m}min {s:02d}s" if m else f"{s}s"
            ok = messagebox.askyesno(
                "Modo Foco ativo",
                f"Foco em andamento — {time_str} restante.\n\nCancelar o modo foco?",
                icon="question",
            )
            if ok:
                self._focus_cancel()
            return

        # Janela de configuração
        dlg = tk.Toplevel(self)
        dlg.title("Modo Foco")
        dlg.configure(bg=C["bg"])
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        # Barra vermelha no topo
        tk.Frame(dlg, bg=C["red"], height=3).pack(fill="x")

        tk.Label(dlg, text="🎯  MODO FOCO",
                 font=("Georgia", 14, "bold"),
                 bg=C["bg"], fg=C["text"],
                 pady=16).pack()

        tk.Label(dlg,
                 text="Durante o foco você não poderá\n"
                      "trocar de livro nem sair do app\n"
                      "sem confirmar.",
                 font=("Georgia", 9),
                 bg=C["bg"], fg=C["text_dim"],
                 justify="center").pack(pady=(0, 14))

        tk.Frame(dlg, bg=C["border"], height=1).pack(fill="x", padx=20)

        # Presets de duração
        tk.Label(dlg, text="DURAÇÃO",
                 font=("Courier", 8, "bold"),
                 bg=C["bg"], fg=C["text_dim"]).pack(anchor="w", padx=20, pady=(12, 4))

        presets = [("15 min", 15), ("25 min", 25), ("30 min", 30),
                   ("45 min", 45), ("60 min", 60), ("90 min", 90)]
        self._focus_minutes = tk.IntVar(value=25)

        preset_frame = tk.Frame(dlg, bg=C["bg"])
        preset_frame.pack(padx=20, fill="x")
        btn_refs = []

        def _select_preset(mins, btns):
            self._focus_minutes.set(mins)
            custom_entry.delete(0, "end")
            for b, m in btns:
                active = (m == mins)
                b.configure(
                    bg=C["red"] if active else C["border"],
                    fg="#fff"   if active else C["text_dim"],
                )

        for col, (label, mins) in enumerate(presets):
            b = tk.Label(preset_frame, text=label,
                         font=("Courier", 9, "bold"),
                         bg=C["border"], fg=C["text_dim"],
                         cursor="hand2", pady=7, anchor="center", width=7)
            b.grid(row=col // 3, column=col % 3, padx=3, pady=3, sticky="ew")
            preset_frame.grid_columnconfigure(col % 3, weight=1)
            btn_refs.append((b, mins))

        for b, mins in btn_refs:
            b.bind("<Button-1>", lambda e, m=mins: _select_preset(m, btn_refs))


        # Campo personalizado
        tk.Label(dlg, text="OU TEMPO PERSONALIZADO (minutos)",
                 font=("Courier", 8, "bold"),
                 bg=C["bg"], fg=C["text_dim"]).pack(anchor="w", padx=20, pady=(12, 4))

        custom_entry = tk.Entry(
            dlg, font=("Courier", 12, "bold"),
            bg=C["panel_alt"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", bd=6, justify="center", width=8,
        )
        custom_entry.pack(padx=20, fill="x")

        # Seleciona 25 min por padrão
        _select_preset(25, btn_refs)

        def _on_custom_change(*_):
            val = custom_entry.get().strip()
            if val.isdigit() and int(val) > 0:
                self._focus_minutes.set(int(val))
                # Desmarca presets visuais
                for b, _ in btn_refs:
                    b.configure(bg=C["border"], fg=C["text_dim"])

        custom_entry.bind("<KeyRelease>", _on_custom_change)

        tk.Frame(dlg, bg=C["border"], height=1).pack(fill="x", padx=20, pady=14)

        # Botões
        btn_row = tk.Frame(dlg, bg=C["bg"])
        btn_row.pack(padx=20, pady=(0, 20), fill="x")

        def _cancel_dlg():
            dlg.destroy()

        def _start():
            mins = self._focus_minutes.get()
            if mins <= 0:
                return
            dlg.destroy()
            self._focus_start(mins)

        cancel_btn = flat_button(btn_row, "Cancelar", _cancel_dlg,
                                  font=FONTS["mono"], bg=C["border"], fg=C["text_dim"],
                                  hover_bg="#333", padx=16, pady=8)
        cancel_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        start_btn = flat_button(btn_row, "🎯  Iniciar Foco", _start,
                                 font=FONTS["mono_bold"], bg=C["red"], fg="#fff",
                                 hover_bg=C["red_hot"], padx=16, pady=8)
        start_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        dlg.bind("<Escape>", lambda _e: _cancel_dlg())
        dlg.bind("<Return>", lambda _e: _start())

        # Centraliza a janela sobre o app
        dlg.update_idletasks()
        w, h = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        x = self.winfo_rootx() + (self.winfo_width()  - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dlg.geometry(f"+{x}+{y}")

    def _focus_start(self, minutes: int):
        """Ativa o modo foco por `minutes` minutos."""
        import time
        self._focus_active  = True
        self._focus_end_ts  = time.time() + minutes * 60

        # Atualiza botão
        self._focus_btn.configure(
            text="🔴 Foco ativo — cancelar",
            fg_color=C["red_deep"],
            border_color=C["red"],
            text_color=C["red"],
        )
        self._focus_tick()

    def _focus_tick(self):
        """Atualiza o contador regressivo a cada segundo."""
        if not self._alive or not self._focus_active:
            return
        import time
        remaining = max(0, int(self._focus_end_ts - time.time()))
        if remaining == 0:
            self._focus_end_naturally()
            return
        m, s = divmod(remaining, 60)
        h, m2 = divmod(m, 60)
        if h:
            txt = f"{h}h {m2:02d}m {s:02d}s"
        else:
            txt = f"{m:02d}:{s:02d}"
        self._focus_lbl.configure(text=txt)
        self._focus_tick_id = self.after(1000, self._focus_tick)

    def _focus_end_naturally(self):
        """Chamado quando o tempo do foco esgota."""
        self._focus_active = False
        self._focus_lbl.configure(text="✓ Foco concluído!")
        self._focus_btn.configure(
            text="🎯 Iniciar Foco",
            fg_color=C["panel"],
            border_color=C["border"],
            text_color=C["text_dim"],
        )
        # Apaga a mensagem de conclusão após 5s
        self.after(5000, lambda: self._focus_lbl.configure(text=""))
        # Notificação visual discreta no título
        self.title("LECTOR  ✓ Foco concluído!")
        self.after(4000, lambda: self.title("LECTOR"))

    def _focus_cancel(self):
        """Cancela o modo foco manualmente."""
        self._focus_active = False
        if self._focus_tick_id:
            self.after_cancel(self._focus_tick_id)
            self._focus_tick_id = None
        self._focus_lbl.configure(text="")
        self._focus_btn.configure(
            text="🎯 Iniciar Foco",
            fg_color=C["panel"],
            border_color=C["border"],
            text_color=C["text_dim"],
        )

    def _focus_blocked_feedback(self):
        """Feedback visual rápido quando uma ação é bloqueada pelo foco."""
        import time
        remaining = max(0, int(self._focus_end_ts - time.time()))
        m, s = divmod(remaining, 60)
        time_str = f"{m}min {s:02d}s" if m else f"{s}s"
        # Pisca o label do foco em vermelho vivo
        self._focus_lbl.configure(
            text=f"🔒 bloqueado  ({time_str})",
            fg=C["red_hot"],
        )
        self.after(1800, lambda: self._focus_lbl.configure(
            fg=C["success"],
            text=f"{m:02d}:{s:02d}" if not m else f"{m}min {s:02d}s",
        ))
