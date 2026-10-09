"""Headless runtime smoke test for stage rendering and transitions."""
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import main
from stage5_tasks import CyberMemoryTask, DreidelSaysTask, MissingLetterTask, SymbolMatrixTask, TriviaTask


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    app = main.EscapeRoomApp()
    app.state = "game"
    app.game_started_at = time.monotonic()
    app.timer_frozen = None

    try:
        # The flashlight must reveal its centre, with darkness increasing toward the edge.
        overlay = app.stage_manager.stage6.make_flashlight_overlay(
            320, 220, (160, 110), pygame, radius=90
        )
        alpha_map = pygame.surfarray.array_alpha(overlay)
        center_alpha = int(alpha_map[160, 110])
        middle_alpha = int(alpha_map[205, 110])
        outside_alpha = int(alpha_map[260, 110])
        require(center_alpha < middle_alpha < outside_alpha,
                f"stage 6 flashlight gradient is reversed: {center_alpha}, {middle_alpha}, {outside_alpha}")

        # Verify the flashlight darkens UI content too, not just the background.
        app.stage_manager.stage6.start()
        test_surface = pygame.Surface((main.WIDTH, main.HEIGHT))
        pygame.mouse.set_pos((main.WIDTH // 2, main.HEIGHT // 2))
        def mark_drawn_text(target, *args, **kwargs):
            main.draw_text(target, *args, **kwargs)
            pygame.draw.rect(target, (255, 255, 255), (8, 8, 12, 12))
        app.stage_manager.stage6.draw(
            test_surface, mark_drawn_text, main.rounded_panel,
            main.glow_circle, pygame, main.WIDTH, main.HEIGHT,
            app.background.time
        )
        corner = test_surface.get_at((12, 12))
        require(max(corner.r, corner.g, corner.b) < 30,
                f"stage 6 flashlight left UI text visible outside its beam: {corner}")
        pygame.mouse.set_pos((main.WIDTH // 2, main.HEIGHT // 2))

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

        # Per-player timers begin when tasks are assigned, not when the task pool is created.
        trivia_task = TriviaTask()
        trivia_task.deadline = time.monotonic() - 1
        trivia_task.reset()
        require(trivia_task.deadline > time.monotonic() + 29,
                "stage 5 trivia timer did not reset when the verified player started")

        # A stale click after time-out cannot be accepted as an answer for the new attempt.
        trivia_task.deadline = time.monotonic() - 1
        answer_click = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (int(main.WIDTH / 2 - 180), 545)}
        )
        trivia_task.handle(answer_click, pygame, main.WIDTH, main.HEIGHT)
        require(not trivia_task.done and trivia_task.timeout_count == 1,
                "stage 5 trivia accepted a stale post-timeout click")

        # The four-branch preview must restart when the player actually receives the task.
        dreidel_task = DreidelSaysTask()
        dreidel_task.preview_until = time.monotonic() - 1
        dreidel_task.reset()
        require(dreidel_task.preview_until > time.monotonic() + 2.2,
                "stage 5 sequence preview expired before the player's turn")
        dreidel_task.update(0.0)
        require(dreidel_task.flash_index == dreidel_task.sequence[0],
                "stage 5 sequence did not begin with its first visible branch")

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

        # Stage 10 snapshot must be hidden before exposure and during the retry notice.
        later.start(10)
        original_scene = later._draw_memory_scene
        scene_calls = []
        def track_memory_scene(*args):
            scene_calls.append(True)
            return original_scene(*args)
        later._draw_memory_scene = track_memory_scene
        later._draw_stage10(
            main.screen, main.draw_text, main.rounded_panel, main.glow_circle,
            pygame, main.WIDTH, main.HEIGHT, app.background.time
        )
        require(not scene_calls, "stage 10 revealed the image before the 30-second timer")
        later.phase = "retry_notice"
        later._draw_stage10(
            main.screen, main.draw_text, main.rounded_panel, main.glow_circle,
            pygame, main.WIDTH, main.HEIGHT, app.background.time
        )
        require(not scene_calls, "stage 10 revealed the image during the retry notice")
        later.phase = "memory"
        later.memory_started = time.monotonic()
        later._draw_stage10(
            main.screen, main.draw_text, main.rounded_panel, main.glow_circle,
            pygame, main.WIDTH, main.HEIGHT, app.background.time
        )
        require(len(scene_calls) == 1, "stage 10 did not show the image during timed exposure")
        later._draw_memory_scene = original_scene

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

        # Oil Catch completes during update; Stage 5 must advance without another input event.
        app.players = [object()]
        stage5 = app.stage_manager.stage5
        stage5.phase = "task"
        stage5.assigned_player = 0
        stage5.current_task_index = 0
        oil = OilCatchTask()
        oil.basket_x = 0.5
        oil.catches = 4
        catch_y = (0.82 - 0.18) / 0.65
        oil.items = [[0.5, catch_y, 0.0]]
        stage5.tasks = [oil]
        stage5.update(0.0)
        require(app.stage_manager.stage == 6, "Stage 5 waited for another input after Oil Catch completed")
        app.players = []

        print("HEADLESS RUNTIME SMOKE TEST PASSED")
    finally:
        app.stage_manager.later._stop_mic()
        app.webcam.release()
        pygame.quit()


if __name__ == "__main__":
    run()
