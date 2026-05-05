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

        Estratégia em 3 etapas, da mais precisa para a mais tolerante:

        1. search_for() com o texto completo — funciona quando o PDF não
           tem quebras de linha no meio da frase.

        2. Âncora pelas primeiras N palavras únicas da frase (N = 4..2).
           Acha o bloco de texto onde a frase começa e retorna o bbox de
           todas as linhas desse bloco que contenham palavras do chunk.
           Evita falsos positivos porque exige uma sequência, não palavras
           soltas.

        3. Só como último recurso, e apenas para frases com ≥ 8 palavras
           significativas: retorna o bbox da linha inteira de cada palavra
           significativa encontrada (em vez de apenas a bbox da palavra).
           Isso produz um grifo de linha inteira em vez de palavras esparsas.
        """
        if not text.strip() or n < 0 or n >= self.total:
            return []
        page = self._doc[n]

        # ── Etapa 1: frase completa ──────────────────────────────────
        matches = page.search_for(text.strip())
        if matches:
            return [{"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1} for r in matches]

        # Coleta palavras da página agrupadas por linha (block, line)
        # words_in_page: lista de (x0,y0,x1,y1,word,block_n,line_n,word_n)
        words_in_page = page.get_text("words")
        if not words_in_page:
            return []

        # Agrupa palavras por (block, line) para poder devolver linhas inteiras
        line_map: dict[tuple, list] = defaultdict(list)
        for w in words_in_page:
            key = (int(w[5]), int(w[6]))   # (block_n, line_n)
            line_map[key].append(w)

        def _line_bbox(key) -> dict:
            ws = line_map[key]
            return {
                "x0": min(w[0] for w in ws),
                "y0": min(w[1] for w in ws),
                "x1": max(w[2] for w in ws),
                "y1": max(w[3] for w in ws),
            }

        def _normalize(s: str) -> str:
            return re.sub(r"[^\w À-ÿ]", "", unicodedata.normalize("NFKC", s).lower()).strip()

        chunk_words = _normalize(text).split()
        if not chunk_words:
            return []

        # ── Etapa 2: âncora pelas primeiras N palavras em sequência ──
        for anchor_len in (4, 3, 2):
            if len(chunk_words) < anchor_len:
                continue
            anchor = chunk_words[:anchor_len]

            # Percorre as palavras da página procurando a sequência âncora
            page_word_list = [(w, (int(w[5]), int(w[6]))) for w in words_in_page]
            for idx in range(len(page_word_list) - anchor_len + 1):
                seq = [_normalize(page_word_list[idx + k][0][4]) for k in range(anchor_len)]
                if seq == anchor:
                    # Encontrou a âncora — coleta as linhas que cobrem o chunk
                    # Estima quantas linhas o chunk ocupa pelo nº de palavras
                    start_key = page_word_list[idx][1]
                    all_keys  = list(line_map.keys())
                    try:
                        start_pos = all_keys.index(start_key)
                    except ValueError:
                        break

                    # Número estimado de linhas = ceil(palavras_chunk / palavras_por_linha)
                    words_per_line = max(1, len(line_map[start_key]))
                    n_lines = max(1, -(-len(chunk_words) // words_per_line))  # ceil division
                    n_lines = min(n_lines + 1, len(all_keys) - start_pos)     # +1 margem

                    result = []
                    for k in range(n_lines):
                        key = all_keys[start_pos + k]
                        result.append(_line_bbox(key))
                    return result

        # ── Etapa 3: fallback — grifo de linha inteira por palavra única ──
        significant = [w for w in chunk_words if len(w) > 4]
        if len(significant) < 4:   # chunk muito curto: não grifa para evitar spam
            return []

        # Conta ocorrências de cada palavra na página para descartar ambíguas
        page_words_norm = [_normalize(w[4]) for w in words_in_page]
        word_counts = {}
        for pw in page_words_norm:
            word_counts[pw] = word_counts.get(pw, 0) + 1

        # Usa apenas palavras que aparecem UMA vez na página (inequívocas)
        unique_sig = [w for w in significant if word_counts.get(w, 0) == 1]
        if not unique_sig:
            unique_sig = significant[:2]   # aceita as duas primeiras se todas são ambíguas

        hit_lines: set[tuple] = set()
        for target in unique_sig:
            for w, key in page_word_list:
                if _normalize(w[4]) == target:
                    hit_lines.add(key)

        if not hit_lines:
            return []

        # Retorna bbox de linha inteira, não de palavra isolada
        return [_line_bbox(k) for k in sorted(hit_lines)]

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