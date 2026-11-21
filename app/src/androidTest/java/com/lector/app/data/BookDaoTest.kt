package com.lector.app.data

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Roda no celular (Run > BookDaoTest). Banco em memória: nada fica salvo. */
class BookDaoTest {
    private lateinit var db: LectorDatabase
    private lateinit var dao: BookDao

    @Before fun setUp() {
        val ctx = ApplicationProvider.getApplicationContext<Context>()
        db = Room.inMemoryDatabaseBuilder(ctx, LectorDatabase::class.java).allowMainThreadQueries().build()
        dao = db.bookDao()
    }

    @After fun tearDown() = db.close()

    private fun book(id: String, uri: String = "content://x/$id", opened: Long = 1L) = BookEntity(
        id = id, uri = uri, title = "Livro $id", totalPages = 100, addedAt = 1L, lastOpenedAt = opened,
    )

    @Test fun insereEBuscaPorId() = runBlocking {
        dao.insert(book("a"))
        assertEquals("Livro a", dao.getById("a")?.title)
        assertNull(dao.getById("inexistente"))
    }

    @Test fun uriDuplicadaEhIgnorada() = runBlocking {
        assertTrue(dao.insert(book("a", uri = "content://same")) != -1L)
        assertEquals(-1L, dao.insert(book("b", uri = "content://same")))
        assertEquals(1, dao.observeAll().first().size)
        assertNotNull(dao.getByUri("content://same"))
    }

    @Test fun listaOrdenadaPeloMaisRecentementeAberto() = runBlocking {
        dao.insert(book("antigo", opened = 10))
        dao.insert(book("novo", opened = 30))
        dao.insert(book("meio", opened = 20))
        assertEquals(listOf("novo", "meio", "antigo"), dao.observeAll().first().map { it.id })
    }

    @Test fun atualizaPosicaoEReordena() = runBlocking {
        dao.insert(book("a", opened = 10))
        dao.insert(book("b", opened = 20))
        dao.updatePosition("a", page = 7, chunk = 3, now = 99)
        val a = dao.getById("a")!!
        assertEquals(7, a.lastPage); assertEquals(3, a.lastChunkIndex); assertEquals(99L, a.lastOpenedAt)
        assertEquals("a", dao.observeAll().first().first().id)
    }

    @Test fun marcaConcluidoEAtualizaTotal() = runBlocking {
        dao.insert(book("a"))
        dao.setFinished("a", true)
        dao.updateTotalPages("a", 250)
        val a = dao.getById("a")!!
        assertTrue(a.finished); assertEquals(250, a.totalPages)
        dao.setFinished("a", false)
        assertFalse(dao.getById("a")!!.finished)
    }

    @Test fun removePorId() = runBlocking {
        dao.insert(book("a")); dao.insert(book("b"))
        dao.deleteById("a")
        assertNull(dao.getById("a"))
        assertEquals(listOf("b"), dao.observeAll().first().map { it.id })
    }
}
