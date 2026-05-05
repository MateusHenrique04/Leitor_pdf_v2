"""
data/history.py — histórico de sessões de leitura.
Cache em memória evita re-leitura do disco a cada sessão.
"""
import json
from config import HISTORY_FILE

_cache: list | None = None


def _load() -> list:
    global _cache
    if _cache is not None:
        return _cache
    if HISTORY_FILE.exists():
        try:
            _cache = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            return _cache
        except Exception:
            pass
    _cache = []
    return _cache


def _save(data: list):
    global _cache
    _cache = data
    HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_session(start: str, duration: str, seconds: float, book: str):
    d = _load()
    d.append({"start": start, "duration": duration,
               "seconds": seconds, "book": book})
    _save(d)


def all_sessions() -> list:
    return _load()