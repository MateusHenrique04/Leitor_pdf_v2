"""
core/tts.py — gera áudio via edge-tts.
Para trocar o motor de TTS, edite só este arquivo.
"""
import asyncio
import edge_tts


async def speak(text: str, voice: str, speed_pct: int) -> tuple[bytes, list[dict]]:
    """
    Gera e retorna (bytes MP3, lista de word-timings).

    word-timings: [{"word": str, "start": float, "end": float}, ...]
    start/end em segundos — usados pelo autoscroll para sincronizar o pan.

    speed_pct: -50 a +100 (% relativo à velocidade normal)
    """
    text = text.strip()
    if not text:
        return b"", []

    rate = f"{speed_pct:+d}%"
    comm = edge_tts.Communicate(text, voice, rate=rate)

    buf      = b""
    timings  = []          # [{word, start, end}]
    last_end = 0.0

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
                last_end = end_s
    except edge_tts.exceptions.NoAudioReceived:
        # Sem internet ou voz indisponível — retorna vazio sem derrubar o app
        return b"", []
    except Exception:
        # Qualquer outro erro (rede, timeout, caracteres inválidos) — ignora o chunk
        return b"", []

    return buf, timings