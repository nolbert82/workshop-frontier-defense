param([string]$Python = '.venv/Scripts/python.exe', [switch]$Usb, [Nullable[int]]$Camera = $null)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path secrets/app.json)) { & $Python scripts/setup.py; if ($LASTEXITCODE) { throw 'Echec de preparation' } }
$composeArguments = @('--env-file', 'secrets/compose.env', '-f', 'compose.yaml')
if ($Usb) { $composeArguments += @('-f', 'compose.usb.yaml') }
elseif ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) { $composeArguments += @('-f', 'compose.windows.yaml') }
docker compose @composeArguments up --build -d --wait
if ($LASTEXITCODE) { throw 'Echec du demarrage Docker' }
Write-Host 'Dashboard : https://localhost (compte dans secrets/operator.txt)'
if (!$Usb -and [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    Write-Host 'Webcam USB : capture automatique. Garder ce terminal ouvert ; Ctrl+C arrete la capture.'
    $cameraArguments = @('-m', 'vision.camera_bridge')
    if ($null -ne $Camera) { $cameraArguments += @('--camera', [string]$Camera) }
    & $Python @cameraArguments
    if ($LASTEXITCODE) { throw 'Echec de la capture webcam' }
}
else { Write-Host 'Vision dans Docker : peripherique USB Linux ou source video configuree.' }
