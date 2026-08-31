# Phantom Fish — arranque local (Windows / PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creando entorno virtual..." -ForegroundColor Cyan
    py -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Se creó .env desde el ejemplo. Revisá SECRET_KEY antes de exponerlo." -ForegroundColor Yellow
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty IPAddress)
Write-Host ""
Write-Host "  App:  http://localhost:8000" -ForegroundColor Green
if ($ip) { Write-Host "  Red:  http://$ip`:8000  (desde el celular en la misma wifi)" -ForegroundColor Green }
Write-Host ""

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
