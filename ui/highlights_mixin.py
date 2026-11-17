import logging
import os
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

import data.highlights as highlights
from config import CHUNK_HIGHLIGHT_OPACITY, DEFAULT_HIGHLIGHT_COLOR, C
from core.word_sync import merge_rects_by_line, word_bboxes

log = logging.getLogger(__name__)


class HighlightsMixin:
    # ──────────────────────────────────────────────────────────────
    # Grifos permanentes (manuais)
    # ──────────────────────────────────────────────────────────────

    def _set_hl_mode(self, on: bool):
        """Liga/desliga o modo de seleção de grifo."""
        self._hl_mode = on
        self.view.set_hl_mode(on)
        self.right_panel.set_select_mode(on)

    def _on_selection(self, x0: float, y0: float, x1: float, y1: float):
        """O usuário soltou um retângulo no modo seleção (pontos PDF)."""
        if not self.renderer or not self.current_path:
            return
        highlights.add(
            book_path=self.current_path,
            page=self.current_page + 1,
            x0=x0, y0=y0, x1=x1, y1=y1,
            color=self._highlight_color_hex, opacity=0.35,
        )
        highlights.save_to_disk()
        self._refresh_saved_highlights()

    def _on_right_click(self, pdf_x: float, pdf_y: float):
        """Remove o grifo sob o cursor (botão direito)."""
        if not self.renderer or not self.current_path:
            return
        for h in reversed(highlights.get(self.current_path, self.current_page + 1)):
            # Margem de 2 pontos para facilitar o clique.
            if h["x0"] - 2 <= pdf_x <= h["x1"] + 2 and h["y0"] - 2 <= pdf_y <= h["y1"] + 2:
                highlights.delete(self.current_path, self.current_page + 1, h["id"])
                self._refresh_saved_highlights()
                return

    def _refresh_saved_highlights(self):
        """Repinta na página os grifos permanentes da página atual."""
        if not self.current_path:
            self.view.set_saved_highlights([])
            return
        self.view.set_saved_highlights([
            {**h,
             "color": h.get("color", DEFAULT_HIGHLIGHT_COLOR),
             "opacity": h.get("opacity", 0.35)}
            for h in highlights.get(self.current_path, self.current_page + 1)
        ])

    # ──────────────────────────────────────────────────────────────
    # Grifo da leitura (efêmero) — acompanha a voz
    # ──────────────────────────────────────────────────────────────

    def _precompute_word_bboxes(
        self,
        timings: list[dict],
        page: int,
    ) -> list[tuple[float, float, list[dict]]]:
        """
        Retângulo de cada palavra que o TTS vai falar nesta página.

        O casamento em si é lógica pura e mora em core/word_sync.py; aqui
        fica só o cursor de posição dentro da página, que faz cada trecho
        continuar de onde o anterior parou. Roda na thread do loop de
        leitura — só lê o renderer (thread-safe) e devolve dados.
        """
        if not self.renderer or not timings:
            return []
        try:
            page_words = self.renderer.word_rects(page)
        except Exception as e:
            log.debug("word_rects falhou na página %d (ignorado): %s", page, e)
            return []

        if getattr(self, "_word_cursor_page", None) != page:
            self._word_cursor_page = page
            self._word_cursor = 0

        result, self._word_cursor = word_bboxes(page_words, timings, self._word_cursor)
        return result

    def _highlight_chunk_from_words(
        self, word_bboxes: list[tuple[float, float, list[dict]]]
    ) -> bool:
        """
        Pinta o trecho inteiro que está prestes a ser lido — o "fundo" sobre
        o qual a palavra corrente se destaca. Usa os retângulos já
        calculados (custo ~0), juntando as palavras de cada linha num só
        retângulo. Retorna False se não houver nenhum, para quem chama
        cair no caminho de busca por texto.
        """
        rects = [r for _, _, rs in word_bboxes for r in rs]
        if not rects:
            return False
        self._ephemeral_highlights = [
            {**r, "color": C["info"], "opacity": CHUNK_HIGHLIGHT_OPACITY}
            for r in merge_rects_by_line(rects)
        ]
        self._word_highlights = []
        self._eph_y_cursor = max(r["y1"] for r in rects)
        if self._alive:
            self.sig_follow.emit()
        return True

    def _highlight_ephemeral(self):
        """
        Fallback usado em seek/prev/next (sem timings de áudio): acha o
        trecho na página por busca de texto. Roda na thread do loop de
        leitura; só escreve listas Python e avisa a UI por sinal.
        """
        if not self.renderer or not self._current_text:
            return

        self._ephemeral_highlights = []
        self._word_highlights = []
        cursor = getattr(self, "_eph_y_cursor", 0.0)

        try:
            group = self.renderer.search_text(self.current_page, self._current_text)
        except Exception:
            group = []

        if not group:
            for line in (ln for ln in self._current_text.split("\n") if len(ln.strip()) > 5):
                try:
                    group.extend(self.renderer.search_text(self.current_page, line))
                except Exception:
                    continue

        if not group:
            if self._alive:
                self.sig_follow.emit()
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
        self._ephemeral_highlights = [
            {**m, "color": C["info"], "opacity": 0.35} for m in best_group
        ]
        if self._alive:
            self.sig_follow.emit()

    def _highlight_manual(self):
        """Salva o trecho lido agora como grifo permanente."""
        if not self.renderer or not self.current_path or not self._ephemeral_highlights:
            return
        for h in self._ephemeral_highlights:
            highlights.add(
                book_path=self.current_path,
                page=self.current_page + 1,
                x0=h["x0"], y0=h["y0"], x1=h["x1"], y1=h["y1"],
                color=self._highlight_color_hex,
                opacity=0.35,
            )
        highlights.save_to_disk()
        self._refresh_saved_highlights()

    def _clear_page_highlights(self):
        """Limpa todos os grifos da página atual."""
        if not self.current_path:
            return
        highlights.clear_page(self.current_path, self.current_page + 1)
        self._refresh_saved_highlights()

    def _export_highlights(self):
        """Exporta todos os grifos do livro atual para um arquivo Markdown."""
        if not self.current_path or not self.renderer:
            QMessageBox.information(self, "Exportar grifos", "Nenhum livro aberto.")
            return

        all_h = highlights.all_for_book(self.current_path)
        if not all_h:
            QMessageBox.information(self, "Exportar grifos", "Nenhum grifo salvo neste livro.")
            return

        book_name = os.path.splitext(os.path.basename(self.current_path))[0]
        dest, _filter = QFileDialog.getSaveFileName(
            self, "Salvar grifos como…", f"grifos_{book_name}.md",
            "Markdown (*.md);;Texto (*.txt);;Todos (*.*)")
        if not dest:
            return

        lines = [f"# Grifos — {book_name}", ""]
        for page_str, page_highlights in sorted(all_h.items(), key=lambda x: int(x[0])):
            page_num = int(page_str)
            lines.append(f"## Página {page_num}")
            lines.append("")
            for h in page_highlights:
                try:
                    text = self.renderer.text_in_rect(
                        page_num - 1, h["x0"], h["y0"], h["x1"], h["y1"])
                except Exception:
                    text = ""
                text = text or "(texto não extraível)"
                lines.append(f"> {text}")
                lines.append(f"<!-- cor: {h.get('color', DEFAULT_HIGHLIGHT_COLOR)} -->")
                lines.append("")

        try:
            Path(dest).write_text("\n".join(lines), encoding="utf-8")
            QMessageBox.information(
                self, "Exportar grifos", f"Grifos exportados com sucesso!\n{dest}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível salvar:\n{e}")
