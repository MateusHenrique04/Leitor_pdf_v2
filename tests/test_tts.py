"""
Testes de core/tts.py sem tocar a rede.

O foco é o contrato que o loop de leitura usa: onde a fala termina
dentro do MP3. Esperar o arquivo inteiro acabar somava ~0,9 s de
silêncio a cada trecho lido (ver core/tts.SPEECH_TAIL_MARGIN).
"""
import inspect

import edge_tts

from core.tts import SPEECH_TAIL_MARGIN, speak, speech_end


def test_speech_end_sem_timings_e_desconhecido():
    """Sem word-timings não dá para saber onde a fala acaba — quem chama
    precisa cair no comportamento de esperar o MP3 inteiro."""
    assert speech_end([]) is None


def test_speech_end_usa_fim_da_ultima_palavra_mais_margem():
    timings = [
        {"word": "primeira", "start": 0.1, "end": 0.6},
        {"word": "ultima", "start": 0.7, "end": 1.25},
    ]
    assert speech_end(timings) == 1.25 + SPEECH_TAIL_MARGIN


def test_speech_end_mantem_uma_margem_positiva():
    """A margem existe para a frase não terminar cortada."""
    assert SPEECH_TAIL_MARGIN > 0


def test_speak_pede_word_boundary_ao_edge_tts():
    """A partir do edge-tts 7 o padrão é SentenceBoundary. Como speak()
    só coleta mensagens WordBoundary, sem pedir explicitamente a lista de
    timings volta sempre vazia e o grifo por palavra morre em silêncio."""
    padrao = inspect.signature(edge_tts.Communicate.__init__).parameters["boundary"].default
    assert padrao == "SentenceBoundary", (
        "o padrão do edge-tts mudou; reveja a necessidade do argumento em speak()"
    )
    assert 'boundary="WordBoundary"' in inspect.getsource(speak)
