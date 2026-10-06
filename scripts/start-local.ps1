param([switch]$RealCamera, [switch]$SimulatedCamera, [string]$Python = "", [string]$VisionPython = "")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (!$Python) {
    if (Test-Path .venv-dev/Scripts/python.exe) { $Python = (Resolve-Path .venv-dev/Scripts/python.exe).Path }
    elseif (Test-Path .venv/Scripts/python.exe) { $Python = (Resolve-Path .venv/Scripts/python.exe).Path }
    else { throw "Créer un environnement Python selon le README." }
}
if (!(Test-Path secrets/app.json)) { & $Python scripts/setup.py; if ($LASTEXITCODE) { throw "Échec de préparation" } }
if (!(Test-Path backend/ml/model.joblib)) { & $Python -m backend.ml.train; if ($LASTEXITCODE) { throw "Échec de l'entraînement" } }
if (!(Test-Path frontend/dist/index.html)) { throw "Construire le dashboard : cd frontend ; pnpm install ; pnpm build" }
New-Item -ItemType Directory -Force -Path data | Out-Null
if ($RealCamera -and $SimulatedCamera) { throw "Choisir la webcam réelle ou la simulation, pas les deux." }
$selectedVisionPython = & "$PSScriptRoot/select-vision-python.ps1" -Python $VisionPython -FallbackPython $Python -SimulatedCamera:$SimulatedCamera
$env:SENTINEL_SECURE_COOKIES = "false"
$visionArguments = @('-m', 'vision.service', '--url', 'http://127.0.0.1:8000')
if ($SimulatedCamera) { $visionArguments += '--simulate' }
$vision = Start-Process -FilePath $selectedVisionPython -ArgumentList $visionArguments -WindowStyle Hidden -PassThru -RedirectStandardOutput data/vision.stdout.log -RedirectStandardError data/vision.stderr.log
Write-Host "Dashboard : http://127.0.0.1:8000 (compte dans secrets/operator.txt)"
Write-Host "Mode local : SQLite et HTTP sur loopback. Ctrl+C pour arreter."
try { & $Python -m uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers }
finally { Stop-Process -Id $vision.Id -ErrorAction SilentlyContinue; Remove-Item Env:SENTINEL_SECURE_COOKIES -ErrorAction SilentlyContinue }
