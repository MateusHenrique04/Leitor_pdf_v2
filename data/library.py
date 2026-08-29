"""
data/library.py — lê e escreve library.json.
Toda persistência de livros passa por aqui.
Cache em memória evita I/O redundante a cada operação.
"""
import logging

from config import LIBRARY_FILE
from data._jsonio import load_json, save_json

log = logging.getLogger(__name__)

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = load_json(LIBRARY_FILE, {})
    return _cache


def _save(data: dict):
    global _cache
    _cache = data
    if not save_json(LIBRARY_FILE, data):
        log.error("Biblioteca não pôde ser salva — alterações desta sessão podem ser perdidas.")


def all_books() -> dict:
    return _load()


def add(path: str):
    d = _load()
    d.setdefault(path, {"last_page": 0})
    _save(d)


def remove(path: str):
    d = _load()
    d.pop(path, None)
    _save(d)


def get(path: str) -> dict:
    return _load().get(path, {})


def save_position(path: str, page: int, chunk_idx: int = 0):
    d = _load()
    if path in d:
        d[path]["last_page"] = page
        d[path]["last_chunk_idx"] = chunk_idx
        _save(d)


def save_total(path: str, total: int):
    d = _load()
    if path in d:
        d[path]["total_pages"] = total
        _save(d)


def mark_finished(path: str, finished: bool):
    d = _load()
    if path in d:
        d[path]["finished"] = finished
        _save(d)


def is_finished(path: str) -> bool:
    return _load().get(path, {}).get("finished", False)
