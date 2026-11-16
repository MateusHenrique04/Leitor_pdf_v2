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
    "red":         "#CC0000",   # preenchimentos e acentos — NÃO para texto pequeno
    "red_hot":     "#FF1A1A",
    "red_deep":    "#3A0000",   # fundo de estado "ativo/perigo" discreto
    "red_text":    "#FF4D4D",   # ver nota de legibilidade abaixo
    "on_accent":   "#FFFFFF",   # texto sobre preenchimento vermelho (5,9:1)

    # ── Rampa de texto ───────────────────────────────────────────
    # Três níveis, todos legíveis. Antes eram seis (#505050, #606060,
    # #303030 entre eles), e os três mais escuros ficavam entre 1,4:1 e
    # 2,7:1 de contraste sobre o fundo do painel — abaixo do mínimo de
    # 4,5:1. Na prática os rótulos de seção, os botões do painel e a
    # duração do livro eram quase invisíveis; "CONTROLES", a 1,4:1, não
    # se lia de jeito nenhum.
    #
    # Os valores são o cinza mais escuro que ainda passa de 4,5:1 no
    # fundo mais claro em que cada um é usado — mantém a intenção de
    # "discreto" sem sacrificar a leitura.
    "text":        "#E8E8E8",   # conteúdo principal        15,0:1
    "text_soft":   "#B4B4B4",   # secundário                 8,2:1
    "text_dim":    "#8C8C8C",   # rótulos, metadados         5,4:1 (4,6:1 sobre border)
    "success":     "#1DB954",
    "info":        "#00E5FF",   # grifo de leitura (TTS) e destaques de foco
    "warn":        "#FF6D00",   # resultado de busca atual
    "search":      "#FFD600",   # demais resultados de busca
}
# Nota de legibilidade: o vermelho da marca (#CC0000) rende só 3,1:1 sobre
# o fundo escuro. Serve para preenchimento (com texto branco por cima,
# 5,9:1) e para texto grande e em negrito, como o cronômetro — mas não
# para rótulos pequenos. Para esses existe `red_text`, que mantém a
# identidade e chega a 5,6:1.

# ──────────────────────────────────────────────────────────────────
# Tipografia — única fonte de verdade para toda a UI.
#
# Os rótulos que são só símbolo (▶ ⏸ ⏮ ⏭ ◂ ▸ ↕ + − ✕ ▾) usam
# _SYMBOL_FAMILY, e não Georgia/Courier: nenhuma das duas tem esses
# glifos, então o Tk ia buscar cada um numa fonte de fallback diferente.
# O resultado aparecia na tela — "⏮"/"⏭" vinham desenhados dentro de uma
# caixa enquanto "◂"/"▸" eram triângulos limpos, e o "⇕" do auto-scroll
# saía como um borrão. Declarando a família que tem todos os glifos, o
# conjunto inteiro vem do mesmo desenho. Em sistemas sem essa fonte o Tk
# cai no fallback — o mesmo que já acontecia antes.
# ──────────────────────────────────────────────────────────────────
_SYMBOL_FAMILY = "Segoe UI Symbol"

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
    "timeline":   ("Courier", 11, "bold"),  # posição/duração do audiolivro
    # Rótulos que são só símbolo — ver _SYMBOL_FAMILY acima.
    "icon_lg":    (_SYMBOL_FAMILY, 20),   # play/pause
    "icon":       (_SYMBOL_FAMILY, 15),   # pular página
    "icon_sm":    (_SYMBOL_FAMILY, 13),   # pular trecho
    "symbol":     (_SYMBOL_FAMILY, 10, "bold"),   # zoom, busca, dropdown
}

# Vozes edge-tts. O rótulo segue sempre "Nome (IDIOMA-PAÍS)", então o
# país já está no próprio nome: BR = Brasil, US = Estados Unidos,
# ES = Espanha, MX = México.
#
# O espanhol aparece em duas variantes porque o sotaque muda bastante a
# experiência de escuta: ES-ES é o espanhol peninsular (da Espanha) e
# ES-MX é o mexicano — a variante usada como padrão neutro em dublagem e
# audiolivros para a América Latina, o "espanhol latino".
VOICES = {
    "Antonio (PT-BR)":   "pt-BR-AntonioNeural",
    "Francisca (PT-BR)": "pt-BR-FranciscaNeural",
    "Guy (EN-US)":       "en-US-GuyNeural",
    "Aria (EN-US)":      "en-US-AriaNeural",
    "Jorge (ES-MX)":     "es-MX-JorgeNeural",
    "Dalia (ES-MX)":     "es-MX-DaliaNeural",
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
# Resolução de renderização das páginas.
#
# PDF_RENDER_DPI é o PISO, não um valor fixo: a página é renderizada na
# resolução que a tela realmente vai usar (ver ui/viewer._target_px_width).
# Com um DPI fixo, um livro de formato pequeno — "Meditações Metafísicas",
# 252x331 pt, metade de um A4 — rendia 350x460 px e era AMPLIADO para
# preencher a janela: ampliar não cria detalhe, e o texto saía borrado.
# Um A4 no mesmo DPI rende 827x1169 px, é REDUZIDO para caber, e por isso
# sempre pareceu nítido. A resolução agora acompanha o tamanho de exibição.
PDF_RENDER_DPI = 100
# Teto de resolução: protege a memória com zoom alto (o zoom vai até 5x).
# Acima disto a página volta a ser ampliada — já em resolução alta o
# bastante para a diferença não aparecer.
#
# O teto é em PIXELS, não em DPI: é pixel que ocupa RAM, e o mesmo DPI
# rende imagens de tamanhos bem diferentes conforme o formato do livro.
# Um teto em DPI penalizaria justamente os livros pequenos, que precisam
# de MAIS DPI para chegar à mesma quantidade de pixels — o problema que
# esta mudança veio corrigir.
PDF_RENDER_MAX_PX  = 4000   # maior lado da imagem renderizada, em pixels
PDF_RENDER_CACHE_MB = 192   # orçamento do cache de páginas renderizadas

# Cores disponíveis para grifos manuais — única fonte, usada por
# ui/right_panel.py e ui/highlights_mixin.py.
HIGHLIGHT_COLORS = {
    "🟡 Amarelo": "#FFDD00",
    "🟢 Verde":   "#00E676",
    "🔵 Ciano":   "#00E5FF",
    "🔴 Rosa":    "#FF4081",
}
# Opacidade do trecho inteiro (fundo) e da palavra sendo falada durante
# a leitura. Com valores próximos, a palavra corrente sumia dentro do
# fundo do trecho; o fundo é bem mais fraco para ela se destacar.
CHUNK_HIGHLIGHT_OPACITY = 0.18
WORD_HIGHLIGHT_OPACITY  = 0.45

DEFAULT_HIGHLIGHT_COLOR = "#FFDD00"
DEFAULT_HIGHLIGHT_LABEL = "🟡 Amarelo"
assert DEFAULT_HIGHLIGHT_LABEL in HIGHLIGHT_COLORS
