# 🛡️ היוונים חוזרים — The Greeks Are Back

Cinematic Hanukkah digital escape room for Windows.

## Vision

A premium, full-screen cyber-thriller escape-room experience based on the supplied Hebrew specification.

Core pillars:

- Cinematic hacker / Ancient Greece visual language
- Full-screen game presentation
- Animated HUD, scanlines, particles, glitches and dramatic transitions
- 12-stage progression
- Physical clue integration through configurable text
- Webcam-based player registration
- Per-player verification gates
- Timers, audio cues and adaptive pacing
- Hidden operator controls for testing and emergency exit

## Current build

The first commit establishes the visual/gameplay foundation:

- cinematic intro sequence
- operator setup screen
- global 60-minute game timer
- animated cyber-Hanukkah background
- stage routing
- player roster UI
- webcam player enrollment prototype
- first cipher stage with the specified A/B/C/D equations

## Run on Windows

1. Install Python 3.11+.
2. Open a terminal in the repository.
3. Run:

```powershell
python -m pip install -r requirements.txt
python main.py
```

The app opens in a borderless full-screen presentation.

### Operator controls

- `Ctrl + Shift + Right` — skip current stage
- `Ctrl + Shift + Esc` — safe emergency exit to Windows

The operator panel is reachable before the game starts.

## Important

The application currently uses a **safe application-level kiosk presentation** (borderless full-screen / always-on-top behavior). It does not disable Windows security mechanisms such as Task Manager. A stronger managed-device kiosk layer can be added later if the deployment environment requires it.
