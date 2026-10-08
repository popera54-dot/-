from __future__ import annotations

import math
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pygame

from stage4_puzzle import Stage4Controller
from stage5_tasks import TaskBase, OilCatchTask, create_task_pool
from stage6_protocol import Stage6Controller
from stage7_server_cipher import Stage7Controller

# ============================================================
# THE GREEKS ARE BACK
# Cinematic Hanukkah escape-room foundation
# ============================================================

WIDTH, HEIGHT = 1600, 900
FPS = 60
TOTAL_SECONDS = 60 * 60
DATA_DIR = Path("data")
PLAYER_DIR = DATA_DIR / "players"
DATA_DIR.mkdir(exist_ok=True)
PLAYER_DIR.mkdir(exist_ok=True)

pygame.init()
pygame.font.init()
pygame.mixer.init()

screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.SCALED)
WIDTH, HEIGHT = screen.get_size()
pygame.display.set_caption("היוונים חוזרים — Antiochus 2.0")
pygame.mouse.set_visible(True)

FONT_NAME = pygame.font.match_font("segoeui") or pygame.font.get_default_font()
MONO_NAME = pygame.font.match_font("consolas") or pygame.font.get_default_font()
BOLD_NAME = pygame.font.match_font("segoeuib") or FONT_NAME


def font(size: int, mono: bool = False, bold: bool = False) -> pygame.font.Font:
    name = MONO_NAME if mono else (BOLD_NAME if bold else FONT_NAME)
    return pygame.font.Font(name, size)


def clamp(value, low, high):
    return max(low, min(high, value))


def draw_text(surface, text, size, pos, color=(235, 245, 255),
              *, align="topleft", mono=False, bold=False):
    f = font(size, mono=mono, bold=bold)
    img = f.render(text, True, color)
    rect = img.get_rect()
    setattr(rect, align, pos)
    surface.blit(img, rect)
    return rect


def rounded_panel(surface, rect, fill, border=(70, 255, 210), radius=24, width=1):
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    if width:
        pygame.draw.rect(surface, border, rect, width, border_radius=radius)


