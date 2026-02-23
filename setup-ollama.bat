@echo off
echo Installing Ollama and Llama3 model...

REM Check if Ollama is installed
ollama --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Ollama is not installed or not in PATH
    echo Please:
    echo 1. Download Ollama from https://ollama.ai/download/windows
    echo 2. Install it and restart your terminal
    echo 3. Run this script again
    pause
    exit /b 1
)

echo Ollama is installed! Pulling Llama3 model...
echo This may take several minutes depending on your internet speed...
ollama pull llama3

echo Verifying Llama3 model...
ollama list

echo Testing Ollama service...
ollama serve &
timeout /t 5 /nobreak >nul
curl -s http://localhost:11434/api/tags

echo Ollama setup complete!
echo Llama3 model is ready for use.
pause