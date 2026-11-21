package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Testes portados de tests/test_word_sync.py, mais os casos de trecho que cruza páginas. */
class WordSyncEngineTest {

    private fun timings(frase: String) =
        frase.split(" ").filter { it.isNotEmpty() }
            .mapIndexed { i, w -> WordTiming(w, i * 0.5f, i * 0.5f + 0.4f) }

    /** Página sintética: cada palavra ganha um retângulo; cada linha fica em y = 72 + 28 * linha. */
    private fun page(vararg linhas: String): List<PageWord> {
        val out = ArrayList<PageWord>()
        linhas.forEachIndexed { li, linha ->
            var x = 72f
            for (w in linha.split(" ")) {
                out.add(PageWord(normalizeWord(w), WordRect(x, 72f + 28f * li, x + w.length * 5f, 82f + 28f * li)))
                x += w.length * 5f + 4f
            }
        }
        return out
    }

    private val pagina = page(
        "O gato preto dormia sobre o telhado quente.",
        "Depois o gato desceu do telhado devagar.",
    )
    private val engine = WordSyncEngine { if (it == 0) pagina else emptyList() }

    // ── casamento palavra a palavra ──

    @Test fun cadaPalavraFaladaRecebeSeuRetangulo() {
        val frase = "O gato preto dormia sobre o telhado quente."
        val tim = timings(frase)
        val res = engine.sync(0, 0, tim)
        assertEquals(frase.split(" ").size, res.words.size)
        assertTrue("toda palavra devia ter sido localizada", res.words.all { it.rect != null })
        assertEquals(tim.map { it.startSeconds }, res.words.map { it.startSeconds })
        assertEquals(tim.map { it.endSeconds }, res.words.map { it.endSeconds })
    }

    @Test fun grifoAvancaENaoVoltaParaPalavraRepetida() {
        val primeira = engine.sync(0, 0, timings("O gato preto dormia sobre o telhado quente."))
        val res = engine.sync(0, 0, timings("Depois o gato desceu do telhado devagar."), primeira.cursor)
        val ys = res.words.mapNotNull { it.rect?.y0 }
        assertTrue("nenhuma palavra localizada na segunda linha", ys.isNotEmpty())
        assertTrue(ys.min() > pagina[0].rect.y0)
    }

    @Test fun cursorAvancaACadaTrecho() {
        val res = engine.sync(0, 0, timings("O gato preto"))
        assertEquals(SyncCursor(0, 3), res.cursor)
    }

    @Test fun palavraAusenteNaPaginaNaoDeslocaOGrifo() {
        val res = engine.sync(0, 0, timings("O gato xyzinexistente preto dormia"))
        assertNull(res.words[2].rect)
        assertNotNull("a palavra seguinte devia continuar sendo localizada", res.words[3].rect)
    }

    @Test fun semTimingsOuSemPalavrasNaoQuebra() {
        val vazio = engine.sync(0, 0, emptyList())
        assertTrue(vazio.words.isEmpty())
        assertEquals(SyncCursor(0, 0), vazio.cursor)

        val semPagina = WordSyncEngine { emptyList() }.sync(0, 0, timings("qualquer coisa"))
        assertEquals(SyncCursor(0, 0), semPagina.cursor)
        assertTrue(semPagina.words.all { it.rect == null })
        assertEquals(2, semPagina.words.size)
    }

    @Test fun palavraSoDePontuacaoNaoTemRetangulo() {
        val res = engine.sync(0, 0, timings("O — gato"))
        assertNull(res.words[1].rect)
        assertNotNull(res.words[2].rect)
    }

    @Test fun cursorDeOutraPaginaEIgnorado() {
        // trecho começa na página 0, mas o cursor veio da página 3: começa do início
        val res = engine.sync(0, 0, timings("O gato preto"), SyncCursor(3, 9))
        assertTrue(res.words.all { it.rect != null })
        assertEquals(SyncCursor(0, 3), res.cursor)
    }

    // ── helpers ──

    @Test fun matchForwardRespeitaAJanelaDeBusca() {
        val palavras = listOf("alvo") + List(WordSync.WORD_LOOKAHEAD + 5) { "ruido" } + listOf("alvo")
        assertEquals(0, WordSync.matchForward(palavras, "alvo", 0))
        assertEquals(-1, WordSync.matchForward(palavras, "alvo", 1))
    }

    @Test fun matchForwardAceitaCasamentoParcial() {
        assertEquals(0, WordSync.matchForward(listOf("introducao"), "intro", 0))
        assertEquals(0, WordSync.matchForward(listOf("intro"), "introducao", 0))
        assertEquals(-1, WordSync.matchForward(listOf("outra"), "intro", 0))
    }

