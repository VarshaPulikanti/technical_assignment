# Start both servers (run from assignment folder)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "Stopping old servers on 8000 / 3000..."
Get-NetTCPConnection -LocalPort 8000,3000 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Write-Host "Backend http://127.0.0.1:8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\activate; uvicorn app.main:app --host 127.0.0.1 --port 8000"

Start-Sleep -Seconds 3

Write-Host "Frontend http://localhost:3000 (clean .next)"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; if (Test-Path .next) { Remove-Item -Recurse -Force .next }; npm run dev"

Write-Host "Done. Open http://localhost:3000 in ~30 seconds."
