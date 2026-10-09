# Backup Client

O `backup-client.exe` funciona como um aplicativo residente do Windows.

## Uso normal

Basta abrir:

```text
backup-client.exe
```

Não é mais necessário executar `agent` pelo Prompt de Comando.

Na primeira inicialização, o client:

1. registra a máquina no servidor, se necessário;
2. sincroniza as pastas locais;
3. inicia o servidor local usado pela interface web;
4. fica consultando os jobs de backup/restauração;
5. cria o ícone **Backup Client** na área de notificação do Windows;
6. registra a inicialização automática no Windows para o usuário atual.

O Windows pode colocar o ícone dentro de **Ícones ocultos**. Isso também pode ser configurado pelo próprio usuário nas opções da barra de tarefas.

## Encerrar

Clique com o botão direito no ícone do Backup Client e escolha **Encerrar client**.

O encerramento é apenas da execução atual. Na próxima entrada no Windows, o client será iniciado novamente enquanto a inicialização automática estiver registrada.

## Compilar o executável

No Windows, com a virtualenv ativa:

```powershell
pip install -r client/requirements-client.txt
pyinstaller --clean backup-client.spec
```

O executável será criado em:

```text
dist/backup-client.exe
```

A versão compilada usa modo `windowed`, portanto não abre uma janela preta de Prompt de Comando.
