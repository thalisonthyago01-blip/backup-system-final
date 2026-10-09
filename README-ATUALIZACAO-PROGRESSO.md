# Atualização: barra de progresso de backup

Esta atualização adiciona progresso real de envio ao painel: percentual, bytes enviados/total, arquivos enviados/total e nome relativo do arquivo atual. O progresso é enviado pelo `backup-client.exe` à API e salvo na tabela `backup_jobs`.

## Aplicar no projeto existente

1. Feche o `backup-client.exe` pela bandeja do Windows antes de compilar/substituir o executável. Não apague os volumes do Docker.
2. Extraia este pacote na raiz de `backup-system-final`, mantendo as pastas `api`, `client`, `database` e `frontend`. Autorize a substituição dos arquivos.
3. No PowerShell, estando na raiz do projeto, aplique a migração no banco já existente:

   ```powershell
   Get-Content .\database\migrations\006_backup_job_progress.sql -Raw | docker exec -i backup-postgres psql -U backup_user -d backup_system
   ```

4. Reconstrua a API e o frontend:

   ```powershell
   docker compose up --build -d api frontend
   ```

5. Recompile o cliente Windows usando o código que agora reporta progresso. No PowerShell, execute:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\rebuild-client.ps1
   ```

   Isso exige Python no Windows e gera o `dist\backup-client.exe` atualizado. Se o executável antigo continuar em execução, feche-o e abra o novo.

6. No navegador, faça uma atualização forçada com `Ctrl+F5`. Inicie um backup novo para testar a barra; tarefas antigas não têm métricas históricas de bytes.

## Observações

- Não execute `docker compose down -v`; isso pode apagar o banco e os backups guardados nos volumes.
- A barra mostra bytes lidos e enviados pelo cliente durante a transmissão da requisição, mais a contagem de arquivos. Após chegar a 100%, o servidor ainda pode estar compactando/registrando o backup; nesse momento, a mensagem muda para finalização.
- O arquivo de cliente compilado não é recriado nesta máquina Linux; por isso o script PowerShell deve ser executado no Windows do usuário.
