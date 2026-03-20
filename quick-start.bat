@echo off
echo ========================================
echo NAAC Compliance Intelligence System
echo Quick Start Setup
echo ========================================
echo.

REM Step 1: Check .env file
echo [1/3] Checking environment file...
if not exist ".env" (
    copy .env.example .env
    echo ✅ Created .env from template
) else (
    echo ✅ .env file found
)

REM Step 2: Check Hugging Face token
echo [2/3] Checking HF_API_TOKEN...
set HF_API_TOKEN_VALUE=
for /f "tokens=1,* delims==" %%A in ('findstr /B /C:"HF_API_TOKEN=" .env') do set HF_API_TOKEN_VALUE=%%B

if "%HF_API_TOKEN_VALUE%"=="" (
    echo ❌ HF_API_TOKEN is missing or empty in .env
    echo    1. Create a Hugging Face token from https://huggingface.co/settings/tokens
    echo    2. Edit .env and set HF_API_TOKEN=your_token_here
    echo    3. Run this script again
    pause
    exit /b 1
)
echo ✅ HF_API_TOKEN is configured

REM Step 3: Display next steps
echo [3/3] Ready to start system!
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