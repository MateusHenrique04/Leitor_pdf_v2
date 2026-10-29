# Proposta: ampliar a pré-geração de áudio

**Status:** aguardando aprovação — não implementar sem decisão do autor.

## Problema

`ControlsMixin._read_loop` já pré-gera **1 frase adiante**: enquanto o
chunk `i` está tocando, `asyncio.create_task(speak(chunks[i+1], ...))` já
dispara a geração do próximo áudio (ver `core/tts.py`). Isso esconde a
maior parte da latência de rede do TTS entre frases, mas ainda deixa dois
pontos sem tratamento:

1. Se a frase `i+1` falhar ao gerar (rede instável), o loop só percebe
   quando chega nela — mostra o aviso transitório e pula, sem tentar de
   novo.
2. Não há cache: se o usuário voltar uma frase (`←`) e avançar de novo, o
   áudio da frase que já tinha sido gerado é descartado e regenerado do
   zero.

## Alternativa

- Pré-gerar **2 a 3 frases adiante** em vez de 1, mantendo um pequeno cache
  em memória por página (chave: texto do chunk + voz + velocidade), para
  que navegar frase a frase (`←`/`→`) dentro da mesma página reaproveite
  áudio já gerado em vez de chamar o TTS de novo.
- Adicionar uma **nova tentativa** (retry) antes de desistir de uma frase
  que falhou — ex.: tentar de novo uma vez após um pequeno delay, e só
  mostrar o aviso/pular se a segunda tentativa também falhar.
- Avaliar também o `asyncio.sleep(0.15)` fixo entre frases em `_read_loop`
  (comentário no código diz que evita uma *race condition* do pygame).
  Antes de remover ou ajustar esse delay, **testar empiricamente** se ele
  ainda é necessário (reproduzir vozes coladas ou cortadas sem ele, com o
  pygame/mixer na versão atual) — se não for mais necessário, removê-lo
  reduziria uma pausa perceptível entre frases.

## Riscos

- Cache de áudio em memória por página consome RAM proporcional a
  `tamanho_do_audio × frases_pré-geradas` — para páginas com muitas frases
  curtas isso é pequeno, mas merece um limite explícito (ex.: só cachear a
  página atual, descartar ao virar de página).
- Pré-gerar mais frases adiante significa mais chamadas de rede em voo ao
  mesmo tempo — se o usuário pular várias páginas rapidamente, tasks
  `asyncio` de gerações que não serão mais usadas precisam ser canceladas
  explicitamente (hoje isso já é parcialmente coberto pelo token de geração
  do `_read_loop`, mas vale confirmar que nenhuma `asyncio.Task` de TTS fica
  "pendurada" gerando áudio que nunca será tocado).
- Testar o delay de 0.15s requer reproduzir a race condition original do
  pygame — se ela for rara/intermitente, a ausência de erro num teste manual
  não prova que o delay é seguro de remover.

## Esforço estimado

Médio: a pré-geração de +1-2 frases e o cache por página são uma extensão
direta do pipeline já existente em `_read_loop`; o retry é pequeno. Testar
o delay do pygame com confiança é a parte que exige mais cuidado.
