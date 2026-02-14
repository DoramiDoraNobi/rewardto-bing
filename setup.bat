@echo off
chcp 65001 >nul 2>&1
title Bing Rewards - Setup
echo ============================================================
echo   ⚙️  BING REWARDS - SETUP / INSTALL
echo ============================================================
echo.

cd /d "%~dp0"

echo [*] Mengecek tools yang tersedia...
echo.

REM Try uv first (recommended)
where uv >nul 2>&1
if %errorlevel%==0 (
    echo [✓] uv ditemukan!
    echo [*] Menjalankan uv sync...
    echo.
    uv sync
    echo.
    echo [✓] Setup selesai! Sekarang jalankan run.bat
    goto :done
)

REM Fallback to pip
where python >nul 2>&1
if %errorlevel%==0 (
    echo [✓] Python ditemukan
    echo [*] Membuat virtual environment...
    python -m venv .venv
    echo [*] Menginstall dependencies...
    ".venv\Scripts\pip.exe" install -e .
    echo.
    echo [✓] Setup selesai! Sekarang jalankan run.bat
    goto :done
)

echo [✗] Tidak ada Python atau uv yang ditemukan!
echo.
echo     Pilih salah satu untuk install:
echo     1. uv (direkomendasikan): https://docs.astral.sh/uv/
echo     2. Python 3.10+: https://python.org
echo.

:done
echo.
echo ============================================================
echo   Tekan tombol apa saja untuk menutup...
echo ============================================================
pause >nul
