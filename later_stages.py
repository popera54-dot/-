from __future__ import annotations

import math
import random
import time

import cv2
import numpy as np
import pygame
import pygame.sndarray


class LaterStagesController:
    """Stages 8–12 plus the ten-minute trivia lifeline."""

    MEMORY_QUESTIONS = [
        ("כמה נרות דולקים הופיעו בחנוכייה שבתמונה?", "5"),
        ("כמה סביבונים הונחו על השולחן?", "3"),
        ("כמה כדי שמן היו בתמונה?", "4"),
    ]

    LIFELINE_QUESTIONS = [
        ("כמה ימים נמשך נס פך השמן לפי המסורת?", ("5", "7", "8", "10"), 2),
        ("באיזה חודש עברי מתחיל חנוכה בדרך כלל?", ("תשרי", "כסלו", "ניסן", "אדר"), 1),
        ("איזו ברכה מוסיפים בתפילת העמידה בחנוכה?", ("על הנסים", "יעלה ויבוא", "הלל הגדול", "נחם"), 0),
        ("מה מסובבים במשחק חנוכה מסורתי?", ("כדור", "קובייה", "סביבון", "חישוק"), 2),
        ("מהו המאכל המטוגן המתוק המזוהה עם חנוכה?", ("אוזן המן", "סופגנייה", "מצה", "עוגת דבש"), 1),
        ("כמה קנים יש בחנוכייה, כולל השמש?", ("6", "7", "8", "9"), 3),
        ("מי הוביל את מרד החשמונאים לפי המסורת?", ("יהודה המכבי", "בר כוכבא", "שמשון", "גדעון"), 0),
        ("איזה כלי קשור לסיפור נס השמן?", ("כד שמן", "סל קמח", "בקבוק יין", "קערת מים"), 0),
        ("מה מדליקים בכל ערב של חנוכה?", ("מדורה", "נרות חנוכה", "לפידים ברחוב", "פנס"), 1),
        ("איזו אות אינה מופיעה על סביבון ישראלי רגיל?", ("נ", "ג", "ה", "ש"), 3),
    ]

    def __init__(self, app):
        self.app = app
        self.stage = 0
        self.phase = ""
        self.phase_started = time.monotonic()
        self.error = ""
        self.rotation_angle = 180.0
        self.rotation_scale = 1.0
        self.rotation_transition = False
        self.audio_enabled = False
        self.sound = None
        self._mic_stream = None
        self.music_sound = None
        self.music_channel = None
        self.mic_level = 0.0
        self._previous_gray = None
        self.energy = 0.0
        self.dance_started = 0.0
        self.victory_started = None
        self.countdown_started = None
        self.lifeline_active = False
        self.lifeline_used = False
        self.lifeline_index = 0
        self.lifeline_correct = 0
        self.lifeline_feedback = ""
        self.lifeline_feedback_until = 0.0
        self._memory_scene_seed = 2026
        self.lifeline_option_rects = []
        self.memory_start_button = None
        self.memory_field_rects = []
        self.memory_submit = None
        self.quantum_field_rects = []
        self.quantum_submit = None
        self.number_rects = {}
        self.sequence = []
        self.number_positions = {}
        self.number_velocities = {}
        self.replay_only = False
        self.replay_button = None

    def _stop_mic(self):
        if self._mic_stream is not None:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception:
                pass
        self._mic_stream = None
        if self.music_channel is not None:
            try:
                self.music_channel.stop()
            except Exception:
                pass
        self.music_channel = None
        self.music_sound = None

    def start(self, stage):
        self._stop_mic()
        self.stage = stage
        self.phase_started = time.monotonic()
        self.error = ""
        self.rotation_angle = 180.0
        self.rotation_scale = 1.0
        self.rotation_transition = False

        if stage == 8:
            self.phase = "listen"
            self.signal_groups = [3, 5, 1, 4]
            self.signal_frequencies = [440, 554, 392, 659]
            self.audio_group = 0
            self.audio_beep = 0
            self.next_beep_at = time.monotonic() + 1.2
            self.verify_index = 0
            self.verify_score = 0.0
            self.code_input = ""
            self.replay_only = False
            self.replay_button = None
            self._make_beep()
            if not self.app.players:
                self.phase = "code"

        elif stage == 9:
            self.phase = "play"
            self.phase_started = time.monotonic()
            self.sequence = sorted(random.sample(range(10, 100), 10))
            self.next_number_index = 0
            self.number_positions = {}
            self.number_velocities = {}
            for number in self.sequence:
                self.number_positions[number] = [
                    random.uniform(150, max(151, self.app_width() - 150)),
                    random.uniform(245, max(246, self.app_height() - 150)),
                ]
                self.number_velocities[number] = [
                    random.choice([-1, 1]) * random.uniform(38, 95),
                    random.choice([-1, 1]) * random.uniform(28, 80),
                ]
            self.number_rects = {}
            self.wrong_until = 0.0

        elif stage == 10:
            self.phase = "intro"
            self.memory_started = 0.0
            self.memory_attempt = 0
            self.memory_answers = ["", "", ""]
            self.memory_active_field = 0
            self.memory_error = ""

        elif stage == 11:
            self.phase = "input"
            self.quantum_started = time.monotonic()
            self.quantum_values = ["", "", ""]
            self.quantum_active_field = 0
            self.quantum_error = ""
            self.quantum_done_at = None

        elif stage == 12:
            self.phase = "dance"
            self.energy = 0.0
            self.dance_started = time.monotonic()
            self.victory_started = None
            self.countdown_started = None
            self._previous_gray = None
            self.mic_level = 0.0
            self.app.timer_frozen = self.app.remaining_seconds
            self._start_mic()
            self._start_celebration_music()

    def app_width(self):
        return self.app.screen_width if hasattr(self.app, "screen_width") else pygame.display.get_surface().get_width()

    def app_height(self):
        return self.app.screen_height if hasattr(self.app, "screen_height") else pygame.display.get_surface().get_height()

    def _make_beep(self):
        """Create a soft, shaped note for the four-part listening puzzle."""
        try:
            mixer = pygame.mixer.get_init()
            if not mixer:
                return
            sample_rate, sample_format, channels = mixer
            if sample_format != -16:
                return
            duration = 0.16
            sample_count = int(sample_rate * duration)
            t = np.arange(sample_count, dtype=np.float32) / float(sample_rate)
            frequency = self.signal_frequencies[min(self.audio_group, 3)]
            attack = np.minimum(1.0, t / 0.009)
            release = np.clip((duration - t) / 0.035, 0.0, 1.0)
            envelope = attack * release * np.exp(-t * 1.55)
            wave = np.sin(2 * np.pi * frequency * t) + 0.12 * np.sin(2 * np.pi * frequency * 2.01 * t)
            samples = np.asarray(wave * envelope * 9500, dtype=np.int16)
            if channels > 1:
                samples = np.repeat(samples[:, None], channels, axis=1)
            self.sound = pygame.sndarray.make_sound(np.ascontiguousarray(samples))
            master = getattr(getattr(self.app, "audio", None), "master_volume", 1.0)
            self.sound.set_volume(0.24 * master)
            self.audio_enabled = True
        except Exception:
            self.sound = None
            self.audio_enabled = False

    def _play_beep(self):
        if self.app.audio.enabled and self.sound is not None:
            try:
                self.sound.play()
            except Exception:
                pass

    def _start_celebration_music(self):
        """Generate a short original synth celebration loop; no external track is required."""
        try:
            mixer = pygame.mixer.get_init()
            if not mixer:
                return
            sample_rate, sample_format, channels = mixer
            if sample_format != -16:
                return
            duration = 8.0
            count = int(sample_rate * duration)
            t = np.arange(count, dtype=np.float32) / float(sample_rate)

            melody_notes = np.asarray(
                [659.25, 659.25, 783.99, 659.25, 587.33, 587.33, 523.25, 587.33,
                 659.25, 783.99, 880.00, 783.99, 659.25, 587.33, 523.25, 587.33],
                dtype=np.float32
            )
            melody_step = np.floor(t / 0.25).astype(np.int32) % len(melody_notes)
            melody_phase = np.mod(t, 0.25)
            melody_envelope = np.minimum(1.0, melody_phase * 30.0) * np.exp(-melody_phase * 5.0)
            melody = np.sin(2 * np.pi * melody_notes[melody_step] * t) * melody_envelope * 0.16

            bass_notes = np.asarray([110.0, 146.83, 130.81, 164.81], dtype=np.float32)
            bass_step = np.floor(t / 0.5).astype(np.int32) % len(bass_notes)
            bass_phase = np.mod(t, 0.5)
            bass_envelope = np.exp(-bass_phase * 3.0)
            bass = np.sin(2 * np.pi * bass_notes[bass_step] * t) * bass_envelope * 0.12

            beat_phase = np.mod(t, 0.5)
            kick_envelope = np.where(beat_phase < 0.16, np.exp(-beat_phase * 28.0), 0.0)
            kick_frequency = 76.0 - 110.0 * beat_phase
            kick = np.sin(2 * np.pi * kick_frequency * t) * kick_envelope * 0.22

            snare_phase = np.mod(t, 1.0)
            snare_envelope = np.where((snare_phase > 0.48) & (snare_phase < 0.56),
                                      np.exp(-(snare_phase - 0.48) * 38.0), 0.0)
            noise = np.random.default_rng(77).normal(0.0, 1.0, count).astype(np.float32)
            snare = noise * snare_envelope * 0.045

            mix = melody + bass + kick + snare
            peak = max(1.0, float(np.max(np.abs(mix))))
            samples = np.asarray(mix / peak * 25000, dtype=np.int16)
            if channels > 1:
                samples = np.repeat(samples[:, None], channels, axis=1)
            self.music_sound = pygame.sndarray.make_sound(samples.copy())
            self.music_sound.set_volume(0.38)
            self.music_channel = pygame.mixer.find_channel(True)
            if self.music_channel is not None:
                self.music_channel.set_volume(
                    getattr(getattr(self.app, "audio", None), "master_volume", 1.0)
                )
                if self.app.audio.enabled:
                    self.music_channel.play(self.music_sound, loops=-1)
        except Exception:
            self.music_sound = None
            self.music_channel = None

    def _start_mic(self):
        try:
            import sounddevice as sd

            def audio_callback(indata, frames, timing, status):
                if indata is not None and len(indata):
                    self.mic_level = float(np.sqrt(np.mean(np.square(indata.astype(np.float32)))))

            self._mic_stream = sd.InputStream(
                channels=1, samplerate=16000, blocksize=1024,
                callback=audio_callback
            )
            self._mic_stream.start()
        except Exception:
            self._mic_stream = None

    def update(self, dt):
        now = time.monotonic()

        if self.stage == 8:
            if self.phase == "listen":
                safety = 0
                while self.phase == "listen" and now >= self.next_beep_at and safety < 20:
                    safety += 1
                    self._play_beep()
                    self.audio_beep += 1
                    count = self.signal_groups[self.audio_group]
                    if self.audio_beep >= count:
                        self.audio_group += 1
                        self.audio_beep = 0
                        if self.audio_group >= len(self.signal_groups):
                            if self.replay_only:
                                # Replay is an audio aid after biometric checks, not a new round.
                                self.phase = "code"
                                self.replay_only = False
                            else:
                                self.phase = "verify" if self.app.players else "code"
                                self.verify_index = 0
                            break
                        self.next_beep_at += 0.72
                        self._make_beep()
                    else:
                        self.next_beep_at += 0.22
            elif self.phase == "verify":
                self.app.webcam.read()

        elif self.stage == 9 and self.phase == "play":
            self._update_number_motion(dt)
            self.rotation_transition = (now - self.phase_started) % 12.0 < 1.25
            if self.rotation_transition:
                progress = ((now - self.phase_started) % 12.0) / 1.25
                self.rotation_angle = (180.0 + progress * 360.0) % 360.0
            else:
                self.rotation_angle = 180.0
            if time.monotonic() < self.wrong_until:
                pass

        elif self.stage == 10:
            if self.phase == "memory" and now - self.memory_started >= 30:
                self.phase = "questions"
                self.memory_answers = ["", "", ""]
                self.memory_active_field = 0
            elif self.phase == "retry_notice" and now >= self.memory_retry_at:
                self.phase = "memory"
                self.memory_started = now
                self.memory_attempt += 1
                self.memory_error = ""

        elif self.stage == 11:
            if self.phase == "input" and now - self.quantum_started >= 180:
                self.phase = "timeout"
                self.quantum_done_at = now
            elif self.phase == "timeout" and now - (self.quantum_done_at or now) >= 2.2:
                self.app.stage_message = "TIME MANAGER // FINAL PROTOCOL"
                self.app.stage_manager.goto(12)

        elif self.stage == 12:
            self._update_energy(dt, now)

    def _update_number_motion(self, dt):
        width, height = self.app_width(), self.app_height()
        for number in self.sequence:
            x, y = self.number_positions[number]
            vx, vy = self.number_velocities[number]
            x += vx * dt
            y += vy * dt
            if x < 110 or x > width - 110:
                vx *= -1
                x = max(110, min(width - 110, x))
            if y < 225 or y > height - 125:
                vy *= -1
                y = max(225, min(height - 125, y))
            self.number_positions[number] = [x, y]
            self.number_velocities[number] = [vx, vy]

    def _update_energy(self, dt, now):
        frame = self.app.webcam.read()
        motion = 0.0
        if frame is not None:
            try:
                gray = cv2.cvtColor(cv2.resize(frame, (96, 72)), cv2.COLOR_BGR2GRAY)
                if self._previous_gray is not None:
                    motion = float(cv2.absdiff(gray, self._previous_gray).mean()) / 255.0
                self._previous_gray = gray
            except Exception:
                motion = 0.0

        motion_boost = min(1.35, motion * 42.0)
        mic_boost = min(0.75, max(0.0, (self.mic_level - 0.012) * 28.0))
        # Slowly rising baseline prevents a broken camera/microphone from trapping the family forever.
        # A steady 0.84%/second baseline guarantees completion within about two minutes
        # even when a camera or microphone is unavailable; live movement/voice speeds it up.
        increment = 0.84 + motion_boost + mic_boost
        if self.energy < 100:
            self.energy = min(100.0, self.energy + increment * dt)

        elapsed = now - self.dance_started
        if self.energy >= 100 and elapsed >= 90:
            self.energy = 100
            if self.victory_started is None:
                self.victory_started = now
                self.countdown_started = now
                self.phase = "countdown"
                self.app.audio.play("victory")

        if self.phase == "countdown" and self.countdown_started is not None:
            if now - self.countdown_started >= 4.8:
                self._stop_mic()
                self.app.running = False

    def handle(self, event, width, height):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.running = False
            return

        if self.stage == 8:
            self._handle_stage8(event)
        elif self.stage == 9:
            self._handle_stage9(event, width, height)
        elif self.stage == 10:
            self._handle_stage10(event, width, height)
        elif self.stage == 11:
            self._handle_stage11(event, width, height)
        elif self.stage == 12:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and self.phase == "dance":
                # Backup for a blocked camera/mic; movement and singing remain the intended interaction.
                self.energy = min(99.0, self.energy + 0.2)

    def _handle_stage8(self, event):
        if self.phase == "verify":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                if self.verify_index >= len(self.app.players):
                    self.phase = "code"
                    return
                player = self.app.players[self.verify_index]
                reference = player.load()
                ok, score = self.app.webcam.verify_against(reference)
                self.verify_score = score
                if ok:
                    self.verify_index += 1
                    if self.verify_index >= len(self.app.players):
                        self.phase = "code"
            return

        if self.phase == "code" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.replay_button and self.replay_button.collidepoint(event.pos):
                self.phase = "listen"
                self.replay_only = True
                self.audio_group = 0
                self.audio_beep = 0
                self.next_beep_at = time.monotonic() + 0.45
                self.code_input = ""
                self.error = ""
                self._make_beep()
            return

        if self.phase == "code" and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.code_input = self.code_input[:-1]
            elif event.unicode.isdigit() and len(self.code_input) < 4:
                self.code_input += event.unicode
                if len(self.code_input) == 4:
                    if self.code_input == "3514":
                        self.app.stage_message = "SIGNAL DECRYPTED // 3514"
                        self.app.stage_manager.goto(9)
                    else:
                        self.code_input = ""
                        self.error = "קוד שגוי — הקשיבו שוב לדפוס הצלילים."

    def _handle_stage9(self, event, width, height):
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        # During the rotation animation the interface deliberately ignores clicks.
        if self.rotation_transition or self.next_number_index >= len(self.sequence):
            return

        pos = self._map_rotated_pointer(event.pos, width, height)
        for number, rr in self.number_rects.items():
            if rr.collidepoint(pos):
                expected = self.sequence[self.next_number_index]
                if number == expected:
                    self.next_number_index += 1
                    if self.next_number_index >= len(self.sequence):
                        self.app.stage_message = "INVERSION OVERRIDE // ACCEPTED"
                        self.app.stage_manager.goto(10)
                    else:
                        self.app.audio.play("confirm")
                else:
                    self.next_number_index = 0
                    self.wrong_until = time.monotonic() + 1.0
                    self.error = "שגיאה — הרצף אופס. התחילו שוב מהמספר הקטן ביותר."
                return

    def _map_rotated_pointer(self, pos, width, height):
        # In normal puzzle mode the rendered canvas is inverted by exactly 180°.
        if not self.rotation_transition:
            return (width - pos[0], height - pos[1])
        return pos

    def _handle_stage10(self, event, width, height):
        if self.phase == "intro" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.memory_start_button and self.memory_start_button.collidepoint(event.pos):
                self.phase = "memory"
                self.memory_started = time.monotonic()
            return

        if self.phase == "questions":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, rr in enumerate(self.memory_field_rects):
                    if rr.collidepoint(event.pos):
                        self.memory_active_field = i
                        return
                if self.memory_submit and self.memory_submit.collidepoint(event.pos):
                    self._submit_memory()
                return

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    self.memory_answers[self.memory_active_field] = self.memory_answers[self.memory_active_field][:-1]
                elif event.key == pygame.K_TAB:
                    self.memory_active_field = (self.memory_active_field + 1) % 3
                elif event.key == pygame.K_RETURN:
                    if self.memory_active_field < 2:
                        self.memory_active_field += 1
                    else:
                        self._submit_memory()
                elif event.unicode.isdigit() and len(self.memory_answers[self.memory_active_field]) < 2:
                    self.memory_answers[self.memory_active_field] += event.unicode

    def _submit_memory(self):
        expected = [answer for _, answer in self.MEMORY_QUESTIONS]
        if self.memory_answers == expected:
            self.app.stage_message = "MEMORY MATRIX // VERIFIED"
            self.app.stage_manager.goto(11)
            return
        self.memory_error = "לא מדויק. התמונה תחזור ל־30 שניות נוספות."
        self.phase = "retry_notice"
        self.memory_retry_at = time.monotonic() + 2.0

    def _handle_stage11(self, event, width, height):
        if self.phase != "input":
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rr in enumerate(self.quantum_field_rects):
                if rr.collidepoint(event.pos):
                    self.quantum_active_field = i
                    return
            if self.quantum_submit and self.quantum_submit.collidepoint(event.pos):
                self._submit_quantum()
                return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.quantum_values[self.quantum_active_field] = self.quantum_values[self.quantum_active_field][:-1]
            elif event.key == pygame.K_TAB:
                self.quantum_active_field = (self.quantum_active_field + 1) % 3
            elif event.key == pygame.K_RETURN:
                if self.quantum_active_field < 2:
                    self.quantum_active_field += 1
                else:
                    self._submit_quantum()
            elif event.unicode.isdigit() and len(self.quantum_values[self.quantum_active_field]) < 3:
                self.quantum_values[self.quantum_active_field] += event.unicode

    def _submit_quantum(self):
        if self.quantum_values == ["64", "200", "66"]:
            self.app.stage_message = "QUANTUM CURRENT // STABLE"
            self.app.stage_manager.goto(12)
        else:
            self.quantum_values = ["", "", ""]
            self.quantum_active_field = 0
            self.quantum_error = "זרם לא יציב — בדקו את שלוש המבחנות."

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        if self.stage == 9:
            self._draw_stage9_rotated(surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t)
            return

        self.app.background.draw(surface, danger=1.0 if self.stage in (8, 11) else 0.0)
        self.app.stage_manager.draw_stage_chip(surface)
        if self.stage == 8:
            self._draw_stage8(surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t)
        elif self.stage == 10:
            self._draw_stage10(surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t)
        elif self.stage == 11:
            self._draw_stage11(surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t)
        elif self.stage == 12:
            self._draw_stage12(surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t)

    def _draw_stage8(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "STAGE 08 // MACCABEAN FREQUENCY", 14, (width / 2, 76),
                  (255, 61, 80), align="center", mono=True, bold=True)
        draw_text(surface, "תדר המכבים", 44, (width / 2, 120),
                  (240, 248, 250), align="center", bold=True)
        draw_text(surface, "האזינו לדפוס הצלילים מתוך השיר המשובש. אין רמז כתוב לקוד.",
                  18, (width / 2, 164), (146, 172, 177), align="center")

        cx, cy = int(width / 2), 355
        for i in range(48):
            a = i * math.tau / 48 + t * 0.32
            r1 = 84 + 20 * math.sin(t * 2.0 + i * .4)
            r2 = 124 + 18 * math.sin(t * 1.2 + i * .25)
            p1 = (int(cx + math.cos(a) * r1), int(cy + math.sin(a) * r1))
            p2 = (int(cx + math.cos(a) * r2), int(cy + math.sin(a) * r2))
            pygame.draw.line(surface, (255, 58, 81) if i % 6 == 0 else (43, 201, 159), p1, p2, 2)
        pygame.draw.circle(surface, (9, 30, 34), (cx, cy), 70)
        pygame.draw.circle(surface, (53, 255, 211), (cx, cy), 70, 2)
        draw_text(surface, "SIGNAL", 17, (cx, cy - 6), (87, 255, 212), align="center", mono=True, bold=True)
        if self.phase == "listen":
            row = min(self.audio_group + 1, 4)
            draw_text(surface, f"RECEIVING PACKET {row}/4", 14, (width / 2, 500),
                      (255, 193, 78), align="center", mono=True, bold=True)
            draw_text(surface, "האזינו היטב. לאחר מכן כל שחקן יתייצב לאימות פנים.",
                      17, (width / 2, 550), (229, 238, 240), align="center")
        elif self.phase == "verify":
            name = self.app.players[self.verify_index].name if self.verify_index < len(self.app.players) else ""
            draw_text(surface, "BIOMETRIC HANDSHAKE", 13, (width / 2, 493),
                      (255, 62, 80), align="center", mono=True, bold=True)
            draw_text(surface, f"התייצב מול המצלמה: {name}", 22, (width / 2, 538),
                      (255, 203, 103), align="center", bold=True)
            draw_text(surface, f"SIMILARITY {self.verify_score:.2f}  //  ENTER לאימות",
                      13, (width / 2, 584), (117, 157, 160), align="center", mono=True)
            frame = self.app.webcam.pygame_frame((260, 170))
            if frame:
                surface.blit(frame, (width // 2 - 130, 615))
        elif self.phase == "code":
            draw_text(surface, "ENTER THE FOUR-DIGIT FREQUENCY", 13, (width / 2, 500),
                      (74, 255, 208), align="center", mono=True, bold=True)
            rr = pygame.Rect(width / 2 - 180, 530, 360, 70)
            rounded_panel(surface, rr, (3, 10, 14), (255, 194, 78), 16, 2)
            draw_text(surface, self.code_input or "____", 38, rr.center,
                      (255, 220, 125), align="center", mono=True, bold=True)
            if self.error:
                draw_text(surface, self.error, 16, (width / 2, 625), (255, 75, 91), align="center", bold=True)
            self.replay_button = pygame.Rect(width / 2 - 170, 655, 340, 46)
            rounded_panel(surface, self.replay_button, (6, 25, 29), (58, 231, 189), 12, 2)
            draw_text(surface, "השמעת דפוס הצלילים שוב", 16,
                      self.replay_button.center, (98, 255, 213), align="center", bold=True)
        else:
            self.replay_button = None
        draw_text(surface, f"OSCILLATOR // {int(t * 17) % 9999:04d}", 11,
                  (width / 2, height - 93), (70, 138, 124), align="center", mono=True)

    def _draw_stage9_rotated(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        canvas = pygame.Surface((width, height), pygame.SRCALPHA)
        self.app.background.draw(canvas, danger=1.0)
        draw_text(canvas, "STAGE 09 // DIGITAL INVERSION", 14, (width / 2, 62),
                  (255, 61, 80), align="center", mono=True, bold=True)
        draw_text(canvas, "פרוטוקול ההיפוך הדיגיטלי של אנטיוכוס 2.0. שיגעתי אתכם! לחצו על המספרים מהקטן לגדול",
                  20, (width / 2, 106), (242, 248, 249), align="center", bold=True)
        draw_text(canvas, "CLICK ALL 10 NUMBERS // SMALLEST TO LARGEST", 15,
                  (width / 2, 151), (255, 194, 78), align="center", mono=True, bold=True)
        draw_text(canvas, f"PROGRESS // {self.next_number_index:02d}/10", 13,
                  (width / 2, 184), (70, 255, 210), align="center", mono=True)
        draw_text(canvas, f"GLOBAL TIMER // {self.app.timer_string()}", 11,
                  (width - 145, 44), (255, 67, 84), align="center", mono=True, bold=True)
        self.number_rects = {}
        for number in self.sequence:
            x, y = self.number_positions[number]
            pulse = 0.5 + .5 * math.sin(t * 5 + number)
            size = int(64 + pulse * 8)
            rr = pygame.Rect(int(x - size / 2), int(y - size / 2), size, size)
            self.number_rects[number] = rr
            col = (255, 58, 79) if number == self.sequence[self.next_number_index] else (47, 223, 177)
            glow_circle(canvas, rr.center, 20, col, 12)
            rounded_panel(canvas, rr, (3, 17, 22), col, 14, 2)
            draw_text(canvas, f"{number:02d}", 23, rr.center,
                      (248, 252, 251), align="center", mono=True, bold=True)
        if self.error and time.monotonic() < self.wrong_until:
            draw_text(canvas, self.error, 18, (width / 2, height - 105),
                      (255, 68, 83), align="center", bold=True)
        draw_text(canvas, "MOUSE INVERTED // ORIENTATION LOCKED", 12,
                  (width / 2, height - 56), (120, 145, 149), align="center", mono=True)
        self.rotation_transition = (time.monotonic() - self.phase_started) % 12.0 < 1.25
        if self.rotation_transition:
            progress = ((time.monotonic() - self.phase_started) % 12.0) / 1.25
            angle = (180.0 + progress * 360.0) % 360.0
        else:
            angle = 180.0
        self.rotation_angle = angle
        rotated = pygame.transform.rotate(canvas, angle)
        scale = min(width / max(1, rotated.get_width()), height / max(1, rotated.get_height()))
        self.rotation_scale = scale
        out = pygame.transform.smoothscale(
            rotated,
            (max(1, int(rotated.get_width() * scale)), max(1, int(rotated.get_height() * scale)))
        )
        surface.fill((0, 3, 7))
        surface.blit(out, out.get_rect(center=(width // 2, height // 2)))

    def _draw_memory_scene(self, surface, rect, pygame, draw_text):
        # The scene is drawn once as fixed vector artwork, so retries use the exact same composition.
        pygame.draw.rect(surface, (9, 26, 42), rect)
        pygame.draw.rect(surface, (41, 104, 117), rect, 2)
        sky = pygame.Rect(rect.x + 14, rect.y + 14, rect.w - 28, int(rect.h * .48))
        pygame.draw.rect(surface, (8, 18, 44), sky, border_radius=12)
        for i in range(42):
            sx = sky.x + ((i * 83 + 29) % max(1, sky.w - 8))
            sy = sky.y + ((i * 37 + 11) % max(1, sky.h - 8))
            pygame.draw.circle(surface, (133 + i % 70, 167 + i % 60, 200), (sx, sy), 1 + (i % 3 == 0))
        moon = (sky.right - 58, sky.y + 50)
        pygame.draw.circle(surface, (245, 229, 168), moon, 22)
        pygame.draw.circle(surface, (8, 18, 44), (moon[0] + 8, moon[1] - 5), 20)
        window = pygame.Rect(sky.x + 26, sky.y + 22, 108, 96)
        pygame.draw.rect(surface, (21, 49, 66), window, border_radius=4)
        pygame.draw.rect(surface, (166, 202, 211), window, 3, border_radius=4)
        pygame.draw.line(surface, (166, 202, 211), (window.centerx, window.y), (window.centerx, window.bottom), 3)
        pygame.draw.line(surface, (166, 202, 211), (window.x, window.centery), (window.right, window.centery), 3)

        # Four family silhouettes in the background.
        for i, xoff in enumerate((0.26, 0.42, 0.59, 0.75)):
            px = int(rect.x + rect.w * xoff)
            py = sky.bottom + int(rect.h * .05)
            head_r = 13 + (i % 2) * 3
            pygame.draw.circle(surface, (199, 157 + i * 5, 120 + i * 7), (px, py), head_r)
            body = pygame.Rect(px - 20, py + head_r - 2, 40, int(rect.h * .19))
            pygame.draw.ellipse(surface, ((42 + i * 8), (93 + i * 5), (112 + i * 6)), body)
            pygame.draw.line(surface, (190, 147, 112), (px - 12, body.bottom - 2), (px - 26, body.bottom + 20), 7)
            pygame.draw.line(surface, (190, 147, 112), (px + 12, body.bottom - 2), (px + 25, body.bottom + 20), 7)

        # Table and cloth.
        table_y = rect.y + int(rect.h * .72)
        pygame.draw.rect(surface, (87, 48, 33), (rect.x + 34, table_y, rect.w - 68, int(rect.h * .18)), border_radius=12)
        pygame.draw.rect(surface, (167, 111, 62), (rect.x + 34, table_y, rect.w - 68, 13), border_radius=5)
        pygame.draw.line(surface, (46, 28, 24), (rect.x + 86, table_y + 25), (rect.x + 86, rect.bottom - 22), 8)
        pygame.draw.line(surface, (46, 28, 24), (rect.right - 86, table_y + 25), (rect.right - 86, rect.bottom - 22), 8)

        # Exactly five lit candles on the menorah.
        menorah_x = rect.x + int(rect.w * .52)
        candle_y = table_y - 46
        pygame.draw.line(surface, (224, 176, 84), (menorah_x - 55, candle_y + 12), (menorah_x + 55, candle_y + 12), 5)
        candle_positions = [menorah_x - 48, menorah_x - 24, menorah_x, menorah_x + 24, menorah_x + 48]
        for i, cx in enumerate(candle_positions):
            candle_h = 26 + (i % 2) * 5
            pygame.draw.line(surface, (250, 205, 109), (cx, candle_y + 10), (cx, candle_y - candle_h), 5)
            flame = (cx, candle_y - candle_h - 9)
            pygame.draw.polygon(surface, (255, 184, 69), [(cx, flame[1] - 7), (cx - 5, flame[1] + 3), (cx + 5, flame[1] + 3)])
            pygame.draw.circle(surface, (255, 231, 154), flame, 3)

        # Three dreidels.
        for i, cx in enumerate((rect.x + int(rect.w * .19), rect.x + int(rect.w * .31), rect.x + int(rect.w * .82))):
            cy = table_y + 42 + (i % 2) * 4
            color = ((56, 201, 166), (224, 76, 88), (78, 128, 232))[i]
            points = [(cx, cy - 15), (cx + 14, cy), (cx, cy + 15), (cx - 14, cy)]
            pygame.draw.polygon(surface, color, points)
            pygame.draw.line(surface, (234, 239, 231), (cx, cy - 15), (cx, cy - 22), 3)

        # Four oil jugs.
        for i, cx in enumerate((rect.x + int(rect.w * .41), rect.x + int(rect.w * .46), rect.x + int(rect.w * .67), rect.x + int(rect.w * .72))):
            cy = table_y + 43
            color = (113 + i * 15, 150 + i * 9, 161 + i * 7)
            body = pygame.Rect(cx - 12, cy - 15, 24, 29)
            pygame.draw.ellipse(surface, color, body)
            pygame.draw.ellipse(surface, (219, 221, 190), body, 2)
            pygame.draw.rect(surface, color, (cx - 5, cy - 24, 10, 10), border_radius=2)

        # Other festive details: coins, doughnuts, gift box and garland.
        for i in range(7):
            cx = rect.x + 75 + i * int((rect.w - 150) / 7)
            cy = table_y + int(rect.h * .13) + (i % 2) * 8
            pygame.draw.circle(surface, (255, 204, 83), (cx, cy), 7)
            pygame.draw.circle(surface, (156, 105, 36), (cx, cy), 4, 1)
        for i in range(6):
            cx = rect.x + 80 + i * int((rect.w - 160) / 6)
            cy = table_y + int(rect.h * .04) + (i % 2) * 8
            pygame.draw.circle(surface, (185, 92, 74), (cx, cy), 11)
            pygame.draw.circle(surface, (255, 211, 151), (cx, cy), 4)
        gift = pygame.Rect(rect.right - 76, table_y - 35, 42, 34)
        pygame.draw.rect(surface, (75, 143, 184), gift, border_radius=4)
        pygame.draw.line(surface, (255, 204, 83), (gift.centerx, gift.y), (gift.centerx, gift.bottom), 4)
        pygame.draw.arc(surface, (255, 204, 83), (gift.x + 7, gift.y - 8, 14, 12), 0, math.pi, 2)
        pygame.draw.arc(surface, (255, 204, 83), (gift.centerx, gift.y - 8, 14, 12), 0, math.pi, 2)

        draw_text(surface, "FAMILY MEMORY SNAPSHOT // FRAME LOCKED", 12,
                  (rect.centerx, rect.y + 27), (114, 255, 218), align="center", mono=True, bold=True)

    def _draw_stage10(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "STAGE 10 // FAMILY MEMORY MATRIX", 14,
                  (width / 2, 74), (255, 60, 80), align="center", mono=True, bold=True)
        draw_text(surface, "מטריצת הזיכרון המשפחתית", 38,
                  (width / 2, 115), (240, 248, 250), align="center", bold=True)

        scene = pygame.Rect(int(width * .07), 155, int(width * .86), int(height * .65))
        if self.phase == "memory":
            self._draw_memory_scene(surface, scene, pygame, draw_text)
        else:
            pygame.draw.rect(surface, (5, 15, 22), scene)
            pygame.draw.rect(surface, (34, 79, 87), scene, 2)
            if self.phase == "intro":
                label = "SNAPSHOT SEALED // PRESS START"
            elif self.phase == "retry_notice":
                label = "REPLAY INITIALIZING"
            else:
                label = "MEMORY IMAGE HIDDEN"
            draw_text(surface, label, 18, scene.center,
                      (97, 142, 147), align="center", mono=True, bold=True)

        if self.phase == "intro":
            draw_text(surface, "יש לכם 30 שניות לזכור כמה שיותר פרטים.", 19,
                      (width / 2, height - 110), (228, 239, 240), align="center")
            self.memory_start_button = pygame.Rect(width / 2 - 190, height - 86, 380, 50)
            rounded_panel(surface, self.memory_start_button, (7, 29, 31), (60, 244, 194), 14, 2)
            draw_text(surface, "חשיפת התמונה // התחל", 18,
                      self.memory_start_button.center, (86, 255, 211), align="center", bold=True)
        elif self.phase == "memory":
            remain = max(0, 30 - int(time.monotonic() - self.memory_started))
            draw_text(surface, f"MEMORY CAPTURE // 00:{remain:02d}", 19,
                      (width - 100, 116), (255, 194, 78), align="center", mono=True, bold=True)
            draw_text(surface, "סִרְקוּ את כל הפרטים — כשהתמונה תיעלם, תצטרכו לשחזר אותם יחד.",
                      15, (width / 2, height - 45), (165, 190, 193), align="center")
        elif self.phase == "retry_notice":
            draw_text(surface, self.memory_error, 18, (width / 2, height - 72),
                      (255, 75, 91), align="center", bold=True)
        elif self.phase == "questions":
            draw_text(surface, "הקלידו את שלוש התשובות. אין צורך באימות פנים.", 16,
                      (width / 2, 156), (128, 164, 168), align="center")
            labels = [q for q, _ in self.MEMORY_QUESTIONS]
            self.memory_field_rects = []
            start_y = 220
            for i, label in enumerate(labels):
                rr = pygame.Rect(width / 2 - 420, start_y + i * 105, 840, 84)
                self.memory_field_rects.append(rr)
                active = i == self.memory_active_field
                rounded_panel(surface, rr, (5, 17, 22), (255, 194, 78) if active else (39, 89, 92), 14, 2 if active else 1)
                draw_text(surface, label, 17, (rr.x + 20, rr.y + 22),
                          (233, 242, 243), align="midleft", bold=True)
                value = self.memory_answers[i] or "הקלידו מספר"
                draw_text(surface, value, 22, (rr.right - 22, rr.y + 57),
                          (255, 210, 109) if self.memory_answers[i] else (102, 135, 139),
                          align="midright", mono=True, bold=True)
            self.memory_submit = pygame.Rect(width / 2 - 150, height - 82, 300, 48)
            rounded_panel(surface, self.memory_submit, (8, 31, 32), (63, 255, 197), 13, 2)
            draw_text(surface, "שליחת תשובות", 18, self.memory_submit.center,
                      (95, 255, 212), align="center", bold=True)
            if self.memory_error:
                draw_text(surface, self.memory_error, 14, (width / 2, height - 105),
                          (255, 76, 91), align="center", bold=True)

    def _draw_stage11(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        elapsed = time.monotonic() - self.quantum_started
        remaining = max(0, 180 - int(elapsed))
        draw_text(surface, "STAGE 11 // QUANTUM CURRENT LOCK", 14,
                  (width / 2, 78), (255, 60, 80), align="center", mono=True, bold=True)
        draw_text(surface, "מנעול הזרם הקוונטי", 43,
                  (width / 2, 121), (240, 248, 250), align="center", bold=True)
        timer_col = (255, 65, 80) if remaining <= 30 else (255, 196, 78)
        draw_text(surface, f"{remaining // 60:02d}:{remaining % 60:02d}", 35,
                  (width / 2, 177), timer_col, align="center", mono=True, bold=True)

        hints = [
            "X = מספר ימי נס השמן בריבוע",
            "Y = גימטריית אור פחות מספר קני המנורה",
            "Z = (X + Y) / 4",
        ]
        for i, hint in enumerate(hints):
            rr = pygame.Rect(width / 2 - 390, 230 + i * 70, 780, 55)
            rounded_panel(surface, rr, (4, 14, 20), (44, 93, 93), 12, 1)
            draw_text(surface, hint, 17, rr.center, (83, 255, 209), align="center", bold=True)

        self.quantum_field_rects = []
        names = ("X", "Y", "Z")
        for i, (name, value) in enumerate(zip(names, self.quantum_values)):
            rr = pygame.Rect(width / 2 - 300 + i * 205, 475, 185, 106)
            self.quantum_field_rects.append(rr)
            active = i == self.quantum_active_field
            rounded_panel(surface, rr, (3, 11, 16), (255, 194, 78) if active else (39, 91, 90), 16, 2 if active else 1)
            draw_text(surface, name, 17, (rr.centerx, rr.y + 25),
                      (94, 255, 211), align="center", mono=True, bold=True)
            draw_text(surface, value or "___", 34, (rr.centerx, rr.y + 70),
                      (255, 219, 129), align="center", mono=True, bold=True)

        self.quantum_submit = pygame.Rect(width / 2 - 160, 623, 320, 52)
        rounded_panel(surface, self.quantum_submit, (9, 30, 31), (61, 247, 194), 14, 2)
        draw_text(surface, "STABILIZE CURRENT", 16, self.quantum_submit.center,
                  (89, 255, 212), align="center", mono=True, bold=True)
        if self.quantum_error:
            draw_text(surface, self.quantum_error, 16, (width / 2, 712),
                      (255, 74, 90), align="center", bold=True)
        if self.phase == "timeout":
            draw_text(surface, "TIMEOUT // AUTO-ADVANCING", 16,
                      (width / 2, 755), (255, 64, 80), align="center", mono=True, bold=True)

    def _draw_stage12(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        frame = self.app.webcam.pygame_frame((width - 30, int(height * .66)))
        if frame:
            frame_rect = frame.get_rect(center=(width // 2, int(height * .53)))
            surface.blit(frame, frame_rect)
            pygame.draw.rect(surface, (65, 255, 190), frame_rect, 3)
        else:
            self.app.background.draw(surface)
            draw_text(surface, "CAMERA OFFLINE // KEEP THE CELEBRATION GOING",
                      18, (width / 2, int(height * .52)), (255, 77, 92), align="center", mono=True, bold=True)

        pygame.draw.rect(surface, (3, 19, 18), (20, 20, width - 40, 105))
        pygame.draw.rect(surface, (63, 255, 186), (20, 20, width - 40, 105), 2)
        draw_text(surface, "MACCABEAN ENERGY PROTOCOL", 17,
                  (width / 2, 46), (95, 255, 192), align="center", mono=True, bold=True)
        draw_text(surface, "כל הכבוד! הגעתם לשרת המרכזי הראשי!", 29,
                  (width / 2, 80), (236, 255, 243), align="center", bold=True)

        elapsed = time.monotonic() - self.dance_started
        meter = pygame.Rect(width // 2 - 330, int(height * .78), 660, 45)
        rounded_panel(surface, meter, (4, 17, 16), (68, 255, 188), 14, 2)
        fill_width = int((meter.w - 10) * self.energy / 100.0)
        if fill_width > 0:
            pygame.draw.rect(surface, (53, 245, 161), (meter.x + 5, meter.y + 5, fill_width, meter.h - 10))
        draw_text(surface, f"ENERGY // {int(self.energy):03d}%", 18,
                  (width / 2, meter.y + meter.h + 22), (91, 255, 194), align="center", mono=True, bold=True)
        mic_text = "MIC ACTIVE" if self._mic_stream is not None else "MIC UNAVAILABLE"
        draw_text(surface, f"MOTION + VOICE // {mic_text} // KEEP DANCING AND SINGING",
                  11, (width / 2, height - 27), (144, 195, 174), align="center", mono=True)
        if self.phase == "countdown" and self.countdown_started is not None:
            count = max(1, 5 - int(time.monotonic() - self.countdown_started))
            overlay = pygame.Surface((width, height), pygame.SRCALPHA)
            overlay.fill((6, 57, 35, 115 if count % 2 else 45))
            surface.blit(overlay, (0, 0))
            draw_text(surface, "אנטיוכוס 2.0 הובס!", 30,
                      (width / 2, int(height * .28)), (255, 239, 150), align="center", bold=True)
            draw_text(surface, str(count), 150,
                      (width / 2, int(height * .48)), (255, 255, 255), align="center", mono=True, bold=True)

    def lifeline_update(self):
        if self.lifeline_used or self.lifeline_active:
            return
        if self.app.remaining_seconds <= 600 and 5 <= self.app.stage_manager.stage <= 11:
            self.lifeline_active = True
            self.lifeline_index = 0
            self.lifeline_correct = 0
            self.lifeline_feedback = ""

    def handle_lifeline(self, event, width, height):
        if not self.lifeline_active:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.running = False
                return True
            if event.unicode in ("1", "2", "3", "4"):
                self._answer_lifeline(int(event.unicode) - 1)
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rr in enumerate(self.lifeline_option_rects):
                if rr.collidepoint(event.pos):
                    self._answer_lifeline(i)
                    return True
        return True

    def _answer_lifeline(self, choice):
        if not self.lifeline_active:
            return
        question, options, correct = self.LIFELINE_QUESTIONS[self.lifeline_index]
        if choice == correct:
            self.app.game_started_at -= 60
            self.lifeline_correct += 1
            self.lifeline_feedback = "+01:00 — דקה נוספת!"
            self.app.audio.play("confirm")
        else:
            self.lifeline_feedback = "לא הפעם. השעון לא נוסף."
            self.app.audio.play("error")
        self.lifeline_feedback_until = time.monotonic() + 0.75
        self.lifeline_index += 1
        if self.lifeline_index >= len(self.LIFELINE_QUESTIONS):
            self.lifeline_active = False
            self.lifeline_used = True

    def draw_lifeline(self, surface, draw_text, rounded_panel, pygame, width, height):
        if not self.lifeline_active:
            return
        veil = pygame.Surface((width, height), pygame.SRCALPHA)
        veil.fill((4, 8, 7, 228))
        surface.blit(veil, (0, 0))
        pulse = .5 + .5 * math.sin(time.monotonic() * 7)
        panel = pygame.Rect(width // 2 - 470, height // 2 - 300, 940, 590)
        rounded_panel(surface, panel, (15, 21, 12), (255, int(180 + 60 * pulse), 50), 24, 3)
        draw_text(surface, "ANTIOCHUS 2.0 // LAST TEN MINUTES", 14,
                  (width / 2, panel.y + 34), (255, 190, 60), align="center", mono=True, bold=True)
        draw_text(surface, "גלגל ההצלה", 42, (width / 2, panel.y + 85),
                  (255, 240, 192), align="center", bold=True)
        draw_text(surface, "כל תשובה נכונה מוסיפה דקה לשעון הכללי.", 18,
                  (width / 2, panel.y + 127), (232, 236, 214), align="center")
        question, options, correct = self.LIFELINE_QUESTIONS[self.lifeline_index]
        draw_text(surface, f"שאלה {self.lifeline_index + 1} מתוך 10", 15,
                  (width / 2, panel.y + 168), (255, 193, 78), align="center", mono=True, bold=True)
        draw_text(surface, question, 22, (width / 2, panel.y + 215),
                  (247, 249, 239), align="center", bold=True)
        self.lifeline_option_rects = []
        for i, option in enumerate(options):
            rr = pygame.Rect(panel.x + 65 + (i % 2) * 415,
                             panel.y + 270 + (i // 2) * 83, 390, 62)
            self.lifeline_option_rects.append(rr)
            rounded_panel(surface, rr, (16, 30, 21), (93, 166, 75), 13, 2)
            draw_text(surface, f"{i + 1}.  {option}", 19, rr.center,
                      (234, 242, 220), align="center", bold=True)
        draw_text(surface, f"תשובות נכונות: {self.lifeline_correct}  //  נשארו {10 - self.lifeline_index}",
                  14, (width / 2, panel.bottom - 26), (175, 208, 139), align="center", mono=True)
