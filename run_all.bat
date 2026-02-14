@echo off
chcp 65001 >nul 2>&1
title Bing Rewards - Daily + Search (Semua)
echo ============================================================
echo   BING REWARDS - DAILY ACTIVITIES + SEARCH (SEMUA)
echo ============================================================
echo.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment tidak ditemukan. Membuat otomatis...
    call :setup_venv
    if not exist ".venv\Scripts\python.exe" (
        echo [X] Gagal membuat .venv! Install Python/uv dulu.
        goto :end
    )
)

REM Check if playwright is installed
".venv\Scripts\python.exe" -c "import playwright" 2>nul
if %errorlevel% neq 0 (
    echo [*] Menginstall Playwright...
    ".venv\Scripts\pip.exe" install "playwright>=1.40"
)

echo [OK] Menjalankan daily activities + search...
echo.
".venv\Scripts\python.exe" -m bing_rewards --daily
goto :end

:setup_venv
where uv >nul 2>&1
if %errorlevel%==0 ( uv sync & goto :eof )
where python >nul 2>&1
if %errorlevel%==0 ( python -m venv .venv & ".venv\Scripts\pip.exe" install -e . & goto :eof )
echo [X] Tidak ada Python atau uv!
goto :eof

:end
echo.
echo ============================================================
echo   Selesai. Tekan tombol apa saja untuk menutup...
echo ============================================================
pause >nul
