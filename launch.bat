@echo off
title The Greeks Are Back - Antiochus 2.0
python main.py
if errorlevel 1 (
  echo.
  echo The game could not start. Check that Python and the requirements are installed.
  pause
)
