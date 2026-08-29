import os
from tkinter import filedialog, messagebox

import data.highlights as highlights
from config import DEFAULT_HIGHLIGHT_COLOR, C


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
                fg_color=C["border"], hover_color="#333",
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
        for i in range(len(page_highlights) - 1, -1, -1):
            h = page_highlights[i]
            # Considera uma pequena margem (2 pontos) para facilitar o clique
            if h["x0"] - 2 <= pdf_x <= h["x1"] + 2 and h["y0"] - 2 <= pdf_y <= h["y1"] + 2:
                highlights.delete(self.current_path, self.current_page + 1, i)
                highlights.save_to_disk()
                self._redraw()
                return

    def _precompute_word_bboxes(
        self,
        chunks: list[str],
        chunk_idx: int,
        timings: list[dict],
        page: int,
    ) -> list[tuple[float, float, list[dict]]]:
        """
        Para cada word-timing do chunk, encontra os retângulos no PDF.
        Retorna lista de (start_s, end_s, [rects]) — uma entrada por palavra.

        Estratégia de busca por contexto:
          - Para localizar a palavra com precisão, busca uma janela de
            "palavra_anterior + palavra + palavra_seguinte" no PDF.
          - Se não achar com contexto, tenta a palavra isolada.
          - O cursor y é atualizado progressivamente para não regredir.

        É executado ANTES do player.play(), então não bloqueia a UI.
        """
        if not self.renderer or not timings:
            return []

        result: list[tuple[float, float, list[dict]]] = []
        cursor_y = getattr(self, "_eph_y_cursor", 0.0)

        # Palavras do chunk para montar janela de contexto
        chunk_words = timings  # cada item: {word, start, end}

        for wi, t in enumerate(chunk_words):
            word = t["word"].strip()
            if not word:
                result.append((t["start"], t["end"], []))
                continue

            # Janela de contexto: até 2 palavras antes + atual + 2 depois
            ctx_start = max(0, wi - 2)
            ctx_end   = min(len(chunk_words), wi + 3)
            context   = " ".join(cw["word"] for cw in chunk_words[ctx_start:ctx_end])

            rects = []

            # Tenta com contexto primeiro
            if len(context) > len(word):
                try:
                    rects = self.renderer.search_text(page, context)
                except Exception:
                    rects = []

            # Fallback: palavra isolada
            if not rects and len(word) > 2:
                try:
                    rects = self.renderer.search_text(page, word)
                except Exception:
                    rects = []

            # Filtra e escolhe o grupo à frente do cursor
            if rects:
                rects_sorted = sorted(rects, key=lambda r: r["y0"])

                # Agrupa retângulos contíguos
                sub_groups: list[list[dict]] = []
                cur_sg: list[dict] = []
                for rect in rects_sorted:
                    if not cur_sg or rect["y0"] - cur_sg[-1]["y1"] <= 30:
                        cur_sg.append(rect)
                    else:
                        sub_groups.append(cur_sg)
                        cur_sg = [rect]
                if cur_sg:
                    sub_groups.append(cur_sg)

                # Escolhe grupo à frente do cursor (nunca regride)
                candidates = [
                    sg for sg in sub_groups
                    if min(r["y0"] for r in sg) >= cursor_y
                ]
                if candidates:
                    best = min(candidates, key=lambda sg: min(r["y0"] for r in sg))
                else:
                    best = max(sub_groups, key=lambda sg: min(r["y0"] for r in sg))

                cursor_y = max(r["y1"] for r in best)
                rects = best

            result.append((t["start"], t["end"], rects))

        # Atualiza cursor para o próximo chunk
        if result:
            last_rects = next((r[2] for r in reversed(result) if r[2]), [])
            if last_rects:
                self._eph_y_cursor = max(r["y1"] for r in last_rects)

        return result

    def _highlight_ephemeral(self):
        """
        Fallback de grifo usado em seek/prev/next (sem áudio ativo).
        Durante a leitura normal, o grifo palavra-por-palavra é feito
        pelo loop em _read_loop via _precompute_word_bboxes.
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
            self.after(0, self._redraw)
            self.after(0, self._auto_scroll_to_highlight)

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

        all_h = highlights._load().get(self.current_path, {})
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
                    page_obj = self.renderer._doc[page_num - 1]
                    rect = __import__("pymupdf").Rect(h["x0"], h["y0"],
                                                   h["x1"], h["y1"])
                    text = page_obj.get_text("text", clip=rect).strip()
                    text = " ".join(text.split())  # normaliza espaços/quebras
                except Exception:
                    text = "(texto não extraível)"
                color = h.get("color", DEFAULT_HIGHLIGHT_COLOR)
                lines.append(f"> {text}")
                lines.append(f"<!-- cor: {color} -->")
                lines.append("")

        content_md = "\n".join(lines)
        try:
            open(dest, "w", encoding="utf-8").write(content_md)
            messagebox.showinfo("Exportar Grifos",
                                f"Grifos exportados com sucesso!\n{dest}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar:\n{e}")
