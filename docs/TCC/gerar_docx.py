"""
Gera o arquivo .docx do TCC a partir de TCC-Lector.md.

Os títulos recebem os estilos de título do Word (Título 1/2/3), que é o
que permite usar Referências > Sumário > Sumário Automático, conforme a
instrução do modelo institucional.

Uso:
    python docs/TCC/gerar_docx.py
"""
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BASE = Path(__file__).resolve().parent
FONTE = "Arial"
CORPO_PT = 12
MONO_PT = 8

CAPA = {
    "instituicao": "UNIVERSIDADE DE FRANCA (UNIFRAN)",
    "curso": "CIÊNCIA DA COMPUTAÇÃO",
    "autores": ["MATEUS HENRIQUE SILVA SOUZA", "VINÍCIUS NUNES BENEDITO"],
    "titulo": "LECTOR",
    "subtitulo": ("Leitor de PDF com narração sintetizada e acompanhamento "
                  "visual sincronizado palavra a palavra"),
    "cidade": "FRANCA",
    "ano": "2026",
    "natureza": ("Trabalho de Conclusão de Curso apresentado ao Curso de "
                 "Ciência da Computação da Universidade de Franca (Unifran), "
                 "como requisito para [DESCREVER A FINALIDADE CONFORME "
                 "REGULAMENTO INSTITUCIONAL]."),
    "orientador": "Orientador: Prof. Dr. [NOME DO ORIENTADOR]",
}


# ── formatação base ───────────────────────────────────────────────

def configurar(doc: Document):
    """Margens e fonte padrão segundo a ABNT NBR 14724."""
    for sec in doc.sections:
        sec.top_margin = Cm(3)
        sec.left_margin = Cm(3)
        sec.bottom_margin = Cm(2)
        sec.right_margin = Cm(2)
    normal = doc.styles["Normal"]
    normal.font.name = FONTE
    normal.font.size = Pt(CORPO_PT)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONTE)
    pf = normal.paragraph_format
    pf.line_spacing = 1.5
    pf.space_after = Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for nivel, tam in ((1, 12), (2, 12), (3, 12)):
        est = doc.styles[f"Heading {nivel}"]
        est.font.name = FONTE
        est.font.size = Pt(tam)
        est.font.bold = True
        est.font.color.rgb = RGBColor(0, 0, 0)
        est.paragraph_format.space_before = Pt(18)
        est.paragraph_format.space_after = Pt(12)
        est.paragraph_format.line_spacing = 1.5
        est.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT


def centrado(doc, texto, *, tam=CORPO_PT, negrito=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(texto)
    r.font.size = Pt(tam)
    r.font.bold = negrito
    return p


def linhas_vazias(doc, quantas: int):
    """Distribui o conteúdo da capa com linhas em branco.

    Usar `space_after` grande empurrava a cidade e o ano para uma segunda
    página — a capa da ABNT tem de caber em uma folha só.
    """
    for _ in range(quantas):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0


def quebra_pagina(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ── páginas pré-textuais ──────────────────────────────────────────

def capa(doc):
    centrado(doc, CAPA["instituicao"], negrito=True)
    centrado(doc, CAPA["curso"], negrito=True)
    linhas_vazias(doc, 7)
    for autor in CAPA["autores"]:
        centrado(doc, autor)
    linhas_vazias(doc, 9)
    centrado(doc, CAPA["titulo"], tam=16, negrito=True)
    centrado(doc, CAPA["subtitulo"])
    linhas_vazias(doc, 9)
    centrado(doc, CAPA["cidade"])
    centrado(doc, CAPA["ano"])
    quebra_pagina(doc)


def folha_de_rosto(doc):
    for autor in CAPA["autores"]:
        centrado(doc, autor)
    linhas_vazias(doc, 7)
    centrado(doc, CAPA["titulo"], tam=16, negrito=True)
    centrado(doc, CAPA["subtitulo"])
    linhas_vazias(doc, 5)

    # Nota de natureza do trabalho: recuo de 8 cm, espaçamento simples
    for texto in (CAPA["natureza"], CAPA["orientador"]):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(8)
        pf.line_spacing = 1.0
        pf.space_after = Pt(10)
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        r = p.add_run(texto)
        r.font.size = Pt(10)

    linhas_vazias(doc, 5)
    centrado(doc, CAPA["cidade"])
    centrado(doc, CAPA["ano"])
    quebra_pagina(doc)


def sumario_automatico(doc):
    centrado(doc, "SUMÁRIO", tam=12, negrito=True)
    linhas_vazias(doc, 1)
    p = doc.add_paragraph()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), r'TOC \o "1-3" \h \z \u')
    aviso = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = ("Clique com o botão direito aqui e escolha “Atualizar campo” "
              "para gerar o sumário.")
    aviso.append(t)
    fld.append(aviso)
    p._p.append(fld)
    quebra_pagina(doc)


# ── conversão do corpo ────────────────────────────────────────────

_INLINE = re.compile(r"(\*\*.+?\*\*|`.+?`|\*.+?\*)")


