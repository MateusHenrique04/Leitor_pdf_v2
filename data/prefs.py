"""
data/prefs.py — preferências de leitura persistidas entre sessões
(voz, velocidade, volume, zoom, auto-scroll, cor de grifo padrão).

Antes dessas preferências resetavam para os padrões de config.py a
cada abertura do app (só a geometria da janela era salva). Agora
seguem o mesmo padrão de cache+persistência de library.py/history.py.
"""
from config import PREFS_FILE
from data._jsonio import load_json, save_json

_DEFAULTS = {
    "voice": None,                  # nome (chave de VOICES); None = usa DEFAULT_VOICE
    "speed": None,                  # label (chave de SPEEDS); None = usa DEFAULT_SPEED
    "volume": None,                 # 0..1; None = usa DEFAULT_VOLUME
    "zoom": None,                   # float; None = usa o padrão da UI
    "autoscroll": True,
    "highlight_color_label": None,  # None = usa DEFAULT_HIGHLIGHT_LABEL
}

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        data = load_json(PREFS_FILE, {})
        _cache = {**_DEFAULTS, **data}
    return _cache


def get_all() -> dict:
    """Retorna uma cópia das preferências salvas (com defaults para chaves ausentes)."""
    return dict(_load())


def set(key: str, value) -> None:
    """Define uma preferência e persiste imediatamente."""
    d = _load()
    d[key] = value
    save_json(PREFS_FILE, d)
