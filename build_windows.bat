@echo off
setlocal
title Build The Greeks Are Back for Windows

python -m pip install --upgrade pip
if errorlevel 1 goto :error

python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

python -m PyInstaller --noconfirm --clean --windowed --name TheGreeksAreBack --collect-all cv2 --collect-all pygame --collect-all sounddevice --collect-all numpy --hidden-import pygame.sndarray main.py
if errorlevel 1 goto :error

(
  echo THE GREEKS ARE BACK - WINDOWS BUILD
  echo.
  echo Keep this folder intact after extraction.
  echo Run TheGreeksAreBack.exe to start the game.
  echo The game creates a data folder next to the executable.
  echo Webcam access is needed for registration and face-check stages.
  echo Microphone access is optional.
  echo Emergency exit: Ctrl + Alt + Shift + Esc.
) > dist\TheGreeksAreBack\HOW_TO_RUN.txt

(
  echo @echo off
  echo cd /d "%%~dp0"
  echo start "" "%%~dp0TheGreeksAreBack.exe"
) > dist\TheGreeksAreBack\StartGame.bat

echo.
echo Build completed: dist\TheGreeksAreBack
echo Zip that folder to share the portable game.
pause
exit /b 0

:error
echo.
echo Build failed. Read the error above before trying again.
pause
exit /b 1
