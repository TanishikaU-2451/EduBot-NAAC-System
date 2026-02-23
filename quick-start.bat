@echo off
echo ========================================
echo NAAC Compliance Intelligence System
echo Quick Start Setup
echo ========================================
echo.

REM Step 1: Check Ollama Installation
echo [1/4] Checking Ollama installation...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Ollama not found. Please install first:
    echo    1. Download from https://ollama.ai/download/windows
    echo    2. Install and restart terminal
    echo    3. Run: setup-ollama.bat
    echo    4. Then run this script again
    pause
    exit /b 1
)
echo ✅ Ollama is installed

REM Step 2: Check Llama3 Model
echo [2/4] Checking Llama3 model...
ollama list | findstr llama3 >nul 2>&1
if errorlevel 1 (
    echo ❌ Llama3 model not found. Installing now...
    echo This may take 5-10 minutes depending on internet speed...
    ollama pull llama3
    if errorlevel 1 (
        echo ❌ Failed to download Llama3 model
        echo Check your internet connection and try again
        pause
        exit /b 1
    )
    echo ✅ Llama3 model installed successfully
) else (
    echo ✅ Llama3 model is available
)

REM Step 3: Start Ollama Service
echo [3/4] Starting Ollama service...
start /B ollama serve
timeout /t 3 /nobreak >nul

REM Test Ollama connection
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo ❌ Ollama service not responding
    echo Please ensure Ollama is running and try again
    pause
    exit /b 1
)
echo ✅ Ollama service is running

REM Step 4: Display next steps
echo [4/4] Ready to start system!
echo.
echo ========================================
echo NEXT STEPS:
echo ========================================
echo.
echo 1. 📁 ADD DOCUMENTS (Optional - can do after startup):
echo    - Place NAAC PDFs in: data\naac_documents\
echo    - Place MVSR PDFs in: data\mvsr_documents\
echo    - See DOCUMENT_UPLOAD_GUIDE.md for details
echo.
echo 2. 🚀 START THE SYSTEM:
echo    - Run: start.bat
echo    - Backend will start at: http://localhost:8000
echo    - Frontend will start at: http://localhost:3000
echo.
echo 3. 💬 BEGIN USING:
echo    - Open http://localhost:3000 in your browser
echo    - Ask questions about NAAC compliance
echo    - Upload more documents as needed
echo.
echo Ready to launch? Press any key to start the system...
pause >nul

echo Starting NAAC Compliance Intelligence System...
call start.bat