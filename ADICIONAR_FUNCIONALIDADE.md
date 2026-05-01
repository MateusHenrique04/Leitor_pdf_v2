# Como adicionar funcionalidades

## Estrutura

```
lector/
├── main.py              ← só inicializa
├── config.py            ← cores, vozes, velocidades, caminhos
├── core/
│   ├── pdf_renderer.py  ← abre PDF, renderiza páginas como imagem, extrai texto
│   ├── tts.py           ← gera áudio via edge-tts
│   └── player.py        ← controla pygame
├── data/
│   ├── library.py       ← lê/escreve library.json
│   └── history.py       ← lê/escreve history.json
└── ui/
    └── app.py           ← janela principal
```

## Regra de ouro

| Quero mudar...           | Edito...              |
|--------------------------|-----------------------|
| Cores / fontes / tamanho | `config.py`           |
| Vozes disponíveis        | `config.py` → VOICES  |
| Velocidades disponíveis  | `config.py` → SPEEDS  |
| Como o PDF é aberto      | `core/pdf_renderer.py`|
| Motor de TTS             | `core/tts.py`         |
| Controle de áudio        | `core/player.py`      |
| O que salva por livro    | `data/library.py`     |
| Histórico de sessões     | `data/history.py`     |
| Layout / botões          | `ui/app.py`           |

## Exemplos práticos

### Adicionar grifos
1. Criar `data/grifos.py` com `add()`, `get()`, `delete()`
2. Em `ui/app.py`, adicionar botão "Grifar" no painel direito
3. Capturar clique no canvas → converter coordenadas → salvar via `grifos.add()`

### Adicionar busca no texto
1. Em `core/pdf_renderer.py`, usar `page.search_for(termo)` → retorna lista de coordenadas
2. Em `ui/app.py`, desenhar retângulos no canvas sobre as coordenadas encontradas

### Trocar resolução do PDF
Em `config.py`, mudar `PDF_RENDER_DPI = 150` para valor maior (melhor qualidade)
ou menor (mais rápido).

### Adicionar nova voz
Em `config.py`, adicionar no dicionário VOICES:
```python
"Nova Voz (PT-BR)": "pt-BR-NomeNeural",
```
O dropdown se atualiza automaticamente.

### Adicionar nova velocidade
Em `config.py`, adicionar no dicionário SPEEDS:
```python
"3×": 200,
```
O grid de botões se atualiza automaticamente.
