$ErrorActionPreference = "Stop"

python -m pip install -r requirements.txt
python -m pytest
python -m PyInstaller --clean --noconfirm trade_lead_collector.spec
if (-not (Test-Path "dist\config.json")) {
    Copy-Item "config.example.json" "dist\config.json"
}

Write-Host "构建完成：dist\外贸客户采集软件_v10.exe"
