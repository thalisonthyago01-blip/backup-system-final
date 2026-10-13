# Uploads em lotes e retomáveis

Esta atualização substitui o envio de todos os arquivos em uma única requisição por uma sessão de upload com uma requisição por arquivo. O servidor mantém uma lista persistente dos arquivos confirmados no volume `backup-temp` e só gera o ZIP quando todos os arquivos da seleção estiverem recebidos.

## O que foi implementado

- Sessão de upload identificada por UUID estável para a mesma seleção de arquivos, raiz e versão dos arquivos (tamanho e data de modificação).
- Envio de um arquivo por requisição, reduzindo o impacto de limites multipart e permitindo retomar os arquivos já confirmados.
- Estado da sessão salvo no serviço de backup; se o cliente for interrompido e a mesma seleção for executada novamente, os arquivos confirmados são ignorados.
- Até três tentativas automáticas por arquivo em caso de falha transitória.
- O servidor recusa finalizar a sessão se houver arquivos pendentes.
- O ZIP final e os metadados continuam no formato que o sistema atual espera; a interface e a restauração não precisam de migração de banco.
- O progresso chega a 100% somente após a finalização do ZIP e o registro dos metadados.

## Instalação (Windows / PowerShell)

Na pasta extraída do projeto:

```powershell
docker compose down
docker compose build --no-cache api backup
docker compose up -d --force-recreate
```

Como o protocolo do cliente mudou, é necessário recompilar o executável. Execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\rebuild-client.ps1
```

O novo executável será gerado em `dist\backup-client.exe`. Substitua a cópia instalada nos computadores clientes pelo executável recém-gerado e reinicie o cliente.

## Teste essencial

1. Faça backup de uma pasta com alguns arquivos e confirme que aparece um único backup na interface.
2. Faça backup de uma pasta com mais de 1.000 arquivos.
3. Interrompa a conexão durante o envio e execute novamente a mesma seleção. Os arquivos já confirmados devem ser ignorados pelo servidor.
4. Restaure alguns arquivos e confira o conteúdo e os caminhos relativos.

## Observações e limites atuais

- O sistema não é literalmente ilimitado: o espaço disponível, o tempo de compactação e o número de arquivos continuam limitados pelos recursos do servidor.
- O envio ocorre sequencialmente por enquanto. Paralelismo configurável é uma próxima otimização; não foi habilitado para evitar sobrecarregar discos ou perder estabilidade antes de medir o desempenho.
- Sessões incompletas ficam no volume `backup-temp` para permitir retomada. A limpeza automática por idade pode ser adicionada posteriormente; monitore o espaço temporário do Docker.
- Se um arquivo for alterado (tamanho ou data de modificação) entre tentativas, ele gera uma nova assinatura de sessão e não reaproveita o upload antigo.
