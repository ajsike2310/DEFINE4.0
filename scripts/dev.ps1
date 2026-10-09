# Start backend (8000) and frontend (5173). Database tables are created automatically on backend start.
$env:PYTHONPATH = (Get-Location).Path
Start-Process powershell -ArgumentList "-NoExit","-Command","`$env:PYTHONPATH='$($env:PYTHONPATH)'; .venv\Scripts\python.exe -m uvicorn member2.backend.app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd member1\frontend; npm run dev"
Write-Host "Backend: http://localhost:8000/docs   Frontend: http://localhost:5173"
