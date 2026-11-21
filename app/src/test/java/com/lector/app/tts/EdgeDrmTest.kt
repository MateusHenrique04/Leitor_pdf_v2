package com.lector.app.tts

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Valores gerados rodando o drm.py ORIGINAL do edge-tts 7.2.8 com o TRUSTED_CLIENT_TOKEN real.
 * Se estes testes falharem, o porte do token está errado (e o serviço recusaria a conexão).
 */
class EdgeDrmTest {
    private val token = EdgeConstants.TRUSTED_CLIENT_TOKEN

    @Test fun vetor1() = assertEquals(
        "8C2FFDE3E8CB7C9C-24B30FBE46FE35C1D7CF4BBAB939A3E6FC6339EA695CF8FAAB32C21670D202A0",
        EdgeDrm.generateSecMsGec(1763553600.0, token),
    )

    @Test fun vetor2() = assertEquals(
        "2CD23A2CA0B2595A-F3C846C370E05F9CC83ACC5F995C5F5D87A4D0F14CE8936A0F902E64099E38A2",
        EdgeDrm.generateSecMsGec(1700000000.5, token),
    )

    @Test fun vetor3() = assertEquals(
        "2D1951B5991865A9-9BBEE7BB61D7DFEF1880360F2C69FC9188BA618B0672852724E063AFDC154A20",
        EdgeDrm.generateSecMsGec(1763540000.123, token),
    )

    @Test fun tokenMudaACada5Minutos() {
        // 1763553600 já é múltiplo de 300: ...899.999 ainda é o mesmo bloco, ...900 é o próximo.
        assertEquals(
            EdgeDrm.generateSecMsGec(1763553600.0, token),
            EdgeDrm.generateSecMsGec(1763553899.999, token),
        )
        assertEquals(
            "E3AAB8DAC577FEBC-5EE74DA11D679BEFFAF9661F49C9296FABA83418E8BBBC1F3BC755194B75EABF",
            EdgeDrm.generateSecMsGec(1763553900.0, token),
        )
    }

    @Test fun formatoDoToken() {
        val t = EdgeDrm.generateSecMsGec(1763553600.0, token)
        assertEquals(16 + 1 + 64, t.length)
        assertEquals('-', t[16])
    }
}
