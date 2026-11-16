"""
core/pdf_renderer.py
--------------------
Responsabilidade única: abrir um PDF e fornecer:
  - render_page(n)  → imagem PIL da página n (para exibir)
  - text_for_page(n) → texto limpo da página n (para TTS)
  - word_rects(n)   → palavras da página com seus retângulos (grifo)
  - page_lengths    → quantidade de texto por página (duração estimada)
  - total_pages     → int

Usa PyMuPDF (fitz). Para trocar a biblioteca de renderização, edite só este arquivo.

Nota de performance: __init__ varre todas as páginas do documento para
detectar cabeçalhos/rodapés repetidos, o que pode ser perceptível em
livros grandes. Por isso a UI (ui/sidebar.py) cria PDFRenderer em uma
thread de background, nunca na thread principal.
"""

import logging
import re
import threading
import unicodedata
from collections import OrderedDict, defaultdict

import pymupdf as fitz  # PyMuPDF (novo nome do pacote; `fitz` está deprecated)
from PIL import Image

from config import PDF_RENDER_DPI

log = logging.getLogger(__name__)


def normalize_word(s: str) -> str:
    """Reduz uma palavra à forma usada para comparar o texto do PDF com o
    texto devolvido pelo TTS: minúscula, sem acentuação quebrada (NFKC) e
    sem pontuação. "«Mercados»," e "mercados" viram a mesma chave."""
    return re.sub(r"\W", "", unicodedata.normalize("NFKC", s).lower())


# Cabeçalhos e rodapés correntes são curtos ("www.editora.com — Página
# 17", "CAPÍTULO 3 · 57"). Uma linha de texto corrido num livro comum tem
# 70–95 caracteres. O limite separa os dois casos — ver _skip_key.
_MAX_RUNNING_HEAD_CHARS = 60


def _skip_key(line: str) -> str | None:
    """
    Chave usada para reconhecer a mesma linha de cabeçalho/rodapé em
    páginas diferentes, ou None se a linha não pode ser candidata.

    Dígitos viram "#" para que "Página 17" e "Página 18" contem como a
    mesma linha repetida — sem isso o rodapé numerado nunca batia o
    limiar de repetição e acabava lido em voz alta a cada página.

    O mascaramento é limitado a linhas curtas: uma linha de texto corrido
    que só mude um numeral ("...aumentou 3 por cento naquele ano.")
    também viraria uma "repetição" depois de mascarada, e conteúdo de
    verdade seria descartado. Linhas sem dígito nenhum não são afetadas
    pelo mascaramento e por isso não precisam do limite.
    """
    line = line.strip()
    if any(c.isdigit() for c in line) and len(line) > _MAX_RUNNING_HEAD_CHARS:
        return None
    return re.sub(r"\d+", "#", line)


class PDFOpenError(Exception):
    """Erro ao abrir um PDF: arquivo corrompido, protegido por senha,
    ou que não é um PDF válido. Mensagem já é segura para exibir ao usuário."""


