"""
Testes de core/duration.py — a linha do tempo estimada do audiolivro.

O ponto central: a POSIÇÃO na barra é uma razão e não depende da
constante de caracteres por segundo; só os rótulos de hora dependem.
"""
import pytest

from core.duration import BASE_CHARS_PER_SECOND, BookTimeline, format_hms


def test_format_hms_omite_hora_quando_nao_passa_de_uma():
    assert format_hms(0) == "00:00"
    assert format_hms(59) == "00:59"
    assert format_hms(62) == "01:02"
    assert format_hms(3600) == "1:00:00"
    assert format_hms(67350) == "18:42:30"


def test_format_hms_nao_quebra_com_negativo():
    assert format_hms(-5) == "00:00"


def test_constante_padrao_esta_na_faixa_medida():
    """17 c/s saiu de medir trechos de livro de verdade (15,3–19,0 c/s).
    Se alguém mexer nela, é para ficar dentro do que foi observado."""
    assert 15.0 <= BASE_CHARS_PER_SECOND <= 21.0
    t = BookTimeline([1700])
    assert t.total_seconds == pytest.approx(1700 / BASE_CHARS_PER_SECOND)


def test_total_de_segundos_vem_do_texto_do_livro():
    t = BookTimeline([1900] * 10, chars_per_second=19.0)
    assert t.total_chars == 19000
    assert t.total_seconds == pytest.approx(1000.0)


def test_posicao_avanca_junto_com_a_pagina():
    t = BookTimeline([1900] * 10, chars_per_second=19.0)
    assert t.seconds_at(0) == pytest.approx(0.0)
    assert t.seconds_at(5) == pytest.approx(500.0)
    assert t.seconds_at(5, 0.5) == pytest.approx(550.0)


def test_locate_e_o_inverso_de_seconds_at():
    t = BookTimeline([1000, 3000, 2000, 500], chars_per_second=19.0)
    for pagina, fracao in [(0, 0.0), (1, 0.5), (2, 0.25), (3, 0.9)]:
        segundos = t.seconds_at(pagina, fracao)
        p, f = t.locate(segundos)
        assert p == pagina
        assert f == pytest.approx(fracao, abs=1e-6)


def test_locate_fora_dos_limites_fica_dentro_do_livro():
    t = BookTimeline([1000, 1000], chars_per_second=19.0)
    assert t.locate(-100) == (0, 0.0)
    pagina, _ = t.locate(10**6)
    assert pagina == 1


def test_a_fracao_da_barra_nao_depende_da_constante():
    """O motivo de a estimativa ser aceitável: a barra é
    (lido ÷ total), e a constante se cancela."""
    paginas = [1200, 3400, 900, 2600]
    lenta = BookTimeline(paginas, chars_per_second=12.0)
    rapida = BookTimeline(paginas, chars_per_second=25.0)
    for pagina in range(len(paginas)):
        assert lenta.fraction_at(pagina, 0.3) == pytest.approx(
            rapida.fraction_at(pagina, 0.3))


def test_velocidade_encurta_a_duracao_estimada():
    t = BookTimeline([1900] * 10, chars_per_second=19.0)
    normal = t.total_seconds
    t.speed_pct = 100          # 2× no edge-tts
    assert t.total_seconds == pytest.approx(normal / 2)
    t.speed_pct = -50          # 0,5×
    assert t.total_seconds == pytest.approx(normal * 2)


def test_calibracao_aproxima_a_estimativa_do_ritmo_real():
    t = BookTimeline([1000], chars_per_second=19.0)
    for _ in range(30):
        t.observe(chars=240, seconds=240 / 16.0)   # ritmo real: 16 c/s
    assert t.chars_per_second == pytest.approx(16.0, abs=0.3)


def test_calibracao_desconta_a_velocidade_escolhida():
    """A 2× o áudio sai com o dobro de caracteres por segundo; isso não
    pode ser confundido com uma voz naturalmente mais rápida."""
    t = BookTimeline([1000], speed_pct=100, chars_per_second=19.0)
    for _ in range(30):
        t.observe(chars=240, seconds=240 / 38.0)   # 38 c/s = 19 c/s a 2×
    t.speed_pct = 0
    assert t.chars_per_second == pytest.approx(19.0, abs=0.3)


def test_medicao_implausivel_e_descartada():
    """Uma pausa longa do usuário no meio do trecho faria a leitura
    parecer lentíssima — a medição é ignorada."""
    t = BookTimeline([1000], chars_per_second=19.0)
    assert t.observe(chars=240, seconds=600) is False
    assert t.observe(chars=240, seconds=0.01) is False
    assert t.chars_per_second == pytest.approx(19.0)
    assert t.observe(chars=0, seconds=10) is False
    assert t.observe(chars=240, seconds=0) is False


def test_reset_calibration_volta_ao_padrao():
    t = BookTimeline([1000], chars_per_second=19.0)
    for _ in range(30):
        t.observe(chars=240, seconds=240 / 12.0)
    assert t.chars_per_second < 15
    t.reset_calibration()
    assert t.chars_per_second == pytest.approx(19.0)


def test_uma_medicao_aberrante_nao_move_a_estimativa():
    """O motivo de a calibração usar mediana e não média: já aconteceu de
    um trecho vir com os limites de palavra pela metade, medindo ~64 c/s.
    Com média, esse ponto sozinho jogava o total estimado de 12h para 8h."""
    t = BookTimeline([1000], chars_per_second=17.0)
    for _ in range(10):
        t.observe(chars=240, seconds=240 / 17.0)
    antes = t.chars_per_second
    # a medição absurda nem é aceita
    assert t.observe(chars=240, seconds=240 / 64.0) is False
    assert t.chars_per_second == pytest.approx(antes)
    # e mesmo uma medição aceita, mas isolada e no limite, quase não move
    t.observe(chars=240, seconds=240 / 26.0)
    assert t.chars_per_second == pytest.approx(antes, abs=0.5)


def test_estimativa_so_muda_depois_de_medicoes_suficientes():
    """Até ter base estatística, o rótulo fica parado na constante — em
    vez de dançar a cada trecho lido."""
    t = BookTimeline([1000], chars_per_second=17.0)
    for _ in range(4):
        t.observe(chars=240, seconds=240 / 13.0)
        assert t.chars_per_second == pytest.approx(17.0)
    t.observe(chars=240, seconds=240 / 13.0)
    assert t.chars_per_second == pytest.approx(13.0, abs=0.2)


def test_livro_sem_texto_nao_divide_por_zero():
    """PDF só de imagens: a barra fica desligada, mas nada pode estourar."""
    t = BookTimeline([0, 0, 0])
    assert t.total_chars == 0
    assert t.total_seconds == 0.0
    assert t.seconds_at(1, 0.5) == 0.0
    assert t.fraction_at(2) == 0.0
    assert t.locate(50) == (0, 0.0)


def test_paginas_vazias_no_meio_do_livro():
    """Folhas de rosto e páginas em branco têm 0 caracteres e não podem
    capturar a posição nem fazer locate devolver uma fração inválida."""
    t = BookTimeline([1000, 0, 0, 1000], chars_per_second=10.0)
    assert t.seconds_at(3, 0.0) == pytest.approx(100.0)
    pagina, fracao = t.locate(150.0)
    assert pagina == 3
    assert fracao == pytest.approx(0.5)
