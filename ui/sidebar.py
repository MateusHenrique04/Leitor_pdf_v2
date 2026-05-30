import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from config import C
from core.pdf_renderer import PDFRenderer
import data.library as lib
import data.highlights as highlights

class SidebarMixin:
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

        scroll_container = ctk.CTkScrollableFrame(
            sb,
            fg_color=C["panel"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["text_dim"],
        )
        scroll_container.pack(fill="both", expand=True, padx=0, pady=0)
        self._lib_frame = scroll_container

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
        for path, meta in books.items():
            name = os.path.basename(path)
            disp = name[:22] + "…" if len(name) > 23 else name
            outer = tk.Frame(self._lib_frame, bg=C["panel"])
            outer.pack(fill="x")
            row  = tk.Frame(outer, bg=C["panel"], cursor="hand2")
            row.pack(fill="x")
            dot = tk.Label(row, text="▸", font=("Courier", 9),
                           bg=C["panel"], fg=C["red"], padx=10)
            dot.pack(side="left")
            lbl = tk.Label(row, text=disp, font=("Georgia", 10),
                           bg=C["panel"], fg="#909090",
                           anchor="w", pady=6)
            lbl.pack(side="left", fill="x", expand=True)

            # Barra de progresso
            total = meta.get("total_pages", 0)
            last  = meta.get("last_page", 0)
            pct   = (last / total) if total > 0 else 0.0
            pct_txt = f"{int(pct*100)}%"
            prog_bg = tk.Frame(outer, bg=C["border"], height=2)
            prog_bg.pack(fill="x", padx=0)
            prog_fill = tk.Frame(prog_bg, bg=C["red"], height=2)
            prog_fill.place(relwidth=pct, relheight=1.0)
            pct_lbl = tk.Label(outer, text=pct_txt,
                               font=("Courier", 7), bg=C["panel"],
                               fg=C["text_dim"], anchor="e", padx=10)
            pct_lbl.pack(fill="x")

            # Botão remover (×) — fica discreto, vermelho no hover
            btn_rm = tk.Label(row, text="×", font=("Georgia", 13, "bold"),
                              bg=C["panel"], fg=C["text_dim"],
                              padx=8, pady=4, cursor="hand2")
            btn_rm.pack(side="right")

            def _open(p=path): self._load_book(p)
            def _remove(p=path): self._remove_book(p)

            def _on(e, r=row, d=dot, l=lbl, o=outer, pl=pct_lbl, b=btn_rm):
                for w in (r, d, l, o, pl, b): w.configure(bg="#1C1C1C")
                b.configure(fg=C["red"])
            def _off(e, r=row, d=dot, l=lbl, o=outer, pl=pct_lbl, b=btn_rm):
                for w in (r, d, l, o, pl, b): w.configure(bg=C["panel"])
                b.configure(fg=C["text_dim"])

            for w in (outer, row, dot, lbl, pct_lbl):
                w.bind("<Button-1>", lambda e, fn=_open: fn())
                w.bind("<Enter>", _on); w.bind("<Leave>", _off)

            btn_rm.bind("<Button-1>", lambda e, fn=_remove: fn())
            btn_rm.bind("<Enter>", _on); btn_rm.bind("<Leave>", _off)

    def _remove_book(self, path: str):
        """Remove o livro da biblioteca após confirmação."""
        name = os.path.basename(path)
        ok = messagebox.askyesno(
            "Remover livro",
            f'Remover "{name}" da biblioteca?\n\nO arquivo PDF não será apagado.',
            icon="warning",
        )
        if not ok:
            return

        # Se o livro removido estiver aberto, limpa a tela
        if self.current_path == path:
            self._stop.set()
            self.player.stop()
            if self.renderer:
                self.renderer.close()
                self.renderer = None
            self.current_path = None
            self._title_lbl.configure(text="Nenhum livro aberto")
            self._page_lbl.configure(text="")
            self._canvas.delete("all")
            self._canvas_img_ref = None

        lib.remove(path)
        highlights.clear_book(path)
        self._refresh_lib()

    def _open_file(self):
        if self._focus_active:
            self._focus_blocked_feedback()
            return
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        lib.add(path)
        self._load_book(path)
        self._refresh_lib()

    def _load_book(self, path: str):
        # Bloqueia troca de livro durante o modo foco
        if self._focus_active and path != self.current_path:
            self._focus_blocked_feedback()
            return
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

        import asyncio
        # Inicia o loop de leitura
        threading.Thread(target=lambda: asyncio.run(self._read_loop()),
                         daemon=True).start()

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
