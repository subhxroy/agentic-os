@echo off
echo ========================================
echo  AgentOS Desktop - Starting
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

REM Check Node
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Install Node 18+ from nodejs.org
    pause
    exit /b 1
)

REM Install Python dependencies
echo [1/3] Installing Python dependencies...
cd /d "%~dp0phase0"
pip install -r "../electron/requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Some Python packages failed to install. Voice features may be unavailable.
)

REM Install Node dependencies
echo [2/3] Installing Electron dependencies...
cd /d "%~dp0electron"
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] npm install failed
    pause
    exit /b 1
)

REM Launch Electron
echo [3/3] Starting AgentOS Desktop...
call npm start

pause
