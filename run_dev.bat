@echo off
TITLE Project Launcher

echo ====================================================
echo Starting Backend (FastAPI) in a new window...
echo ====================================================
:: Uses the explicit travel environment to run uvicorn
start "Backend (FastAPI)" cmd /k "cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo ====================================================
echo Starting Frontend (Bun) in a new window...
echo ====================================================
:: Runs the frontend. Change "cd ." to "cd frontend_folder" if your frontend is in a subfolder.
start "Frontend (Bun)" cmd /k "cd frontend && bun run dev"

echo ====================================================
echo Both servers are starting up! You can close this window.
echo ====================================================
pause