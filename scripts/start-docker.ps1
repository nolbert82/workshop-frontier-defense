param([string]$Python = '.venv/Scripts/python.exe', [switch]$Usb, [Nullable[int]]$Camera = $null)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (!(Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Installer et ouvrir Docker Desktop avant de lancer start.ps1.' }
$windowsCamera = !$Usb -and [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$mutex = $null
$ownsMutex = $false
$started = $false
$composeArguments = @('--env-file', 'secrets/compose.env', '-f', 'compose.yaml')
if ($Usb) { $composeArguments += @('-f', 'compose.usb.yaml') }
elseif ($windowsCamera) { $composeArguments += @('-f', 'compose.windows.yaml') }
try {
    if ($windowsCamera) {
        $mutex = [Threading.Mutex]::new($false, 'Local\SentinelXUsbCapture')
        try { $ownsMutex = $mutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
        if (!$ownsMutex) { throw 'SENTINEL-X est deja lance. Utiliser le terminal existant, ou y faire Ctrl+C avant de relancer.' }
    }
    if ($Python -eq '.venv/Scripts/python.exe') {
        if (!(Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Installer uv avant de lancer start.ps1.' }
        if (!(Test-Path -LiteralPath $Python)) {
            uv python install 3.12.11
            if ($LASTEXITCODE) { throw 'Echec de l installation de Python 3.12.11.' }
            uv venv --python 3.12.11 .venv
            if ($LASTEXITCODE) { throw 'Echec de la creation du venv.' }
        }
        uv pip install --python $Python -r requirements.txt --quiet
        if ($LASTEXITCODE) { throw 'Echec de l installation des dependances.' }
    }
    if (!(Test-Path secrets/app.json)) {
        & $Python scripts/setup.py
        if ($LASTEXITCODE) { throw 'Echec de preparation.' }
    }
    docker compose @composeArguments up --build -d --wait
    if ($LASTEXITCODE) { throw 'Echec du demarrage Docker.' }
    $started = $true
    Write-Host 'Dashboard : https://localhost (compte dans secrets/operator.txt)'
    if ($windowsCamera) {
        Write-Host 'Webcam USB automatique. Garder ce terminal ouvert ; Ctrl+C arrete l application.'
        $cameraArguments = @('-m', 'vision.camera_bridge')
        if ($null -ne $Camera) { $cameraArguments += @('--camera', [string]$Camera) }
        & $Python @cameraArguments
        if ($LASTEXITCODE -and $LASTEXITCODE -ne -1073741510 -and $LASTEXITCODE -ne 130) { throw 'Echec de la capture webcam.' }
    }
}
finally {
    if ($windowsCamera -and $started) { docker compose @composeArguments stop }
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
}
