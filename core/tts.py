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
    comm = edge_tts.Communicate(text, voice, rate=rate)

    buf      = b""
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

    return buf, timings
