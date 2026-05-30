import tkinter as tk
from tkinter import messagebox
from config import C

class TocMixin:
    def _show_toc(self):
        """Abre janela com sumário extraído do PDF via PyMuPDF."""
        if not self.renderer:
            messagebox.showinfo("Sumário", "Nenhum livro aberto.")
            return
        toc = self.renderer.get_toc()
        if not toc:
            messagebox.showinfo("Sumário",
                                "Este PDF não possui sumário embutido. "
                                "Tente um PDF com marcadores/bookmarks.")
            return

        win = tk.Toplevel(self)
        win.title("Sumário")
        win.configure(bg=C["bg"])
        win.geometry("420x560")
        win.resizable(True, True)

        tk.Frame(win, bg=C["red"], height=3).pack(fill="x")
        tk.Label(win, text="SUMÁRIO", font=("Georgia", 13, "bold"),
                 bg=C["bg"], fg=C["text"], pady=12).pack()
        tk.Frame(win, bg=C["border"], height=1).pack(fill="x", padx=16)

        frame = tk.Frame(win, bg=C["bg"])
        frame.pack(fill="both", expand=True, padx=0, pady=8)

        scrollbar = tk.Scrollbar(frame, bg=C["border"],
                                  troughcolor=C["panel"], bd=0, width=8)
        scrollbar.pack(side="right", fill="y")

        canvas = tk.Canvas(frame, bg=C["bg"], highlightthickness=0,
                           yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=canvas.yview)

        inner = tk.Frame(canvas, bg=C["bg"])
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        inner.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(
            canvas_window, width=e.width))

        for level, title, page in toc:
            indent = (level - 1) * 16
            row = tk.Frame(inner, bg=C["bg"], cursor="hand2")
            row.pack(fill="x", pady=1)

            # Indicador de nível
            color = C["red"] if level == 1 else C["text_dim"]
            prefix = "▸ " if level == 1 else "  · "
            lbl = tk.Label(row,
                           text=prefix + title,
                           font=("Georgia", 10 if level == 1 else 9,
                                 "bold" if level == 1 else "normal"),
                           bg=C["bg"], fg=color,
                           anchor="w", padx=12 + indent, pady=5,
                           wraplength=320, justify="left")
            lbl.pack(side="left", fill="x", expand=True)

            page_lbl = tk.Label(row, text=str(page),
                                font=("Courier", 8), bg=C["bg"],
                                fg=C["text_dim"], padx=10)
            page_lbl.pack(side="right")

            def _go(p=page):
                self.current_page = p - 1
                self.current_chunk_idx = 0
                self._restart_loop()
                win.destroy()

            def _hover_on(e, r=row, l=lbl, pl=page_lbl):
                for w in (r, l, pl): w.configure(bg="#1C1C1C")
            def _hover_off(e, r=row, l=lbl, pl=page_lbl):
                for w in (r, l, pl): w.configure(bg=C["bg"])

            for w in (row, lbl, page_lbl):
                w.bind("<Button-1>", lambda e, fn=_go: fn())
                w.bind("<Enter>", _hover_on)
                w.bind("<Leave>", _hover_off)

        win.bind("<MouseWheel>", lambda e: canvas.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))
