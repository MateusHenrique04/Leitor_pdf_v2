package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Test

class BookTitleTest {
    @Test fun removeExtensaoPdf() = assertEquals("Livro", BookTitle.fromFileName("Livro.pdf"))
    @Test fun extensaoEmMaiusculas() = assertEquals("Livro", BookTitle.fromFileName("Livro.PDF"))
    @Test fun sublinhadosViramEspaco() = assertEquals("Fundamentos da Matematica", BookTitle.fromFileName("Fundamentos_da_Matematica.pdf"))
    @Test fun colapsaEspacosEAparas() = assertEquals("A B", BookTitle.fromFileName("  A   B .pdf"))
    @Test fun mantemHifenEPontosInternos() = assertEquals("cap-1 v2.0", BookTitle.fromFileName("cap-1 v2.0.pdf"))
    @Test fun nuloViraSemTitulo() = assertEquals(BookTitle.UNTITLED, BookTitle.fromFileName(null))
    @Test fun vazioViraSemTitulo() = assertEquals(BookTitle.UNTITLED, BookTitle.fromFileName("   "))
    @Test fun apenasExtensaoViraSemTitulo() = assertEquals(BookTitle.UNTITLED, BookTitle.fromFileName(".pdf"))
}
