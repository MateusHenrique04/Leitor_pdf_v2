package com.lector.app.domain

/**
 * Porte de split_sentences e _split_long_sentence (core/text.py). Kotlin puro.
 * Abreviações, decimais e reticências não terminam frase.
 */
object TextSplitter {
    private val ABBREVIATIONS = setOf(
        // Português
        "dr", "dra", "sr", "sra", "srta", "prof", "profa", "exmo", "exma",
        "pág", "pag", "p", "pp", "fig", "figs", "cap", "caps",
        "vol", "vols", "ed", "trad", "org", "orgs", "jr",
        // English
        "mr", "mrs", "ms", "st", "vs", "no",
        // Español
        "ud", "uds",
    )

    // Sem \b (muda entre JVM e Android): "não precedido por letra/dígito/_" faz o mesmo papel.
    private const val NOT_AFTER_WORD = """(?<![\p{L}\p{N}_])"""

    private val ABBR_RE = Regex(
        NOT_AFTER_WORD + "(" + ABBREVIATIONS.sortedByDescending { it.length }.joinToString("|") + """)\.""",
        RegexOption.IGNORE_CASE,
    )

    // "etc." só NÃO termina a frase quando a próxima palavra começa com minúscula.
    private val ETC_RE = Regex(NOT_AFTER_WORD + """(?i:etc)\.(?=\s+[a-zà-ÿ])""")
    private val ELLIPSIS_RE = Regex("""\.\.\.+""")
    private val DECIMAL_RE = Regex("""(?<=\p{Nd})\.(?=\p{Nd})""")
    private val SPLIT_RE = Regex("""(?<=[.!?])\s+|\n""")

    // Caractere de controle que "esconde" pontos antes do split e volta a "." no final.
    private const val GUARD = '\u0000'

    private val CLAUSE_BREAKS = listOf("; ", ": ", " — ", " – ", ", ")

    /** Divide em frases/linhas (também quebra em "\n"). Nunca devolve strings vazias. */
    fun splitSentences(text: String): List<String> {
        if (text.isBlank()) return emptyList()

        var guarded = ELLIPSIS_RE.replace(text) { it.value.replace('.', GUARD) }
        guarded = DECIMAL_RE.replace(guarded) { GUARD.toString() }
        guarded = ETC_RE.replace(guarded) { it.value.dropLast(1) + GUARD }
        guarded = ABBR_RE.replace(guarded) { it.value.dropLast(1) + GUARD }

        return SPLIT_RE.split(guarded)
            .map { it.replace(GUARD, '.').trim() }
            .filter { it.isNotEmpty() }
    }

    /**
     * Quebra uma frase maior que [maxChars] em pontos de oração (; : — – ,), no ponto mais próximo
     * do limite. Sem ponto de oração, devolve a frase inteira (melhor longa do que cortar palavra).
     */
    fun splitLongSentence(sentence: String, maxChars: Int): List<String> {
        if (sentence.length <= maxChars) return listOf(sentence)

        val window = sentence.substring(0, maxChars) // equivale ao rfind(sep, 0, max) do Python
        for (sep in CLAUSE_BREAKS) {
            val cut = window.lastIndexOf(sep)
            if (cut > maxChars / 3) { // evita um primeiro pedaço minúsculo
                val head = sentence.substring(0, cut + sep.length).trim()
                val tail = sentence.substring(cut + sep.length).trim()
                return listOf(head) + splitLongSentence(tail, maxChars)
            }
        }
        return listOf(sentence)
    }
}
