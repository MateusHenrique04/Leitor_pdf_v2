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
        Busca texto na página n (0-indexed) e retorna coordenadas em pontos do PDF.

        Estratégia em duas etapas para evitar que palavras curtas (artigos,
        preposições) grifem todas as ocorrências no texto:
          1. Tenta encontrar a frase/linha completa — é o mais preciso.
          2. Se não achar (PDF com colunas, hifenização), busca palavras
             individuais com comprimento > 3 chars usando word boundary,
             ignorando palavras com ≤ 2 chars completamente.
        """
        if not text.strip() or n < 0 or n >= self.total:
            return []
        page = self._doc[n]

        # Etapa 1: frase completa
        matches = page.search_for(text.strip())
        if matches:
            return [{"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1} for r in matches]

        # Etapa 2: palavras significativas com word boundary (> 3 chars)
        words_in_page = page.get_text("words")   # (x0,y0,x1,y1,word,block,line,word_n)
        significant   = [w for w in text.split() if len(w) > 3]
        if not significant:
            return []

        results = []
        for target in significant:
            pattern = re.compile(
                r"(?<![A-Za-zÀ-ÿ0-9])" + re.escape(target) + r"(?![A-Za-zÀ-ÿ0-9])",
                re.IGNORECASE,
            )
            for (x0, y0, x1, y1, word, *_) in words_in_page:
                clean = re.sub(r"[^\w\-'À-ÿ]", "", word)
                if pattern.fullmatch(clean):
                    results.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1})
        return results

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

    def close(self):
        self._doc.close()
        self._cache.clear()