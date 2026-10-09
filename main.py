from __future__ import annotations

import json
import math
import os
import random
import re
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from functools import lru_cache

import cv2
import numpy as np
import pygame

from stage4_puzzle import Stage4Controller
from stage5_tasks import TaskBase, OilCatchTask, create_task_pool
from stage6_protocol import Stage6Controller
from stage7_server_cipher import Stage7Controller
from later_stages import LaterStagesController

# ============================================================
# THE GREEKS ARE BACK
# Cinematic Hanukkah escape-room foundation
# ============================================================

WIDTH, HEIGHT = 1600, 900
FPS = 60
TOTAL_SECONDS = 60 * 60

# Keep operator settings and face templates next to the portable app executable
# in packaged builds, and next to the source file during development.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
PLAYER_DIR = DATA_DIR / "players"
DATA_DIR.mkdir(exist_ok=True)
PLAYER_DIR.mkdir(exist_ok=True)


def _log_uncaught_exception(exc_type, exc, tb):
    """Persist fatal runtime errors for packaged builds where no console is visible."""
    log_path = DATA_DIR / "crash.log"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if log_path.exists() and log_path.stat().st_size > 1_000_000:
            log_path.write_text("", encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n=== UNHANDLED GAME ERROR ===\n")
            log.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            log.write(f"Python: {sys.version.split()[0]}\n")
            log.write(f"Frozen build: {bool(getattr(sys, 'frozen', False))}\n")
            traceback.print_exception(exc_type, exc, tb, file=log)
    except Exception:
        # Logging must never mask the original failure.
        pass
    try:
        if sys.__stderr__ is not None:
            sys.__excepthook__(exc_type, exc, tb)
    except Exception:
        pass


sys.excepthook = _log_uncaught_exception

pygame.init()
pygame.font.init()
try:
    pygame.mixer.init()
except pygame.error:
    # Sound is optional; later-stage sound generation already degrades gracefully.
    pass

# Use one logical canvas across every monitor. Pygame scales these coordinates
# to the display, preventing text, puzzles, and click targets from drifting.
try:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
except pygame.error:
    try:
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED)
    except pygame.error:
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
WIDTH, HEIGHT = screen.get_size()
pygame.display.set_caption("היוונים חוזרים — Antiochus 2.0")
pygame.mouse.set_visible(True)

FONT_NAME = pygame.font.match_font("segoeui") or pygame.font.get_default_font()
MONO_NAME = pygame.font.match_font("consolas") or pygame.font.get_default_font()
BOLD_NAME = pygame.font.match_font("segoeuib") or FONT_NAME


try:
    from bidi.algorithm import get_display as _bidi_get_display
except ImportError:
    _bidi_get_display = None

_HEBREW_RE = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")


def is_rtl_text(text: str) -> bool:
    """Return True when a string contains Hebrew/RTL characters."""
    return bool(_HEBREW_RE.search(str(text)))


def _display_text(text: str) -> str:
    """Reorder mixed Hebrew/Latin text for Pygame's left-to-right text renderer."""
    text = str(text)
    if _bidi_get_display is None or not is_rtl_text(text):
        return text
    try:
        return _bidi_get_display(text)
    except (AssertionError, TypeError, ValueError):
        # Malformed user text must never crash the UI.
        return text


@lru_cache(maxsize=96)
def font(size: int, mono: bool = False, bold: bool = False) -> pygame.font.Font:
    name = MONO_NAME if mono else (BOLD_NAME if bold else FONT_NAME)
    return pygame.font.Font(name, size)


@lru_cache(maxsize=4096)
def _render_text(text: str, size: int, color: tuple, mono: bool, bold: bool):
    # Pygame surfaces are safe to reuse as immutable blit sources.
    # All screens share this BiDi pass so Hebrew and embedded numbers render consistently.
    return font(size, mono=mono, bold=bold).render(_display_text(text), True, color)


def fit_text(text: str, size: int, max_width: int, *, mono=False, bold=False) -> str:
    """Ellipsize a label without allowing player names to spill into adjacent UI."""
    value = str(text)
    max_width = max(0, int(max_width))
    if not value or max_width == 0:
        return ""
    ink = (235, 245, 247)
    if _render_text(value, int(size), ink, mono, bold).get_width() <= max_width:
        return value
    while value:
        value = value[:-1].rstrip()
        candidate = value + "…"
        if _render_text(candidate, int(size), ink, mono, bold).get_width() <= max_width:
            return candidate
    return "…"


def clamp(value, low, high):
    return max(low, min(high, value))


def draw_text(surface, text, size, pos, color=(235, 245, 255),
              *, align="topleft", mono=False, bold=False):
    text = str(text)
    img = _render_text(text, int(size), tuple(color), mono, bold)
    rect = img.get_rect()
    setattr(rect, align, pos)
    surface.blit(img, rect)
    return rect


