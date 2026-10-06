param([string]$Python = "", [string]$FallbackPython = "")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$candidates = if ($Python) { @($Python) } else {
    @((Join-Path $projectRoot '.venv/Scripts/python.exe'), $FallbackPython)
}
$modules = "['cv2','httpx','ultralytics','torch','cv2_enumerate_cameras']"
foreach ($candidate in $candidates) {
    if (!$candidate -or !(Test-Path -LiteralPath $candidate)) { continue }
    $check = & $candidate -c "import importlib.util; print(all(importlib.util.find_spec(m) is not None for m in $modules))" 2>$null
    if ($LASTEXITCODE -eq 0 -and $check -eq 'True') { return (Resolve-Path -LiteralPath $candidate).Path }
}
throw "Dépendances vision absentes : installer requirements.txt dans l'environnement Python choisi, puis utiliser -VisionPython CHEMIN."
