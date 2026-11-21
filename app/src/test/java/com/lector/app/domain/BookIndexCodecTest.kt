package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class BookIndexCodecTest {
    private val chunks = listOf(
        Chunk(0, 0, 0, 0, "Primeiro trecho, com acentuação: ção."),
        Chunk(1, 0, 1, 1, "Cruza a página \\ com barra, \t tab e emoji 😀."),
        Chunk(2, 1, 1, 0, "Linha\ncom quebra\r\ne fim\\"),
    )
    private val index = BookIndex(1, 2, chunks)

    @Test fun idaEVoltaPreservaTudo() {
        val back = BookIndexCodec.decode(BookIndexCodec.encode(index))
        assertEquals(index, back)
    }

    @Test fun indiceVazioVoltaVazio() {
        val vazio = BookIndex(1, 3, emptyList())
        assertEquals(vazio, BookIndexCodec.decode(BookIndexCodec.encode(vazio)))
    }

    @Test fun cabecalhoInvalidoDevolveNull() {
        assertNull(BookIndexCodec.decode(""))
        assertNull(BookIndexCodec.decode("qualquer coisa"))
        assertNull(BookIndexCodec.decode("LECTOR-INDEX\t99\t1\t2\t0\n"))
        assertNull(BookIndexCodec.decode("LECTOR-INDEX\t1\tx\t2\t0\n"))
    }

    @Test fun arquivoCortadoDevolveNull() {
        val s = BookIndexCodec.encode(index)
        assertNull(BookIndexCodec.decode(s.substring(0, s.length - 12)))
        assertNull(BookIndexCodec.decode(s.trimEnd('\n'))) // sem o \n final
    }

    @Test fun quantidadeDiferenteDoCabecalhoDevolveNull() {
        val s = BookIndexCodec.encode(index).replaceFirst("\t3\n", "\t4\n")
        assertNull(BookIndexCodec.decode(s))
    }

    @Test fun indiceForaDeOrdemDevolveNull() {
        val torto = BookIndex(1, 2, listOf(Chunk(0, 0, 0, 0, "a"), Chunk(5, 0, 0, 1, "b")))
        assertNull(BookIndexCodec.decode(BookIndexCodec.encode(torto)))
    }

    @Test fun paginaForaDoLivroDevolveNull() {
        val ruim = BookIndex(1, 2, listOf(Chunk(0, 7, 7, 0, "a")))
        assertNull(BookIndexCodec.decode(BookIndexCodec.encode(ruim)))
    }

    @Test fun escapeInvalidoDevolveNull() {
        val s = "LECTOR-INDEX\t1\t1\t1\t1\n0\t0\t0\t0\tfoo\\x\n"
        assertNull(BookIndexCodec.decode(s))
    }

    @Test fun guardaAVersaoDoPlanner() {
        val back = BookIndexCodec.decode(BookIndexCodec.encode(BookIndex(7, 1, listOf(Chunk(0, 0, 0, 0, "a")))))
        assertNotNull(back)
        assertEquals(7, back!!.plannerVersion)
    }
}
