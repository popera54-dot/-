from __future__ import annotations

import math
import time


class Stage6Controller:
    """
    Stage 6 from the supplied specification:
    dark screen + mouse flashlight, physical 8421 clue, group presence
    verification, then 8421 code entry.
    """

    def __init__(self, app):
        self.app = app
        self.phase = "dark"
        self.verify_index = 0
        self.verify_score = 0.0
        # Reuse one full-frame alpha layer; allocating a 1600x900 surface at 60 FPS
        # caused avoidable memory churn in the flashlight stage.
        self._flashlight_surface = None

    @property
    def current_player(self):
        if not self.app.players:
            return None
        return self.app.players[min(self.verify_index, len(self.app.players) - 1)]

    def start(self):
        self.phase = "dark"
        self.verify_index = 0
        self.verify_score = 0.0
        self.app.cipher_digits.clear()

    def begin_verification(self):
        if not self.app.players:
            self.phase = "code"
            return
        self.phase = "verify"
        self.verify_score = 0.0
        self.app.webcam.read()

    def verify_current_player(self):
        player = self.current_player
        if not player:
            self.phase = "code"
            return
        ref = player.load()
        ok, score = self.app.webcam.verify_against(ref)
        self.verify_score = score
        if ok:
            self.verify_index += 1
            if self.verify_index >= len(self.app.players):
                self.phase = "code"

    def update(self, dt):
        if self.phase == "verify":
            self.app.webcam.read()

    def handle(self, event, pygame, width, height):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.running = False
            return

        if self.phase == "dark":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                secret = pygame.Rect(width * .72, height * .67, 260, 76)
                if secret.collidepoint(event.pos):
                    self.begin_verification()

        elif self.phase == "verify":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self.verify_current_player()

        elif self.phase == "code":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    self.app.cipher_digits = self.app.cipher_digits[:-1]
                elif event.unicode.isdigit() and len(self.app.cipher_digits) < 4:
                    if not self.app.cipher_digits:
                        self.app.stage_message = ""
                    self.app.cipher_digits.append(event.unicode)
                    if len(self.app.cipher_digits) == 4:
                        if "".join(self.app.cipher_digits) == "8421":
                            self.app.stage_message = "DARK PROTOCOL CRACKED"
                            self.app.stage_manager.goto(7)
                        else:
                            self.app.stage_message = "CODE REJECTED // RECHECK THE PHYSICAL CLUE"
                            self.app.cipher_digits.clear()

    @staticmethod
    def make_flashlight_overlay(width, height, center, pygame, radius=108, target_surface=None):
        """Fill a reusable black alpha layer with a soft spotlight cutout."""
        radius = max(1, int(radius))
        size = (int(width), int(height))
        overlay = target_surface
        if overlay is None or overlay.get_size() != size:
            overlay = pygame.Surface(size, pygame.SRCALPHA)
        overlay.set_clip(None)
        overlay.fill((0, 0, 0, 249))
        cx, cy = map(int, center)
        # The gradient is small compared with the full-screen layer; clip prevents
        # any accidental pixels outside the spotlight from being rewritten by the circles.
        spotlight_rect = pygame.Rect(cx - radius, cy - radius, radius * 2 + 1, radius * 2 + 1)
        overlay.set_clip(spotlight_rect.clip(overlay.get_rect()))
        for r in range(radius, 0, -3):
            alpha = int(249 * (r / radius) ** 1.65)
            pygame.draw.circle(overlay, (0, 0, 0, alpha), (cx, cy), r)
        overlay.set_clip(None)
        return overlay

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        self.app.background.draw(surface)
        self.app.stage_manager.draw_stage_chip(surface)

        mx, my = pygame.mouse.get_pos()

        if self.phase == "dark":
            draw_text(surface, "DARK LIGHT PROTOCOL", 14, (width / 2, 55),
                      (70, 255, 210), align="center", mono=True, bold=True)
            draw_text(surface, "חושבים שאתם קרובים לנצח?", 31, (width / 2, 115),
                      (238, 244, 246), align="center", bold=True)
            draw_text(surface, "בשביל להמשיך הלאה תאלצו לכבות את האור בחדר.",
                      20, (width / 2, 154), (255, 68, 86),
                      align="center", bold=True)

            secret = pygame.Rect(width * .72, height * .67, 260, 76)
            if secret.collidepoint(mx, my):
                glow_circle(surface, secret.center, 34, (66, 255, 207), 18)
                rounded_panel(surface, secret, (4, 18, 22), (66, 255, 207), 16, 3)
                draw_text(surface, "עברנו הכל — ממשיכים", 18, secret.center,
                          (231, 248, 245), align="center", bold=True)

            draw_text(surface, "חפשו את הקוד הזוהר בחדר.", 15,
                      (width / 2, height - 58), (255, 196, 91),
                      align="center", bold=True)

        elif self.phase == "verify":
            player = self.current_player
            draw_text(surface, "SECURITY ROSTER // PRESENCE CHECK", 13,
                      (width / 2, 50), (255, 59, 78),
                      align="center", mono=True, bold=True)
            draw_text(surface, "התייצב מול המצלמה", 42, (width / 2, 105),
                      (240, 245, 247), align="center", bold=True)
            if player:
                draw_text(surface, player.name, 30, (width / 2, 155),
                          (255, 204, 92), align="center", bold=True)

            cam = pygame.Rect(width * .20, 220, width * .60, 410)
            rounded_panel(surface, cam, (2, 8, 12, 235),
                          (55, 255, 210), 24, 2)
            frame = self.app.webcam.pygame_frame((cam.w - 12, cam.h - 12))
            if frame:
                surface.blit(frame, (cam.x + 6, cam.y + 6))
            else:
                draw_text(surface, "WEBCAM OFFLINE", 25, cam.center,
                          (255, 62, 82), align="center", mono=True, bold=True)

            cx, cy = cam.center
            sweep = int((math.sin(t * 2.5) + 1) * cam.w * .25)
            pygame.draw.line(surface, (58, 255, 208),
                             (cam.left + 30 + sweep, cam.top + 15),
                             (cam.left + 30 + sweep, cam.bottom - 15), 2)
            pygame.draw.circle(surface, (68, 255, 210), (cx, cy), 118, 2)
            draw_text(surface, f"PLAYER {self.verify_index + 1}/{len(self.app.players)}",
                      11, (cam.left + 18, cam.bottom - 24),
                      (76, 255, 207), mono=True)
            draw_text(surface, f"SIM {self.verify_score:0.2f}",
                      11, (cam.right - 18, cam.bottom - 24),
                      (255, 62, 78), align="topright", mono=True)
            draw_text(surface, "לחצו ENTER לאחר שהשחקן הנכון מופיע במסגרת.",
                      14, (width / 2, height - 58),
                      (130, 155, 160), align="center")

        elif self.phase == "code":
            draw_text(surface, "FINAL ACCESS CHECK", 13, (width / 2, 50),
                      (70, 255, 210), align="center", mono=True, bold=True)
            draw_text(surface, "הזינו את הקוד שמצאתם בחדר", 35,
                      (width / 2, 110), (239, 246, 248),
                      align="center", bold=True)
            code = "".join(self.app.cipher_digits)
            rr = pygame.Rect(width / 2 - 220, 220, 440, 82)
            rounded_panel(surface, rr, (3, 10, 14), (255, 195, 86), 18, 2)
            draw_text(surface, code or "____", 42, rr.center,
                      (255, 220, 130), align="center", mono=True, bold=True)
            draw_text(surface, "PRESENCE VERIFIED // CORE INPUT READY",
                      11, (width / 2, 335), (59, 187, 143),
                      align="center", mono=True)

        # Darken the complete frame after all HUD, instructions, camera content,
        # and the hidden control have been drawn. The cursor-sized light then
        # reveals only the pixels beneath it instead of leaving text always visible.
        light_radius = 108 + int((math.sin(t * 3.1) + 1) * 9)
        dark = self.make_flashlight_overlay(
            width, height, (mx, my), pygame, light_radius,
            target_surface=self._flashlight_surface
        )
        self._flashlight_surface = dark
        surface.blit(dark, (0, 0))
