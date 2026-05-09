@echo off
echo =========================================
echo  ANPR Command Center - Setup Script
echo =========================================

echo.
echo [1/4] Creating video directory...
if not exist "video" mkdir video
echo Note: Please place your video file as "video.mp4" inside the "video" folder.

echo.
echo [2/4] Setting up Python backend...
cd backend
echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat
echo Upgrading pip...
python -m pip install --upgrade pip
echo Installing requirements...
pip install -r requirements.txt
cd ..

echo.
echo [3/5] Setting up React frontend...
cd frontend
echo Installing npm dependencies...
call npm install
cd ..

echo.
echo [4/5] Installing Tesseract OCR (Required for Python 3.13+)...
echo Checking if Tesseract is installed...
where tesseract >nul 2>&1
if %errorlevel% neq 0 (
    echo Tesseract not found. Installing via winget...
    winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements
    echo Tesseract installed! You might need to restart your terminal or computer if Tesseract is not found later.
) else (
    echo Tesseract is already installed!
)

echo.
echo [5/5] Setup completed successfully!
echo.
echo You can now run start.bat to start both servers.
pause
