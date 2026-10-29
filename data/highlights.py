"""
data/highlights.py — lê e escreve os grifos de cada livro.

Estrutura do highlights.json:
{
  "/caminho/livro.pdf": {
    "3": [                          ← número da página (str)
      {
        "id": "a1b2c3...",          ← uuid4().hex, identifica o grifo
        "x0": 72.5, "y0": 100.2,   ← coordenadas no espaço PDF (pontos)
        "x1": 400.1, "y1": 115.8,
        "color": "#FFDD00",
        "opacity": 0.35
      }
    ]
  }
}

Grifos são identificados por "id" (não pelo índice na lista — apagar por
índice dependia da ordem continuar a mesma entre desenhar e apagar).
Arquivos antigos sem "id" são migrados na primeira leitura: cada grifo
sem id recebe um novo, e o arquivo é salvo de volta — nenhum dado é
perdido nesse processo.

Toda função que modifica um grifo salva em disco imediatamente
(save_to_disk é chamado internamente) — grifos não dependem mais de o
usuário fechar o app normalmente para não serem perdidos em um crash.
`save_to_disk()` continua exposta para quem quiser forçar um flush.
"""
import logging
import uuid

import config
from data._jsonio import load_json, save_json

log = logging.getLogger(__name__)

_cache: dict | None = None


def _migrate_missing_ids(data: dict) -> bool:
    """Dá um id único a grifos de um highlights.json antigo que não têm.
    Retorna True se algo foi alterado (para o chamador persistir)."""
    changed = False
    for book in data.values():
        for page_list in book.values():
            for h in page_list:
                if "id" not in h:
                    h["id"] = uuid.uuid4().hex
                    changed = True
    return changed


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = load_json(config.HIGHLIGHTS_FILE, {})
        if _migrate_missing_ids(_cache):
            save_json(config.HIGHLIGHTS_FILE, _cache)
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


def all_for_book(book_path: str) -> dict[str, list[dict]]:
    """Retorna todos os grifos do livro, por página (dict vazio se não houver)."""
    return _load().get(book_path, {})


def add(book_path: str, page: int, x0: float, y0: float,
        x1: float, y1: float,
        color: str = config.DEFAULT_HIGHLIGHT_COLOR, opacity: float = 0.35) -> str | None:
    """Adiciona um grifo à página do livro e persiste imediatamente.
    Retorna o id do grifo criado, ou None se era duplicata de um existente."""
    data = _load()
    book = data.setdefault(book_path, {})
    page_list = book.setdefault(str(page), [])

    # Evitar duplicação do mesmo retângulo (margem de 1 ponto)
    for h in page_list:
        if (abs(h["x0"] - x0) < 1.0 and abs(h["y0"] - y0) < 1.0 and
            abs(h["x1"] - x1) < 1.0 and abs(h["y1"] - y1) < 1.0):
            return None  # Grifo idêntico já existe

    new_id = uuid.uuid4().hex
    page_list.append({
        "id": new_id,
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "color": color, "opacity": opacity
    })
    save_to_disk()
    return new_id


def delete(book_path: str, page: int, highlight_id: str) -> None:
    """Remove o grifo pelo id na lista da página e persiste.

    Identificar por id (em vez do índice na lista) evita apagar o grifo
    errado quando a ordem muda entre desenhar e apagar."""
    data = _load()
    try:
        page_list = data[book_path][str(page)]
    except KeyError:
        return
    before = len(page_list)
    page_list[:] = [h for h in page_list if h.get("id") != highlight_id]
    if len(page_list) != before:
        save_to_disk()


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