class PDFRenderer:
    def __init__(self, filepath: str):
        # PyMuPDF não é thread-safe: a UI, as threads de prefetch, a busca
        # em todas as páginas e o loop de leitura acessam _doc e _cache
        # concorrentemente. Este lock protege todo acesso a ambos.
        self._lock = threading.RLock()
        self._closed = False
        try:
            self._doc = fitz.open(filepath)
        except Exception as e:
            log.error("Falha ao abrir PDF %r: %s", filepath, e)
            raise PDFOpenError(
                f"Não foi possível abrir o arquivo.\nDetalhes: {e}"
            ) from e

        if self._doc.needs_pass:
            self._doc.close()
            raise PDFOpenError("Este PDF está protegido por senha.")

        self.total  = len(self._doc)
        if self.total == 0:
            self._doc.close()
            raise PDFOpenError("O PDF não contém nenhuma página.")

        self._cache: OrderedDict[int, Image.Image] = OrderedDict()   # LRU de páginas renderizadas
        # LRU das palavras já extraídas por página (ver word_rects)
        self._words_cache: OrderedDict[int, list[tuple[str, dict]]] = OrderedDict()

        # Detecta cabeçalhos/rodapés repetidos (≥30% das páginas) para remover do TTS
        # (__init__ roda antes de qualquer outra thread conhecer este
        # renderer, então o lock aqui é só por consistência com os demais
        # métodos, não por uma race real.)
        #
        # A contagem usa a linha com os dígitos mascarados (_skip_key): a
        # maioria dos rodapés carrega o número da página — "Editora X —
        # Página 17", "17 | Capítulo 2" — e com a string literal como chave
        # cada página virava uma ocorrência única, nunca batendo o limiar.
        # O rodapé escapava e era lido em voz alta a cada virada de página.
        #
        # A mesma varredura já tem o texto de cada página na mão, então
        # aproveita para medir quanto texto cada uma tem (page_lengths):
        # é disso que sai a estimativa de duração do audiolivro, sem
        # custar uma segunda passagem pelo documento.
        hdr: dict[str, int] = {}
        ftr: dict[str, int] = {}
        self.page_lengths: list[int] = []
        with self._lock:
            for page in self._doc:
                lines = [ln.strip() for ln in page.get_text().split("\n") if ln.strip()]
                self.page_lengths.append(sum(len(ln) for ln in lines))
                if lines:
                    k = _skip_key(lines[0])
                    if k is not None:
                        hdr[k] = hdr.get(k, 0) + 1
                if len(lines) > 1:
                    k = _skip_key(lines[-1])
                    if k is not None:
                        ftr[k] = ftr.get(k, 0) + 1

        thr = max(3, int(self.total * 0.30))
        self._skip = {k for k, v in {**hdr, **ftr}.items() if v >= thr}

    def render_page(self, n: int) -> Image.Image:
        """Renderiza a página n (0-indexed) e retorna uma imagem PIL."""
        with self._lock:
            if self._closed:
                raise ValueError("PDFRenderer já foi fechado")
            if n in self._cache:
                self._cache.move_to_end(n)   # LRU: marca como usada recentemente
                return self._cache[n]
            mat  = fitz.Matrix(PDF_RENDER_DPI / 72, PDF_RENDER_DPI / 72)
            pix  = self._doc[n].get_pixmap(matrix=mat, alpha=False)
            width, height, samples = pix.width, pix.height, pix.samples
        # pix.samples já é uma cópia independente do documento — a conversão
        # para PIL.Image não precisa do lock.
        img = Image.frombytes("RGB", (width, height), samples)
        with self._lock:
            # Limita cache a 10 páginas para não consumir muita RAM (política LRU real)
            if len(self._cache) >= 10:
                self._cache.popitem(last=False)
            self._cache[n] = img
        return img

    def text_for_page(self, n: int) -> str:
        """
        Retorna o texto limpo da página n (0-indexed) para o TTS, com UM
        parágrafo por linha.

        Por que não usar `get_text()` direto: o PDF guarda cada linha
        *visual* separada por "\\n", então uma frase que ocupa três linhas
        na página volta como três linhas de texto. Como quem consome isto
        (core/text.py) também quebra em "\\n", cada linha virava uma
        requisição de TTS própria — uma frase era lida em três pedaços,
        com uma pausa (e entonação de fim de frase) no meio. Numa página
        típica isso dava ~49 trechos de ~9 palavras em vez de ~12 frases
        inteiras.

        `get_text("blocks")` entrega os blocos de texto que o PyMuPDF já
        agrupa — na prática, parágrafos e títulos. Juntando as linhas de
        dentro de cada bloco com espaço e separando os blocos com "\\n",
        o "\\n" passa a significar "fim de parágrafo" de verdade.
        """
        with self._lock:
            if self._closed:
                return ""
            blocks = self._doc[n].get_text("blocks")

        paragraphs = []
        for b in blocks:
            # b = (x0, y0, x1, y1, texto, bloco_n, tipo); tipo 1 = imagem
            if len(b) > 6 and b[6] != 0:
                continue
            raw = unicodedata.normalize("NFKC", str(b[4]))
            # Hifenização dentro do bloco: "hifeniza-\ncao" → "hifenizacao".
            # Feito antes de juntar as linhas, senão o hífen vira "- " solto.
            raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw)
            lines = []
            for ln in raw.split("\n"):
                ln = ln.strip()
                key = _skip_key(ln)
                if not ln or (key is not None and key in self._skip):
                    continue
                # Número de página isolado não é conteúdo para ler em voz alta
                if re.fullmatch(r"\d{1,4}", ln):
                    continue
                lines.append(ln)
            if lines:
                paragraphs.append(" ".join(lines))

        text = "\n".join(paragraphs)
        # Hifenização que caiu entre dois blocos (PDFs em que cada linha
        # vira um bloco próprio) — mesma regra, agora entre parágrafos.
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def word_rects(self, n: int) -> list[tuple[str, dict]]:
        """
        Palavras da página n em ordem de leitura, cada uma com o seu
        retângulo em pontos PDF: [(palavra_normalizada, {x0,y0,x1,y1}), ...]

        Serve ao grifo que acompanha a voz. A alternativa — chamar
        search_text() uma vez por palavra — custava ~9 ms por palavra e,
        por casar o trecho por âncoras, devolvia a LINHA inteira em vez do
        retângulo da palavra. Aqui uma única leitura da página resolve o
        trecho todo, e o retângulo é o da palavra de verdade.

        O resultado fica em cache porque o loop de leitura percorre vários
        trechos da mesma página em sequência.
        """
        if n < 0 or n >= self.total:
            return []
        with self._lock:
            if self._closed:
                return []
            cached = self._words_cache.get(n)
            if cached is not None:
                self._words_cache.move_to_end(n)
                return cached
            raw = self._doc[n].get_text("words")

        # (x0, y0, x1, y1, palavra, bloco, linha, n_palavra) — a ordem de
        # leitura é a de (bloco, linha, palavra), não a da lista crua.
        ordered = sorted(raw, key=lambda w: (int(w[5]), int(w[6]), int(w[7])))
        words = [
            (normalize_word(w[4]),
             {"x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3]})
            for w in ordered
            if normalize_word(w[4])
        ]

        with self._lock:
            if len(self._words_cache) >= 6:
                self._words_cache.popitem(last=False)
            self._words_cache[n] = words
        return words

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

        # Todo o acesso a self._doc/page fica dentro do lock; a partir daqui
        # (words_in_page já é uma lista Python independente) o casamento de
        # palavras roda sem segurar o lock, mesmo sendo a parte mais lenta.
        with self._lock:
            if self._closed:
                return []
            page = self._doc[n]

            # ── Etapa 1: frase completa via search_for ───────────────
            # Tenta com quads=True para múltiplos retângulos em frases multi-linha
            try:
                quads = page.search_for(text.strip(), quads=True)
                if quads:
                    rects = []
                    for q in quads:
                        r = q.rect
                        rects.append({"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1})
                    return rects
            except Exception as e:
                log.debug("search_for(quads=True) falhou na página %d: %s", n, e)

            # Fallback search_for sem quads
            try:
                matches = page.search_for(text.strip())
            except Exception as e:
                log.debug("search_for() falhou na página %d: %s", n, e)
                matches = []
            if matches:
                return [{"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1} for r in matches]

            # ── Monta estrutura de palavras por linha ─────────────────
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

    def text_in_rect(self, n: int, x0: float, y0: float, x1: float, y1: float) -> str:
        """Retorna o texto contido no retângulo (em pontos PDF) da página n.
        Usado para exportar o texto por baixo de um grifo sem a UI precisar
        acessar _doc nem o tipo Rect do PyMuPDF diretamente."""
        if n < 0 or n >= self.total:
            return ""
        with self._lock:
            if self._closed:
                return ""
            rect = fitz.Rect(x0, y0, x1, y1)
            text = self._doc[n].get_text("text", clip=rect)
        return " ".join(text.split())

    def word_at(self, n: int, pdf_x: float, pdf_y: float) -> str | None:
        """
        Retorna a palavra que contém o ponto (pdf_x, pdf_y) na página n (0-indexed).
        Usa get_text('words') do PyMuPDF — cada item é (x0, y0, x1, y1, word, ...).
        Retorna None se nenhuma palavra for encontrada nessa posição.
        """
        if n < 0 or n >= self.total:
            return None
        with self._lock:
            if self._closed:
                return None
            words = self._doc[n].get_text("words")
        for w in words:
            x0, y0, x1, y1, word = w[0], w[1], w[2], w[3], w[4]
            if x0 <= pdf_x <= x1 and y0 <= pdf_y <= y1:
                return re.sub(r"[^\w\-']", "", word).strip() or None
        return None

    def prefetch(self, n: int) -> None:
        """
        Pré-renderiza as páginas adjacentes a n em threads daemon.
        Chamado após renderizar a página atual para eliminar atraso na troca.
        """
        with self._lock:
            pending = [adj for adj in (n - 1, n + 1)
                       if 0 <= adj < self.total and adj not in self._cache]
        for adj in pending:
            threading.Thread(
                target=self._prefetch_one, args=(adj,), daemon=True
            ).start()

    def _prefetch_one(self, n: int) -> None:
        # Documento pode já ter sido fechado (troca de livro) entre o
        # agendamento do prefetch e esta thread rodar — falha silenciosa,
        # sem log de erro barulhento, pois é esperado nesse caso.
        try:
            self.render_page(n)
        except Exception as e:
            log.debug("Prefetch da página %d falhou (ignorado): %s", n, e)

    def get_toc(self) -> list[tuple[int, str, int]]:
        """
        Retorna o sumário do PDF como lista de (level, title, page).
        level: 1=capítulo, 2=seção, 3=subseção etc.
        Retorna [] se o PDF não tiver TOC.
        """
        try:
            with self._lock:
                if self._closed:
                    return []
                toc = self._doc.get_toc()
            return [(item[0], item[1], item[2]) for item in toc]
        except Exception as e:
            log.warning("Falha ao ler sumário do PDF: %s", e)
            return []

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._doc.close()
            self._cache.clear()
            self._words_cache.clear()
