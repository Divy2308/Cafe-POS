@echo off
REM Quick start script for development with Tailwind CSS

echo ==========================================
echo POS Cafe - Development Setup
echo ==========================================
echo.

REM Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Node.js is not installed!
    echo Please install Node.js from https://nodejs.org/
    echo.
    pause
    exit /b 1
)

echo ✅ Node.js found
node --version
npm --version
echo.

REM Check if node_modules exists
if not exist "node_modules\" (
    echo Installing dependencies...
    call npm install
    echo.
)

REM Start the Tailwind watch process
echo.
echo ==========================================
echo Starting Tailwind CSS watch mode...
echo ==========================================
echo Watching for changes in templates/
echo CSS will rebuild to static/output.css
echo.
echo Press Ctrl+C to stop
echo.

call npm run watch
