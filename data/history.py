"""
data/history.py — histórico de sessões de leitura.
Cache em memória evita re-leitura do disco a cada sessão.
"""
import logging

from config import HISTORY_FILE
from data._jsonio import load_json, save_json

log = logging.getLogger(__name__)

_cache: list | None = None


def _load() -> list:
    global _cache
    if _cache is None:
        _cache = load_json(HISTORY_FILE, [])
    return _cache


def _save(data: list):
    global _cache
    _cache = data
    if not save_json(HISTORY_FILE, data):
        log.error("Histórico não pôde ser salvo — a sessão atual pode ser perdida.")


def add_session(start: str, duration: str, seconds: float, book: str):
    d = _load()
    d.append({"start": start, "duration": duration,
               "seconds": seconds, "book": book})
    _save(d)


def all_sessions() -> list:
    return _load()
