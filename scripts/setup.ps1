# One-time setup: venv, backend deps, frontend deps. Run from repo root.
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r member2\backend\requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Push-Location member1\frontend; npm install; Pop-Location
Write-Host "Setup complete. Run scripts\dev.ps1 to start both servers."