def rounded_panel(surface, rect, fill, border=(70, 255, 210), radius=24, width=1):
    """Draw a tactical frame with clipped corners instead of a soft rounded card."""
    r = pygame.Rect(rect)
    if r.w <= 4 or r.h <= 4:
        pygame.draw.rect(surface, fill, r)
        if width:
            pygame.draw.rect(surface, border, r, width)
        return
    cut = min(max(5, int(radius * 0.72)), max(2, min(r.w, r.h) // 3))
    points = [
        (r.left + cut, r.top),
        (r.right - cut - 1, r.top),
        (r.right - 1, r.top + cut),
        (r.right - 1, r.bottom - cut - 1),
        (r.right - cut - 1, r.bottom - 1),
        (r.left + cut, r.bottom - 1),
        (r.left, r.bottom - cut - 1),
        (r.left, r.top + cut),
    ]
    pygame.draw.polygon(surface, fill, points)
    if width:
        pygame.draw.polygon(surface, border, points, width)
        rail_end = min(r.right - cut - 3, r.left + cut + max(18, min(64, r.w // 4)))
        if rail_end > r.left + cut + 3:
            pygame.draw.line(surface, border, (r.left + cut + 3, r.top + 1),
                             (rail_end, r.top + 1), max(1, width))


@lru_cache(maxsize=12)
def _glow_layer(radius: int, color: tuple, alpha: int):
    """Build reusable glow pixels once; the cached surface is never mutated."""
    radius = max(1, int(radius))
    layer = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
    cx = cy = radius * 3
    for r in range(radius * 3, max(2, radius // 2), -4):
        a = int(alpha * (1 - r / (radius * 3)) ** 2)
        pygame.draw.circle(layer, (*color, a), (cx, cy), r)
    pygame.draw.circle(layer, (*color, min(255, alpha * 3)), (cx, cy), radius)
    return layer


def glow_circle(surface, pos, radius, color, alpha=45):
    radius = max(1, int(radius))
    color = tuple(color)
    layer = _glow_layer(radius, color, int(alpha))
    cx = cy = radius * 3
    surface.blit(layer, (int(pos[0]) - cx, int(pos[1]) - cy))


@lru_cache(maxsize=4)
def _scanline_layer(size: tuple, spacing: int, alpha: int):
    """Reuse immutable scanline surfaces across frames and stages."""
    width, height = size
    spacing = max(1, int(spacing))
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(0, height, spacing):
        pygame.draw.line(overlay, (140, 255, 225, int(alpha)), (0, y), (width, y))
    return overlay


def draw_scanlines(surface, spacing=5, alpha=16):
    surface.blit(_scanline_layer(surface.get_size(), int(spacing), int(alpha)), (0, 0))


@lru_cache(maxsize=4)
def _scan_beam_layer(width: int, height: int = 90):
    """The horizontal scan beam is static; only its blit position changes."""
    beam = pygame.Surface((int(width), int(height)), pygame.SRCALPHA)
    pygame.draw.rect(beam, (45, 255, 203, 12), (0, 36, width, 18))
    pygame.draw.rect(beam, (45, 255, 203, 5), (0, 10, width, 52))
    return beam



def draw_intrusion_monitor(surface, rect, t=0.0, *, silhouette=True, compact=False):
    """Cinematic breached-system display inspired by an ominous green control-room screen.

    The intruder is only a featureless shadow under a hood: no cartoon face,
    helmet, glowing eyes, or mascot-like character.
    """
    r = pygame.Rect(rect)
    if r.w < 80 or r.h < 90:
        return

    cut = max(6, min(24, min(r.w, r.h) // 18))
    bezel = [
        (r.left + cut, r.top), (r.right - cut - 1, r.top),
        (r.right - 1, r.top + cut), (r.right - 1, r.bottom - cut - 1),
        (r.right - cut - 1, r.bottom - 1), (r.left + cut, r.bottom - 1),
        (r.left, r.bottom - cut - 1), (r.left, r.top + cut),
    ]
    pygame.draw.polygon(surface, (4, 12, 12), bezel)
    pygame.draw.lines(surface, (24, 92, 67), True, bezel, 2)

    screen = r.inflate(-12, -12)
    screen.inflate_ip(-2, -2)
    pygame.draw.rect(surface, (1, 8, 7), screen)
    pygame.draw.rect(surface, (28, 133, 83), screen, 1)
    pygame.draw.line(surface, (68, 224, 143), (screen.left + 8, screen.top + 2),
                     (screen.right - 8, screen.top + 2), 1)

    # Data streams: stable columns whose contents move like live telemetry.
    glyphs = "013579ACEFKMNX<>/\\[]{}:;+=#"
    step_x = max(13, min(23, screen.w // 50))
    glyph_size = max(8, min(13, screen.w // 92))
    stream_rows = max(5, min(32, screen.h // max(10, glyph_size + 4)))
    stream_h = max(1, screen.h - 28)
    for col_index, x in enumerate(range(screen.left + 10, screen.right - 8, step_x)):
        offset = int((t * (14 + (col_index * 11) % 31) + col_index * 29) % stream_h)
        for row_index in range(stream_rows):
            y = screen.top + 9 + (offset - row_index * (glyph_size + 3)) % stream_h
            code = glyphs[(col_index * 7 + row_index * 13 + int(t * 1.7)) % len(glyphs)]
            bright = row_index == 0 or col_index % 11 == 0
            color = (81, 255, 157) if bright else (25, 112 + (col_index % 5) * 5, 69)
            draw_text(surface, code, glyph_size, (x, y), color, mono=True, align="center")

    sx, sy, sw, sh = screen.x, screen.y, screen.w, screen.h
    cx = sx + sw // 2
    # Luminous data filaments sweep around the unknown intruder like cables in a breached server room.
    for i in range(22):
        side = -1 if i % 2 == 0 else 1
        band = i // 2
        y0 = sy + int(sh * (0.22 + (band % 9) * 0.073))
        y3 = sy + int(sh * (0.19 + ((band * 3) % 9) * 0.078))
        margin = int(sw * (0.025 + (band % 5) * 0.018))
        x0 = sx + margin if side < 0 else sx + sw - margin
        x3 = cx + side * int(sw * (0.16 + (band % 5) * 0.025))
        p0 = (x0, y0)
        p1 = (sx + int(sw * (0.24 + (band % 4) * 0.035)) if side < 0
              else sx + sw - int(sw * (0.24 + (band % 4) * 0.035)),
              sy + int(sh * (0.02 + (band % 4) * 0.16)))
        p2 = (cx + side * int(sw * (0.34 + (band % 3) * 0.035)),
              sy + int(sh * (0.94 - (band % 5) * 0.13)))
        p3 = (x3, y3)
        curve = []
        for j in range(29):
            u = j / 28
            v = 1 - u
            px = v**3 * p0[0] + 3 * v**2 * u * p1[0] + 3 * v * u**2 * p2[0] + u**3 * p3[0]
            py = v**3 * p0[1] + 3 * v**2 * u * p1[1] + 3 * v * u**2 * p2[1] + u**3 * p3[1]
            curve.append((int(px), int(py)))
        tint = (39, 180 + (band % 3) * 20, 100) if i % 4 else (89, 255, 164)
        pygame.draw.lines(surface, tint, False, curve, 2 if i % 5 == 0 else 1)

    if silhouette:
        # Hood and shoulders read as one ominous silhouette, with absolutely no facial detail.
        base = screen.bottom - 2
        shoulder_y = sy + int(sh * 0.62)
        body = [
            (cx - int(sw * 0.30), base),
            (cx - int(sw * 0.29), sy + int(sh * 0.79)),
            (cx - int(sw * 0.25), sy + int(sh * 0.65)),
            (cx - int(sw * 0.19), shoulder_y),
            (cx - int(sw * 0.12), sy + int(sh * 0.54)),
            (cx - int(sw * 0.10), sy + int(sh * 0.44)),
            (cx + int(sw * 0.10), sy + int(sh * 0.44)),
            (cx + int(sw * 0.12), sy + int(sh * 0.54)),
            (cx + int(sw * 0.19), shoulder_y),
            (cx + int(sw * 0.25), sy + int(sh * 0.65)),
            (cx + int(sw * 0.29), sy + int(sh * 0.79)),
            (cx + int(sw * 0.30), base),
        ]
        pygame.draw.polygon(surface, (1, 6, 6), body)
        pygame.draw.lines(surface, (13, 54, 43), False, body[1:6], 2)
        pygame.draw.lines(surface, (13, 54, 43), False, body[6:11], 2)

        hood = [
            (cx - int(sw * 0.105), sy + int(sh * 0.52)),
            (cx - int(sw * 0.145), sy + int(sh * 0.42)),
            (cx - int(sw * 0.155), sy + int(sh * 0.32)),
            (cx - int(sw * 0.12), sy + int(sh * 0.25)),
            (cx - int(sw * 0.06), sy + int(sh * 0.225)),
            (cx, sy + int(sh * 0.215)),
            (cx + int(sw * 0.06), sy + int(sh * 0.225)),
            (cx + int(sw * 0.12), sy + int(sh * 0.25)),
            (cx + int(sw * 0.155), sy + int(sh * 0.32)),
            (cx + int(sw * 0.145), sy + int(sh * 0.42)),
            (cx + int(sw * 0.105), sy + int(sh * 0.52)),
        ]
        pygame.draw.polygon(surface, (3, 12, 12), hood)
        pygame.draw.lines(surface, (35, 119, 78), False, hood, 2)
        face_void = [
            (cx - int(sw * 0.105), sy + int(sh * 0.315)),
            (cx - int(sw * 0.075), sy + int(sh * 0.285)),
            (cx, sy + int(sh * 0.275)),
            (cx + int(sw * 0.075), sy + int(sh * 0.285)),
            (cx + int(sw * 0.105), sy + int(sh * 0.315)),
            (cx + int(sw * 0.09), sy + int(sh * 0.43)),
            (cx + int(sw * 0.055), sy + int(sh * 0.505)),
            (cx - int(sw * 0.055), sy + int(sh * 0.505)),
            (cx - int(sw * 0.09), sy + int(sh * 0.43)),
        ]
        pygame.draw.polygon(surface, (0, 3, 4), face_void)
        # A restrained green rim catches the hood; there are no eyes or artificial face marks.
        pygame.draw.lines(surface, (25, 82, 58), False,
                          [hood[1], hood[2], hood[3], hood[4], hood[5]], 1)
        pygame.draw.line(surface, (19, 72, 50),
                         (cx - int(sw * 0.14), sy + int(sh * 0.72)),
                         (cx - int(sw * 0.19), base - 6), 1)
        pygame.draw.line(surface, (19, 72, 50),
                         (cx + int(sw * 0.14), sy + int(sh * 0.72)),
                         (cx + int(sw * 0.19), base - 6), 1)

        title_size = max(16, min(31, sw // 38))
        sub_size = max(12, min(23, sw // 50))
        draw_text(surface, "SYSTEM COMPROMISED!", title_size,
                  (cx, sy + int(sh * 0.035)), (255, 143, 107), align="midtop",
                  mono=True, bold=True)
        draw_text(surface, "UNLOCK THE FIREWALL", sub_size,
                  (cx, sy + int(sh * 0.085)), (255, 157, 119), align="midtop",
                  mono=True, bold=True)
        draw_text(surface, "TO REGAIN CONTROL!", sub_size,
                  (cx, sy + int(sh * 0.125)), (255, 157, 119), align="midtop",
                  mono=True, bold=True)
    else:
        size = max(9, min(13, sw // 30))
        draw_text(surface, "HOSTILE SIGNAL // UNKNOWN", size,
                  (cx, sy + 14), (255, 132, 103), align="midtop", mono=True, bold=True)
        draw_text(surface, "TRACE ORIGIN: MASKED", max(8, size - 2),
                  (cx, sy + 34), (57, 207, 136), align="midtop", mono=True)
        # Tiny signal bars and a broken link indicator; the panel stays abstract, not character-led.
        for i, width in enumerate((sw * 0.23, sw * 0.13, sw * 0.31, sw * 0.18, sw * 0.27)):
            bar = pygame.Rect(sx + 18, sy + int(sh * 0.70) + i * 12, int(width), 3)
            pygame.draw.rect(surface, (12, 43, 32), bar.inflate(2, 2))
            pygame.draw.rect(surface, (36, 199, 117), bar)
        draw_text(surface, "CONNECTION ACTIVE  /  0x7F", max(8, size - 2),
                  (sx + 18, screen.bottom - 22), (96, 170, 135), mono=True)


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
    # Moving scan beam uses a cached layer; animation comes from its position.
    beam_y = int((t * 115) % (HEIGHT + 180)) - 90
    surface.blit(_scan_beam_layer(WIDTH, 90), (0, beam_y))

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
        rounded_panel(surface, self.rect, fill, border, 11, 2)
        cut = min(13, max(7, self.rect.h // 5))
        pygame.draw.line(surface, self.accent,
                         (self.rect.left + 7, self.rect.top + cut),
                         (self.rect.left + 7, self.rect.bottom - cut), 2)
        if self.hover:
            pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 8.0)
            pygame.draw.line(surface, border,
                             (self.rect.left + 18, self.rect.top + 7),
                             (self.rect.right - 18, self.rect.top + 7), 2)
            # A narrow scan pulse moves across hovered controls; it stops at the panel edges.
            scan_span = max(1, self.rect.w - 20)
            scan_x = self.rect.left + 10 + int((time.monotonic() * 235) % scan_span)
            pygame.draw.line(surface, tuple(int(c * (0.55 + pulse * 0.45)) for c in border),
                             (scan_x, self.rect.top + 12),
                             (scan_x, self.rect.bottom - 12), 2)
            corner = 8 + int(pulse * 3)
            pygame.draw.line(surface, border, (self.rect.right - corner - 5, self.rect.bottom - 5),
                             (self.rect.right - 5, self.rect.bottom - 5), 2)
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
            task = self.current_task
            if isinstance(task, OilCatchTask):
                task.update_and_collide(dt, WIDTH, HEIGHT)
            else:
                task.update(dt)
            # Oil Catch can complete in the frame update rather than from an input event.
            # Advance immediately so the game never waits for an unrelated extra click.
            if task.done:
                self.advance()

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
                player_label = fit_text(
                    self.app.players[i].name, 13, rr.w - 12, bold=True
                )
                draw_text(surface, player_label, 13,
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
        self.later = LaterStagesController(app)
        self.transition_started_at = None
        self.transition_from = 0
        self.transition_to = 0

    def goto(self, stage):
        previous_stage = self.stage
        requested_stage = stage
        if self.app.game_started_at and 5 <= stage <= 11:
            remaining = self.app.remaining_seconds
            # Preserve the timed 180-second quantum challenge and at least 90 seconds for the finale.
            estimated_needed = 270 + max(0, 11 - stage) * 30
            if remaining < estimated_needed:
                stage = 11 if remaining >= 270 else 12

        if previous_stage and stage != previous_stage:
            self.transition_from = previous_stage
            self.transition_to = stage
            self.transition_started_at = time.monotonic()

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
        elif 8 <= stage <= 12:
            self.later.start(stage)

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
        elif 8 <= self.stage <= 12:
            self.later.draw(surface, draw_text, rounded_panel, glow_circle, pygame, WIDTH, HEIGHT, self.app.background.time)
        else:
            self.draw_placeholder(surface)

    def draw_transition(self, surface):
        """Short visual payoff when a security layer is breached and the next stage opens."""
        if self.transition_started_at is None:
            return
        elapsed = time.monotonic() - self.transition_started_at
        duration = 0.86
        if elapsed >= duration:
            self.transition_started_at = None
            return

        progress = clamp(elapsed / duration, 0.0, 1.0)
        intensity = 1.0 - progress
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((1, 5, 7, int(48 * intensity)))
        surface.blit(veil, (0, 0))

        # Fast broken scan bars, like a security firewall tearing open.
        sweep_y = int((progress * 1.24 - 0.12) * HEIGHT)
        for i in range(11):
            y = sweep_y + ((i * 73) % 240) - 120
            x = (i * 193 + int(progress * WIDTH * 0.62)) % WIDTH
            width = 90 + ((i * 67) % 280)
            color = (37, 255, 151) if i % 3 else (255, 77, 71)
            if 0 <= y < HEIGHT:
                pygame.draw.rect(surface, color, (x, y, width, 1 + (i % 3 == 0)))

        # Two expanding signal rings give the unlock a physical, pulse-like feel.
        center = (WIDTH // 2, HEIGHT // 2)
        ring_radius = int(50 + progress * 570)
        if ring_radius < max(WIDTH, HEIGHT):
            pygame.draw.circle(surface, (24, 110, 75), center, ring_radius, 2)
        inner_radius = int(28 + progress * 290)
        pygame.draw.circle(surface, (38, 196, 121), center, inner_radius, 1)

        panel = pygame.Rect(WIDTH // 2 - 345, HEIGHT // 2 - 112, 690, 224)
        rounded_panel(surface, panel, (2, 10, 12), (56, 239, 154), 18, 2)
        pygame.draw.line(surface, (255, 73, 68),
                         (panel.x + 22, panel.y + 14),
                         (panel.x + 103, panel.y + 14), 2)
        pygame.draw.line(surface, (53, 255, 169),
                         (panel.right - 105, panel.bottom - 14),
                         (panel.right - 22, panel.bottom - 14), 2)

        stage = max(1, min(12, int(self.transition_to)))
        draw_text(surface, f"SECURITY LAYER // {stage:02d}", 13,
                  (panel.centerx, panel.y + 31), (80, 229, 151),
                  align="center", mono=True, bold=True)
        draw_text(surface, f"PROTOCOL {stage:02d} UNLOCKED", 34,
                  (panel.centerx, panel.y + 83), (245, 255, 249),
                  align="center", mono=True, bold=True)
        stage_label = self.app.stage_names.get(stage, "UNKNOWN SIGNAL")
        draw_text(surface, fit_text(stage_label.upper(), 17, panel.w - 62, mono=True, bold=True),
                  17, (panel.centerx, panel.y + 127), (255, 174, 105),
                  align="center", mono=True, bold=True)

        # Compact 12-stage progression strip; completed nodes stay lit behind the active node.
        node_w, node_gap = 30, 10
        total_w = 12 * node_w + 11 * node_gap
        start_x = panel.centerx - total_w // 2
        for index in range(12):
            rr = pygame.Rect(start_x + index * (node_w + node_gap), panel.bottom - 31, node_w, 4)
            if index + 1 < stage:
                color = (56, 220, 131)
            elif index + 1 == stage:
                color = (255, 160, 92)
            else:
                color = (30, 52, 49)
            pygame.draw.rect(surface, color, rr)

    def draw_stage_1(self, surface):
        elapsed = time.monotonic() - self.app.stage_started_at
        self.app.background.draw(surface, danger=min(1.0, elapsed / 2.5))

        # One dominant cinematic display replaces the old scattered popups and cartoon avatar.
        display_rect = pygame.Rect(218, 72, WIDTH - 436, HEIGHT - 224)
        draw_intrusion_monitor(surface, display_rect, elapsed, silhouette=True)

        # The system speaks from the terminal rather than through a mascot.
        if elapsed >= 3.2:
            quote_rect = pygame.Rect(WIDTH // 2 - 430, HEIGHT - 139, 860, 62)
            rounded_panel(surface, quote_rect, (2, 9, 8, 238), (36, 128, 79), 10, 1)
            draw_text(surface, "ANTIOCHUS 2.0  //  REMOTE SESSION ACTIVE", 12,
                      (WIDTH // 2, quote_rect.y + 10), (71, 218, 140),
                      align="midtop", mono=True, bold=True)
            draw_text(surface, '"המחשב שלכם שייך לי כעת. השעון מתחיל... עכשיו."', 18,
                      (WIDTH // 2, quote_rect.y + 32), (227, 239, 231),
                      align="midtop")

        if elapsed > 8.8:
            self.goto(2)

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
            pygame.draw.rect(surface, (65, 255, 210), cam_rect.inflate(-18, -18), 2)
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

        # Ten players must fit above the two action buttons without overlapping.
        for idx, p in enumerate(self.app.players[:10]):
            y = panel.y + 60 + idx * 30
            pygame.draw.line(surface, (20, 45, 50),
                             (panel.x + 14, y + 14), (panel.right - 14, y + 14), 1)
            pygame.draw.circle(surface, (72, 255, 210), (panel.x + 14, y), 4)
            draw_text(surface, f"{idx + 1:02d}", 10, (panel.x + 26, y),
                      (100, 130, 135), align="midleft", mono=True)
            name_text = fit_text(p.name, 14, panel.w - 162, bold=True)
            if is_rtl_text(p.name):
                draw_text(surface, name_text, 14, (panel.right - 108, y),
                          (235, 245, 247), align="midright", bold=True)
            else:
                draw_text(surface, name_text, 14, (panel.x + 45, y),
                          (235, 245, 247), align="midleft", bold=True)
            draw_text(surface, "DNA OK", 9, (panel.right - 13, y),
                      (70, 255, 190), align="midright", mono=True)

        input_rect = pygame.Rect(WIDTH * 0.10, HEIGHT * 0.82, WIDTH * 0.52, 58)
        rounded_panel(surface, input_rect, (5, 13, 18), (42, 83, 90), 14, 1)
        entry_text = self.app.player_name or "הזן שם מכבי…"
        if is_rtl_text(entry_text):
            draw_text(surface, entry_text, 21, (input_rect.right - 18, input_rect.centery),
                      (225, 240, 242) if self.app.player_name else (92, 116, 122),
                      align="midright")
        else:
            draw_text(surface, entry_text, 21, (input_rect.x + 18, input_rect.centery),
                      (225, 240, 242) if self.app.player_name else (92, 116, 122),
                      align="midleft")

        Button((panel.x + 20, panel.bottom - 118, panel.w - 40, 52),
               "סרוק ושמור DNA", (57, 255, 202)).draw(surface)
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
            clue_text = fit_text(
                f"רמז: חפשו {self.app.setup_clue_location}", 15, WIDTH - 220, bold=True
            )
            draw_text(surface, clue_text, 15, (WIDTH / 2, HEIGHT - 70),
                      (255, 194, 70), align="center", bold=True)

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
        self.timer_frozen = None

        self.setup_clue_location = "במיקום שהוגדר בלוח המפעיל"
        self.setup_server_location = "במיקום שהוגדר בלוח המפעיל"
        self.setup_puzzle_locations = [""]
        self.setup_active_piece = None
        self.setup_active_text_field = None
        self.setup_piece_scroll = 0
        self.load_setup_config()

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
            Button((WIDTH * 0.18, HEIGHT * 0.86, WIDTH * 0.18, 62), "שמור הגדרות"),
            Button((WIDTH * 0.41, HEIGHT * 0.86, WIDTH * 0.20, 62), "הפעל משחק",
                   (255, 58, 82), "START // KIOSK"),
            Button((WIDTH * 0.66, HEIGHT * 0.86, WIDTH * 0.16, 62), "יציאה",
                   (255, 58, 82)),
        ]

    def start_game(self):
        self.save_setup_config(silent=True)
        self.game_started_at = time.monotonic()
        self.stage_manager.goto(1)
        self.state = "game"

    @property
    def remaining_seconds(self):
        if self.timer_frozen is not None:
            return int(self.timer_frozen)
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
        draw_text(surface, "היוונים חוזרים", 62, (720, 105), (245, 249, 250),
                  align="topright", bold=True)
        draw_text(surface, "OPERATOR CONSOLE  /  PRE-GAME SETUP", 16, (74, 173),
                  (114, 145, 150), mono=True)
        draw_text(surface, "ROOT ACCESS // LOCAL TERMINAL", 12, (WIDTH - 520, 55),
                  (255, 58, 82), mono=True, bold=True)
        draw_text(surface, ">>> SYSTEM WAITING FOR OPERATOR COMMAND", 11, (WIDTH - 520, 76),
                  (41, 180, 126), mono=True)
        pygame.draw.line(surface, (255, 42, 62), (70, 206), (720, 206), 2)
        draw_text(surface, "THREAT CLASS // HOSTILE  |  TRACE STATUS // ACTIVE",
                  11, (70, 218), (255, 72, 88), mono=True, bold=True)

        # The operator console shows an abstract hostile signal feed, not a mascot.
        art = pygame.Rect(WIDTH - 520, 80, 390, 470)
        draw_intrusion_monitor(surface, art, time.monotonic() * 0.7,
                               silhouette=False, compact=True)

        # Setup fields rendered as stylized cards
        self.setup_field(surface, 70, 245, 650, "STAGE 03  //  CLUE LOCATION", self.setup_clue_location, "clue")
        self.setup_field(surface, 70, 365, 650, "STAGE 07  //  SERVER CLUE LOCATION", self.setup_server_location, "server")
        self.draw_puzzle_location_editor(surface)

        for b in self.setup_buttons:
            b.draw(surface)

        if self.stage_message:
            draw_text(surface, self.stage_message, 12, (WIDTH / 2, HEIGHT - 48),
                      (255, 204, 100), align="center", bold=True)
        draw_text(surface, "ISOLATED GAME MODE  //  WINDOWS SECURITY UNCHANGED  //  OPERATOR EXIT ENABLED",
                  12, (WIDTH / 2, HEIGHT - 20), (80, 103, 108), align="center", mono=True)

    def load_setup_config(self):
        config_path = DATA_DIR / "operator_config.json"
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.setup_clue_location = str(config.get("setup_clue_location", self.setup_clue_location))
            self.setup_server_location = str(config.get("setup_server_location", self.setup_server_location))
            locations = config.get("setup_puzzle_locations", self.setup_puzzle_locations)
            if isinstance(locations, list):
                self.setup_puzzle_locations = [str(value)[:120] for value in locations] or [""]
        except (OSError, ValueError, TypeError):
            pass

    def save_setup_config(self, silent=False):
        config_path = DATA_DIR / "operator_config.json"
        payload = {
            "setup_clue_location": self.setup_clue_location,
            "setup_server_location": self.setup_server_location,
            "setup_puzzle_locations": self.setup_puzzle_locations,
        }
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            if not silent:
                count = len([value for value in self.setup_puzzle_locations if value.strip()])
                self.stage_message = f"ההגדרות נשמרו • {count} מיקומי פאזל."
            return True
        except OSError:
            if not silent:
                self.stage_message = "לא ניתן לשמור את ההגדרות בתיקיית המשחק."
            return False

    def setup_field(self, surface, x, y, w, label, value, field_key=None):
        rr = pygame.Rect(x, y, w, 86)
        active = field_key is not None and self.setup_active_text_field == field_key
        rounded_panel(surface, rr, (5, 16, 21, 245),
                      (255, 194, 78) if active else (32, 71, 78), 18, 2 if active else 1)
        draw_text(surface, label, 11, (x + 18, y + 17), (74, 255, 211), mono=True, bold=True)
        if len(value) <= 62:
            shown = value
        elif is_rtl_text(value):
            shown = value[:59] + "…"
        else:
            shown = "…" + value[-59:]
        draw_text(surface, shown, 17, (rr.right - 18, y + 53),
                  (224, 237, 239), align="midright")
        if active:
            draw_text(surface, "EDITING // ENTER TO FINISH", 9, (rr.right - 14, rr.y + 15),
                      (255, 194, 78), align="topright", mono=True, bold=True)

    def draw_puzzle_location_editor(self, surface):
        panel = pygame.Rect(70, 480, 650, 178)
        rounded_panel(surface, panel, (4, 12, 17, 245), (40, 86, 90), 18, 1)
        draw_text(surface, "STAGE 04  //  PHYSICAL PUZZLE PIECE LOCATIONS", 11,
                  (panel.x + 18, panel.y + 15), (74, 255, 211), mono=True, bold=True)
        draw_text(surface, "הוסף כמה חלקים שצריך. לחץ על שורה וכתוב את מקום המחבוא.",
                  13, (panel.right - 18, panel.y + 38), (152, 176, 179),
                  align="topright")
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
            draw_text(surface, f"חלק {idx + 1:02d}", 11, (rr.x + 76, rr.centery),
                      (255, 194, 78), align="midright", mono=True, bold=True)
            value = self.setup_puzzle_locations[idx] or "לחץ כאן והקלד מיקום…"
            preview = value if len(value) <= 57 else (value[:54] + "…" if is_rtl_text(value) else "…" + value[-54:])
            draw_text(surface, preview, 13, (rr.right - 10, rr.centery),
                      (235, 243, 245) if self.setup_puzzle_locations[idx] else (93, 120, 124),
                      align="midright")
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
        if not self.game_started_at or self.stage_manager.stage in (9, 12):
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

            if self.setup_active_text_field is not None:
                field = self.setup_active_text_field
                attr = "setup_clue_location" if field == "clue" else "setup_server_location"
                current = getattr(self, attr)
                if event.key == pygame.K_BACKSPACE:
                    setattr(self, attr, current[:-1])
                elif event.key == pygame.K_RETURN:
                    self.setup_active_text_field = None
                    self.stage_message = "מיקום הרמז נשמר לעריכה."
                elif len(event.unicode) == 1 and event.unicode.isprintable() and len(current) < 120:
                    setattr(self, attr, current + event.unicode)
                return

            if self.setup_active_piece is not None:
                if event.key == pygame.K_BACKSPACE:
                    current = self.setup_puzzle_locations[self.setup_active_piece]
                    self.setup_puzzle_locations[self.setup_active_piece] = current[:-1]
                    return
                if event.key == pygame.K_DELETE:
                    self.setup_puzzle_locations.pop(self.setup_active_piece)
                    if not self.setup_puzzle_locations:
                        self.setup_puzzle_locations = [""]
                    self.setup_active_piece = min(self.setup_active_piece, len(self.setup_puzzle_locations) - 1)
                    self.setup_piece_scroll = min(self.setup_piece_scroll, max(0, len(self.setup_puzzle_locations) - 3))
                    return
                if event.key == pygame.K_RETURN:
                    self.stage_message = f"מיקום חלק {self.setup_active_piece + 1} נערך. לחצו על שמור הגדרות."
                    self.setup_active_piece = None
                    return
                if len(event.unicode) == 1 and event.unicode.isprintable():
                    current = self.setup_puzzle_locations[self.setup_active_piece]
                    if len(current) < 120:
                        self.setup_puzzle_locations[self.setup_active_piece] = current + event.unicode
                    return
            elif event.key == pygame.K_RETURN:
                self.start_game()
                return

        if event.type == pygame.MOUSEWHEEL:
            panel = pygame.Rect(70, 480, 650, 178)
            if panel.collidepoint(pygame.mouse.get_pos()):
                max_start = max(0, len(self.setup_puzzle_locations) - 3)
                self.setup_piece_scroll = max(0, min(max_start, self.setup_piece_scroll - event.y))
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            clue_rect = pygame.Rect(70, 245, 650, 86)
            server_rect = pygame.Rect(70, 365, 650, 86)
            if clue_rect.collidepoint(event.pos):
                self.setup_active_text_field = "clue"
                self.setup_active_piece = None
                return
            if server_rect.collidepoint(event.pos):
                self.setup_active_text_field = "server"
                self.setup_active_piece = None
                return

            panel = pygame.Rect(70, 480, 650, 178)
            add_rect = pygame.Rect(panel.right - 92, panel.y + 12, 74, 29)
            if add_rect.collidepoint(event.pos):
                self.setup_active_text_field = None
                # The editor starts with one empty row; focus it instead of creating a blank-number gap.
                if not self.setup_puzzle_locations or self.setup_puzzle_locations[-1].strip():
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
                    self.setup_active_text_field = None
                    self.setup_puzzle_locations.pop(idx)
                    if not self.setup_puzzle_locations:
                        self.setup_puzzle_locations = [""]
                    self.setup_active_piece = min(idx, len(self.setup_puzzle_locations) - 1)
                    self.setup_piece_scroll = min(self.setup_piece_scroll, max(0, len(self.setup_puzzle_locations) - 3))
                    return
                if rr.collidepoint(event.pos):
                    self.setup_active_text_field = None
                    self.setup_active_piece = idx
                    return

            if self.setup_buttons[0].rect.collidepoint(event.pos):
                self.save_setup_config()
            elif self.setup_buttons[1].rect.collidepoint(event.pos):
                self.start_game()
            elif self.setup_buttons[2].rect.collidepoint(event.pos):
                self.running = False

    def handle_roster_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_BACKSPACE:
                self.player_name = self.player_name[:-1]
                self.roster_error = ""
            elif event.key == pygame.K_RETURN and self.player_name.strip():
                self.try_register()
            else:
                if len(event.unicode) == 1 and event.unicode.isprintable():
                    if len(self.player_name) < 24:
                        self.player_name += event.unicode
                        self.roster_error = ""
                    else:
                        self.roster_error = "השם מוגבל ל־24 תווים."

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

        # Write a temporary image first. Only register the player after the file is
        # readable and can be moved into place; failed writes must not create a dead profile.
        filename = PLAYER_DIR / f"player_{len(self.players) + 1:02d}.png"
        pending_filename = PLAYER_DIR / f"player_{len(self.players) + 1:02d}.pending.png"
        try:
            PLAYER_DIR.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(pending_filename), face):
                raise OSError("OpenCV returned False while saving the face image.")
            if cv2.imread(str(pending_filename)) is None:
                raise OSError("The saved face image could not be read back.")
            pending_filename.replace(filename)
        except (cv2.error, OSError):
            try:
                pending_filename.unlink(missing_ok=True)
            except OSError:
                pass
            self.roster_error = "לא ניתן לשמור את תמונת הרישום. בדקו הרשאות בתיקיית המשחק."
            return

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
        if self.stage_manager.later.handle_lifeline(event, WIDTH, HEIGHT):
            return
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
        elif 8 <= self.stage_manager.stage <= 12:
            self.stage_manager.later.handle(event, WIDTH, HEIGHT)
        else:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
    def handle_secret_keys(self, event):
        """Return True when a privileged operator shortcut consumed the key event."""
        if event.type != pygame.KEYDOWN:
            return False
        # Use the modifiers captured on this specific event, not a separate keyboard poll.
        mods = getattr(event, "mod", pygame.key.get_mods())
        skip_pressed = (
            (mods & pygame.KMOD_CTRL)
            and (mods & pygame.KMOD_SHIFT)
            and event.key == pygame.K_RIGHT
        )
        exit_pressed = (
            (mods & pygame.KMOD_CTRL)
            and (mods & pygame.KMOD_ALT)
            and (mods & pygame.KMOD_SHIFT)
            and event.key == pygame.K_ESCAPE
        )
        if exit_pressed:
            self.running = False
            return True
        if skip_pressed and self.state == "game":
            if self.stage_manager.stage < 12:
                self.stage_manager.goto(self.stage_manager.stage + 1)
            return True
        return False

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
        elif self.state == "game" and 8 <= self.stage_manager.stage <= 12:
            self.stage_manager.later.update(dt)

        if self.state == "game":
            self.stage_manager.later.lifeline_update()

    def draw(self):
        if self.state == "setup":
            self.operator_setup(screen)
        else:
            self.stage_manager.draw(screen)
            self.stage_manager.draw_transition(screen)
            self.stage_manager.later.draw_lifeline(screen, draw_text, rounded_panel, pygame, WIDTH, HEIGHT)
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
                if self.handle_secret_keys(event):
                    if not self.running:
                        break
                    continue
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
