$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "Instalando as dependências necessárias para compilar o cliente..." -ForegroundColor Cyan
python -m pip install -r .\client\requirements-client.txt

Write-Host "Compilando backup-client.exe com o código atualizado..." -ForegroundColor Cyan
python -m PyInstaller --noconfirm --clean .\backup-client.spec

if (-not (Test-Path .\dist\backup-client.exe)) {
    throw "A compilação terminou sem gerar dist\backup-client.exe."
}

Write-Host "Cliente atualizado criado em dist\backup-client.exe" -ForegroundColor Green
