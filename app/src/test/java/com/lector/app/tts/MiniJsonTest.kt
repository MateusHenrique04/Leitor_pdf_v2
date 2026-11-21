package com.lector.app.tts

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class MiniJsonTest {
    @Test fun objetoAninhado() {
        val v = MiniJson.parse("""{"a":1,"b":[true,false,null,"x"],"c":{"d":2.5}}""") as Map<*, *>
        assertEquals(1L, v["a"])
        assertEquals(listOf(true, false, null, "x"), v["b"])
        assertEquals(2.5, (v["c"] as Map<*, *>)["d"])
    }

    @Test fun textoComEscapes() {
        assertEquals("a\"b\\c/d\ne\u00E1", MiniJson.parse(""""a\"b\\c\/d\ne\u00e1""""))
    }

    @Test fun numerosInteirosGrandesFicamLong() {
        assertEquals(12345678901L, MiniJson.parse("12345678901"))
        assertEquals(-5L, MiniJson.parse("-5"))
        assertEquals(1.5e3, MiniJson.parse("1.5e3"))
    }

    @Test fun espacosEVazios() {
        assertEquals(emptyMap<String, Any?>(), MiniJson.parse("  { }  "))
        assertEquals(emptyList<Any?>(), MiniJson.parse("[ ]"))
        assertNull(MiniJson.parse("null"))
    }

    @Test fun erros() {
        for (bad in listOf("", "{", "[1,", """{"a" 1}""", "tru", """"aberta""", "{} x")) {
            try {
                MiniJson.parse(bad)
                fail("deveria falhar: $bad")
            } catch (e: IllegalArgumentException) {
                assertTrue(e.message!!.startsWith("JSON inválido"))
            }
        }
    }
}
