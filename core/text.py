"""
core/text.py — divisão de texto em trechos (chunks) para o TTS.

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


# ──────────────────────────────────────────────────────────────────
# Agrupamento de frases em trechos (chunks) para o TTS
# ──────────────────────────────────────────────────────────────────
# Cada chunk vira UMA requisição ao edge-tts, e toda requisição custa
# uma pausa: o MP3 devolvido tem ~0,25 s de silêncio antes da fala e
# ~0,9 s depois, além da latência de rede. Ler frase por frase paga
# esse preço o tempo todo e ainda entrega ao sintetizador pouco
# contexto, o que piora a entonação (cada frase sai com cadência de
# "fim de parágrafo").
#
# Juntar frases vizinhas do MESMO parágrafo até um tamanho alvo resolve
# os dois lados. O limite de parágrafo é respeitado de propósito: um
# título seguido do texto não deve ser lido de enfiada, e a pausa entre
# parágrafos é justamente onde ela soa natural.
TARGET_CHUNK_CHARS = 240   # tamanho que tentamos atingir juntando frases
MAX_CHUNK_CHARS    = 520   # teto: acima disso a latência de geração incomoda

# Pontos onde uma frase longa demais pode ser cortada sem soar quebrada,
# em ordem de preferência (ponto-e-vírgula separa orações melhor que vírgula).
_CLAUSE_BREAKS = ("; ", ": ", " — ", " – ", ", ")


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Quebra uma frase maior que `max_chars` em pontos de oração
    (`;`, `:`, travessão, `,`), escolhendo sempre o mais próximo do
    limite para fazer o menor número possível de cortes. Se não houver
    nenhum ponto de oração, devolve a frase inteira — melhor uma
    requisição longa do que cortar no meio de uma palavra."""
    if len(sentence) <= max_chars:
        return [sentence]

    for sep in _CLAUSE_BREAKS:
        cut = sentence.rfind(sep, 0, max_chars)
        if cut > max_chars // 3:          # evita um primeiro pedaço minúsculo
            head = sentence[:cut + len(sep)].strip()
            tail = sentence[cut + len(sep):].strip()
            return [head, *_split_long_sentence(tail, max_chars)]

    return [sentence]


def build_chunks(
    text: str,
    target_chars: int = TARGET_CHUNK_CHARS,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[str]:
    """
    Divide `text` nos trechos que serão enviados ao TTS, um por vez.

    `text` vem de PDFRenderer.text_for_page(), onde cada "\n" marca um
    parágrafo (não uma linha visual da página). Dentro de cada parágrafo
    as frases são agrupadas até ~`target_chars`; nunca se junta texto de
    parágrafos diferentes, e nenhum trecho passa de `max_chars`.
    """
    chunks: list[str] = []

    for paragraph in text.split("\n"):
        if not paragraph.strip():
            continue

        buf = ""
        for sentence in split_sentences(paragraph):
            for part in _split_long_sentence(sentence, max_chars):
                if buf and len(buf) + 1 + len(part) > max_chars:
                    chunks.append(buf)
                    buf = part
                else:
                    buf = f"{buf} {part}" if buf else part
                if len(buf) >= target_chars:
                    chunks.append(buf)
                    buf = ""
        if buf:
            chunks.append(buf)

    return chunks
