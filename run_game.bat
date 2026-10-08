@echo off
setlocal
title The Greeks Are Back — Antiochus 2.0

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m pip install -r requirements.txt
    py -3 main.py
    exit /b %errorlevel%
)

where python >nul 2>&1
if %errorlevel%==0 (
    python -m pip install -r requirements.txt
    python main.py
    exit /b %errorlevel%
)

echo Python 3.11+ was not found.
echo Install Python from https://www.python.org/downloads/
pause
