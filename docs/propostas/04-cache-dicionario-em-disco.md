# Proposta: persistir o cache do dicionário em disco

**Status:** aguardando aprovação — não implementar sem decisão do autor.

## Problema

`core/dictionary._dict_cache` (protegido por lock e limitado a 500 entradas
desde a auditoria de concorrência) só existe em memória — reinicia a cada
abertura do app. Palavras já consultadas em sessões anteriores são buscadas
de novo nos backends externos (dicio.com.br, Wiktionary, Free Dictionary
API), mesmo sendo definições que não mudam.

## Alternativa

Persistir o cache em um arquivo JSON (`DICTIONARY_CACHE_FILE`, seguindo o
mesmo padrão de `data/_jsonio.py` usado por `library.json`/`prefs.json`),
carregado na primeira chamada de `lookup()` e salvo quando uma entrada nova
é adicionada (ou em lote, com debounce, para não gravar em disco a cada
clique de palavra).

Pontos de design a decidir:
- **O que persistir**: só resultados positivos (que não expiram) faz
  sentido persistir; resultados negativos (TTL de 10 min) não valem a pena
  persistir entre sessões, já que a janela de validade é curta.
- **Limite de tamanho em disco**: o limite de 500 entradas em memória
  existe para a sessão atual; persistir pode usar a mesma política LRU ou
  um limite maior, já que é só leitura esporádica, não um hot path.
- **Invalidação**: se o site/API de origem mudar a definição de uma palavra
  (raro, mas possível), o cache em disco nunca seria atualizado
  automaticamente — precisa de um jeito de limpar manualmente (ex.: apagar
  o arquivo, ou um botão "limpar cache" nas preferências).

## Riscos

- Arquivo de cache pode crescer sem o usuário perceber (ex.: quem lê muitos
  livros em idiomas diferentes acumula milhares de palavras) — precisa de
  um limite e política de descarte claros antes de implementar, não só "o
  que já existe em memória, salvo em disco".
- Primeira leitura do arquivo de cache ao abrir o app é mais um I/O de
  disco na inicialização — pequeno, mas deve rodar em background como os
  outros `data/*.json`, não bloquear a UI.

## Esforço estimado

Baixo: é essencialmente aplicar o padrão já usado em `data/prefs.py`/
`data/library.py` ao `_dict_cache` existente, decidindo antes os pontos de
design acima (o que persistir, limite, invalidação).
