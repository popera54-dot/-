# היוונים חוזרים — The Greeks Are Back

A cinematic, full-screen Hanukkah escape-room game for Windows, built with Python, Pygame, OpenCV, and NumPy.

## Included game flow

- 1 — Antiochus 2.0 intrusion sequence and countdown HUD
- 2 — Player registration with webcam capture
- 3 — Oil Cipher; the playable answer is 3832
- 4 — Visual Hanukkah maze with a numbered exit, plus the physical 48-piece puzzle location board
- 5 — One digital challenge per registered player, with per-player face verification
- 6 — Dark Light Protocol with the physical code 8421
- 7 — Server color cipher
- 8 — Maccabean Frequency audio pattern; answer 3514
- 9 — Digital Inversion with moving numbers, inverted mouse control, and periodic screen rotation inside the game
- 10 — Family Memory Matrix, three numeric questions, and a repeat exposure when answers are wrong
- 11 — 180-second Quantum Current Lock; X=64, Y=200, Z=66
- 12 — Webcam celebration finale with motion/voice energy, original generated synth music, and a 5-to-1 countdown

The operator console lets you edit the Stage 3 clue location, Stage 7 clue location, and as many Stage 4 puzzle-piece locations as needed. Settings are stored locally in `data/operator_config.json`.

The 10-minute Trivia Lifeline can appear while the family is in stages 5–7; every correct answer adds 60 seconds. The adaptive time manager can skip intermediate stages when there is no longer enough time to complete the remaining challenges and finale.

## Run on Windows

1. Install Python 3.11 or later.
2. Open PowerShell in the repository folder.
3. Install dependencies and start the game:

```powershell
python -m pip install -r requirements.txt
python main.py
```

The finale uses the webcam to estimate movement and optionally opens the microphone through `sounddevice`. Audio input is measured live only to drive the energy meter; the game does not save audio recordings.

## Operator controls

- `Ctrl + Shift + Right Arrow` — skip the current stage for testing
- `Ctrl + Alt + Shift + Esc` — emergency exit to Windows

## Important limitations

The webcam face comparison is a gameplay prototype based on image-histogram similarity, not production-grade biometric identification. The kiosk is full-screen application mode; it does not disable Windows security features or prevent operating-system shortcuts.
