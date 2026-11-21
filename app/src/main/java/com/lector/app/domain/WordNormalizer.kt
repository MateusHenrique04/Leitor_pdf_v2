package com.lector.app.domain

import java.text.Normalizer

// Python \W é Unicode; em Java/ICU o \w varia entre JVM e Android. Classe explícita = mesmo resultado nos dois.
private val NON_WORD = Regex("""[^\p{L}\p{N}_]""")

/**
 * Porte de normalize_word (core/pdf_renderer.py): forma usada para comparar o texto do PDF com o
 * texto devolvido pelo TTS: NFKC, minúscula e sem pontuação. "«Mercados»," e "mercados" viram a mesma chave.
 */
fun normalizeWord(s: String): String =
    NON_WORD.replace(Normalizer.normalize(s, Normalizer.Form.NFKC).lowercase(), "")