    @Test fun matchForwardPrefereIgualdadeExataAoParcial() {
        // "intro" casa parcial com "introducao" (índice 0), mas existe a exata logo depois
        assertEquals(1, WordSync.matchForward(listOf("introducao", "intro"), "intro", 0))
    }

    @Test fun matchForwardIgnoraPalavraVaziaDaPagina() {
        assertEquals(-1, WordSync.matchForward(listOf("", ""), "intro", 0))
    }

    @Test fun anchorChunkProcuraParaTrasQuandoPreciso() {
        val palavras = listOf("inicio", "do", "texto", "meio", "do", "texto")
        assertEquals(0, WordSync.anchorChunk(palavras, listOf("inicio", "do", "texto"), 4))
        assertEquals(-1, WordSync.anchorChunk(palavras, listOf("nao", "existe", "aqui"), 0))
    }

    @Test fun anchorChunkUsaSoAsTresPrimeirasPalavrasNaoVazias() {
        val palavras = listOf("a", "b", "c", "d")
        assertEquals(0, WordSync.anchorChunk(palavras, listOf("", "a", "b", "c", "zzz"), 0))
        assertEquals(-1, WordSync.anchorChunk(palavras, listOf("", ""), 0))
    }

    @Test fun mergeRectsJuntaPalavrasDaMesmaLinha() {
        val rects = listOf(WordRect(10f, 50f, 30f, 60f), WordRect(35f, 50f, 70f, 60f), WordRect(10f, 80f, 45f, 90f))
        val linhas = WordSync.mergeRectsByLine(rects)
        assertEquals(2, linhas.size)
        assertEquals(WordRect(10f, 50f, 70f, 60f), linhas[0])
    }

    @Test fun mergeRectsNaoAlteraAListaRecebida() {
        val rects = listOf(WordRect(10f, 50f, 30f, 60f), WordRect(35f, 50f, 70f, 60f))
        val copia = rects.toList()
        WordSync.mergeRectsByLine(rects)
        assertEquals(copia, rects)
    }

    // ── trecho que cruza páginas (lógica nova) ──

    private val p0 = page("Fim da pagina um e a frase continua")
    private val p1 = page("depois na pagina dois ela termina agora", "Outro trecho comeca aqui")
    private val duas = WordSyncEngine { when (it) { 0 -> p0; 1 -> p1; else -> emptyList() } }

    @Test fun trechoQueCruzaPaginaContinuaNaSeguinte() {
        val res = duas.sync(0, 1, timings("a frase continua depois na pagina dois ela termina"), SyncCursor(0, 4))
        assertTrue(res.words.all { it.rect != null })
        assertEquals(listOf(0, 0, 0, 1, 1, 1, 1, 1, 1), res.words.map { it.pageIndex })
        assertEquals(SyncCursor(1, 6), res.cursor)
    }

    @Test fun trechoQueNaoCruzaNaoSaltaParaPaginaSeguinte() {
        // endPage == startPage: "depois" só existe na página 1, então fica sem retângulo
        val res = duas.sync(0, 0, timings("a frase continua depois"), SyncCursor(0, 4))
        assertNull(res.words[3].rect)
        assertTrue(res.words.all { it.pageIndex == 0 })
    }

    @Test fun naoMudaDePaginaSePalavraFaltanteEstaNoMeioDaPagina() {
        // "depois" existe na pág. 1, mas estamos no começo da pág. 0 (longe do fim): não salta.
        // (Palavras longas de propósito: com letras soltas, "depois" casaria por prefixo com "d".)
        val longa = page("alfa beta gama delta epsilon zeta eta teta iota kappa lambda mi ni xi omicron pi ro sigma tau upsilon")
        val eng = WordSyncEngine { if (it == 0) longa else p1 }
        val res = eng.sync(0, 1, timings("alfa beta depois"), SyncCursor(0, 0))
        assertEquals(0, res.words[2].pageIndex)
        assertNull(res.words[2].rect)
    }

    @Test fun proximoTrechoComecaNaPaginaOndeOAnteriorTerminou() {
        val primeiro = duas.sync(0, 1, timings("a frase continua depois na pagina dois ela termina"), SyncCursor(0, 4))
        val segundo = duas.sync(1, 1, timings("agora outro trecho comeca aqui"), primeiro.cursor)
        // o 2º trecho começa na pág. 1, onde o 1º terminou: o cursor (1, 6) é aproveitado
        val ys = segundo.words.mapNotNull { it.rect?.y0 }
        assertTrue(ys.isNotEmpty())
        assertEquals(SyncCursor(1, p1.size), segundo.cursor)
    }
}
