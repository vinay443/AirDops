# Build AirDops.exe locally on Windows (the GitHub Actions workflow does the same).
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-build.txt
.\.venv\Scripts\python scripts\build_rnnoise.py   # needs LLVM clang or Visual Studio Build Tools
.\.venv\Scripts\python scripts\make_icon.py
.\.venv\Scripts\python scripts\make_version_info.py
$env:AIRDOPS_ONEDIR = "1"
.\.venv\Scripts\pyinstaller --noconfirm --clean airdops.spec
Write-Host "Built: dist\AirDops\AirDops.exe"
# Optional installer (needs Inno Setup 6):
#   & "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer\AirDops.iss
# Single-file exe instead (slower to start):  Remove-Item Env:AIRDOPS_ONEDIR; pyinstaller --noconfirm airdops.spec
