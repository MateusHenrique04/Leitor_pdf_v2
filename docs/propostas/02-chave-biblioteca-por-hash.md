# Proposta: chave da biblioteca por hash do conteúdo em vez de caminho

**Status:** aguardando aprovação — não implementar sem decisão do autor.

## Problema

`data/library.py` e `data/highlights.py` identificam um livro pelo caminho
absoluto do arquivo (`str`, usado como chave do dict em `library.json` e
`highlights.json`). Se o usuário mover ou renomear o PDF, o app não
reconhece que é "o mesmo livro" — progresso de leitura e grifos salvos ficam
órfãos, associados a um caminho que não existe mais, e um novo registro é
criado do zero ao reabrir o arquivo movido.

## Alternativa

Identificar o livro por um hash do conteúdo (ex.: SHA-256 dos primeiros N
MB do arquivo, ou de todo o arquivo — a decidir pelo trade-off
custo/robustez) em vez do caminho. O caminho passaria a ser só um campo de
metadado (`"path": "..."`) dentro do registro, atualizado toda vez que o
livro é aberto a partir de um caminho diferente do já registrado para aquele
hash.

Esboço de migração:
```python
def _migrate_to_hash_keys(library_data: dict) -> dict:
    """Reconstrói library.json usando hash do conteúdo como chave,
    preservando o caminho atual em cada registro."""
    new_data = {}
    for path, meta in library_data.items():
        if not os.path.exists(path):
            continue  # não há como gerar hash de um arquivo que não existe mais
        key = _hash_file(path)
        new_data[key] = {**meta, "path": path}
    return new_data
```
A mesma migração precisaria rodar para `highlights.json`.

## Riscos

- **Migração em arquivos existentes é obrigatória** e tem um caso sem
  solução: se o arquivo já foi movido/apagado *antes* da migração rodar,
  não há como calcular o hash — o registro antigo (por caminho) seria
  perdido nesse caso específico. Precisa de uma decisão explícita de como
  comunicar isso ao usuário (ex.: manter o registro antigo órfão com um
  aviso, em vez de simplesmente descartá-lo).
- Calcular hash de PDFs grandes a cada abertura tem custo de I/O/CPU —
  precisa decidir se é do arquivo inteiro ou só de uma amostra (ex.:
  primeiros/últimos X KB + tamanho do arquivo), o que é mais rápido mas
  tecnicamente pode colidir (dois PDFs diferentes com a mesma amostra).
- Dois arquivos *idênticos* em caminhos diferentes (ex.: cópia de backup)
  passariam a ser tratados como "o mesmo livro" — pode ser desejável ou não,
  dependendo do uso esperado.

## Esforço estimado

Médio: a mudança de chave em si é localizada (`data/library.py`,
`data/highlights.py`), mas a migração "sem perder dados de ninguém" e o
tratamento do caso sem solução acima merecem decisão explícita do autor
antes de implementar.
