"""
core/pdf_renderer.py
--------------------
Responsabilidade única: abrir um PDF e fornecer:
  - render_page(n)  → imagem PIL da página n (para exibir)
  - text_for_page(n) → texto limpo da página n (para TTS)
  - total_pages     → int

Usa PyMuPDF (fitz). Para trocar a biblioteca de renderização, edite só este arquivo.
"""

import re
import unicodedata
from collections import defaultdict
import fitz          # PyMuPDF
from PIL import Image
import io

from config import PDF_RENDER_DPI


class PDFRenderer:
    def __init__(self, filepath: str):
        self._doc   = fitz.open(filepath)
        self.total  = len(self._doc)
        self._cache: dict[int, Image.Image] = {}   # cache de páginas já renderizadas

        # Detecta cabeçalhos/rodapés repetidos (≥30% das páginas) para remover do TTS
        hdr: dict[str, int] = {}
        ftr: dict[str, int] = {}
        for page in self._doc:
            lines = [l.strip() for l in page.get_text().split("\n") if l.strip()]
            if lines:
                hdr[lines[0]]  = hdr.get(lines[0], 0) + 1
            if len(lines) > 1:
                ftr[lines[-1]] = ftr.get(lines[-1], 0) + 1

        thr = max(3, int(self.total * 0.30))
        self._skip = {k for k, v in {**hdr, **ftr}.items() if v >= thr}

    def render_page(self, n: int) -> Image.Image:
        """Renderiza a página n (0-indexed) e retorna uma imagem PIL."""
        if n in self._cache:
            return self._cache[n]
        mat  = fitz.Matrix(PDF_RENDER_DPI / 72, PDF_RENDER_DPI / 72)
        pix  = self._doc[n].get_pixmap(matrix=mat, alpha=False)
        img  = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        # Limita cache a 10 páginas para não consumir muita RAM
        if len(self._cache) >= 10:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[n] = img
        return img

    def text_for_page(self, n: int) -> str:
        """Retorna o texto limpo da página n (0-indexed) para o TTS."""
        raw   = unicodedata.normalize("NFKC", self._doc[n].get_text())
        lines = [l for l in raw.split("\n") if l.strip() not in self._skip]
        text  = "\n".join(lines)
        # Corrige hifenização de fim de linha
        text  = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
        # Remove números de página isolados
        text  = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
        # Normaliza espaços
        text  = re.sub(r"[ \t]+", " ", text)
        text  = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def search_text(self, n: int, text: str) -> list[dict]:
        """
        Busca o trecho `text` na página n e retorna bboxes em pontos PDF.

        Estratégia em 4 etapas, da mais precisa para a mais tolerante:

        1. search_for() com o texto completo — retorna múltiplos retângulos
           quando a frase atravessa linhas (quads=True).

        2. Âncora pelas primeiras N palavras em sequência (N = 5..2).
           Encontra onde a frase começa e coleta TODAS as linhas até cobrir
           o número de palavras do chunk (sem limite arbitrário de n_lines).

        3. Âncora pelo FINAL da frase (últimas 3 palavras) — captura casos
           onde o início é genérico mas o fim é único.

        4. Último recurso: palavras únicas na página → retorna linhas inteiras.
           Só ativa para chunks com ≥ 6 palavras significativas.
        """
        if not text.strip() or n < 0 or n >= self.total:
            return []
        page = self._doc[n]

        # ── Etapa 1: frase completa via search_for ───────────────────
        # Tenta com quads=True para obter múltiplos retângulos em frases multi-linha
        try:
            quads = page.search_for(text.strip(), quads=True)
            if quads:
                rects = []
                for q in quads:
                    r = q.rect
                    rects.append({"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1})
                return rects
        except Exception:
            pass

        # Fallback search_for sem quads
        matches = page.search_for(text.strip())
        if matches:
            return [{"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1} for r in matches]

        # ── Monta estrutura de palavras por linha ────────────────────
        # words_in_page: lista de (x0,y0,x1,y1,word,block_n,line_n,word_n)
        words_in_page = page.get_text("words")
        if not words_in_page:
            return []

        # Ordena por posição vertical e depois horizontal (garante ordem de leitura)
        words_in_page = sorted(words_in_page, key=lambda w: (round(w[1], 1), w[0]))

        # Recalcula chaves de linha baseadas em y0 agrupado (mais estável que block/line)
        # Agrupa palavras cuja y0 difere em menos de 4pt como mesma linha
        line_map: dict[tuple, list] = defaultdict(list)
        # Primeiro passa: usa (block_n, line_n) como chave canônica
        for w in words_in_page:
            key = (int(w[5]), int(w[6]))
            line_map[key].append(w)

        # Ordena as chaves de linha por posição y (topo da linha)
        sorted_keys = sorted(line_map.keys(),
                             key=lambda k: min(w[1] for w in line_map[k]))

        def _line_bbox(key) -> dict:
            ws = line_map[key]
            return {
                "x0": min(w[0] for w in ws),
                "y0": min(w[1] for w in ws),
                "x1": max(w[2] for w in ws),
                "y1": max(w[3] for w in ws),
            }

        def _normalize(s: str) -> str:
            nfkc = unicodedata.normalize("NFKC", s).lower()
            return re.sub(r"[^\w À-ÿ]", "", nfkc).strip()

        chunk_words = _normalize(text).split()
        if not chunk_words:
            return []

        # Lista plana de palavras da página com suas chaves de linha
        page_word_list = [(_normalize(w[4]), (int(w[5]), int(w[6]))) for w in words_in_page]
        page_words_only = [pw for pw, _ in page_word_list]

        def _collect_lines_from_anchor(anchor_idx: int, n_chunk_words: int) -> list[dict]:
            """
            A partir da palavra em anchor_idx na página, coleta linhas até
            ter coberto n_chunk_words palavras.  Retorna lista de bboxes.
            """
            # Descobre qual linha contém a palavra âncora
            anchor_key = page_word_list[anchor_idx][1]
            try:
                key_pos = sorted_keys.index(anchor_key)
            except ValueError:
                return []

            words_accumulated = 0
            result_keys = []

            for ki in range(key_pos, len(sorted_keys)):
                key = sorted_keys[ki]
                result_keys.append(key)
                words_accumulated += len(line_map[key])
                # Para quando acumulamos palavras suficientes
                # (+2 de margem para linhas que terminam com pontuação)
                if words_accumulated >= n_chunk_words - 2:
                    break

            return [_line_bbox(k) for k in result_keys]

        # ── Etapa 2: âncora pelo INÍCIO da frase ────────────────────
        for anchor_len in (5, 4, 3, 2):
            if len(chunk_words) < anchor_len:
                continue
            anchor = chunk_words[:anchor_len]

            for idx in range(len(page_words_only) - anchor_len + 1):
                if page_words_only[idx: idx + anchor_len] == anchor:
                    result = _collect_lines_from_anchor(idx, len(chunk_words))
                    if result:
                        return result

        # ── Etapa 3: âncora pelo FINAL da frase ─────────────────────
        anchor_len_end = 3
        if len(chunk_words) >= anchor_len_end:
            anchor_end = chunk_words[-anchor_len_end:]
            for idx in range(len(page_words_only) - anchor_len_end + 1):
                if page_words_only[idx: idx + anchor_len_end] == anchor_end:
                    # Encontrou o fim — volta para encontrar o início estimado
                    end_key = page_word_list[idx][1]
                    try:
                        end_pos = sorted_keys.index(end_key)
                    except ValueError:
                        continue

                    # Estima quantas linhas para trás precisamos ir
                    words_per_line = max(1, len(line_map[end_key]))
                    lines_needed = max(1, -(-len(chunk_words) // words_per_line))
                    start_pos = max(0, end_pos - lines_needed)

                    result = [_line_bbox(k) for k in sorted_keys[start_pos: end_pos + 1]]
                    if result:
                        return result

        # ── Etapa 4: fallback — palavras únicas → linhas inteiras ────
        significant = [w for w in chunk_words if len(w) > 4]
        if len(significant) < 6:
            return []

        # Conta ocorrências para usar só palavras inequívocas
        word_counts: dict[str, int] = {}
        for pw in page_words_only:
            word_counts[pw] = word_counts.get(pw, 0) + 1

        unique_sig = [w for w in significant if word_counts.get(w, 0) == 1]
        if not unique_sig:
            unique_sig = significant[:3]

        hit_lines: set[tuple] = set()
        for target in unique_sig:
            for pw, key in page_word_list:
                if pw == target:
                    hit_lines.add(key)

        if not hit_lines:
            return []

        # Retorna as linhas em ordem de leitura
        ordered = [k for k in sorted_keys if k in hit_lines]
        return [_line_bbox(k) for k in ordered]

    def word_at(self, n: int, pdf_x: float, pdf_y: float) -> str | None:
        """
        Retorna a palavra que contém o ponto (pdf_x, pdf_y) na página n (0-indexed).
        Usa get_text('words') do PyMuPDF — cada item é (x0, y0, x1, y1, word, ...).
        Retorna None se nenhuma palavra for encontrada nessa posição.
        """
        if n < 0 or n >= self.total:
            return None
        page = self._doc[n]
        for w in page.get_text("words"):
            x0, y0, x1, y1, word = w[0], w[1], w[2], w[3], w[4]
            if x0 <= pdf_x <= x1 and y0 <= pdf_y <= y1:
                import re
                return re.sub(r"[^\w\-']", "", word).strip() or None
        return None

    def prefetch(self, n: int) -> None:
        """
        Pré-renderiza as páginas adjacentes a n em threads daemon.
        Chamado após renderizar a página atual para eliminar atraso na troca.
        """
        import threading
        for adj in (n - 1, n + 1):
            if 0 <= adj < self.total and adj not in self._cache:
                threading.Thread(
                    target=self.render_page, args=(adj,), daemon=True
                ).start()

    def get_toc(self) -> list[tuple[int, str, int]]:
        """
        Retorna o sumário do PDF como lista de (level, title, page).
        level: 1=capítulo, 2=seção, 3=subseção etc.
        Retorna [] se o PDF não tiver TOC.
        """
        try:
            return [(item[0], item[1], item[2]) for item in self._doc.get_toc()]
        except Exception:
            return []

    def close(self):
        self._doc.close()
        self._cache.clear()