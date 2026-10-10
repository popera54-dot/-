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
- 12 — Webcam celebration finale with motion/voice energy, original generated synth music, a 5-to-1 victory countdown, and a mission debrief with team rank, XP, clears, and errors

The final debrief stays on screen for up to 12 seconds so the team can review the result; press Enter or Space to close it sooner. The celebration music continues under the debrief and the microphone is stopped as soon as the movement finale ends.

The operator console lets you edit the Stage 3 clue location, Stage 7 clue location, and as many Stage 4 puzzle-piece locations as needed. Settings are stored locally in `data/operator_config.json`.

The 10-minute Trivia Lifeline can appear while the family is in stages 5–11; every correct answer adds 60 seconds. The adaptive time manager can skip intermediate stages when there is no longer enough time to complete the remaining challenges and finale.

Successful puzzle clears award team XP, with a speed bonus for quick solves. Rejected submissions increment the team error count and trigger a one-shot error cue; the finale shows total XP, cleared stages, errors, and a team rank based on time remaining and mistakes.

## Portable Windows build

A Windows build can be produced without installing Python on the target PC:

- The repository's **Build Windows Portable App** workflow packages the game on a Windows runner and publishes a downloadable artifact when it succeeds.
- Open the repository's **Actions** tab, select the latest **Build Windows Portable App** run, and download the `TheGreeksAreBack-Windows-x64` artifact. Extract the ZIP and keep the folder intact; run `StartGame.bat` or `TheGreeksAreBack.exe`.
- To build locally on Windows, double-click `build_windows.bat`. The output folder is `dist\\TheGreeksAreBack`.

The portable build stores its operator configuration and player face templates in a `data` folder next to the executable. If the game crashes, a diagnostic `data/crash.log` is written beside it when possible; include that file when reporting a repeatable error.

## Run from source on Windows

1. Install Python 3.11 or later.
2. Open PowerShell in the repository folder.
3. Install dependencies and start the game:

```powershell
python -m pip install -r requirements.txt
python main.py
```

The webcam tries the Windows DirectShow backend first, then OpenCV's default backend. A failed camera read clears the previous frame so stale images cannot be reused for registration or presence checks. If the camera is connected late or repeatedly fails, the game releases the dead handle and retries discovery at a throttled interval instead of requiring a restart. The finale uses the webcam to estimate movement and optionally opens the microphone through `sounddevice`. Audio input is measured live only to drive the energy meter; the game does not save audio recordings.


## Sound design

- The game synthesizes layered sound effects and a low-volume ambient drone; no extra audio files are required.
- Correct solutions, wrong inputs, stage unlocks, the opening intrusion, the last 10 seconds, and the final victory use distinct audio cues. Stage 8 keeps its four-note auditory puzzle.
- `F7` toggles the low-volume suspense drone independently, `F8` mutes/restores all game audio, and `F9` / `F10` lower or raise master volume. The current sound level and ambience state appear in the HUD.
- The soundtrack remains restrained during the main mission, gets subtly louder as the deadline approaches, and adds a low double-heartbeat cue in the final minute before the last-ten-second beeps.
- Each stage unlock gets a distinct success callout; error tones are triggered by rejected answers, not by repeatedly drawing the error text.
- Sound settings are saved to `data/audio_settings.json`; master mute, ambience on/off, and volume level persist across launches.
- If no audio output device is available, the HUD says so and the game continues without blocking puzzles or stage progression.

## Operator controls

- `Esc` during gameplay — pause/resume the mission; the global clock and puzzle deadlines freeze while paused. Press `Enter` or `Space` to resume from the pause screen.
- The pause panel provides clickable sound, ambience, and master-volume controls; no puzzle input is accepted underneath the overlay.
- `F7` — toggle suspense ambience
- `F8` — mute/unmute game audio
- `F9` / `F10` — lower/raise master volume
- `Ctrl + Shift + Right Arrow` — skip the current stage for testing
- `Ctrl + Alt + Shift + Esc` — emergency exit to Windows

## Important limitations

The webcam face comparison is a gameplay prototype based on image-histogram similarity, not production-grade biometric identification. The kiosk is full-screen application mode; it does not disable Windows security features or prevent operating-system shortcuts.
