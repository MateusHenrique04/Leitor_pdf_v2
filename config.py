"""
config.py — constantes globais.
Para mudar cores, vozes ou caminhos: edite AQUI e só aqui.
"""
import sys
from pathlib import Path

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

# Persistência
LIBRARY_FILE = BASE / "library.json"
HISTORY_FILE = BASE / "history.json"
TEMP_DIR     = BASE / ".tmp_audio"

# Cores
C = {
    "bg":       "#0E0E0E",
    "panel":    "#141414",
    "border":   "#242424",
    "red":      "#CC0000",
    "red_hot":  "#FF1A1A",
    "text":     "#E8E8E8",
    "text_dim": "#505050",
    "success":  "#1DB954",
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

DEFAULT_VOLUME = 0.7
PDF_RENDER_DPI = 100   # resolução da renderização das páginas
