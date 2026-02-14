@echo off
chcp 65001 >nul 2>&1
title Bing Rewards - Mobile Only
echo ============================================================
echo   BING REWARDS - MOBILE SEARCH ONLY
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

echo [OK] Menjalankan mobile search...
echo.
".venv\Scripts\python.exe" -m bing_rewards -m
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
pause >nul
