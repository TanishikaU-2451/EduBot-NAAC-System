@echo off
echo Starting NAAC Compliance Intelligence System...

REM Check if virtual environment exists
if not exist "naac_env" (
    echo Creating virtual environment...
    python -m venv naac_env
)

REM Activate virtual environment
call naac_env\Scripts\activate

REM Install/update dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Create directories
if not exist "data" mkdir data
if not exist "data\naac_documents" mkdir data\naac_documents
if not exist "data\mvsr_documents" mkdir data\mvsr_documents
if not exist "cache" mkdir cache
if not exist "uploads" mkdir uploads
if not exist "chroma_db" mkdir chroma_db

REM Copy environment file if it doesn't exist
if not exist ".env" (
    copy .env.example .env
    echo Created .env file - please configure it before running the system
    pause
    exit /b 1
)

REM Check if Ollama is running
echo Checking Ollama service...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo ERROR: Ollama is not running or not accessible at http://localhost:11434
    echo Please install and start Ollama with Llama3 model:
    echo   1. Install Ollama from https://ollama.ai/
    echo   2. Run: ollama pull llama3
    echo   3. Ensure Ollama service is running
    pause
    exit /b 1
)

echo Starting FastAPI backend...
cd backend
start "NAAC Backend" python -m api.main

REM Wait a moment for backend to start
timeout /t 5 /nobreak >nul

REM Check if Node.js is installed
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

REM Start frontend
echo Starting React frontend...
cd ..\frontend

REM Install npm dependencies if needed
if not exist "node_modules" (
    echo Installing npm dependencies...
    npm install
)

start "NAAC Frontend" npm start

echo System is starting up...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo Press any key to open the application in your browser...
pause >nul

REM Open browser
start http://localhost:3000

echo NAAC Compliance Intelligence System is now running!
echo.
echo To stop the system:
echo 1. Close this command window
echo 2. Or press Ctrl+C in the backend/frontend windows
echo.
pause