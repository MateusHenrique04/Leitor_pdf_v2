"""
core/duration.py — quanto tempo de áudio tem um livro e onde estamos nele.

O áudio nunca existe inteiro: cada trecho é sintetizado sob demanda
enquanto a leitura avança. Não há, portanto, nenhum arquivo cuja duração
se possa medir — a linha do tempo do livro precisa ser *estimada* a
partir do texto.

A estimativa usa uma constante de caracteres por segundo. Isso é menos
frágil do que parece:

  - A **posição na barra** é uma razão (caracteres lidos ÷ caracteres
    totais). A constante aparece no numerador e no denominador e se
    cancela: a barra fica certa mesmo que a constante esteja errada.
  - Só os **rótulos de horas** dependem do valor absoluto. Por isso a
    constante é calibrada durante a leitura, com o tempo real gasto em
    cada trecho (`observe`), e os rótulos convergem para a voz e a
    velocidade que o usuário escolheu.

A constante inicial (17 c/s) foi medida em texto de livro de verdade, com
o tempo de relógio que cada trecho consome de fato — incluindo o silêncio
que o MP3 traz no início e a pausa entre trechos. Nos 14 trechos medidos a
dispersão foi pequena: 15,3 a 19,0 c/s, mediana 17,0.
"""
import statistics
from bisect import bisect_right
from collections import deque

# Caracteres por segundo a 1× antes de qualquer calibração.
BASE_CHARS_PER_SECOND = 17.0

# A calibração usa a MEDIANA das medições recentes, não uma média móvel.
# Com média, uma única medição estranha (já vista: um trecho cujo TTS
# devolveu os limites de palavra pela metade, dando ~64 c/s) empurrava o
# total em horas de uma vez — o rótulo chegou a oscilar entre 8h e 12h no
# mesmo minuto de leitura. Mediana ignora o ponto fora da curva.
_CALIBRATION_WINDOW = 25     # medições mantidas
_CALIBRATION_MINIMUM = 5     # antes disso, usa a constante

# Medições fora desta faixa em relação à constante padrão são descartadas
# antes mesmo de entrar na janela. Cobre com folga a variação real entre
# vozes e idiomas (15–21 c/s) e corta o que só pode ser defeito.
_PLAUSIBLE_RANGE = (0.6, 1.6)


def format_hms(seconds: float) -> str:
    """Formata segundos como H:MM:SS (ou MM:SS quando não chega a uma hora)."""
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class BookTimeline:
    """
    Mapa entre "instante do audiolivro" e "posição no livro".

    `page_lengths` é a quantidade de texto de cada página, na ordem das
    páginas (ver PDFRenderer.page_lengths).
    """

    def __init__(
        self,
        page_lengths: list[int],
        speed_pct: int = 0,
        chars_per_second: float = BASE_CHARS_PER_SECOND,
    ):
        # Soma acumulada: _cum[i] = caracteres antes da página i.
        self._cum = [0]
        for n in page_lengths:
            self._cum.append(self._cum[-1] + max(0, n))
        self._lengths = [max(0, n) for n in page_lengths]
        self._default_cps = chars_per_second
        self._samples: deque[float] = deque(maxlen=_CALIBRATION_WINDOW)
        self.speed_pct = speed_pct

    # ── leitura ───────────────────────────────────────────────────

    @property
    def total_chars(self) -> int:
        return self._cum[-1]

    @property
    def base_chars_per_second(self) -> float:
        """Ritmo a 1×: a mediana das medições, ou a constante enquanto
        ainda não houver medições suficientes para ela ser confiável."""
        if len(self._samples) < _CALIBRATION_MINIMUM:
            return self._default_cps
        return statistics.median(self._samples)

    @property
    def chars_per_second(self) -> float:
        """Ritmo no ajuste de velocidade atual. `speed_pct` é o mesmo
        número que vai para o edge-tts: +100 significa o dobro da
        velocidade e, portanto, o dobro de caracteres por segundo."""
        return self.base_chars_per_second * (1 + self.speed_pct / 100)

    @property
    def total_seconds(self) -> float:
        return self.total_chars / self.chars_per_second if self.total_chars else 0.0

    def seconds_at(self, page: int, fraction_into_page: float = 0.0) -> float:
        """Instante em que a leitura chega a `fraction_into_page` da página."""
        if not self.total_chars:
            return 0.0
        page = max(0, min(page, len(self._lengths) - 1))
        fraction_into_page = max(0.0, min(1.0, fraction_into_page))
        chars = self._cum[page] + self._lengths[page] * fraction_into_page
        return chars / self.chars_per_second

    def fraction_at(self, page: int, fraction_into_page: float = 0.0) -> float:
        """O mesmo que seconds_at, mas como fração de 0 a 1 do livro —
        é isto que a barra desenha, e não depende da constante."""
        if not self.total_chars:
            return 0.0
        return min(1.0, self.seconds_at(page, fraction_into_page)
                   * self.chars_per_second / self.total_chars)

    def locate(self, seconds: float) -> tuple[int, float]:
        """Inverso de seconds_at: devolve (página, fração dentro da página)."""
        if not self.total_chars:
            return 0, 0.0
        alvo = max(0.0, seconds) * self.chars_per_second
        # A última página tem direito ao seu próprio índice, por isso o
        # teto é len(_lengths) - 1 e não o fim do acumulado.
        page = min(bisect_right(self._cum, alvo) - 1, len(self._lengths) - 1)
        page = max(0, page)
        restante = alvo - self._cum[page]
        tamanho = self._lengths[page]
        return page, min(1.0, restante / tamanho) if tamanho else 0.0

    # ── calibração ────────────────────────────────────────────────

    def observe(self, chars: int, seconds: float) -> bool:
        """
        Registra que `chars` caracteres levaram `seconds` de relógio para
        serem lidos, na velocidade atual. Devolve True se a medição foi
        aceita.

        Medições implausíveis são ignoradas — quase sempre significam que
        o usuário pausou no meio do trecho.
        """
        if chars <= 0 or seconds <= 0:
            return False
        medido = chars / seconds / (1 + self.speed_pct / 100)
        baixo, alto = _PLAUSIBLE_RANGE
        if not (self._default_cps * baixo <= medido <= self._default_cps * alto):
            return False
        self._samples.append(medido)
        return True

    def reset_calibration(self, chars_per_second: float | None = None):
        """Esquece o que foi medido — usado quando a voz muda, porque o
        ritmo aprendido era o da voz anterior. Sem argumento, volta à
        constante com que esta linha do tempo foi criada."""
        self._samples.clear()
        if chars_per_second is not None:
            self._default_cps = chars_per_second
