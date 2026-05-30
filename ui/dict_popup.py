import tkinter as tk
import threading
from config import C
from core import dictionary as dic

class DictPopupMixin:
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
        if self._alive:
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

        # Fecha ao clicar fora do popup — usa bind no próprio toplevel com guard
        def _on_focus_out(e):
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass
        popup.bind("<FocusOut>", _on_focus_out)
        popup.focus_set()
