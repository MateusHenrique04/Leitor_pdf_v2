# Proposta: grifo sincronizado sem busca textual

**Status:** IMPLEMENTADA — ver `core/word_sync.py` e
`PDFRenderer.word_rects()`.

A solução adotada chega ao mesmo resultado por um caminho um pouco
diferente do proposto abaixo. Em vez de **gerar o texto do TTS a partir**
da lista de palavras (guardando o índice de cada uma), `text_for_page`
continua como está e a lista de palavras é casada **depois**, contra a
sequência de word-timings que o edge-tts devolve — com um cursor que só
anda para a frente dentro da página, e uma janela de tolerância para
palavras que o TTS fala mas que não existem no texto (marcadores de nota,
siglas soletradas).

Motivo da escolha: preserva `text_for_page` como a única fonte do texto
lido em voz alta — o reflow de parágrafos, a dehifenização e a remoção de
cabeçalho/rodapé continuam num lugar só — e não exige que o TTS e o PDF
concordem palavra a palavra.

Medido numa página real: **98,3% das palavras localizadas**, em 0–4 ms por
trecho (antes: ~9 ms *por palavra*, e devolvendo a linha inteira em vez do
retângulo da palavra). `search_text` continua existindo como caminho de
retorno para quando o TTS não devolve word-timings.

---

*(texto original da proposta abaixo)*

## Problema

`PDFRenderer.search_text(n, text)` existe porque o texto gerado para o TTS
(`text_for_page`) já não é idêntico ao texto nativo da página: hifenização
de fim de linha é corrigida, cabeçalho/rodapé repetido é removido e espaços
são normalizados. Para destacar visualmente o trecho que está sendo lido, o
código precisa *procurar de volta* esse texto alterado dentro do PDF
original — daí as 4 estratégias heurísticas (frase completa → âncora pelo
início → âncora pelo fim → palavras únicas), cada uma um fallback para
quando a anterior não encontra nada.

Isso tem dois custos:
- É heurístico: em layouts irregulares (colunas, tabelas, texto rotacionado)
  pode não achar o trecho certo, ou achar um trecho errado que por acaso
  bate com as palavras de âncora.
- É código relativamente complexo e caro de manter (~170 linhas, 4 casos a
  testar — ver `tests/test_pdf_renderer.py`).

## Alternativa

Em vez de regenerar o texto e procurá-lo de volta no PDF, montar a lista de
palavras da página via `page.get_text("words")` **uma única vez**, e gerar o
texto do TTS **a partir dessa lista**, guardando o índice de cada palavra do
texto final na lista de palavras original. Assim, quando o TTS retorna um
`word-timing`, o código já sabe exatamente qual índice de palavra original
(e portanto qual bbox) corresponde — sem precisar procurar nada.

Esboço:
```python
words = page.get_text("words")  # [(x0,y0,x1,y1,word,block,line,word_idx)]
tts_text, word_index_map = build_tts_text(words, skip_lines=self._skip)
# word_index_map[i] = índice em `words` correspondente à i-ésima palavra de tts_text
```
`_precompute_word_bboxes` passaria a indexar `word_index_map` em vez de
chamar `search_text` por palavra/contexto.

## Riscos

- É uma reescrita não-trivial de `text_for_page` + `search_text` +
  `_precompute_word_bboxes` + `_highlight_ephemeral` — toca o fluxo mais
  usado do app (toda leitura passa por aqui).
- A lógica de remover cabeçalho/rodapé e corrigir hifenização precisa ser
  refeita operando sobre a lista de palavras (com índices), não sobre uma
  string — mais delicado de acertar sem quebrar casos já cobertos pelos
  testes atuais.
- `search_text` continuaria sendo necessária para a **busca manual** do
  usuário (Ctrl+F) — essa proposta não a elimina, só o uso dela no grifo
  sincronizado da leitura.

## Esforço estimado

Alto (vários dias): reescrita de 3 módulos + testes novos + validação
manual extensiva em PDFs variados (a heurística atual, por todas as suas
limitações, já foi ajustada contra uma variedade real de documentos).
