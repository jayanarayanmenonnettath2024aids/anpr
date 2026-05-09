@echo off
echo =========================================
echo  ANPR Command Center - Start Servers
echo =========================================

echo Starting Backend Server...
start "ANPR Backend" cmd /c "cd backend && set VIDEO_SOURCE=../video/video.mp4 && call venv\Scripts\activate.bat && python main.py"

echo Starting Frontend Server...
start "ANPR Frontend" cmd /c "cd frontend && npm run dev"

echo.
echo Both servers are starting in separate windows.
echo - Backend will be available at http://localhost:8000
echo - Frontend will be available at http://localhost:5173
echo.
echo Please ensure you have placed your video file in the 'video' folder.
pause
