package com.lector.app.domain

/**
 * Texto simples para guardar os [WordTiming] de um trecho no banco (uma palavra por linha:
 * `início<TAB>fim<TAB>palavra`, com \\, \t, \n e \r escapados na palavra). Sem JSON e sem Android: testável no PC.
 * [decode] devolve null se o texto estiver malformado (o trecho é então tratado como "não baixado").
 */
object TimingsCodec {
    fun encode(timings: List<WordTiming>): String {
        val sb = StringBuilder()
        for (t in timings) {
            sb.append(t.startSeconds).append('\t').append(t.endSeconds).append('\t')
            for (ch in t.word) {
                when (ch) {
                    '\\' -> sb.append("\\\\")
                    '\t' -> sb.append("\\t")
                    '\n' -> sb.append("\\n")
                    '\r' -> sb.append("\\r")
                    else -> sb.append(ch)
                }
            }
            sb.append('\n')
        }
        return sb.toString()
    }

    fun decode(data: String): List<WordTiming>? {
        if (data.isEmpty()) return emptyList()
        if (!data.endsWith('\n')) return null
        val out = ArrayList<WordTiming>()
        for (line in data.substring(0, data.length - 1).split('\n')) {
            val f = line.split('\t', limit = 3)
            if (f.size != 3) return null
            val start = f[0].toFloatOrNull() ?: return null
            val end = f[1].toFloatOrNull() ?: return null
            val word = unescape(f[2]) ?: return null
            out.add(WordTiming(word, start, end))
        }
        return out
    }

    private fun unescape(s: String): String? {
        if (s.indexOf('\\') < 0) return s
        val sb = StringBuilder(s.length)
        var i = 0
        while (i < s.length) {
            val ch = s[i]
            if (ch != '\\') { sb.append(ch); i++; continue }
            if (i + 1 >= s.length) return null
            when (s[i + 1]) {
                '\\' -> sb.append('\\')
                't' -> sb.append('\t')
                'n' -> sb.append('\n')
                'r' -> sb.append('\r')
                else -> return null
            }
            i += 2
        }
        return sb.toString()
    }
}
