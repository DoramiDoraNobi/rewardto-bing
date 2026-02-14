@echo off
chcp 65001 >nul 2>&1
title Bing Rewards Searcher
echo ============================================================
echo   BING REWARDS SEARCHER
echo ============================================================
echo.

cd /d "%~dp0"

REM Auto-create .venv if not found
if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment tidak ditemukan. Membuat otomatis...
    echo.
    call :setup_venv
    if not exist ".venv\Scripts\python.exe" (
        echo [X] Gagal membuat virtual environment!
        echo     Install Python 3.10+ dari https://python.org
        echo     Atau install uv dari https://docs.astral.sh/uv/
        goto :end
    )
)

echo [OK] Virtual environment siap
echo [*] Menjalankan Bing Rewards...
echo.
".venv\Scripts\python.exe" -m bing_rewards
goto :end

:setup_venv
where uv >nul 2>&1
if %errorlevel%==0 (
    echo [*] Menggunakan uv untuk setup...
    uv sync
    echo [OK] Setup dengan uv selesai
    goto :eof
)
where python >nul 2>&1
if %errorlevel%==0 (
    echo [*] Menggunakan pip untuk setup...
    python -m venv .venv
    ".venv\Scripts\pip.exe" install -e .
    echo [OK] Setup dengan pip selesai
    goto :eof
)
echo [X] Tidak ada Python atau uv yang ditemukan!
goto :eof

:end
echo.
echo ============================================================
echo   Program selesai. Tekan tombol apa saja untuk menutup...
echo ============================================================
pause >nul
