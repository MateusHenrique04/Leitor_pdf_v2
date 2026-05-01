"""
data/history.py — histórico de sessões de leitura.
"""
import json
from config import HISTORY_FILE


def _load() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(data: list):
    HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_session(start: str, duration: str, seconds: float, book: str):
    d = _load()
    d.append({"start": start, "duration": duration,
               "seconds": seconds, "book": book})
    _save(d)


def all_sessions() -> list:
    return _load()
