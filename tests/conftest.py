"""
Fixtures compartilhadas. Cria um PDF de teste em memória com pymupdf
(evita depender de um arquivo .pdf binário versionado no repositório).
"""
import sys
from pathlib import Path

# Garante que o pacote do projeto (config.py, core/, data/, ui/) seja
# importável quando os testes rodam via `pytest` a partir da raiz.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf
import pytest


@pytest.fixture
def sample_pdf_path(tmp_path) -> str:
    """Gera um PDF de 3 páginas com texto conhecido e retorna o caminho."""
    doc = pymupdf.open()

    page1 = doc.new_page()
    page1.insert_text((72, 72), "Capitulo Um")
    page1.insert_text((72, 100), "O gato preto dormia tranquilo sobre o telhado quente.")
    page1.insert_text((72, 120), "Ele nao se importava com o barulho da rua.")

    page2 = doc.new_page()
    page2.insert_text((72, 72), "Segunda pagina de teste com outro conteudo qualquer.")

    page3 = doc.new_page()
    page3.insert_text((72, 72), "Terceira e ultima pagina do documento de teste.")

    try:
        doc.set_toc([[1, "Capitulo Um", 1], [1, "Segunda Parte", 2]])
    except Exception:
        pass

    path = tmp_path / "sample.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def corrupted_pdf_path(tmp_path) -> str:
    """Cria um arquivo .pdf com conteúdo inválido (não é um PDF de verdade)."""
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"isto nao e um pdf valido")
    return str(path)
