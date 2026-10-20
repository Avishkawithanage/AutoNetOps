@echo off
setlocal EnableExtensions
title AutoNetOps
cd /d "%~dp0"
set "ROOT=%CD%"
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"
set "PORT=8000"

echo ============================================
echo   AutoNetOps - setup and start
echo ============================================

rem ---- 1. Python virtual environment + dependencies
if not exist "%PY%" (
    echo [1/4] Creating Python virtual environment...
    where python >nul 2>&1 || ( echo ERROR: Python 3.12+ not found in PATH. Install it from python.org & pause & exit /b 1 )
    python -m venv "%ROOT%\backend\.venv" || ( echo ERROR: venv creation failed & pause & exit /b 1 )
    "%PY%" -m pip install --quiet --upgrade pip
    "%PY%" -m pip install --quiet -r "%ROOT%\backend\requirements-dev.txt" || ( echo ERROR: pip install failed & pause & exit /b 1 )
) else (
    echo [1/4] Python environment OK
)

rem ---- 2. Dashboard build (needs Node.js, only when dist is missing)
if not exist "%ROOT%\frontend\dist\index.html" (
    echo [2/4] Building dashboard...
    where npm >nul 2>&1 || ( echo ERROR: Node.js not found. Install it from nodejs.org & pause & exit /b 1 )
    pushd "%ROOT%\frontend"
    if not exist node_modules ( call npm install --no-audit --no-fund || ( echo ERROR: npm install failed & popd & pause & exit /b 1 ) )
    call npm run build || ( echo ERROR: build failed & popd & pause & exit /b 1 )
    popd
) else (
    echo [2/4] Dashboard build OK
)

rem ---- 3. .env (first run: demo mode with a generated admin password)
if not exist "%ROOT%\.env" (
    echo [3/4] Creating .env in demo ^(mock^) mode...
    for /f %%P in ('powershell -NoProfile -Command "[Convert]::ToBase64String((1..12 | ForEach-Object {Get-Random -Maximum 256}) -as [byte[]]).Replace('+','A').Replace('/','B').Replace('=','')"') do set "GENPW=%%P"
    > "%ROOT%\.env" (
        echo DRIVER_MODE=mock
        echo SSH_STRICT_HOST_KEY=false
        echo ADMIN_USERNAME=admin
        echo ADMIN_PASSWORD=%GENPW%
    )
    echo.
    echo   Login:    admin
    echo   Password: %GENPW%   ^(saved in .env^)
    echo.
) else (
    echo [3/4] .env OK
)

rem ---- 4. Start
echo [4/4] Starting server on http://localhost:%PORT%  ^(Ctrl+C to stop^)
start "" /min powershell -NoProfile -Command "Start-Sleep 4; Start-Process 'http://localhost:%PORT%'"
cd /d "%ROOT%\backend"
"%PY%" -m uvicorn app.main:app --port %PORT%

echo.
echo Server stopped.
pause
