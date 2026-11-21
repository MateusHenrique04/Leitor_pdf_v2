package com.lector.app.domain

/**
 * Texto simples (sem JSON, sem Android) para gravar o [BookIndex] em arquivo:
 *
 *     LECTOR-INDEX<TAB>1<TAB>versãoDoPlanner<TAB>páginas<TAB>quantidadeDeTrechos
 *     index<TAB>página<TAB>páginaFinal<TAB>indexNaPágina<TAB>texto (com \\, \t, \n e \r escapados)
 *
 * [decode] devolve null para qualquer arquivo malformado (o índice é só refeito; nunca quebra o app).
 */
object BookIndexCodec {
    const val FORMAT = 1
    private const val MAGIC = "LECTOR-INDEX"

    fun encode(index: BookIndex): String {
        val sb = StringBuilder()
        sb.append(MAGIC).append('\t').append(FORMAT).append('\t').append(index.plannerVersion).append('\t')
            .append(index.pageCount).append('\t').append(index.chunks.size).append('\n')
        for (c in index.chunks) {
            sb.append(c.index).append('\t').append(c.pageIndex).append('\t').append(c.endPageIndex).append('\t')
                .append(c.indexInPage).append('\t').append(escape(c.text)).append('\n')
        }
        return sb.toString()
    }

    fun decode(data: String): BookIndex? = try {
        val lines = data.split('\n')
        val head = lines[0].split('\t')
        if (head.size != 5 || head[0] != MAGIC || head[1].toInt() != FORMAT) {
            null
        } else {
            val version = head[2].toInt()
            val pages = head[3].toInt()
            val count = head[4].toInt()
            // Depois dos trechos sobra só a string vazia depois do último "\n".
            if (count < 0 || lines.size != count + 2 || lines.last().isNotEmpty()) {
                null
            } else {
                val chunks = ArrayList<Chunk>(count)
                var ok = true
                for (i in 0 until count) {
                    val f = lines[i + 1].split('\t', limit = 5)
                    if (f.size != 5) { ok = false; break }
                    val chunk = Chunk(f[0].toInt(), f[1].toInt(), f[2].toInt(), f[3].toInt(), unescape(f[4]) ?: run { ok = false; "" })
                    if (!ok || chunk.index != i || chunk.pageIndex !in 0 until pages || chunk.endPageIndex < chunk.pageIndex) {
                        ok = false
                        break
                    }
                    chunks.add(chunk)
                }
                if (ok) BookIndex(version, pages, chunks) else null
            }
        }
    } catch (_: NumberFormatException) {
        null
    } catch (_: IndexOutOfBoundsException) {
        null
    }

    private fun escape(s: String): String {
        val sb = StringBuilder(s.length + 8)
        for (ch in s) {
            when (ch) {
                '\\' -> sb.append("\\\\")
                '\t' -> sb.append("\\t")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                else -> sb.append(ch)
            }
        }
        return sb.toString()
    }

    /** null se houver escape inválido. */
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
