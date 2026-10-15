# Offline Package and Model Staging Script (PowerShell)
# Pre-stages all wheels and model assets for offline/air-gapped deployment.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$WheelhouseDir = Join-Path $ScriptDir "wheelhouse"
$ModelsDir = Join-Path $ScriptDir "models"

Write-Host "=== Enterprise Intranet Assistant - Offline Staging ===" -ForegroundColor Cyan

if (-not (Test-Path $WheelhouseDir)) { New-Item -ItemType Directory -Path $WheelhouseDir | Out-Null }
if (-not (Test-Path $ModelsDir)) { New-Item -ItemType Directory -Path $ModelsDir | Out-Null }

Write-Host "[1/3] Downloading pinned wheels from approved internal package source..."
$pythonScript = @"
import tomllib
with open(r'$ProjectRoot\pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
for dep in data['project']['dependencies']:
    print(dep)
"@

$deps = python -c "$pythonScript"
$depsFile = Join-Path $ScriptDir "requirements-temp.txt"
$deps | Out-File -FilePath $depsFile -Encoding utf8

python -m pip download --dest $WheelhouseDir -r $depsFile
Remove-Item -Force $depsFile

Write-Host "[2/3] Wheels staged successfully in $WheelhouseDir." -ForegroundColor Green

Write-Host "[3/3] Checking model directory..."
$stagedModels = Get-ChildItem -Path $ModelsDir
if ($stagedModels.Count -eq 0) {
    Write-Host "NOTICE: '$ModelsDir' is empty. Copy approved internal model files here before deployment." -ForegroundColor Yellow
} else {
    Write-Host "Model files detected in $ModelsDir." -ForegroundColor Green
}

Write-Host "=== Staging complete. Containers can build and run offline. ===" -ForegroundColor Cyan
