param([string]$Python = '.venv/Scripts/python.exe', [switch]$Usb)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path secrets/app.json)) { & $Python scripts/setup.py; if ($LASTEXITCODE) { throw 'Echec de preparation' } }
if (!(Test-Path vision/model/yolo26n.pt)) { throw 'Poids YOLO absents : placer yolo26n.pt dans vision/model.' }
$composeArguments = @('--env-file', 'secrets/compose.env', '-f', 'compose.yaml')
if ($Usb) { $composeArguments += @('-f', 'compose.usb.yaml') }
docker compose @composeArguments up --build -d --wait
if ($LASTEXITCODE) { throw 'Echec du demarrage Docker' }
Write-Host 'Dashboard : https://localhost (compte dans secrets/operator.txt)'
Write-Host 'Vision dans Docker : configurer VISION_SOURCE ou utiliser la configuration USB Linux.'
