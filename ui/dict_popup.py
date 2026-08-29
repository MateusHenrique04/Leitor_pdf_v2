import threading
import tkinter as tk

from config import FONTS, C
from core import dictionary as dic
from ui.widgets import flat_button


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
        """Exibe popup estilizado com a definição da palavra.
        Conteúdo longo (muitas acepções) rola dentro de uma área com
        altura máxima, em vez de vazar para fora da tela."""
        # Fecha popup anterior se existir
        if hasattr(self, "_dict_popup") and self._dict_popup and self._dict_popup.winfo_exists():
            self._dict_popup.destroy()

        popup = tk.Toplevel(self)
        self._dict_popup = popup
        popup.overrideredirect(True)   # sem barra de título
        popup.configure(bg=C["panel_alt"])
        popup.attributes("-topmost", True)

        # Borda colorida
        border = tk.Frame(popup, bg=C["red"], padx=2, pady=2)
        border.pack(fill="both", expand=True)
        outer = tk.Frame(border, bg=C["panel_alt2"])
        outer.pack(fill="both", expand=True)

        # ── Área de conteúdo rolável ──
        max_h = int(self.winfo_screenheight() * 0.7)
        content_canvas = tk.Canvas(outer, bg=C["panel_alt2"], highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(outer, orient="vertical", command=content_canvas.yview,
                            bg=C["border"], troughcolor=C["panel_alt2"], bd=0, width=8)
        content_canvas.configure(yscrollcommand=vsb.set)
        inner = tk.Frame(content_canvas, bg=C["panel_alt2"])
        inner_window = content_canvas.create_window((0, 0), window=inner, anchor="nw")

        network_error = bool(result and result.get("_network_error"))

        if network_error:
            tk.Label(inner, text=f'"{word}"', font=FONTS["body_bold"],
                     bg=C["panel_alt2"], fg=C["text"], padx=12, pady=8).pack()
            tk.Label(inner,
                     text="Sem conexão com a internet.\nVerifique sua rede e tente novamente.",
                     font=FONTS["body_small"], bg=C["panel_alt2"], fg=C["text_dim"],
                     padx=12, pady=4, justify="left").pack()
        elif result:
            # Texto simples em vez de emoji de bandeira: bandeiras (sequências
            # de "regional indicator") não renderizam de forma confiável no
            # Tkinter no Windows — apareciam como pontos quebrados.
            lang_label = {"pt-BR": "PT-BR", "en": "EN", "es": "ES"}
            lang_tag = lang_label.get(result["lang"], result["lang"])

            # Header
            hdr = tk.Frame(inner, bg=C["panel_alt3"])
            hdr.pack(fill="x")

            tk.Label(hdr, text=result["word"].lower(),
                     font=FONTS["title"],
                     bg=C["panel_alt3"], fg=C["text"],
                     padx=12, pady=8, anchor="w").pack(side="left")

            tag_row = tk.Frame(hdr, bg=C["panel_alt3"])
            tag_row.pack(side="right", padx=10)
            tk.Label(tag_row, text=lang_tag,
                     font=FONTS["label"],
                     bg=C["red"], fg="#fff",
                     padx=6, pady=2).pack()

            if result.get("phonetic"):
                tk.Label(inner, text=result["phonetic"],
                         font=FONTS["mono"],
                         bg=C["panel_alt2"], fg=C["text_dim"],
                         padx=12, anchor="w").pack(fill="x")

            tk.Frame(inner, bg=C["border"], height=1).pack(fill="x", padx=10, pady=4)

            # Definições
            for meaning in result["meanings"]:
                tk.Label(inner,
                         text=meaning["part_of_speech"],
                         font=("Courier", 8, "bold italic"),
                         bg=C["panel_alt2"], fg=C["red"],
                         padx=12, anchor="w").pack(fill="x", pady=(4, 0))
                for i, d in enumerate(meaning["definitions"], 1):
                    tk.Label(inner,
                             text=f"  {i}. {d}",
                             font=FONTS["body_small"],
                             bg=C["panel_alt2"], fg=C["text_soft"],
                             padx=12, pady=2,
                             anchor="w", justify="left",
                             wraplength=320).pack(fill="x")
        else:
            tk.Label(inner,
                     text=f'"{word}"',
                     font=FONTS["body_bold"],
                     bg=C["panel_alt2"], fg=C["text"],
                     padx=12, pady=8).pack()
            tk.Label(inner,
                     text="Definição não encontrada.",
                     font=FONTS["body_small"],
                     bg=C["panel_alt2"], fg=C["text_dim"],
                     padx=12, pady=4, justify="left").pack()

        # Botão fechar
        close_row = tk.Frame(inner, bg=C["panel_alt2"])
        close_row.pack(fill="x", pady=(4, 6))
        close_btn = flat_button(
            close_row, "×  Fechar (Esc)", lambda: popup.destroy(),
            font=FONTS["mono_bold"], bg=C["border"], fg="#888", hover_bg="#333",
        )
        close_btn.pack(side="right", padx=10)

        # ── Mede o conteúdo já populado e decide altura/scrollbar ──
        popup.update_idletasks()
        content_w = max(inner.winfo_reqwidth(), 260)
        content_h = inner.winfo_reqheight()
        shown_h = min(content_h, max_h)
        content_canvas.configure(width=content_w, height=shown_h)
        content_canvas.itemconfig(inner_window, width=content_w)
        content_canvas.configure(scrollregion=(0, 0, content_w, content_h))

        content_canvas.pack(side="left", fill="both", expand=True)
        if content_h > max_h:
            vsb.pack(side="right", fill="y")

        def _on_mousewheel(e):
            content_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        content_canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)

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
            sy = max(0, sh - ph - 10)
        popup.geometry(f"+{sx}+{sy}")

        # Fecha ao clicar fora do popup ou pressionar Esc
        def _on_focus_out(e):
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass
        popup.bind("<FocusOut>", _on_focus_out)
        popup.bind("<Escape>", lambda _e: popup.destroy())
        popup.focus_set()
