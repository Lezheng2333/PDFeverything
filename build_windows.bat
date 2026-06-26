@echo off
cd /d "%~dp0"

echo.
echo ======================================================
echo   PDFeverything - Windows Setup Builder
echo ======================================================
echo.

where python >nul 2>&1
if not errorlevel 1 goto run

where py >nul 2>&1
if not errorlevel 1 (
    py -3 build_windows.py
    goto end
)

echo Python not found.
echo Please install Python 3.10+ from python.org/downloads/
echo Then run this script again.
pause
exit /b 1

:run
python build_windows.py

:end
if errorlevel 1 (
    echo.
    echo ======================================================
    echo   Build failed. See errors above.
    echo ======================================================
)
pause
