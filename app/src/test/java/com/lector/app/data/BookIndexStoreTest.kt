package com.lector.app.data

import com.lector.app.domain.BookIndex
import com.lector.app.domain.Chunk
import com.lector.app.domain.ChunkPlanner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class BookIndexStoreTest {
    @get:Rule val tmp = TemporaryFolder()

    private val id = "1b4e28ba-2fa1-11d2-883f-0016d3cca427"
    private fun index(pages: Int = 2, version: Int = ChunkPlanner.VERSION) =
        BookIndex(version, pages, listOf(Chunk(0, 0, 0, 0, "Olá."), Chunk(1, 1, 1, 0, "Mundo.")))

    private fun store() = BookIndexStore(File(tmp.root, "index"))

    @Test fun salvaECarrega() {
        val s = store()
        s.save(id, index())
        assertEquals(index(), s.load(id, 2))
    }

    @Test fun naoExisteDevolveNull() = assertNull(store().load(id, 2))

    @Test fun numeroDePaginasDiferenteInvalida() {
        val s = store()
        s.save(id, index(pages = 2))
        assertNull(s.load(id, 3))
    }

    @Test fun arquivoCorrompidoDevolveNull() {
        val s = store()
        s.save(id, index())
        File(tmp.root, "index/$id.v${ChunkPlanner.VERSION}.idx").writeText("lixo")
        assertNull(s.load(id, 2))
    }

    @Test fun salvarDeNovoSubstitui() {
        val s = store()
        s.save(id, index())
        val novo = BookIndex(ChunkPlanner.VERSION, 2, listOf(Chunk(0, 0, 0, 0, "Outro.")))
        s.save(id, novo)
        assertEquals(novo, s.load(id, 2))
    }

    @Test fun apagaIndicesDeVersoesAntigasAoSalvar() {
        val dir = File(tmp.root, "index").apply { mkdirs() }
        val velho = File(dir, "$id.v0.idx").apply { writeText("velho") }
        val outroLivro = File(dir, "outro-livro.v0.idx").apply { writeText("x") }
        store().save(id, index())
        assertFalse(velho.exists())
        assertTrue("não pode mexer em outros livros", outroLivro.exists())
    }

    @Test fun deleteRemoveSoOLivro() {
        val s = store()
        val outro = "aaaaaaaa-0000-0000-0000-000000000000"
        s.save(id, index())
        s.save(outro, index())
        s.delete(id)
        assertNull(s.load(id, 2))
        assertEquals(index(), s.load(outro, 2))
    }

    @Test fun naoDeixaArquivoTemporario() {
        store().save(id, index())
        val sobras = File(tmp.root, "index").listFiles()!!.filter { it.name.endsWith(".tmp") }
        assertTrue(sobras.isEmpty())
    }

    @Test(expected = IllegalArgumentException::class)
    fun idComBarraEhRejeitado() {
        store().save("../fora", index())
    }
}
