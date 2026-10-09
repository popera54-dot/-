"""Headless runtime smoke test for stage rendering and transitions."""
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import main
from stage5_tasks import CyberMemoryTask, MissingLetterTask, SymbolMatrixTask


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    app = main.EscapeRoomApp()
    app.state = "game"
    app.game_started_at = time.monotonic()
    app.timer_frozen = None

    try:
        # Render every implemented stage at least once in a headless SDL surface.
        for stage in (4, 8, 9, 10, 11, 12):
            app.stage_manager.goto(stage)
            app.stage_manager.draw(main.screen)
            pygame.display.flip()
            require(app.stage_manager.stage == stage, f"stage {stage} did not start")

        later = app.stage_manager.later

        # Render the two symbol-heavy mini-games to verify their Windows-safe vector icons.
        matrix_task = SymbolMatrixTask()
        matrix_task.draw(
            main.screen, main.draw_text, main.rounded_panel, main.glow_circle,
            pygame, main.WIDTH, main.HEIGHT, app.background.time
        )
        memory_task = CyberMemoryTask()
        memory_task.revealed = [True] * 8
        memory_task.draw(
            main.screen, main.draw_text, main.rounded_panel, main.glow_circle,
            pygame, main.WIDTH, main.HEIGHT, app.background.time
        )
        pygame.display.flip()

        # The brief missing-letter flash must not accept an answer while the letter is hidden.
        letter_task = MissingLetterTask()
        letter_event = pygame.event.Event(pygame.KEYDOWN, {"unicode": letter_task.current})
        letter_task.handle(letter_event, pygame, main.WIDTH, main.HEIGHT)
        require(not letter_task.done, "stage 5 missing-letter task accepted a hidden letter")
        letter_task.flash_until = time.monotonic() + 1.0
        letter_task.handle(letter_event, pygame, main.WIDTH, main.HEIGHT)
        require(letter_task.done, "stage 5 missing-letter task rejected a visible matching letter")

        # Fast-forward the sound pattern and verify the state machine leaves listening.
        app.stage_manager.goto(8)
        later.next_beep_at = time.monotonic() - 50
        later.update(0.016)
        require(later.phase in ("verify", "code"), "stage 8 audio phase did not complete")

        # The audio puzzle's replay button should replay the signal without restarting face checks.
        later.phase = "code"
        later.replay_button = pygame.Rect(0, 0, 100, 100)
        replay_event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (50, 50)}
        )
        later.handle(replay_event, main.WIDTH, main.HEIGHT)
        require(later.phase == "listen" and later.replay_only, "stage 8 replay did not start")
        later.next_beep_at = time.monotonic() - 50
        later.update(0.016)
        require(later.phase == "code" and not later.replay_only, "stage 8 replay did not return to code entry")

        # Memory image timer advances to questions; correct answers unlock the quantum lock.
        app.stage_manager.goto(10)
        later.phase = "memory"
        later.memory_started = time.monotonic() - 31
        later.update(0.016)
        require(later.phase == "questions", "stage 10 memory timer did not advance")
        later.memory_answers = ["5", "3", "4"]
        later._submit_memory()
        require(app.stage_manager.stage == 11, "stage 10 correct answers did not unlock stage 11")

        # Fixed solution unlocks the finale.
        later.quantum_values = ["64", "200", "66"]
        later._submit_quantum()
        require(app.stage_manager.stage == 12, "stage 11 correct values did not unlock finale")
        app.stage_manager.draw(main.screen)

        # The finale energy meter must still progress with no camera frame or microphone.
        original_read = app.webcam.read
        app.webcam.read = lambda: None
        later.energy = 0.0
        later.dance_started = time.monotonic() - 10
        later._update_energy(1.0, time.monotonic())
        require(later.energy >= 0.8, "stage 12 energy fallback did not progress without camera")

        # The finale cannot end before the specified minimum 90-second celebration.
        later.energy = 99.99
        later.phase = "dance"
        later.dance_started = time.monotonic() - 89
        later._update_energy(0.02, time.monotonic())
        require(later.phase == "dance", "stage 12 ended before the 90-second minimum")
        later.dance_started = time.monotonic() - 91
        later._update_energy(0.02, time.monotonic())
        require(later.phase == "countdown", "stage 12 did not enter countdown when energy was full")
        app.webcam.read = original_read

        # The last-ten-minute lifeline should work in stages 8 through 11 too.
        app.timer_frozen = None
        app.game_started_at = time.monotonic() - (main.TOTAL_SECONDS - 599)
        app.stage_manager.goto(8)
        later.lifeline_update()
        require(later.lifeline_active, "stage 8 did not trigger the last-ten-minute lifeline")

        print("HEADLESS RUNTIME SMOKE TEST PASSED")
    finally:
        app.stage_manager.later._stop_mic()
        app.webcam.release()
        pygame.quit()


if __name__ == "__main__":
    run()
