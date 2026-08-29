"""
data/highlights.py — lê e escreve os grifos de cada livro.

Estrutura do highlights.json:
{
  "/caminho/livro.pdf": {
    "3": [                          ← número da página (str)
      {
        "x0": 72.5, "y0": 100.2,   ← coordenadas no espaço PDF (pontos)
        "x1": 400.1, "y1": 115.8,
        "color": "#FFDD00",
        "opacity": 0.35
      }
    ]
  }
}

Toda função que modifica um grifo salva em disco imediatamente
(save_to_disk é chamado internamente) — grifos não dependem mais de o
usuário fechar o app normalmente para não serem perdidos em um crash.
`save_to_disk()` continua exposta para quem quiser forçar um flush.
"""
import logging

import config
from data._jsonio import load_json, save_json

log = logging.getLogger(__name__)

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = load_json(config.HIGHLIGHTS_FILE, {})
    return _cache


def save_to_disk() -> None:
    """Salva os grifos do cache em memória para o disco."""
    global _cache
    if _cache is not None:
        if not save_json(config.HIGHLIGHTS_FILE, _cache):
            log.error("Grifos não puderam ser salvos — alterações podem ser perdidas.")


# ── API pública ────────────────────────────────────────────────────────────────

def get(book_path: str, page: int) -> list[dict]:
    """Retorna lista de grifos da página (vazia se não houver)."""
    data = _load()
    return data.get(book_path, {}).get(str(page), [])


def add(book_path: str, page: int, x0: float, y0: float,
        x1: float, y1: float,
        color: str = config.DEFAULT_HIGHLIGHT_COLOR, opacity: float = 0.35) -> None:
    """Adiciona um grifo à página do livro e persiste imediatamente."""
    data = _load()
    book = data.setdefault(book_path, {})
    page_list = book.setdefault(str(page), [])

    # Evitar duplicação do mesmo retângulo (margem de 1 ponto)
    for h in page_list:
        if (abs(h["x0"] - x0) < 1.0 and abs(h["y0"] - y0) < 1.0 and
            abs(h["x1"] - x1) < 1.0 and abs(h["y1"] - y1) < 1.0):
            return  # Grifo idêntico já existe

    page_list.append({
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "color": color, "opacity": opacity
    })
    save_to_disk()


def delete(book_path: str, page: int, index: int) -> None:
    """Remove o grifo pelo índice na lista da página e persiste."""
    data = _load()
    try:
        data[book_path][str(page)].pop(index)
        save_to_disk()
    except (KeyError, IndexError):
        pass


def clear_page(book_path: str, page: int) -> None:
    """Remove todos os grifos de uma página e persiste."""
    data = _load()
    if book_path in data:
        data[book_path].pop(str(page), None)
        save_to_disk()


def clear_book(book_path: str) -> None:
    """Remove todos os grifos do livro e persiste."""
    data = _load()
    if book_path in data:
        data.pop(book_path, None)
        save_to_disk()
