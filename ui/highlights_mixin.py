import logging
import os
from pathlib import Path
from tkinter import filedialog, messagebox

import data.highlights as highlights
from config import CHUNK_HIGHLIGHT_OPACITY, DEFAULT_HIGHLIGHT_COLOR, C
from core.word_sync import merge_rects_by_line, word_bboxes

log = logging.getLogger(__name__)


class HighlightsMixin:
    def _toggle_hl_mode(self):
        """Liga/desliga o modo de seleção de grifo."""
        self._hl_mode = not self._hl_mode
        if self._hl_mode:
            self._canvas.configure(cursor="crosshair")
            self._btn_select.configure(
                fg_color=C["red"], hover_color=C["red_hot"],
                text="✕ Cancelar seleção"
            )
        else:
            self._canvas.configure(cursor="")
            self._btn_select.configure(
                fg_color=C["border"], hover_color=C["border_soft"],
                text="✏ Selecionar"
            )
            # Limpa retângulo de seleção visual se houver
            if self._sel_rect_id:
                self._canvas.delete(self._sel_rect_id)
                self._sel_rect_id  = None
            self._sel_start_pdf = None

    def _on_sel_start(self, event):
        coords = self._canvas_to_pdf_coords(event.x, event.y)
        if not coords:
            return
        self._sel_start_pdf  = coords
        self._sel_start_canvas = (event.x, event.y)
        if self._sel_rect_id:
            self._canvas.delete(self._sel_rect_id)
        self._sel_rect_id = self._canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=self._highlight_color.get(),
            width=2, dash=(4, 2),
        )

    def _on_sel_drag(self, event):
        if not self._sel_rect_id or not self._sel_start_pdf:
            return
        sx, sy = self._sel_start_canvas
        self._canvas.coords(self._sel_rect_id, sx, sy, event.x, event.y)

    def _on_sel_end(self, event):
        if not self._sel_start_pdf or not self.renderer or not self.current_path:
            return

        end_coords = self._canvas_to_pdf_coords(event.x, event.y)
        if not end_coords:
            return

        x0_pdf, y0_pdf = self._sel_start_pdf
        x1_pdf, y1_pdf = end_coords

        # Normaliza para que x0<x1, y0<y1
        x0_pdf, x1_pdf = min(x0_pdf, x1_pdf), max(x0_pdf, x1_pdf)
        y0_pdf, y1_pdf = min(y0_pdf, y1_pdf), max(y0_pdf, y1_pdf)

        # Seleção muito pequena (clique acidental) → ignora
        if (x1_pdf - x0_pdf) < 5 or (y1_pdf - y0_pdf) < 3:
            if self._sel_rect_id:
                self._canvas.delete(self._sel_rect_id)
                self._sel_rect_id = None
            self._sel_start_pdf = None
            return

        # Salva o grifo com as coordenadas selecionadas
        color = self._highlight_color.get()
        highlights.add(
            book_path=self.current_path,
            page=self.current_page + 1,
            x0=x0_pdf, y0=y0_pdf,
            x1=x1_pdf, y1=y1_pdf,
            color=color, opacity=0.35,
        )
        highlights.save_to_disk()

        # Limpa seleção visual e redesenha com o novo grifo
        if self._sel_rect_id:
            self._canvas.delete(self._sel_rect_id)
            self._sel_rect_id = None
        self._sel_start_pdf = None
        self._redraw()

    def _on_canvas_right_click(self, event):
        """Remove o grifo sob o cursor ao clicar com o botão direito."""
        if not self.renderer or not self.current_path:
            return

        coords = self._canvas_to_pdf_coords(event.x, event.y)
        if not coords:
            return

        pdf_x, pdf_y = coords
        page_highlights = highlights.get(self.current_path, self.current_page + 1)
        
        # Encontra o grifo clicado (do mais recente para o mais antigo)
        for h in reversed(page_highlights):
            # Considera uma pequena margem (2 pontos) para facilitar o clique
            if h["x0"] - 2 <= pdf_x <= h["x1"] + 2 and h["y0"] - 2 <= pdf_y <= h["y1"] + 2:
                highlights.delete(self.current_path, self.current_page + 1, h["id"])
                self._redraw()
                return

    def _precompute_word_bboxes(
        self,
        timings: list[dict],
        page: int,
    ) -> list[tuple[float, float, list[dict]]]:
        """
        Retângulo de cada palavra que o TTS vai falar nesta página.

        O casamento em si é lógica pura e mora em core/word_sync.py; aqui
        fica só o que é estado da UI: o cursor de posição dentro da
        página, que faz cada trecho continuar de onde o anterior parou.

        Roda na thread de background do loop de leitura — só lê o renderer
        (que é thread-safe) e devolve dados, sem tocar em widget Tk.
        """
        if not self.renderer or not timings:
            return []
        try:
            page_words = self.renderer.word_rects(page)
        except Exception as e:
            log.debug("word_rects falhou na página %d (ignorado): %s", page, e)
            return []

        # Cursor por página: ao mudar de página ele volta ao começo.
        if getattr(self, "_word_cursor_page", None) != page:
            self._word_cursor_page = page
            self._word_cursor = 0

        result, self._word_cursor = word_bboxes(page_words, timings, self._word_cursor)
        return result

    def _highlight_chunk_from_words(
        self, word_bboxes: list[tuple[float, float, list[dict]]]
    ) -> bool:
        """
        Pinta de uma vez o trecho inteiro que está prestes a ser lido,
        usando os retângulos já calculados em _precompute_word_bboxes.

        É o "fundo" sobre o qual o grifo da palavra corrente se destaca.
        Antes esse fundo vinha de _highlight_ephemeral(), que gasta uma
        busca heurística na página (~60 ms) logo antes de tocar o áudio —
        tempo morto entre uma frase e a seguinte. Aqui os retângulos já
        estão na mão: só falta juntar as palavras de cada linha num
        retângulo por linha, senão o desenho sai picotado palavra a
        palavra.

        Retorna False quando não há retângulo nenhum, para quem chama
        cair no caminho antigo.
        """
        rects = [r for _, _, rs in word_bboxes for r in rs]
        if not rects:
            return False

        self._ephemeral_highlights = [
            {**r, "color": C["info"], "opacity": CHUNK_HIGHLIGHT_OPACITY}
            for r in merge_rects_by_line(rects)
        ]
        self._eph_y_cursor = max(r["y1"] for r in rects)
        if self._alive:
            self.after(0, self._follow_highlight)
        return True

    def _highlight_ephemeral(self):
        """
        Fallback de grifo usado em seek/prev/next (sem áudio ativo).
        Durante a leitura normal, o grifo palavra-por-palavra é feito
        pelo loop em _read_loop via _precompute_word_bboxes.

        Também chamado direto da thread de background do _read_loop
        (verificado — item 10 da auditoria): só escreve em
        self._ephemeral_highlights (lista Python simples, não um widget
        Tk) e agenda o redesenho real com self.after(0, ...), que é a
        forma correta de voltar para a thread principal. Não precisa de
        mudança.
        """
        if not self.renderer or not self._current_text:
            return

        self._ephemeral_highlights = []
        cursor = getattr(self, "_eph_y_cursor", 0.0)

        try:
            group = self.renderer.search_text(self.current_page, self._current_text)
        except Exception:
            group = []

        if not group:
            lines = [ln for ln in self._current_text.split("\n") if len(ln.strip()) > 5]
            for line in lines:
                try:
                    partial = self.renderer.search_text(self.current_page, line)
                    group.extend(partial)
                except Exception:
                    continue

        if not group:
            if self._alive:
                self.after(0, self._redraw)
            return

        group_sorted = sorted(group, key=lambda m: m["y0"])
        sub_groups: list[list[dict]] = []
        current_sg: list[dict] = []
        for rect in group_sorted:
            if not current_sg or rect["y0"] - current_sg[-1]["y1"] <= 30:
                current_sg.append(rect)
            else:
                sub_groups.append(current_sg)
                current_sg = [rect]
        if current_sg:
            sub_groups.append(current_sg)

        candidates = [sg for sg in sub_groups if min(r["y0"] for r in sg) >= cursor]
        if candidates:
            best_group = min(candidates, key=lambda sg: min(r["y0"] for r in sg))
        else:
            best_group = max(sub_groups, key=lambda sg: min(r["y0"] for r in sg))

        self._eph_y_cursor = max(r["y1"] for r in best_group)

        for m in best_group:
            m["color"]   = C["info"]
            m["opacity"] = 0.35
            self._ephemeral_highlights.append(m)

        if self._alive:
            self.after(0, self._follow_highlight)

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

    def _export_highlights(self):
        """Exporta todos os grifos do livro atual para um arquivo Markdown."""
        if not self.current_path or not self.renderer:
            messagebox.showinfo("Exportar Grifos", "Nenhum livro aberto.")
            return

        all_h = highlights.all_for_book(self.current_path)
        if not all_h:
            messagebox.showinfo("Exportar Grifos",
                                "Nenhum grifo salvo neste livro.")
            return

        book_name = os.path.splitext(os.path.basename(self.current_path))[0]
        default_name = f"grifos_{book_name}.md"
        dest = filedialog.asksaveasfilename(
            title="Salvar grifos como…",
            initialfile=default_name,
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not dest:
            return

        lines = [f"# Grifos — {book_name}", ""]

        for page_str, page_highlights in sorted(all_h.items(),
                                                 key=lambda x: int(x[0])):
            page_num = int(page_str)
            lines.append(f"## Página {page_num}")
            lines.append("")
            for h in page_highlights:
                # Extrai o texto do trecho grifado via PDFRenderer
                try:
                    text = self.renderer.text_in_rect(
                        page_num - 1, h["x0"], h["y0"], h["x1"], h["y1"],
                    )
                except Exception:
                    text = ""
                text = text or "(texto não extraível)"
                color = h.get("color", DEFAULT_HIGHLIGHT_COLOR)
                lines.append(f"> {text}")
                lines.append(f"<!-- cor: {color} -->")
                lines.append("")

        content_md = "\n".join(lines)
        try:
            Path(dest).write_text(content_md, encoding="utf-8")
            messagebox.showinfo("Exportar Grifos",
                                f"Grifos exportados com sucesso!\n{dest}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar:\n{e}")
