"""
config.py — constantes globais.
Para mudar cores, fontes, vozes ou caminhos: edite AQUI e só aqui.
"""
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_APP_NAME = "Lector"
_FROZEN_BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def _pick_base_dir() -> Path:
    """
    Usa a pasta do executável/script como base (comportamento padrão).
    Se essa pasta não puder ser escrita (ex.: app instalado em
    C:\\Program Files\\, sem permissão de usuário comum), cai para uma
    pasta de dados do usuário (%APPDATA%/Lector no Windows,
    ~/.local/share/Lector no Linux/Mac) para não perder biblioteca,
    histórico e grifos silenciosamente.
    """
    probe = _FROZEN_BASE / ".write_test"
    try:
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
        return _FROZEN_BASE
    except Exception:
        appdata = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") \
            or str(Path.home() / ".local" / "share")
        fallback = Path(appdata) / _APP_NAME
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except Exception:
            fallback = Path.home() / f".{_APP_NAME.lower()}"
            fallback.mkdir(parents=True, exist_ok=True)
        log.warning("Pasta %s não é gravável; usando %s para dados do usuário.",
                    _FROZEN_BASE, fallback)
        return fallback


BASE = _pick_base_dir()

# Persistência
LIBRARY_FILE    = BASE / "library.json"
HISTORY_FILE    = BASE / "history.json"
HIGHLIGHTS_FILE = BASE / "highlights.json"
PREFS_FILE      = BASE / "prefs.json"
GEOMETRY_FILE   = BASE / ".window_geometry"
TEMP_DIR        = BASE / ".tmp_audio"

# ──────────────────────────────────────────────────────────────────
# Cores — única fonte de verdade para toda a UI. Não hardcode hex
# em arquivos de ui/*.py: adicione um token aqui e reutilize C["..."].
# ──────────────────────────────────────────────────────────────────
C = {
    "bg":          "#0E0E0E",
    "canvas_bg":   "#1A1A1A",   # fundo do canvas de visualização do PDF
    "panel":       "#141414",
    "panel_alt":   "#1C1C1C",   # painéis secundários (dropdowns, popups)
    "panel_alt2":  "#202020",
    "panel_alt3":  "#252525",
    "select_bg":   "#2A2A2A",   # item selecionado em listas/dropdowns
    "border":      "#242424",
    "border_soft": "#333333",
    "hover":       "#2E2E2E",
    "red":         "#CC0000",
    "red_hot":     "#FF1A1A",
    "red_deep":    "#3A0000",   # fundo de estado "ativo/perigo" discreto
    "text":        "#E8E8E8",
    "text_dim":    "#505050",
    "text_soft":   "#909090",
    "text_soft2":  "#B0B0B0",
    "text_faint":  "#606060",
    "text_faint2": "#303030",
    "success":     "#1DB954",
    "info":        "#00E5FF",   # grifo de leitura (TTS) e destaques de foco
    "warn":        "#FF6D00",   # resultado de busca atual
    "search":      "#FFD600",   # demais resultados de busca
}

# ──────────────────────────────────────────────────────────────────
# Tipografia — única fonte de verdade para toda a UI.
# ──────────────────────────────────────────────────────────────────
FONTS = {
    "logo":       ("Georgia", 20, "bold"),
    "title":      ("Georgia", 16, "bold"),
    "heading":    ("Georgia", 13, "bold"),
    "body":       ("Georgia", 11),
    "body_bold":  ("Georgia", 11, "bold"),
    "body_small": ("Georgia", 9),
    "label":      ("Courier", 8, "bold"),
    "label_lg":   ("Courier", 9, "bold"),
    "mono":       ("Courier", 9),
    "mono_bold":  ("Courier", 9, "bold"),
    "timer":      ("Courier", 16, "bold"),
    "icon":       ("Georgia", 15),
    "icon_sm":    ("Georgia", 13),
}

# Vozes edge-tts
VOICES = {
    "Antonio (PT-BR)":   "pt-BR-AntonioNeural",
    "Francisca (PT-BR)": "pt-BR-FranciscaNeural",
    "Guy (EN-US)":       "en-US-GuyNeural",
    "Aria (EN-US)":      "en-US-AriaNeural",
    "Alvaro (ES-ES)":    "es-ES-AlvaroNeural",
    "Elvira (ES-ES)":    "es-ES-ElviraNeural",
}
DEFAULT_VOICE = "Antonio (PT-BR)"
assert DEFAULT_VOICE in VOICES, "DEFAULT_VOICE precisa existir em VOICES"

# Velocidade: label → % para edge-tts
SPEEDS = {
    "0.5×": -50,
    "0.75×": -25,
    "1×":     0,
    "1.25×": 25,
    "1.5×":  50,
    "2×":   100,
}
DEFAULT_SPEED = "1×"
assert DEFAULT_SPEED in SPEEDS, "DEFAULT_SPEED precisa existir em SPEEDS"

DEFAULT_VOLUME = 0.7
PDF_RENDER_DPI = 100   # resolução da renderização das páginas

# Cores disponíveis para grifos manuais — única fonte, usada por
# ui/right_panel.py e ui/highlights_mixin.py.
HIGHLIGHT_COLORS = {
    "🟡 Amarelo": "#FFDD00",
    "🟢 Verde":   "#00E676",
    "🔵 Ciano":   "#00E5FF",
    "🔴 Rosa":    "#FF4081",
}
DEFAULT_HIGHLIGHT_COLOR = "#FFDD00"
DEFAULT_HIGHLIGHT_LABEL = "🟡 Amarelo"
assert DEFAULT_HIGHLIGHT_LABEL in HIGHLIGHT_COLORS
