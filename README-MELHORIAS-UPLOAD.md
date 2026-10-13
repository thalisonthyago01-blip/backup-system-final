# Melhorias de upload para backups grandes

Esta versão aplica melhorias incrementais sem alterar o fluxo da interface ou o protocolo usado pelo executável atual.

## O que mudou

- Aumentados os limites multipart do Starlette para até 100.000 arquivos e 100.000 campos por requisição. São limites altos, mas finitos e configuráveis.
- A API encaminha os arquivos recebidos a partir dos arquivos temporários (`UploadFile.file`) em vez de ler cada arquivo inteiro para a memória com `await file.read()`.
- A compactação ZIP usa nível 1, priorizando velocidade de criação. Isso pode gerar ZIPs maiores que os de nível padrão, em troca de reduzir o tempo de CPU.
- Os limites são configurados no `docker-compose.yml` pelas variáveis `BACKUP_MAX_MULTIPART_FILES` e `BACKUP_MAX_MULTIPART_FIELDS`.

## Como aplicar

Na pasta do projeto, execute no PowerShell:

```powershell
docker compose down
docker compose build --no-cache api backup
docker compose up -d
```

Não é necessário recriar o `backup-client.exe` para essas alterações: o protocolo do cliente não foi modificado. Se você alterar o código do cliente futuramente, use `rebuild-client.ps1`.

## Teste recomendado

1. Confirme que os serviços iniciaram:

   ```powershell
   docker compose ps
   docker logs backup-api --tail 100
   docker logs backup-service --tail 100
   ```

2. Faça backup de uma pasta com mais de 1.000 arquivos.
3. Confirme que o backup terminou, que o ZIP aparece na interface e que a restauração de alguns arquivos funciona.
4. Compare o tempo de execução com o backup anterior.

## Limitações importantes

- Isso remove o limite baixo de 1.000 arquivos, mas não torna o armazenamento literalmente ilimitado. Espaço em disco, memória temporária, tempo de processamento e limites do sistema operacional continuam valendo.
- A API e o serviço de backup ainda recebem um backup por requisição e criam um ZIP final. Upload retomável, lotes que compõem um único backup e paralelismo controlado não foram implementados nesta etapa.
- `proxy_request_buffering off` já estava configurado no Nginx. O volume temporário Docker precisa ter espaço suficiente para os arquivos recebidos e processados.
- Como o nível de compressão passou para 1, os arquivos ZIP podem ocupar mais espaço, especialmente quando os dados são compressíveis. Faça um teste representativo antes de usar em produção.


## Correção adicional do limite de 1.000 arquivos

O FastAPI pode passar explicitamente `max_files=1000` ao parser multipart. A correção atual força os limites configurados mesmo quando o FastAPI fornece esse padrão. É necessário reconstruir e recriar os containers da API e do serviço de backup; reiniciar os containers antigos não aplica mudanças no código.

No PowerShell, na pasta do projeto, execute:

```powershell
docker compose down
docker compose build --no-cache api backup
docker compose up -d --force-recreate
```

Confira os logs com `docker logs backup-api --tail 80` e `docker logs backup-service --tail 80`.
