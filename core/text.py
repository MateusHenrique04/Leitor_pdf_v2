"""
core/text.py — divisão de texto em frases para o TTS.

Antes, ui/controls.py tinha a mesma regex `re.split(r'(?<=[.!?])\\s+|\\n', text)`
repetida em dois lugares (_read_loop e _get_current_chunks), e ela quebra
em qualquer abreviação ("Dr.", "Sr.", "p. 23", "etc.", "Fig. 3"), em
números decimais ("3.5") e no meio de reticências usadas como pausa
("Ele hesitou... e decidiu sair." virava duas frases com uma pausa
estranha no meio). split_sentences() centraliza essa lógica e trata
esses três casos antes de dividir.
"""
import re

# Abreviações comuns em português, inglês e espanhol cujo ponto final não
# marca fim de frase. Lista enxuta — cobre os casos citados na auditoria,
# não pretende ser exaustiva.
_ABBREVIATIONS = {
    # Português
    "dr", "dra", "sr", "sra", "srta", "prof", "profa", "exmo", "exma",
    "pág", "pag", "p", "pp", "fig", "figs", "cap", "caps",
    "vol", "vols", "ed", "trad", "org", "orgs", "jr",
    # English
    "mr", "mrs", "ms", "st", "vs", "no",
    # Español
    "ud", "uds",
}

_ABBR_RE = re.compile(
    r"\b(" + "|".join(sorted(_ABBREVIATIONS, key=len, reverse=True)) + r")\.",
    re.IGNORECASE,
)
# "etc." é ambíguo: às vezes termina a frase ("...3, etc. Isso encerra."),
# às vezes continua ("ferramentas, etc. que usamos aqui"). Heurística: só
# tratar como NÃO sendo fim de frase quando a próxima palavra começa com
# minúscula — indício de que a frase continua.
_ETC_RE = re.compile(r"\b(?i:etc)\.(?=\s+[a-zà-ÿ])")
_ELLIPSIS_RE = re.compile(r"\.\.\.+")
_DECIMAL_RE = re.compile(r"(?<=\d)\.(?=\d)")
_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n")

# Caractere de controle que não aparece em texto normal — usado para
# "esconder" pontos que não devem disparar uma quebra de frase antes do
# split, e devolvidos a "." no final.
_GUARD = "\x00"


def split_sentences(text: str) -> list[str]:
    """Divide `text` em frases/linhas, ignorando pontos de abreviação,
    números decimais e reticências usadas como pausa. Também quebra em
    `\\n`, como a regex original. Retorna lista sem strings vazias."""
    if not text or not text.strip():
        return []

    guarded = _ELLIPSIS_RE.sub(lambda m: m.group(0).replace(".", _GUARD), text)
    guarded = _DECIMAL_RE.sub(_GUARD, guarded)
    guarded = _ETC_RE.sub(lambda m: m.group(0)[:-1] + _GUARD, guarded)
    guarded = _ABBR_RE.sub(lambda m: m.group(0)[:-1] + _GUARD, guarded)

    parts = _SPLIT_RE.split(guarded)
    return [p.replace(_GUARD, ".").strip() for p in parts if p.replace(_GUARD, ".").strip()]
