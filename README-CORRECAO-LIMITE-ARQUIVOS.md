# Correção do limite de 1.000 arquivos

Esta versão corrige a causa do erro `Too many files. Maximum number of files is 1000.`

A versão anterior definia os limites com `setdefault`, mas o FastAPI pode passar explicitamente `max_files=1000` ao parser multipart. Agora os valores configurados substituem explicitamente os padrões no serviço da API e no serviço de backup.

## Aplicar no Windows (PowerShell)

1. Extraia este ZIP numa pasta nova ou substitua os arquivos do projeto pela versão atualizada.
2. Abra o PowerShell na pasta que contém `docker-compose.yml`.
3. Execute:

```powershell
docker compose down
docker compose build --no-cache api backup
docker compose up -d --force-recreate api backup
```

4. Confira os logs:

```powershell
docker logs backup-api --tail 50
docker logs backup-service --tail 50
```

5. Tente novamente o backup. Não é necessário gerar outro `backup-client.exe` para esta correção.

## Limite configurável

Por padrão, o parser aceita até 100.000 arquivos e 100.000 campos por requisição. Para alterar, ajuste `BACKUP_MAX_MULTIPART_FILES` e `BACKUP_MAX_MULTIPART_FIELDS` no `docker-compose.yml` e recrie os serviços `api` e `backup`.

Isso remove o limite artificial de 1.000 arquivos, mas não torna armazenamento ou tamanho literalmente infinitos. O espaço em disco e a duração da compactação continuam sendo limites reais; lotes retomáveis são uma melhoria separada ainda necessária para transferências resilientes muito grandes.
