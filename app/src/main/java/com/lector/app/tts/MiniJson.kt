package com.lector.app.tts

/**
 * Leitor de JSON mínimo (Kotlin puro). Existe para os metadados do TTS poderem ser testados com JUnit
 * sem emulador: o org.json do Android não funciona em testes locais.
 * Devolve Map<String, Any?>, List<Any?>, String, Long, Double, Boolean ou null.
 */
object MiniJson {
    fun parse(text: String): Any? {
        val p = Parser(text)
        val v = p.value()
        p.skipWs()
        if (p.pos != text.length) p.fail("texto sobrando depois do valor")
        return v
    }

    private class Parser(private val s: String) {
        var pos = 0

        fun fail(msg: String): Nothing = throw IllegalArgumentException("JSON inválido ($msg) na posição $pos")

        fun skipWs() {
            while (pos < s.length && s[pos].isWhitespace()) pos++
        }

        fun value(): Any? {
            skipWs()
            if (pos >= s.length) fail("fim inesperado")
            val c = s[pos]
            return when {
                c == '{' -> obj()
                c == '[' -> arr()
                c == '"' -> str()
                c == 't' -> literal("true", true)
                c == 'f' -> literal("false", false)
                c == 'n' -> literal("null", null)
                c == '-' || c.isDigit() -> num()
                else -> fail("caractere '$c'")
            }
        }

        private fun literal(word: String, v: Any?): Any? {
            if (!s.startsWith(word, pos)) fail("esperava $word")
            pos += word.length
            return v
        }

        private fun obj(): Map<String, Any?> {
            pos++ // {
            val map = LinkedHashMap<String, Any?>()
            skipWs()
            if (pos < s.length && s[pos] == '}') {
                pos++
                return map
            }
            while (true) {
                skipWs()
                if (pos >= s.length || s[pos] != '"') fail("esperava nome de campo")
                val key = str()
                skipWs()
                if (pos >= s.length || s[pos] != ':') fail("esperava ':'")
                pos++
                map[key] = value()
                skipWs()
                if (pos >= s.length) fail("objeto não terminado")
                when (s[pos++]) {
                    ',' -> continue
                    '}' -> return map
                    else -> fail("esperava ',' ou '}'")
                }
            }
        }

        private fun arr(): List<Any?> {
            pos++ // [
            val list = ArrayList<Any?>()
            skipWs()
            if (pos < s.length && s[pos] == ']') {
                pos++
                return list
            }
            while (true) {
                list.add(value())
                skipWs()
                if (pos >= s.length) fail("lista não terminada")
                when (s[pos++]) {
                    ',' -> continue
                    ']' -> return list
                    else -> fail("esperava ',' ou ']'")
                }
            }
        }

        private fun str(): String {
            pos++ // "
            val sb = StringBuilder()
            while (pos < s.length) {
                val c = s[pos++]
                when (c) {
                    '"' -> return sb.toString()
                    '\\' -> {
                        if (pos >= s.length) fail("escape incompleto")
                        when (val e = s[pos++]) {
                            '"', '\\', '/' -> sb.append(e)
                            'b' -> sb.append('\b')
                            'f' -> sb.append('\u000C')
                            'n' -> sb.append('\n')
                            'r' -> sb.append('\r')
                            't' -> sb.append('\t')
                            'u' -> {
                                if (pos + 4 > s.length) fail("\\u incompleto")
                                val code = s.substring(pos, pos + 4).toIntOrNull(16) ?: fail("\\u inválido")
                                sb.append(code.toChar())
                                pos += 4
                            }
                            else -> fail("escape '\\$e'")
                        }
                    }
                    else -> sb.append(c)
                }
            }
            fail("texto não terminado")
        }

        private fun num(): Any {
            val start = pos
            while (pos < s.length && s[pos] in "+-0123456789.eE") pos++
            val token = s.substring(start, pos)
            val isFloat = token.any { it == '.' || it == 'e' || it == 'E' }
            if (!isFloat) token.toLongOrNull()?.let { return it }
            return token.toDoubleOrNull() ?: fail("número '$token'")
        }
    }
}
