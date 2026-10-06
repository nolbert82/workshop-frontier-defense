param([string]$Python = '.venv-dev/Scripts/python.exe', [string]$VisionPython = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path secrets/app.json)) { & $Python scripts/setup.py; if ($LASTEXITCODE) { throw 'echec de preparation' } }
if (!(Test-Path backend/ml/model.joblib)) { & $Python -m backend.ml.train; if ($LASTEXITCODE) { throw 'echec de l entrainement' } }
$selectedVisionPython = & "$PSScriptRoot/select-vision-python.ps1" -Python $VisionPython -FallbackPython $Python
docker compose --env-file secrets/compose.env up --build -d --wait
if ($LASTEXITCODE) { throw 'echec du demarrage Docker' }
Write-Host 'Dashboard : https://localhost (compte dans secrets/operator.txt)'
Write-Host 'Le service vision doit etre accessible a Docker. Restreindre TCP 8090 au reseau Docker dans le pare-feu Windows.'
$visionArguments = @('-m', 'vision.service', '--bind', '0.0.0.0')
& $selectedVisionPython @visionArguments
