"""Headless runtime smoke test for stage rendering and transitions."""
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import main


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

        # Fast-forward the sound pattern and verify the state machine leaves listening.
        app.stage_manager.goto(8)
        later.next_beep_at = time.monotonic() - 50
        later.update(0.016)
        require(later.phase in ("verify", "code"), "stage 8 audio phase did not complete")

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

        print("HEADLESS RUNTIME SMOKE TEST PASSED")
    finally:
        app.stage_manager.later._stop_mic()
        app.webcam.release()
        pygame.quit()


if __name__ == "__main__":
    run()
