# Como adicionar funcionalidades

## Estrutura

```
lector/
├── main.py                 ← só inicializa
├── config.py                ← cores, fontes, vozes, velocidades, caminhos
├── core/                    ← lógica sem Tk (testável sem UI)
│   ├── pdf_renderer.py      ← abre PDF, renderiza páginas, extrai/busca texto
│   ├── text.py              ← split_sentences() — divisão de texto em frases para o TTS
│   ├── tts.py                ← gera áudio via edge-tts
│   ├── player.py             ← controla pygame (play/pause/posição)
│   ├── dictionary.py         ← busca de definições (dicio.com.br, Wiktionary, Free Dictionary)
│   └── generation.py         ← GenerationGuard — cancela trabalho obsoleto entre threads
├── data/                    ← persistência em JSON (sem Tk)
│   ├── _jsonio.py            ← escrita atômica + backup de JSON corrompido
│   ├── library.py            ← biblioteca de livros (progresso, total de páginas, lido/não lido)
│   ├── highlights.py         ← grifos por livro/página (identificados por id)
│   ├── prefs.py              ← preferências persistidas (voz, velocidade, volume, zoom, etc.)
│   └── history.py            ← histórico de sessões de leitura
└── ui/                      ← interface (CustomTkinter), orquestrada via mixins
    ├── app.py                 ← janela principal — monta os mixins, estado compartilhado
    ├── sidebar.py             ← biblioteca de livros, abrir/remover PDF
    ├── viewer.py              ← canvas da página, zoom/pan, busca no PDF
    ├── controls.py            ← transporte (play/pause/±página/±frase), loop de leitura
    ├── right_panel.py         ← voz, velocidade, volume, cor de grifo
    ├── highlights_mixin.py    ← criar/apagar/exportar grifos, grifo efêmero da leitura
    ├── dict_popup.py          ← popup de definição de palavra
    ├── toc_window.py          ← janela de sumário
    ├── focus_dialog.py        ← modo foco (temporizador)
    └── widgets.py             ← componentes Tk reutilizáveis (ex.: flat_button)
```

`ui/app.py` junta todos os mixins numa única classe `App`; cada mixin assume
que os outros já inicializaram o estado que usa (ver `App.__init__`). Lógica
que não depende de Tk fica em `core/`/`data/` — é o que os testes em `tests/`
exercitam sem precisar abrir a UI.

## Regra de ouro

| Quero mudar...                        | Edito...                  |
|----------------------------------------|----------------------------|
| Cores / fontes / tamanho               | `config.py`               |
| Vozes disponíveis                      | `config.py` → `VOICES`    |
| Velocidades disponíveis                | `config.py` → `SPEEDS`    |
| Como o PDF é aberto/renderizado/buscado| `core/pdf_renderer.py`    |
| Como o texto é dividido em frases      | `core/text.py`            |
| Motor de TTS                           | `core/tts.py`             |
| Controle de áudio (play/pause/posição) | `core/player.py`          |
| Busca de definição de palavra          | `core/dictionary.py`      |
| O que salva por livro (progresso etc.) | `data/library.py`         |
| Grifos salvos                          | `data/highlights.py`      |
| Preferências do usuário                | `data/prefs.py`           |
| Histórico de sessões                   | `data/history.py`         |
| Biblioteca / abrir PDF                 | `ui/sidebar.py`           |
| Visualizador / zoom / busca na página  | `ui/viewer.py`            |
| Transporte / loop de leitura           | `ui/controls.py`          |
| Painel de voz/velocidade/volume/cor    | `ui/right_panel.py`       |
| Criar/apagar/exportar grifo            | `ui/highlights_mixin.py`  |
| Atalhos de teclado / estado global     | `ui/app.py`               |

## Exemplos práticos

### Adicionar um novo campo persistido por livro
1. Em `data/library.py`, criar uma função `save_algo(path, valor)` que lê
   `_load()`, escreve a chave e chama `_save(d)` — siga o padrão de
   `save_total`/`mark_finished`.
2. Usar essa função em `ui/sidebar.py` ou `ui/controls.py`, onde o evento
   que deve disparar a mudança acontece.

### Adicionar busca no texto
`core/pdf_renderer.py` já expõe `search_text(page, texto)` (4 estratégias
heurísticas — ver docstring do método) e `text_in_rect(page, x0, y0, x1, y1)`
para extrair o texto sob um grifo. A UI nunca deve acessar `PDFRenderer._doc`
diretamente — adicione um método público no renderer em vez disso.

### Trocar resolução do PDF
Em `config.py`, mudar `PDF_RENDER_DPI` para valor maior (melhor qualidade)
ou menor (mais rápido).

### Adicionar nova voz
Em `config.py`, adicionar no dicionário `VOICES`:
```python
"Nova Voz (PT-BR)": "pt-BR-NomeNeural",
```
O dropdown em `ui/right_panel.py` se atualiza automaticamente.

### Adicionar nova velocidade
Em `config.py`, adicionar no dicionário `SPEEDS`:
```python
"3×": 200,
```
O grid de botões em `ui/right_panel.py` se atualiza automaticamente.

### Mudar como o texto é dividido em frases para o TTS
Edite `split_sentences()` em `core/text.py` (não em `ui/controls.py` — a
função é compartilhada entre o loop de leitura e a navegação por frase,
e tem testes dedicados em `tests/test_text.py`).
