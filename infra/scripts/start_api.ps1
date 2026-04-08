param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$venvPython = Join-Path (Split-Path -Parent $repoRoot) ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Python not found at $venvPython"
}

# Free the target port if needed
$conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($conn) {
    $procIds = $conn | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $procIds) {
        if ($procId -ne 0) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Output "Starting API on http://127.0.0.1:$Port"
Set-Location $repoRoot
& $venvPython -m uvicorn --app-dir $repoRoot apps.api.main:app --host 0.0.0.0 --port $Port
