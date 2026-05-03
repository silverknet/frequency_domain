@echo off
setlocal enabledelayedexpansion
title Stem Splitter

set "DIR=%~dp0"
set "DIR=%DIR:~0,-1%"
set "SCRIPT=%DIR%\stem_splitter.py"
set "VENV=%DIR%\.venv"
set "VENV_PYTHON=%VENV%\Scripts\python.exe"

echo.
echo  ==========================================
echo       Stem Splitter
echo  ==========================================
echo.

:: ── Python ──────────────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo.
    echo  Download and install Python from: python.org/downloads
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause & exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.9 or newer required.
    echo  Download from: python.org/downloads
    echo.
    pause & exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  OK  %%v

:: ── ffmpeg ───────────────────────────────────────────────────────────────────
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo  [ Installing ffmpeg via winget... ]
    winget install --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo.
        echo  Could not auto-install ffmpeg.
        echo  Install manually with one of:
        echo    winget install Gyan.FFmpeg
        echo    choco install ffmpeg
        echo.
        pause & exit /b 1
    )
    echo  OK  ffmpeg  (you may need to restart for PATH to update^)
) else (
    echo  OK  ffmpeg
)

:: ── Virtual environment ──────────────────────────────────────────────────────
if not exist "%VENV_PYTHON%" (
    echo  [ Creating virtual environment... ]
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
)
echo  OK  Virtual environment

:: ── PyTorch — CUDA build for NVIDIA GPUs, CPU otherwise ─────────────────────
"%VENV_PYTHON%" -c "import torch; exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if errorlevel 1 (
    set "CUDA_DETECTED=0"
    where nvidia-smi >nul 2>&1
    if not errorlevel 1 (
        nvidia-smi >nul 2>&1
        if not errorlevel 1 set "CUDA_DETECTED=1"
    )

    "%VENV_PYTHON%" -c "import torch" >nul 2>&1
    if errorlevel 1 (
        if "!CUDA_DETECTED!"=="1" (
            echo  [ Installing PyTorch with CUDA support... ]
            "%VENV_PYTHON%" -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cu121
        ) else (
            echo  [ Installing PyTorch ^(CPU^)... ]
            "%VENV_PYTHON%" -m pip install --quiet torch
        )
    ) else (
        if "!CUDA_DETECTED!"=="1" (
            echo  [ Upgrading PyTorch with CUDA support... ]
            "%VENV_PYTHON%" -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cu121 --upgrade
        )
    )
)
echo  OK  PyTorch

:: ── Demucs ───────────────────────────────────────────────────────────────────
"%VENV_PYTHON%" -c "import demucs" >nul 2>&1
if errorlevel 1 (
    echo  [ Installing demucs... ]
    "%VENV_PYTHON%" -m pip install --quiet demucs
) else (
    echo  OK  Demucs
)

:: ── torchcodec (audio save backend) ─────────────────────────────────────────
"%VENV_PYTHON%" -c "import torchcodec" >nul 2>&1
if errorlevel 1 (
    echo  [ Installing torchcodec... ]
    "%VENV_PYTHON%" -m pip install --quiet torchcodec >nul 2>&1
    if errorlevel 1 (
        echo  torchcodec unavailable, pinning torchaudio to compatible version...
        "%VENV_PYTHON%" -m pip install --quiet "torchaudio<2.5" --upgrade
    ) else (
        echo  OK  torchcodec
    )
) else (
    echo  OK  torchcodec
)

echo.
echo  Launching...
echo.

"%VENV_PYTHON%" "%SCRIPT%"

if errorlevel 1 (
    echo.
    echo  Stem Splitter exited with an error.
    pause
)