def glow_circle(surface, pos, radius, color, alpha=45):
    layer = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
    cx, cy = radius * 3, radius * 3
    for r in range(radius * 3, max(2, radius // 2), -4):
        a = int(alpha * (1 - r / (radius * 3)) ** 2)
        pygame.draw.circle(layer, (*color, a), (cx, cy), r)
    pygame.draw.circle(layer, (*color, min(255, alpha * 3)), (cx, cy), radius)
    surface.blit(layer, (pos[0] - cx, pos[1] - cy))


def draw_scanlines(surface, spacing=5, alpha=16):
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    for y in range(0, surface.get_height(), spacing):
        pygame.draw.line(overlay, (140, 255, 225, alpha), (0, y), (surface.get_width(), y))
    surface.blit(overlay, (0, 0))


def draw_grid(surface, horizon_y=None):
    horizon_y = horizon_y or int(HEIGHT * 0.62)
    col = (26, 68, 72)
    for x in range(-WIDTH, WIDTH * 2, 80):
        pygame.draw.line(surface, col, (WIDTH // 2, horizon_y), (x, HEIGHT), 1)
    for i in range(14):
        y = horizon_y + int((HEIGHT - horizon_y) * (i / 13) ** 2)
        pygame.draw.line(surface, col, (0, y), (WIDTH, y), 1)


def draw_live_system_overlay(surface, t: float, danger: float = 0.0):
    """
    Always-on ambient motion layer. It intentionally keeps moving even while
    players are reading a puzzle so the screen never feels static.
    """
    # Moving scan beam
    beam_y = int((t * 115) % (HEIGHT + 180)) - 90
    beam = pygame.Surface((WIDTH, 90), pygame.SRCALPHA)
    pygame.draw.rect(beam, (45, 255, 203, 12), (0, 36, WIDTH, 18))
    pygame.draw.rect(beam, (45, 255, 203, 5), (0, 10, WIDTH, 52))
    surface.blit(beam, (0, beam_y))

    # Corner targeting brackets with subtle breathing animation.
    pulse = 0.5 + 0.5 * math.sin(t * 2.7)
    bracket_col = (48, 215, 173)
    red_col = (255, 45, 67)
    b = int(7 + pulse * 7)
    corners = [
        (24, 126, 1, 1),
        (WIDTH - 24, 126, -1, 1),
        (24, HEIGHT - 126, 1, -1),
        (WIDTH - 24, HEIGHT - 126, -1, -1),
    ]
    for x, y, sx, sy in corners:
        pygame.draw.line(surface, bracket_col, (x, y), (x + sx * 36, y), 2)
        pygame.draw.line(surface, bracket_col, (x, y), (x, y + sy * 36), 2)
        pygame.draw.circle(surface, (*bracket_col, 120), (x, y), b, 1)

    # Red pulse marker that travels around the perimeter.
    perimeter = 2 * (WIDTH + HEIGHT)
    d = int((t * 170) % perimeter)
    if d < WIDTH:
        px, py = d, 8
    elif d < WIDTH + HEIGHT:
        px, py = WIDTH - 8, d - WIDTH
    elif d < WIDTH * 2 + HEIGHT:
        px, py = WIDTH * 2 - d, HEIGHT - 8
    else:
        px, py = 8, HEIGHT - (d - WIDTH * 2 - HEIGHT)
    glow_circle(surface, (px, py), 10 + int(pulse * 4), red_col, 10)
    pygame.draw.circle(surface, red_col, (px, py), 3)

    # Live left terminal feed.
    feed_x = 28
    feed_y = 151
    messages = [
        "AUTH::NODE_07  CONNECTED",
        "PACKET_STREAM // LIVE",
        "FIREWALL::SIGMA  BREACH",
        "TRACE::ORIGIN  UNKNOWN",
        "CRYPTO::KEY  ROTATING",
        "MEMORY::ENCRYPTED",
        "SESSION::ANTIOCHUS_2",
        "WATCHDOG::ACTIVE",
        "BIOMETRIC::STANDBY",
        "UPLINK::STABLE",
    ]
    tick = int(t * 2.3)
    for i in range(7):
        msg = messages[(tick + i) % len(messages)]
        yy = feed_y + i * 20
        alpha = 125 if i else 205
        draw_text(surface, f"[{(tick+i)%99:02d}] {msg}", 10,
                  (feed_x, yy), (40, alpha, 103), mono=True)

    # Live right telemetry, values constantly shifting.
    telem_x = WIDTH - 280
    draw_text(surface, "LIVE TELEMETRY", 11, (telem_x, 127),
              (255, 60, 79), mono=True, bold=True)
    telemetry = [
        ("CPU", 38 + 22 * pulse),
        ("RAM", 61 + 13 * math.sin(t * 1.6)),
        ("NET", 74 + 19 * math.sin(t * 2.1 + 1)),
        ("CORE", 52 + 27 * math.sin(t * 1.1 + 2)),
    ]
    for i, (label, value) in enumerate(telemetry):
        yy = 153 + i * 29
        width = int(clamp(value, 4, 98) * 2.0)
        draw_text(surface, label, 10, (telem_x, yy),
                  (108, 139, 144), mono=True)
        pygame.draw.rect(surface, (26, 49, 52), (telem_x + 42, yy + 2, 170, 8))
        pygame.draw.rect(surface,
                         (255, 57, 77) if danger else (52, 220, 175),
                         (telem_x + 42, yy + 2, width, 8))
        draw_text(surface, f"{value:05.1f}%", 9, (telem_x + 217, yy),
                  (221, 232, 235), mono=True, align="topright")

    # Bottom moving ticker / packet lane.
    lane_y = HEIGHT - 69
    pygame.draw.line(surface, (49, 75, 78), (24, lane_y), (WIDTH - 24, lane_y), 1)
    offset = int((t * 120) % 1100)
    ticker = [
        "ANTIOCHUS_2.0",
        "SECURITY_CORE",
        "MKBS_PROTOCOL",
        "INTRUSION_ACTIVE",
        "DECRYPTING",
        "DO_NOT_TRUST",
        "HANNukkAH_SEQUENCE",
        "ROOT_ACCESS",
    ]
    for i in range(9):
        x = ((i * 155 - offset) % (WIDTH + 160)) - 80
        col = (255, 54, 73) if i % 5 == 0 and pulse > 0.65 else (48, 177, 139)
        draw_text(surface, f"// {ticker[i % len(ticker)]} //", 10,
                  (x, lane_y + 14), col, mono=True)

    # Tiny rotating "signal" glyph in a corner.
    cx, cy = WIDTH - 72, HEIGHT - 112
    angle = t * 2.8
    points = []
    for i in range(6):
        a = angle + i * math.tau / 6
        points.append((cx + math.cos(a) * 22, cy + math.sin(a) * 22))
    pygame.draw.polygon(surface, (49, 191, 158), points, 1)
    pygame.draw.circle(surface, (255, 48, 69), (cx, cy), 5 + int(pulse * 3), 1)


@dataclass
class Particle:
    x: float
    y: float
    speed: float
    drift: float
    size: int
    alpha: int

    def update(self, dt):
        self.y += self.speed * dt
        self.x += math.sin(self.y * 0.015) * self.drift * dt
        if self.y > HEIGHT + 20:
            self.y = -20
            self.x = random.uniform(0, WIDTH)

    def draw(self, surface):
        pygame.draw.circle(surface, (90, 255, 215, self.alpha), (int(self.x), int(self.y)), self.size)


class CinematicBackground:
    def __init__(self):
        self.time = 0.0
        self.particles = [
            Particle(
                random.uniform(0, WIDTH),
                random.uniform(0, HEIGHT),
                random.uniform(15, 55),
                random.uniform(-7, 7),
                random.choice([1, 1, 1, 2]),
                random.randint(30, 120),
            )
            for _ in range(150)
        ]

    def update(self, dt):
        self.time += dt
        for p in self.particles:
            p.update(dt)

    def draw(self, surface, danger=0.0):
        surface.fill((3, 7, 12))

        # Deep radial-ish atmosphere
        for i in range(9, 0, -1):
            alpha = 4 + i * 2
            rect = pygame.Rect(
                WIDTH * 0.5 - i * 160,
                HEIGHT * 0.44 - i * 90,
                i * 320,
                i * 180,
            )
            pygame.draw.ellipse(surface, (9, 42, 48, alpha), rect)

        # Cyan and crimson energy blooms
        glow_circle(surface, (WIDTH * 0.14, HEIGHT * 0.22), 150, (15, 210, 180), 25)
        glow_circle(surface, (WIDTH * 0.86, HEIGHT * 0.24), 180, (255, 36, 70), 18)

        draw_grid(surface)

        # Dense hacker terminal data rain: green streams with intermittent red alerts.
        glyphs = ["0", "1", "7", "X", "A", "F", "C", "E", "M", "K", ":", "/", "<", ">", "#", "$"]
        for x in range(10, WIDTH, 28):
            speed = 55 + (x * 17) % 125
            offset = int((self.time * speed + x * 31) % (HEIGHT + 180))
            length = 8 + ((x // 28) % 9)
            for j in range(length):
                yy = (offset - j * 22) % (HEIGHT + 40) - 20
                intensity = clamp(160 - j * 15, 35, 160)
                is_red = ((x // 28) % 17 == 0) and j < 4
                col = (255, intensity // 3, intensity // 3) if is_red else (35, intensity, 88)
                draw_text(surface, random.choice(glyphs), 13,
                          (x, yy), col, mono=True, align="center")

        # Wide terminal panels drifting behind gameplay.
        for k in range(7):
            y = 110 + k * 95
            drift = int(math.sin(self.time * 0.7 + k) * 35)
            draw_text(surface,
                      random.choice([
                          "ACCESSING SECURITY CORE...",
                          "AUTH_CHANNEL::MKBS_2.0",
                          "DECRYPT /████/████/████",
                          "INTRUSION TRACE // 97%",
                          "FIREWALL NODE // BREACHED",
                          "ROOT SESSION // UNKNOWN",
                          "WARNING // SYSTEM INTEGRITY",
                      ]),
                      12, (18 + drift, y), (43, 128, 99), mono=True)

        # Red diagnostic rails, like a compromised military terminal.
        for side in (0, WIDTH - 8):
            pygame.draw.rect(surface, (145, 24, 40), (side, 0, 8, HEIGHT))
        for y in (105, HEIGHT - 105):
            pygame.draw.line(surface, (80, 21, 30), (0, y), (WIDTH, y), 2)

        for p in self.particles:
            p.draw(surface)

        # Danger vignette
        if danger:
            edge = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            pygame.draw.rect(edge, (255, 20, 30, int(35 * danger)), edge.get_rect(), 24)
            surface.blit(edge, (0, 0))

        draw_live_system_overlay(surface, self.time, danger)
        draw_scanlines(surface)


class Button:
    def __init__(self, rect, label, accent=(41, 245, 195), subtitle=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.accent = accent
        self.subtitle = subtitle
        self.hover = False

    def update(self):
        self.hover = self.rect.collidepoint(pygame.mouse.get_pos())

    def draw(self, surface):
        self.update()
        fill = (10, 22, 29) if not self.hover else (12, 34, 39)
        border = tuple(clamp(c + (35 if self.hover else 0), 0, 255) for c in self.accent)
        rounded_panel(surface, self.rect, fill, border, 14, 2)
        if self.hover:
            glow_circle(surface, self.rect.center, 20, self.accent, 13)
        draw_text(surface, self.label, 22, self.rect.center, (235, 255, 250),
                  align="center", bold=True)
        if self.subtitle:
            draw_text(surface, self.subtitle, 12,
                      (self.rect.centerx, self.rect.bottom - 15),
                      (125, 165, 167), align="midbottom")

    def clicked(self, event):
        return event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos)


class Webcam:
    def __init__(self):
        self.cap = None
        self.frame = None
        self.face_box = None
        self.available = False
        self.last_error = None
        self._open()

    def _open(self):
        try:
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            self.available = bool(self.cap and self.cap.isOpened())
        except Exception as exc:
            self.last_error = str(exc)
            self.available = False

    def read(self):
        if not self.available:
            return None
        ok, frame = self.cap.read()
        if not ok:
            return None
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(cascade)
        faces = detector.detectMultiScale(gray, 1.15, 5, minSize=(90, 90))
        self.face_box = max(faces, key=lambda b: b[2] * b[3]) if len(faces) else None
        self.frame = frame
        return frame

    def capture_face(self):
        if self.frame is None or self.face_box is None:
            return None
        x, y, w, h = self.face_box
        margin = int(max(w, h) * 0.25)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(self.frame.shape[1], x + w + margin)
        y2 = min(self.frame.shape[0], y + h + margin)
        return self.frame[y1:y2, x1:x2].copy()

    def verify_against(self, reference_bgr):
        """
        Prototype verification: compares normalized grayscale histograms
        of the detected face crop. This is intentionally NOT presented as
        production biometric identification.
        """
        current = self.capture_face()
        if current is None or reference_bgr is None:
            return False, 0.0
        a = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        b = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2GRAY)
        a = cv2.resize(a, (128, 128))
        b = cv2.resize(b, (128, 128))
        ha = cv2.calcHist([a], [0], None, [32], [0, 256])
        hb = cv2.calcHist([b], [0], None, [32], [0, 256])
        cv2.normalize(ha, ha)
        cv2.normalize(hb, hb)
        score = float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))
        return score > 0.72, score

    def pygame_frame(self, size):
        if self.frame is None:
            return None
        rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, size)
        return pygame.image.frombuffer(rgb.tobytes(), size, "RGB").copy()

    def release(self):
        if self.cap:
            self.cap.release()


class Player:
    def __init__(self, name: str, image_path: Path):
        self.name = name
        self.image_path = image_path

    def load(self):
        data = cv2.imread(str(self.image_path))
        return data


class Stage5Controller:
    """Per-player security-chain controller defined by the supplied specification."""

    def __init__(self, app):
        self.app = app
        self.phase = "briefing"
        self.tasks = []
        self.current_task_index = 0
        self.assigned_player = 0
        self.phase_started = time.monotonic()
        self.verify_score = 0.0

    def start(self):
        count = max(1, len(self.app.players))
        self.tasks = create_task_pool(count)
        self.current_task_index = 0
        self.assigned_player = 0
        self.phase = "briefing"
        self.phase_started = time.monotonic()

    @property
    def current_player(self):
        if not self.app.players:
            return None
        return self.app.players[min(self.assigned_player, len(self.app.players) - 1)]

    @property
    def current_task(self):
        return self.tasks[self.current_task_index] if self.tasks else None

    def begin_verification(self):
        self.phase = "verify"
        self.phase_started = time.monotonic()
        self.verify_score = 0.0
        self.app.webcam.read()

    def accept_verification(self, score):
        self.verify_score = score
        self.phase = "task"
        self.phase_started = time.monotonic()
        if self.current_task:
            self.current_task.reset()

    def advance(self):
        self.assigned_player += 1
        self.current_task_index += 1
        if self.assigned_player >= len(self.app.players):
            self.app.stage_manager.goto(6)
            return
        self.begin_verification()

    def update(self, dt):
        if self.phase == "verify":
            self.app.webcam.read()
        elif self.phase == "task" and self.current_task:
            if isinstance(self.current_task, OilCatchTask):
                self.current_task.update_and_collide(dt, WIDTH, HEIGHT)
            else:
                self.current_task.update(dt)

    def draw(self, surface):
        t = self.app.background.time
        self.app.background.draw(
            surface,
            danger=1.0 if self.phase == "verify" else 0.0,
        )
        player = self.current_player
        task = self.current_task

        if self.phase == "briefing":
            draw_text(surface, "SECURITY CHAIN PROTOCOL", 17, (WIDTH / 2, 72),
                      (255, 58, 78), align="center", mono=True, bold=True)
            draw_text(surface, "שרשרת האבטחה הופעלה", 46, (WIDTH / 2, 130),
                      (246, 248, 249), align="center", bold=True)
            draw_text(surface,
                      f"נרשמו {len(self.app.players)} לוחמים  •  לכל לוחם הוקצתה משימה אחת",
                      20, (WIDTH / 2, 188), (160, 181, 185), align="center")
            for i in range(min(10, len(self.app.players))):
                rr = pygame.Rect(WIDTH / 2 - 350 + (i % 5) * 140,
                                 300 + (i // 5) * 95, 125, 70)
                rounded_panel(surface, rr, (5, 15, 20), (54, 207, 169), 14, 2)
                draw_text(surface, f"{i+1:02d}", 12, (rr.centerx, rr.y + 16),
                          (77, 255, 210), align="center", mono=True)
                draw_text(surface, self.app.players[i].name, 15,
                          (rr.centerx, rr.y + 44), (228, 239, 241),
                          align="center", bold=True)
            draw_text(surface, "המערכת מאתחלת מנעולים אישיים…", 14,
                      (WIDTH / 2, HEIGHT - 110), (109, 143, 148),
                      align="center", mono=True)
            if time.monotonic() - self.phase_started > 2.6:
                self.begin_verification()
            return

        if self.phase == "verify":
            draw_text(surface, "BIOMETRIC LOCK // PLAYER VERIFICATION", 14,
                      (WIDTH / 2, 72), (255, 57, 78), align="center", mono=True, bold=True)
            draw_text(surface, "אימות פנים נדרש", 50, (WIDTH / 2, 128),
                      (242, 247, 248), align="center", bold=True)
            if player:
                draw_text(surface, f"התייצב מול המצלמה:  {player.name}", 24,
                          (WIDTH / 2, 185), (255, 204, 99),
                          align="center", bold=True)

            cam_rect = pygame.Rect(WIDTH * .19, 245, WIDTH * .62, 430)
            rounded_panel(surface, cam_rect, (3, 10, 15, 245),
                          (51, 242, 192), 24, 2)
            frame = self.app.webcam.pygame_frame((cam_rect.w - 12, cam_rect.h - 12))
            if frame:
                surface.blit(frame, (cam_rect.x + 6, cam_rect.y + 6))
            else:
                draw_text(surface, "CAMERA SIGNAL LOST", 25, cam_rect.center,
                          (255, 61, 80), align="center", mono=True, bold=True)

            cx, cy = cam_rect.center
            sweep = int((math.sin(t * 2.2) + 1) * cam_rect.w * .28)
            pygame.draw.line(surface, (58, 255, 208),
                             (cam_rect.left + 40 + sweep, cam_rect.top + 15),
                             (cam_rect.left + 40 + sweep, cam_rect.bottom - 15), 2)
            pygame.draw.circle(surface, (70, 255, 210), (cx, cy), 118, 2)
            pygame.draw.circle(surface, (70, 255, 210), (cx, cy), 94, 1)
            draw_text(surface, "SCANNING...", 12, (cam_rect.left + 20, cam_rect.top + 20),
                      (65, 255, 203), mono=True, bold=True)
            draw_text(surface, f"SIMILARITY  {self.verify_score:0.2f}",
                      12, (cam_rect.right - 20, cam_rect.top + 20),
                      (255, 63, 80), align="topright", mono=True)

            draw_text(surface, "הזיהוי ימשיך רק כאשר השחקן הנכון מזוהה.",
                      15, (WIDTH / 2, HEIGHT - 70), (126, 153, 158),
                      align="center")
            return

        if self.phase == "task" and task:
            draw_text(surface,
                      f"PLAYER {self.assigned_player + 1:02d}  //  {player.name if player else 'UNKNOWN'}",
                      13, (WIDTH / 2, 30), (255, 193, 78),
                      align="center", mono=True, bold=True)
            task.draw(surface, draw_text, rounded_panel, glow_circle, pygame, WIDTH, HEIGHT, t)

    def handle(self, event):
        if self.phase == "verify":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN and self.current_player:
                ref = self.current_player.load()
                ok, score = self.app.webcam.verify_against(ref)
                self.verify_score = score
                if ok:
                    self.accept_verification(score)
            return

        if self.phase == "task" and self.current_task:
            result = self.current_task.handle(event, pygame, WIDTH, HEIGHT)
            if result.completed or self.current_task.done:
                self.advance()


class StageManager:
    def __init__(self, app):
        self.app = app
        self.stage = 0
        self.stage4 = Stage4Controller(app)
        self.stage5 = Stage5Controller(app)
        self.stage6 = Stage6Controller(app)
        self.stage7 = Stage7Controller(app)

    def goto(self, stage):
        self.stage = stage
        self.app.stage_started_at = time.monotonic()
        self.app.stage_message = ""
        if stage == 4:
            self.stage4.start()
        elif stage == 5:
            self.stage5.start()
        elif stage == 6:
            self.stage6.start()
        elif stage == 7:
            self.stage7.start()

    def draw_stage_chip(self, surface):
        if self.stage <= 0:
            return
        label = f"PROTOCOL {self.stage:02d}"
        draw_text(surface, label, 13, (40, 30), (88, 255, 215), mono=True, bold=True)
        draw_text(surface, self.app.stage_names.get(self.stage, "UNKNOWN").upper(),
                  13, (40, 54), (110, 140, 147), mono=True)

    def draw(self, surface):
        if self.stage == 1:
            self.draw_stage_1(surface)
        elif self.stage == 2:
            self.draw_stage_2(surface)
        elif self.stage == 3:
            self.draw_stage_3(surface)
        elif self.stage == 4:
            self.stage4.draw(surface, draw_text, rounded_panel, glow_circle, pygame, WIDTH, HEIGHT, self.app.background.time)
        elif self.stage == 5:
            self.stage5.draw(surface)
        elif self.stage == 6:
            self.stage6.draw(surface, draw_text, rounded_panel, glow_circle, pygame, WIDTH, HEIGHT, self.app.background.time)
        elif self.stage == 7:
            self.stage7.draw(surface, draw_text, rounded_panel, glow_circle, pygame, WIDTH, HEIGHT, self.app.background.time)
        else:
            self.draw_placeholder(surface)

    def draw_stage_1(self, surface):
        elapsed = time.monotonic() - self.app.stage_started_at
        pulse = (math.sin(elapsed * 4.8) + 1) * 0.5
        self.app.background.draw(surface, danger=min(1.0, elapsed / 2.5))

        # Fake error windows
        if elapsed < 2.9:
            for i in range(17):
                x = int((i * 173 + elapsed * (30 + i * 8)) % (WIDTH - 280))
                y = int((i * 59 + abs(math.sin(elapsed * 5 + i)) * 300) % (HEIGHT - 90))
                rect = pygame.Rect(x, y, 260, 64)
                pygame.draw.rect(surface, (222, 234, 238), rect, border_radius=5)
                draw_text(surface, "SYSTEM FAILURE", 12, (x + 12, y + 10), (24, 33, 38), mono=True, bold=True)
                draw_text(surface, "0x" + format((i * 917 + int(elapsed * 99)) % 65535, "04X"),
                          11, (x + 12, y + 33), (130, 32, 42), mono=True)

        # Live hacker terminal status strip.
        status_y = 112
        draw_text(surface, ">> SECURE SHELL // ANTIOCHUS-2.0", 13,
                  (34, status_y), (63, 255, 178), mono=True, bold=True)
        draw_text(surface, f"TRACE:{int(elapsed * 73) % 9999:04d}  NODE:MK-{random.randint(10,99)}  SIGNAL:ACTIVE",
                  12, (34, status_y + 24), (145, 54, 68), mono=True)
        draw_text(surface, "01010111 01100001 01110010 01101110 01101001 01101110 01100111",
                  11, (34, status_y + 48), (31, 125, 91), mono=True)

        # Hacker alert
        if elapsed >= 2.0:
            y = HEIGHT * 0.36
            draw_text(surface, "⚠  WARNING  ⚠", 32, (WIDTH / 2, y - 62),
                      (255, 51, 73), align="center", mono=True, bold=True)
            if elapsed < 7.2:
                alpha_color = (255, 255, 255)
                draw_text(surface, "REMOTE INTRUSION DETECTED", 56,
                          (WIDTH / 2, y), alpha_color, align="center", mono=True, bold=True)
                draw_text(surface, "מערכת ההפעלה נחסמה  •  קוד קיוסק יווני הופעל",
                          24, (WIDTH / 2, y + 54), (165, 225, 218), align="center", bold=True)

        # Antiochus avatar
        if elapsed >= 4.0:
            self.draw_hacker(surface, (WIDTH / 2, HEIGHT * 0.60), 150, pulse)

            rounded_panel(surface,
                          pygame.Rect(WIDTH // 2 - 330, HEIGHT - 150, 660, 82),
                          (5, 12, 18, 235), (255, 52, 72), 18, 2)
            draw_text(surface, "ANTIOCHUS 2.0  //  ACTIVE SESSION", 14,
                      (WIDTH / 2, HEIGHT - 130), (255, 75, 90), align="center", mono=True, bold=True)
            draw_text(surface, '"המחשב שלכם שייך לי כעת. השעון מתחיל... עכשיו."',
                      18, (WIDTH / 2, HEIGHT - 99), (235, 245, 247), align="center")

        if elapsed > 8.8:
            self.goto(2)

    def draw_hacker(self, surface, center, radius, pulse):
        cx, cy = center
        glow_circle(surface, center, radius + 50, (255, 44, 58), 13)
        # cloak
        pygame.draw.ellipse(surface, (15, 18, 24), (cx - 122, cy + 30, 244, 180))
        # helmet / face
        pygame.draw.circle(surface, (34, 40, 48), (cx, cy - 20), radius - 22)
        pygame.draw.arc(surface, (116, 136, 145),
                        (cx - radius + 10, cy - radius + 15, (radius - 10) * 2, (radius - 10) * 2),
                        math.radians(200), math.radians(340), 4)
        # neon visor
        visor = pygame.Rect(cx - 82, cy - 42, 164, 40)
        pygame.draw.rect(surface, (6, 22, 22), visor, border_radius=12)
        pygame.draw.line(surface, (51, 255, 198), (cx - 70, cy - 22), (cx + 70, cy - 22), 4)
        for i in range(7):
            xx = cx - 65 + i * 22
            pygame.draw.circle(surface, (76, 255, 202), (xx, cy - 22), 3 + int(pulse * 2))
        # Greek key motif
        for dx in (-1, 1):
            x = cx + dx * 104
            pygame.draw.line(surface, (221, 180, 91), (x, cy + 15), (x + dx * 18, cy + 33), 3)
        draw_text(surface, "ΑΝΤΙΟΧΟΣ 2.0", 13, (cx, cy + 118), (210, 170, 90),
                  align="center", mono=True, bold=True)

    def draw_stage_2(self, surface):
        self.app.background.draw(surface)
        draw_text(surface, "THE BIO-REGISTRATION", 17, (WIDTH / 2, 42),
                  (86, 255, 215), align="center", mono=True, bold=True)
        draw_text(surface, "פרופיל הגנת המכבים", 43, (WIDTH / 2, 88),
                  (240, 250, 252), align="center", bold=True)
        draw_text(surface, "כל לוחם נרשם בתורו. המערכת תשמור את התמונה לצורך אימות במשימות הבאות.",
                  18, (WIDTH / 2, 137), (137, 162, 171), align="center")

        cam_rect = pygame.Rect(WIDTH * 0.10, HEIGHT * 0.23, WIDTH * 0.52, HEIGHT * 0.55)
        rounded_panel(surface, cam_rect, (4, 12, 18, 235), (55, 255, 210), 28, 2)

        frame = self.app.webcam.pygame_frame((cam_rect.w - 12, cam_rect.h - 12))
        if frame:
            # dark overlay + frame
            surface.blit(frame, (cam_rect.x + 6, cam_rect.y + 6))
            pygame.draw.rect(surface, (65, 255, 210), cam_rect.inflate(-18, -18), 2, border_radius=22)
        else:
            draw_text(surface, "WEBCAM OFFLINE", 28, cam_rect.center, (255, 70, 90),
                      align="center", mono=True, bold=True)

        # reticle
        cx, cy = cam_rect.center
        for s in (80, 110):
            pygame.draw.circle(surface, (75, 255, 210, 170), (cx, cy), s, 2)
        pygame.draw.line(surface, (75, 255, 210), (cx - 125, cy), (cx - 40, cy), 2)
        pygame.draw.line(surface, (75, 255, 210), (cx + 40, cy), (cx + 125, cy), 2)
        pygame.draw.line(surface, (75, 255, 210), (cx, cy - 125), (cx, cy - 40), 2)
        pygame.draw.line(surface, (75, 255, 210), (cx, cy + 40), (cx, cy + 125), 2)

        panel = pygame.Rect(WIDTH * 0.66, HEIGHT * 0.23, WIDTH * 0.25, HEIGHT * 0.55)
        rounded_panel(surface, panel, (5, 14, 20, 240), (36, 76, 83), 24, 1)
        draw_text(surface, "THE ROSTER", 17, (panel.centerx, panel.y + 25),
                  (90, 255, 218), align="center", mono=True, bold=True)

        for idx, p in enumerate(self.app.players):
            y = panel.y + 72 + idx * 48
            pygame.draw.circle(surface, (72, 255, 210), (panel.x + 30, y), 6)
            draw_text(surface, f"{idx + 1:02d}", 12, (panel.x + 50, y),
                      (100, 130, 135), align="midleft", mono=True)
            draw_text(surface, p.name, 18, (panel.x + 80, y),
                      (235, 245, 247), align="midleft", bold=True)
            draw_text(surface, "DNA SECURED", 11, (panel.right - 25, y),
                      (70, 255, 190), align="midright", mono=True)

        input_rect = pygame.Rect(WIDTH * 0.10, HEIGHT * 0.82, WIDTH * 0.52, 58)
        rounded_panel(surface, input_rect, (5, 13, 18), (42, 83, 90), 14, 1)
        draw_text(surface, self.app.player_name or "הזן שם מכבי…", 21,
                  (input_rect.x + 18, input_rect.centery),
                  (225, 240, 242) if self.app.player_name else (92, 116, 122),
                  align="midleft")

        Button((panel.x + 20, panel.bottom - 118, panel.w - 40, 52),
               "💾  סרוק ושמור DNA", (57, 255, 202)).draw(surface)
        Button((panel.x + 20, panel.bottom - 55, panel.w - 40, 42),
               "סיום הרשמה ונעילת פרופיל", (255, 194, 70)).draw(surface)

        if self.app.roster_error:
            draw_text(surface, self.app.roster_error, 15,
                      (WIDTH * 0.36, HEIGHT - 22), (255, 80, 95), align="midbottom", bold=True)

    def draw_stage_3(self, surface):
        self.app.background.draw(surface)
        self.draw_stage_chip(surface)

        # Pulsing core scanner keeps this puzzle visually alive while solving.
        core_cx, core_cy = WIDTH / 2, 705
        core_pulse = 24 + int((math.sin(self.app.background.time * 3.5) + 1) * 9)
        glow_circle(surface, (core_cx, core_cy), core_pulse, (255, 193, 61), 16)
        pygame.draw.circle(surface, (255, 193, 61), (int(core_cx), int(core_cy)), 8, 1)

        draw_text(surface, "THE OIL CIPHER", 14, (WIDTH / 2, 85), (89, 255, 216),
                  align="center", mono=True, bold=True)
        draw_text(surface, "צופן השמן של המכבים", 45, (WIDTH / 2, 132),
                  (239, 246, 249), align="center", bold=True)
        draw_text(surface,
                  "אנטיוכוס 2.0 מחק את פך השמן הטהור. פצחו את ארבעת המשתנים.",
                  20, (WIDTH / 2, 182), (144, 168, 175), align="center")

        rounded_panel(surface,
                      pygame.Rect(WIDTH / 2 - 520, 228, 1040, 58),
                      (4, 10, 14), (145, 30, 45), 12, 1)
        draw_text(surface, "!! ENCRYPTED CORE VARIABLE LOCK // ENTER 4-DIGIT OVERRIDE !!",
                  14, (WIDTH / 2, 257), (255, 64, 82), align="center", mono=True, bold=True)

        equations = ["A + B = 11", "B × C = 24", "C − D = 1", "D + A = 5"]
        start_y = 300
        for i, eq in enumerate(equations):
            rr = pygame.Rect(WIDTH / 2 - 330, start_y + i * 70, 660, 54)
            rounded_panel(surface, rr, (5, 14, 20), (32, 84, 86), 14, 1)
            draw_text(surface, eq, 28, rr.center, (76, 255, 205), align="center", mono=True, bold=True)

        # Keep source values exactly as supplied in the specification.
        draw_text(surface, "CODE ORDER  //  A   B   C   D", 15, (WIDTH / 2, 610),
                  (105, 136, 141), align="center", mono=True)
        code = "".join(self.app.cipher_digits)
        code_rect = pygame.Rect(WIDTH / 2 - 220, 648, 440, 74)
        rounded_panel(surface, code_rect, (2, 10, 14), (255, 194, 70), 18, 2)
        draw_text(surface, code or "____", 40, code_rect.center, (255, 219, 124),
                  align="center", mono=True, bold=True)
        draw_text(surface, "הקלידו את הקוד הסופי", 14,
                  (WIDTH / 2, 737), (133, 156, 161), align="center")

        # Operator-configured physical clue location
        if self.app.setup_clue_location:
            draw_text(surface, f"רמז: חפשו {self.app.setup_clue_location}",
                      15, (WIDTH / 2, HEIGHT - 70), (255, 194, 70),
                      align="center", bold=True)

    def draw_placeholder(self, surface):
        self.app.background.draw(surface)
        self.draw_stage_chip(surface)
        draw_text(surface, "PROTOCOL LOCKED", 18, (WIDTH / 2, HEIGHT * 0.42),
                  (255, 70, 88), align="center", mono=True, bold=True)
        draw_text(surface, f"שלב {self.stage:02d}", 62, (WIDTH / 2, HEIGHT * 0.50),
                  (235, 248, 250), align="center", bold=True)
        draw_text(surface, "המסגרת מוכנה. השלב הבא יושב בתוך מנוע המשחק.",
                  19, (WIDTH / 2, HEIGHT * 0.58), (138, 164, 169), align="center")


class EscapeRoomApp:
    def __init__(self):
        self.running = True
        self.clock = pygame.time.Clock()
        self.background = CinematicBackground()
        self.webcam = Webcam()

        self.state = "setup"
        self.stage_manager = StageManager(self)
        self.stage_started_at = time.monotonic()

        self.players: list[Player] = []
        self.player_name = ""
        self.roster_error = ""
        self.active_player_index = 0

        self.setup_clue_location = "במיקום שהוגדר בלוח המפעיל"
        self.setup_server_location = "במיקום שהוגדר בלוח המפעיל"
        self.setup_puzzle_locations = [""]
        self.setup_active_piece = 0
        self.setup_piece_scroll = 0

        self.cipher_digits: list[str] = []
        self.game_started_at = None
        self.stage_message = ""

        self.stage_names = {
            1: "The Intrusion Alert",
            2: "The Bio-Registration",
            3: "The Oil Cipher",
            4: "Puzzle Assembly",
            5: "Security Chain Protocol",
            6: "Dark Light Protocol",
            7: "Server Lamp Cipher",
            8: "Maccabean Frequency",
            9: "Digital Inversion",
            10: "Family Memory Matrix",
            11: "Quantum Current Lock",
            12: "Maccabean Energy Protocol",
        }

        self.setup_buttons = [
            Button((WIDTH * 0.18, HEIGHT * 0.74, WIDTH * 0.18, 62), "שמור הגדרות"),
            Button((WIDTH * 0.41, HEIGHT * 0.74, WIDTH * 0.20, 62), "נעל מחשב והפעל משחק",
                   (255, 58, 82), "START // KIOSK"),
            Button((WIDTH * 0.66, HEIGHT * 0.74, WIDTH * 0.16, 62), "מצב תצוגה",
                   (120, 166, 255)),
        ]

    def start_game(self):
        self.game_started_at = time.monotonic()
        self.stage_manager.goto(1)
        self.state = "game"

    @property
    def remaining_seconds(self):
        if not self.game_started_at:
            return TOTAL_SECONDS
        return max(0, TOTAL_SECONDS - int(time.monotonic() - self.game_started_at))

    def timer_string(self):
        s = self.remaining_seconds
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def operator_setup(self, surface):
        self.background.draw(surface)
        # Hero header
        draw_text(surface, "THE GREEKS ARE BACK", 18, (70, 48), (75, 255, 211),
                  mono=True, bold=True)
        draw_text(surface, "היוונים חוזרים", 62, (70, 105), (245, 249, 250), bold=True)
        draw_text(surface, "OPERATOR CONSOLE  /  PRE-GAME SETUP", 16, (74, 173),
                  (114, 145, 150), mono=True)
        draw_text(surface, "ROOT ACCESS // LOCAL TERMINAL", 12, (WIDTH - 520, 55),
                  (255, 58, 82), mono=True, bold=True)
        draw_text(surface, ">>> SYSTEM WAITING FOR OPERATOR COMMAND", 11, (WIDTH - 520, 76),
                  (41, 180, 126), mono=True)

        # Large hero composition
        art = pygame.Rect(WIDTH - 520, 80, 390, 470)
        rounded_panel(surface, art, (4, 14, 20, 235), (38, 81, 88), 28, 1)
        self.stage_manager.draw_hacker(surface, art.center, 105,
                                       (math.sin(time.monotonic() * 3) + 1) * 0.5)
        draw_text(surface, "ANTIOCHUS 2.0", 17, (art.centerx, art.bottom - 50),
                  (240, 196, 105), align="center", mono=True, bold=True)
        draw_text(surface, "SECURITY CORE // READY", 12, (art.centerx, art.bottom - 24),
                  (70, 255, 204), align="center", mono=True)

        # Setup fields rendered as stylized cards
        self.setup_field(surface, 70, 245, 650, "STAGE 03  //  CLUE LOCATION", self.setup_clue_location)
        self.setup_field(surface, 70, 365, 650, "STAGE 07  //  SERVER CLUE LOCATION", self.setup_server_location)
        self.draw_puzzle_location_editor(surface)

        for b in self.setup_buttons:
            b.draw(surface)

        draw_text(surface, "SAFE KIOSK  •  NO SYSTEM SECURITY DISABLED  •  OPERATOR EXIT ENABLED",
                  12, (WIDTH / 2, HEIGHT - 20), (80, 103, 108), align="center", mono=True)

    def setup_field(self, surface, x, y, w, label, value):
        rr = pygame.Rect(x, y, w, 86)
        rounded_panel(surface, rr, (5, 13, 18, 245), (32, 71, 78), 18, 1)
        draw_text(surface, label, 11, (x + 18, y + 17), (74, 255, 211), mono=True, bold=True)
        draw_text(surface, value, 18, (x + 18, y + 53), (224, 237, 239), align="midleft")

    def draw_puzzle_location_editor(self, surface):
        panel = pygame.Rect(70, 480, 650, 178)
        rounded_panel(surface, panel, (4, 12, 17, 245), (40, 86, 90), 18, 1)
        draw_text(surface, "STAGE 04  //  PHYSICAL PUZZLE PIECE LOCATIONS", 11,
                  (panel.x + 18, panel.y + 15), (74, 255, 211), mono=True, bold=True)
        draw_text(surface, "הוסף כמה חלקים שצריך. לחץ על שורה וכתוב את מקום המחבוא.",
                  13, (panel.x + 18, panel.y + 38), (152, 176, 179))
        visible = 3
        row_h = 36
        max_start = max(0, len(self.setup_puzzle_locations) - visible)
        self.setup_piece_scroll = clamp(self.setup_piece_scroll, 0, max_start)
        for row in range(visible):
            idx = row + self.setup_piece_scroll
            if idx >= len(self.setup_puzzle_locations):
                break
            y = panel.y + 60 + row * row_h
            rr = pygame.Rect(panel.x + 16, y, panel.w - 98, 29)
            active = idx == self.setup_active_piece
            rounded_panel(surface, rr, (7, 25, 30) if active else (5, 18, 23),
                          (255, 194, 78) if active else (31, 72, 77), 8, 2 if active else 1)
            draw_text(surface, f"חלק {idx + 1:02d}", 11, (rr.x + 10, rr.centery),
                      (255, 194, 78), align="midleft", mono=True, bold=True)
            value = self.setup_puzzle_locations[idx] or "לחץ כאן והקלד מיקום…"
            preview = value if len(value) <= 57 else value[:54] + "..."
            draw_text(surface, preview, 13, (rr.x + 85, rr.centery),
                      (235, 243, 245) if self.setup_puzzle_locations[idx] else (93, 120, 124),
                      align="midleft")
            remove_rect = pygame.Rect(panel.right - 72, y, 52, 29)
            rounded_panel(surface, remove_rect, (18, 13, 18), (255, 71, 92), 8, 1)
            draw_text(surface, "×", 18, remove_rect.center, (255, 95, 112), align="center", bold=True)
        if len(self.setup_puzzle_locations) > visible:
            draw_text(surface, "גלגלת = גלילה בין החלקים", 9, (panel.x + 18, panel.bottom - 10),
                      (92, 124, 129), mono=True, align="midbottom")
        add_rect = pygame.Rect(panel.right - 92, panel.y + 12, 74, 29)
        rounded_panel(surface, add_rect, (7, 29, 31), (55, 221, 180), 8, 1)
        draw_text(surface, "+ חלק", 11, add_rect.center, (91, 255, 211), align="center", bold=True)
    def draw_global_hud(self, surface):
        if not self.game_started_at:
            return
        remaining = self.remaining_seconds
        danger = 1.0 if remaining < 5 * 60 else 0.0
        bar = pygame.Rect(WIDTH - 315, 25, 270, 62)
        rounded_panel(surface, bar, (4, 11, 16, 235),
                      (255, 63, 81) if danger else (40, 83, 89), 18, 2)
        draw_text(surface, "GLOBAL TIMER", 11, (bar.centerx, bar.y + 14),
                  (117, 146, 151), align="center", mono=True)
        draw_text(surface, self.timer_string(), 28, (bar.centerx, bar.y + 43),
                  (255, 74, 91) if danger else (235, 250, 247),
                  align="center", mono=True, bold=True)

    def handle_setup_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
                return
            if event.key == pygame.K_BACKSPACE and self.setup_active_piece is not None:
                self.setup_puzzle_locations[self.setup_active_piece] = self.setup_puzzle_locations[self.setup_active_piece][:-1]
                return
            if event.key == pygame.K_DELETE and self.setup_active_piece is not None:
                self.setup_puzzle_locations.pop(self.setup_active_piece)
                if not self.setup_puzzle_locations:
                    self.setup_puzzle_locations = [""]
                self.setup_active_piece = min(self.setup_active_piece, len(self.setup_puzzle_locations) - 1)
                self.setup_piece_scroll = min(self.setup_piece_scroll, max(0, len(self.setup_puzzle_locations) - 3))
                return
            if event.key == pygame.K_RETURN:
                self.stage_message = f"מיקום חלק {self.setup_active_piece + 1} נשמר."
                return
            if len(event.unicode) == 1 and event.unicode.isprintable() and self.setup_active_piece is not None:
                current = self.setup_puzzle_locations[self.setup_active_piece]
                if len(current) < 120:
                    self.setup_puzzle_locations[self.setup_active_piece] = current + event.unicode
                return

        if event.type == pygame.MOUSEWHEEL:
            panel = pygame.Rect(70, 480, 650, 178)
            if panel.collidepoint(pygame.mouse.get_pos()):
                max_start = max(0, len(self.setup_puzzle_locations) - 3)
                self.setup_piece_scroll = max(0, min(max_start, self.setup_piece_scroll - event.y))
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            panel = pygame.Rect(70, 480, 650, 178)
            add_rect = pygame.Rect(panel.right - 92, panel.y + 12, 74, 29)
            if add_rect.collidepoint(event.pos):
                self.setup_puzzle_locations.append("")
                self.setup_active_piece = len(self.setup_puzzle_locations) - 1
                self.setup_piece_scroll = max(0, len(self.setup_puzzle_locations) - 3)
                return

            for row in range(3):
                idx = row + self.setup_piece_scroll
                if idx >= len(self.setup_puzzle_locations):
                    break
                y = panel.y + 60 + row * 36
                rr = pygame.Rect(panel.x + 16, y, panel.w - 98, 29)
                remove_rect = pygame.Rect(panel.right - 72, y, 52, 29)
                if remove_rect.collidepoint(event.pos):
                    self.setup_puzzle_locations.pop(idx)
                    if not self.setup_puzzle_locations:
                        self.setup_puzzle_locations = [""]
                    self.setup_active_piece = min(idx, len(self.setup_puzzle_locations) - 1)
                    self.setup_piece_scroll = min(self.setup_piece_scroll, max(0, len(self.setup_puzzle_locations) - 3))
                    return
                if rr.collidepoint(event.pos):
                    self.setup_active_piece = idx
                    return

            if self.setup_buttons[0].rect.collidepoint(event.pos):
                count = len([x for x in self.setup_puzzle_locations if x.strip()])
                self.stage_message = f"ההגדרות נשמרו • {count} מיקומי פאזל."
            elif self.setup_buttons[1].rect.collidepoint(event.pos):
                self.start_game()
            elif self.setup_buttons[2].rect.collidepoint(event.pos):
                self.start_game()

    def handle_roster_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_BACKSPACE:
                self.player_name = self.player_name[:-1]
            elif event.key == pygame.K_RETURN and self.player_name.strip():
                self.try_register()
            else:
                if len(event.unicode) == 1 and event.unicode.isprintable():
                    self.player_name += event.unicode

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Cards on the right
            panel = pygame.Rect(WIDTH * 0.66, HEIGHT * 0.23, WIDTH * 0.25, HEIGHT * 0.55)
            save = pygame.Rect(panel.x + 20, panel.bottom - 118, panel.w - 40, 52)
            done = pygame.Rect(panel.x + 20, panel.bottom - 55, panel.w - 40, 42)
            if save.collidepoint(event.pos):
                self.try_register()
            elif done.collidepoint(event.pos):
                if self.players:
                    self.stage_manager.goto(3)
                else:
                    self.roster_error = "יש לרשום לפחות שחקן אחד לפני נעילת הפרופיל."

    def try_register(self):
        name = self.player_name.strip()
        if not name:
            self.roster_error = "הזן שם לפני הסריקה."
            return
        if len(self.players) >= 10:
            self.roster_error = "הגעתם למקסימום של 10 שחקנים."
            return

        face = self.webcam.capture_face()
        if face is None:
            self.roster_error = "לא זוהו פנים במצלמה. התקרבו מעט למסגרת."
            return

        filename = PLAYER_DIR / f"player_{len(self.players) + 1:02d}.png"
        cv2.imwrite(str(filename), face)
        self.players.append(Player(name, filename))
        self.player_name = ""
        self.roster_error = ""

    def handle_stage3_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_BACKSPACE:
                if self.cipher_digits:
                    self.cipher_digits.pop()
            elif event.unicode.isdigit() and len(self.cipher_digits) < 4:
                self.cipher_digits.append(event.unicode)
                if len(self.cipher_digits) == 4:
                    code = "".join(self.cipher_digits)
                    # Source-consistent declared solution: A=3, B=8, C=3, D=2 => 3832.
                    if code == "3832":
                        self.stage_message = "FIREWALL 01 COLLAPSED"
                        self.stage_manager.goto(4)
                    else:
                        self.stage_message = "ACCESS DENIED  //  RECHECK THE CLUE"
                        self.cipher_digits.clear()

    def handle_game_event(self, event):
        if self.stage_manager.stage == 2:
            self.handle_roster_event(event)
        elif self.stage_manager.stage == 3:
            self.handle_stage3_event(event)
        elif self.stage_manager.stage == 4:
            self.stage_manager.stage4.handle(event, pygame, WIDTH, HEIGHT)
        elif self.stage_manager.stage == 5:
            self.stage_manager.stage5.handle(event)
        elif self.stage_manager.stage == 6:
            self.stage_manager.stage6.handle(event, pygame, WIDTH, HEIGHT)
        elif self.stage_manager.stage == 7:
            self.stage_manager.stage7.handle(event, pygame, WIDTH, HEIGHT)
        else:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
    def handle_secret_keys(self, event):
        if event.type != pygame.KEYDOWN:
            return
        # Skip stage
        mods = pygame.key.get_mods()
        if (mods & pygame.KMOD_CTRL) and (mods & pygame.KMOD_SHIFT) and event.key == pygame.K_RIGHT:
            if self.state == "game":
                self.stage_manager.goto(min(12, self.stage_manager.stage + 1))
        # Emergency exit
        if (mods & pygame.KMOD_CTRL) and (mods & pygame.KMOD_ALT) and (mods & pygame.KMOD_SHIFT) and event.key == pygame.K_ESCAPE:
            self.running = False

    def update(self, dt):
        self.background.update(dt)
        if self.state == "game" and self.stage_manager.stage == 2:
            self.webcam.read()
        elif self.state == "game" and self.stage_manager.stage == 4:
            self.stage_manager.stage4.update(dt)
        elif self.state == "game" and self.stage_manager.stage == 5:
            self.stage_manager.stage5.update(dt)
        elif self.state == "game" and self.stage_manager.stage == 6:
            self.stage_manager.stage6.update(dt)
        elif self.state == "game" and self.stage_manager.stage == 7:
            self.stage_manager.stage7.update(dt)

    def draw(self):
        if self.state == "setup":
            self.operator_setup(screen)
        else:
            self.stage_manager.draw(screen)
            self.draw_global_hud(screen)

            if self.stage_message:
                draw_text(screen, self.stage_message, 14,
                          (WIDTH / 2, HEIGHT - 18), (105, 255, 210),
                          align="midbottom", mono=True, bold=True)

        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                self.handle_secret_keys(event)
                if self.state == "setup":
                    self.handle_setup_event(event)
                else:
                    self.handle_game_event(event)

            self.update(dt)
            self.draw()

        self.webcam.release()
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    EscapeRoomApp().run()
