from __future__ import annotations

import math
import time


class Stage7Controller:
    """Stage 7: server lamp cipher with purple as the documented answer."""

    COLORS = [
        ("RED", (235, 59, 72)),
        ("BLUE", (70, 140, 255)),
        ("GREEN", (61, 219, 151)),
        ("YELLOW", (255, 200, 67)),
        ("PURPLE", (179, 77, 255)),
        ("WHITE", (236, 243, 245)),
        ("ORANGE", (255, 130, 54)),
        ("CYAN", (67, 224, 235)),
    ]

    def __init__(self, app):
        self.app = app
        self.phase = "clue"
        self.verify_index = 0
        self.verify_score = 0.0

    @property
    def current_player(self):
        if not self.app.players:
            return None
        return self.app.players[min(self.verify_index, len(self.app.players) - 1)]

    def start(self):
        self.phase = "clue"
        self.verify_index = 0
        self.verify_score = 0.0

    def begin_verification(self):
        if not self.app.players:
            self.phase = "select"
            return
        self.phase = "verify"
        self.verify_score = 0.0
        self.app.webcam.read()

    def verify_current_player(self):
        player = self.current_player
        if not player:
            self.phase = "select"
            return
        ref = player.load()
        ok, score = self.app.webcam.verify_against(ref)
        self.verify_score = score
        if ok:
            self.verify_index += 1
            if self.verify_index >= len(self.app.players):
                self.phase = "select"

    def update(self, dt):
        if self.phase == "verify":
            self.app.webcam.read()

    def handle(self, event, pygame, width, height):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.running = False
            return

        if self.phase == "clue":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.begin_verification()

        elif self.phase == "verify":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self.verify_current_player()

        elif self.phase == "select":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i in range(8):
                    rr = pygame.Rect(width / 2 - 420 + (i % 4) * 220,
                                     390 + (i // 4) * 190, 180, 150)
                    if rr.collidepoint(event.pos):
                        if i == 4:  # documented intended answer: PURPLE
                            self.app.stage_manager.goto(8)
                        else:
                            self.app.stage_message = "SERVER FAILURE // WRONG NODE // RESTART PROTOCOL"
                            self.phase = "clue"
                            self.verify_index = 0
                            self.verify_score = 0.0

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        self.app.background.draw(surface)
        self.app.stage_manager.draw_stage_chip(surface)

        if self.phase == "clue":
            draw_text(surface, "SERVER LAMP CIPHER", 14, (width / 2, 55),
                      (90, 255, 210), align="center", mono=True, bold=True)
            draw_text(surface, "הצפנת החנוכייה הופעלה", 44,
                      (width / 2, 118), (240, 246, 248),
                      align="center", bold=True)
            draw_text(surface,
                      "הרמז חבוי במיקום שהוגדר מראש. פתרו את חידת הצבעים לפני שאתם ממשיכים.",
                      19, (width / 2, 170), (171, 194, 197), align="center")
            panel = pygame.Rect(width / 2 - 460, 245, 920, 265)
            rounded_panel(surface, panel, (4, 13, 18, 238), (52, 208, 169), 24, 2)

            draw_text(surface, "PHYSICAL CLUE // OPERATOR LOCATION", 11,
                      (panel.centerx, panel.y + 28), (255, 60, 78),
                      align="center", mono=True, bold=True)
            draw_text(surface, self.app.setup_server_location, 21,
                      (panel.centerx, panel.y + 70), (255, 203, 94),
                      align="center", bold=True)

            draw_text(surface,
                      "כדי למצוא את הצבע השרת הנכון: דם + שמיים = ?",
                      26, (panel.centerx, panel.y + 138),
                      (236, 243, 245), align="center", bold=True)
            draw_text(surface, "RED  +  BLUE  →  ?", 18,
                      (panel.centerx, panel.y + 186),
                      (83, 255, 210), align="center", mono=True, bold=True)

            btn = pygame.Rect(width / 2 - 190, 610, 380, 66)
            rounded_panel(surface, btn, (6, 18, 23), (255, 194, 79), 15, 2)
            draw_text(surface, "מצאנו את השרת האמיתי", 20,
                      btn.center, (242, 247, 246), align="center", bold=True)

        elif self.phase == "verify":
            player = self.current_player
            draw_text(surface, "SECURITY ROSTER // PRESENCE CHECK", 13,
                      (width / 2, 50), (255, 59, 79),
                      align="center", mono=True, bold=True)
            draw_text(surface, "אימות פנים נדרש לפני הגישה לשרתים", 36,
                      (width / 2, 105), (240, 245, 247),
                      align="center", bold=True)
            if player:
                draw_text(surface, player.name, 28, (width / 2, 150),
                          (255, 204, 92), align="center", bold=True)
            cam = pygame.Rect(width * .20, 205, width * .60, 410)
            rounded_panel(surface, cam, (2, 8, 12, 238),
                          (55, 255, 210), 24, 2)
            frame = self.app.webcam.pygame_frame((cam.w - 12, cam.h - 12))
            if frame:
                surface.blit(frame, (cam.x + 6, cam.y + 6))
            else:
                draw_text(surface, "WEBCAM OFFLINE", 25, cam.center,
                          (255, 62, 82), align="center", mono=True, bold=True)
            cx, cy = cam.center
            pulse = 85 + int((math.sin(t * 2.2) + 1) * 12)
            pygame.draw.circle(surface, (68, 255, 210), (cx, cy), pulse, 2)
            sweep = int((math.sin(t * 2.8) + 1) * cam.w * .24)
            pygame.draw.line(surface, (255, 64, 82),
                             (cam.left + 20 + sweep, cam.top + 10),
                             (cam.left + 20 + sweep, cam.bottom - 10), 2)
            draw_text(surface, f"PLAYER {self.verify_index + 1}/{len(self.app.players)}",
                      11, (cam.left + 18, cam.bottom - 22),
                      (76, 255, 207), mono=True)
            draw_text(surface, f"SIM {self.verify_score:0.2f}",
                      11, (cam.right - 18, cam.bottom - 22),
                      (255, 62, 78), align="topright", mono=True)
            draw_text(surface, "ENTER  //  VERIFY", 12, (width / 2, height - 50),
                      (128, 154, 159), align="center", mono=True)

        elif self.phase == "select":
            draw_text(surface, "SERVER GRID // ONE NODE IS AUTHENTIC", 13,
                      (width / 2, 47), (255, 61, 80),
                      align="center", mono=True, bold=True)
            draw_text(surface, "מצאנו את השרת האמיתי", 40,
                      (width / 2, 100), (239, 247, 249),
                      align="center", bold=True)
            draw_text(surface, "רק שרת אחד יפתח את חומת האש.",
                      18, (width / 2, 143), (166, 189, 193), align="center")
            for i, (name, color) in enumerate(self.COLORS):
                rr = pygame.Rect(width / 2 - 420 + (i % 4) * 220,
                                 390 + (i // 4) * 190, 180, 150)
                rounded_panel(surface, rr, (5, 15, 20), (49, 85, 88), 18, 2)
                cx, cy = rr.centerx, rr.y + 55
                glow_circle(surface, (cx, cy), 28, color, 14)
                pygame.draw.circle(surface, color, (cx, cy), 24)
                # Technical status light.
                pygame.draw.circle(surface, color,
                                   (rr.right - 18, rr.y + 18), 4 + int((math.sin(t * 4 + i) + 1) * 2))
                draw_text(surface, str(i + 1), 12, (rr.x + 16, rr.y + 16),
                          (112, 140, 145), mono=True)
                draw_text(surface, name, 15, (rr.centerx, rr.bottom - 23),
                          (235, 243, 245), align="center", mono=True, bold=True)
