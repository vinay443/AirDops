# Build AirDops.exe locally on Windows (the GitHub Actions workflow does the same).
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-build.txt
.\.venv\Scripts\python scripts\fetch_rnnoise.py
.\.venv\Scripts\python scripts\make_icon.py
.\.venv\Scripts\pyinstaller --noconfirm --clean airdops.spec
Write-Host "Built: dist\AirDops.exe"
