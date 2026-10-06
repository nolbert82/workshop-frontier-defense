param([switch]$RealCamera, [switch]$SimulatedCamera, [string]$Python = ".venv-dev/Scripts/python.exe", [string]$VisionPython = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path secrets/app.json)) { & $Python scripts/setup.py; if ($LASTEXITCODE) { throw "Échec de préparation" } }
if (!(Test-Path backend/ml/model.joblib)) { & $Python -m backend.ml.train; if ($LASTEXITCODE) { throw "Échec de l'entraînement" } }
if ($RealCamera -and $SimulatedCamera) { throw "Choisir la webcam réelle ou la simulation, pas les deux." }
$selectedVisionPython = & "$PSScriptRoot/select-vision-python.ps1" -Python $VisionPython -FallbackPython $Python -SimulatedCamera:$SimulatedCamera
docker compose --env-file secrets/compose.env up --build -d --wait
if ($LASTEXITCODE) { throw "Échec du démarrage Docker" }
Write-Host "Dashboard : https://localhost — compte dans secrets/operator.txt"
Write-Host "Le service vision doit écouter une interface accessible à Docker. Restreindre TCP 8090 au réseau Docker dans le pare-feu Windows (README)."
$visionArguments = @("-m", "vision.service", "--bind", "0.0.0.0")
if ($SimulatedCamera) { $visionArguments += "--simulate" }
& $selectedVisionPython @visionArguments
