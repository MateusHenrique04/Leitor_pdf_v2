# Documentação do TCC

Documentação do Trabalho de Conclusão de Curso, preenchida sobre o
modelo institucional (28 seções) a partir do sistema deste repositório.

## Arquivos

| Arquivo | O que é |
|---|---|
| `TCC-Lector.md` | Texto completo. É a **fonte** — edite aqui |
| `TCC-Lector.docx` | Versão para o Word, gerada a partir do `.md` |
| `gerar_docx.py` | Converte o `.md` no `.docx` |
| `imagens/` | Capturas de tela do aplicativo usadas na seção 13 |

## Regerar o `.docx` depois de editar o `.md`

```bash
python docs/TCC/gerar_docx.py
```

O documento sai com os estilos de título do Word (Título 1/2/3), que é o
que o modelo institucional pede para o sumário automático. Ao abrir no
Word, clique com o botão direito sobre o sumário e escolha **Atualizar
campo** para preencher os números de página.

Formatação aplicada: Arial 12, espaçamento 1,5, texto justificado,
margens de 3 cm (superior e esquerda) e 2 cm (inferior e direita),
conforme a ABNT NBR 14724.

## O que falta preencher

As pendências estão listadas ao final do próprio documento (seção 28), e
são, em resumo:

1. Finalidade do trabalho conforme o regulamento da Unifran (folha de rosto).
2. Nome do orientador (folha de rosto).
3. Data da apresentação final (seção 23).
4. Literatura acadêmica na fundamentação teórica e nas referências.
5. Confirmação da divisão de responsabilidades (seção 27).
6. Revisão ortográfica e técnica final.

Os dois primeiros itens aparecem no `.md` e em `gerar_docx.py` marcados
entre colchetes, como `[NOME DO ORIENTADOR]`.

## Sobre os números citados no documento

Todas as medições apresentadas nas seções 17 e 18 foram obtidas com
instrumentação sobre a própria aplicação e são reprodutíveis. As
principais: silêncio entre trechos (1,39 s → 0,45 s), localização de
palavras na página (95,7% a 98,3%), proporção da janela ocupada pela
página (14,7% → 33,0% a 72,7%) e contraste dos pares texto/fundo
(11 de 19 reprovados → 0 de 20).

Não inclua números que não possa reproduzir. Se alterar o sistema,
refaça a medição antes de atualizar o texto.
