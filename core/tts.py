"""
core/tts.py — gera áudio via edge-tts.
Para trocar o motor de TTS, edite só este arquivo.
"""
import asyncio
import edge_tts


async def speak(text: str, voice: str, speed_pct: int) -> bytes:
    """
    Gera e retorna bytes MP3 do texto dado.
    speed_pct: -50 a +100 (% relativo à velocidade normal)
    """
    text = text.strip()
    if not text:
        return b""
    rate = f"{speed_pct:+d}%"
    comm = edge_tts.Communicate(text, voice, rate=rate)
    buf  = b""
    async for msg in comm.stream():
        if msg["type"] == "audio":
            buf += msg["data"]
    return buf
