"""
data/library.py — lê e escreve library.json.
Toda persistência de livros passa por aqui.
Cache em memória evita I/O redundante a cada operação.
"""
import json
from config import LIBRARY_FILE

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if LIBRARY_FILE.exists():
        try:
            _cache = json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
            return _cache
        except Exception:
            pass
    _cache = {}
    return _cache


def _save(data: dict):
    global _cache
    _cache = data
    LIBRARY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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