"""
core/tts.py — gera áudio via edge-tts.
Para trocar o motor de TTS, edite só este arquivo.
"""
import logging

import edge_tts

log = logging.getLogger(__name__)


async def speak(text: str, voice: str, speed_pct: int) -> tuple[bytes, list[dict]]:
    """
    Gera e retorna (bytes MP3, lista de word-timings).

    word-timings: [{"word": str, "start": float, "end": float}, ...]
    start/end em segundos — usados pelo autoscroll para sincronizar o pan.

    speed_pct: -50 a +100 (% relativo à velocidade normal)

    Em caso de falha (sem internet, voz indisponível, timeout), loga o
    motivo e retorna (b"", []) sem derrubar o app — quem chama (ui/controls.py)
    trata áudio vazio como "pular este trecho" e mostra um aviso ao usuário.
    """
    text = text.strip()
    if not text:
        return b"", []

    rate = f"{speed_pct:+d}%"
    # boundary="WordBoundary" é obrigatório: a partir do edge-tts 7 o
    # padrão passou a ser "SentenceBoundary", e como o laço abaixo só
    # reconhece mensagens WordBoundary a lista de timings vinha sempre
    # vazia. Sem timings o grifo acompanha o texto em blocos grandes em
    # vez de palavra por palavra, e o loop de leitura não sabe onde a
    # fala termina dentro do MP3 (ver ui/controls.py).
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")

    buf      = bytearray()
    timings  = []          # [{word, start, end}]

    try:
        async for msg in comm.stream():
            if msg["type"] == "audio":
                buf += msg["data"]
            elif msg["type"] == "WordBoundary":
                # offset e duration vêm em 100-ns ticks no edge-tts
                start_s = msg["offset"] / 10_000_000
                dur_s   = msg["duration"] / 10_000_000
                end_s   = start_s + dur_s
                timings.append({
                    "word":  msg["text"],
                    "start": start_s,
                    "end":   end_s,
                })
    except edge_tts.exceptions.NoAudioReceived:
        log.warning("TTS: nenhum áudio recebido (rede instável ou voz indisponível) "
                    "para o trecho: %r", text[:60])
        return b"", []
    except TimeoutError as e:
        log.warning("TTS: timeout ao gerar áudio: %s", e)
        return b"", []
    except Exception as e:
        log.error("TTS: erro ao gerar áudio (rede, voz ou serviço indisponível): %s", e)
        return b"", []

    if not buf:
        log.warning("TTS: áudio vazio retornado sem exceção para o trecho: %r", text[:60])

    return bytes(buf), timings


# Todo MP3 devolvido pelo edge-tts termina com ~0,9 s de silêncio depois
# da última palavra — medido igual em pt-BR, en-US e es-ES. Como cada
# trecho é um MP3 próprio, esperar esse silêncio acabar antes de tocar o
# próximo somava quase um segundo de pausa em CADA frase lida.
# SPEECH_TAIL_MARGIN é o quanto desse silêncio se mantém, para a frase
# não terminar abruptamente.
SPEECH_TAIL_MARGIN = 0.10


def speech_end(timings: list[dict]) -> float | None:
    """
    Instante (em segundos, desde o início do MP3) a partir do qual só há
    silêncio: fim da última palavra mais uma margem curta.

    Retorna None quando não há timings — aí não dá para saber onde a fala
    acaba e quem chama precisa esperar o MP3 inteiro.
    """
    if not timings:
        return None
    return timings[-1]["end"] + SPEECH_TAIL_MARGIN