def escrever_inline(par, texto):
    """Aplica negrito, itálico e monoespaçado no texto de um parágrafo."""
    for pedaco in _INLINE.split(texto):
        if not pedaco:
            continue
        if pedaco.startswith("**") and pedaco.endswith("**"):
            par.add_run(pedaco[2:-2]).bold = True
        elif pedaco.startswith("`") and pedaco.endswith("`"):
            r = par.add_run(pedaco[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(10)
        elif pedaco.startswith("*") and pedaco.endswith("*"):
            par.add_run(pedaco[1:-1]).italic = True
        else:
            par.add_run(pedaco)


def add_tabela(doc, linhas):
    cabecalho = [c.strip() for c in linhas[0].strip("|").split("|")]
    corpo = [[c.strip() for c in ln.strip("|").split("|")] for ln in linhas[2:]]
    t = doc.add_table(rows=1, cols=len(cabecalho))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, texto in enumerate(cabecalho):
        cel = t.rows[0].cells[i]
        cel.text = ""
        p = cel.paragraphs[0]
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(texto.replace("**", ""))
        r.bold = True
        r.font.size = Pt(10)
    for linha in corpo:
        cels = t.add_row().cells
        for i, texto in enumerate(linha[:len(cabecalho)]):
            cels[i].text = ""
            p = cels[i].paragraphs[0]
            p.paragraph_format.line_spacing = 1.0
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            escrever_inline(p, texto)
            for r in p.runs:
                r.font.size = Pt(10)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def add_bloco_codigo(doc, linhas):
    """
    Diagramas em arte ASCII: monoespaçado, sem justificação.

    `keep_with_next` mantém o diagrama inteiro na mesma página — sem isso
    o Word o parte ao meio quando ele cai perto do fim da folha.
    """
    for ln in linhas:
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = 1.0
        pf.space_after = Pt(0)
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pf.keep_together = True
        pf.keep_with_next = True
        r = p.add_run(ln if ln else " ")
        r.font.name = "Consolas"
        r.font.size = Pt(MONO_PT)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def converter(doc, markdown: str):
    linhas = markdown.splitlines()
    i = 0
    # pula tudo que antecede a seção 1 (capa e sumário vêm do gerador)
    while i < len(linhas) and not linhas[i].startswith("# 1 "):
        i += 1

    while i < len(linhas):
        ln = linhas[i]

        if ln.startswith("```"):
            bloco = []
            i += 1
            while i < len(linhas) and not linhas[i].startswith("```"):
                bloco.append(linhas[i])
                i += 1
            add_bloco_codigo(doc, bloco)
            i += 1
            continue

        if ln.startswith("|") and i + 1 < len(linhas) and set(linhas[i+1]) <= set("|-: "):
            tabela = []
            while i < len(linhas) and linhas[i].startswith("|"):
                tabela.append(linhas[i])
                i += 1
            add_tabela(doc, tabela)
            continue

        m = re.match(r"!\[(.*?)\]\((.+?)\)", ln)
        if m:
            caminho = BASE / m.group(2)
            if caminho.exists():
                doc.add_picture(str(caminho), width=Cm(15))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1
            continue

        if ln.startswith("### "):
            doc.add_heading(ln[4:].strip(), level=3)
            i += 1
            continue
        if ln.startswith("## "):
            doc.add_heading(ln[3:].strip(), level=2)
            i += 1
            continue
        if ln.startswith("# "):
            doc.add_heading(ln[2:].strip(), level=1)
            i += 1
            continue

        if ln.strip() == "---":
            i += 1
            continue

        if ln.startswith("> "):
            bloco = []
            while i < len(linhas) and linhas[i].startswith(">"):
                bloco.append(linhas[i].lstrip(">").strip())
                i += 1
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = Cm(2)
            pf.line_spacing = 1.0
            pf.space_after = Pt(10)
            escrever_inline(p, " ".join(x for x in bloco if x))
            for r in p.runs:
                r.font.size = Pt(10)
            continue

        m = re.match(r"^(\d+)\.\s+(.*)", ln)
        if m:
            bloco = [m.group(2)]
            i += 1
            while i < len(linhas) and linhas[i].startswith("   "):
                bloco.append(linhas[i].strip())
                i += 1
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.line_spacing = 1.5
            escrever_inline(p, " ".join(bloco))
            continue

        if re.match(r"^[-*]\s+", ln):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.line_spacing = 1.5
            escrever_inline(p, re.sub(r"^[-*]\s+", "", ln))
            i += 1
            continue

        if not ln.strip():
            i += 1
            continue

        # parágrafo comum: junta as linhas até a próxima linha em branco
        bloco = []
        while i < len(linhas) and linhas[i].strip() and not re.match(
                r"^(#|\||>|```|!\[|\d+\.\s|[-*]\s|---)", linhas[i]):
            bloco.append(linhas[i].strip())
            i += 1
        texto = " ".join(bloco)
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(1.25)
        # legendas de figura ficam centralizadas e menores
        if texto.startswith("*Figura") or texto.startswith("*Quadro"):
            p.paragraph_format.first_line_indent = Cm(0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            escrever_inline(p, texto)
            for r in p.runs:
                r.font.size = Pt(10)
        else:
            escrever_inline(p, texto)


def main():
    md = (BASE / "TCC-Lector.md").read_text(encoding="utf-8")
    doc = Document()
    configurar(doc)
    capa(doc)
    folha_de_rosto(doc)
    sumario_automatico(doc)
    converter(doc, md)
    destino = BASE / "TCC-Lector.docx"
    doc.save(destino)
    print(f"gerado: {destino}")
    print(f"  parágrafos: {len(doc.paragraphs)}  tabelas: {len(doc.tables)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
