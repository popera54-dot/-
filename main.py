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


def draw_face_lock(surface, webcam, display_rect):
    """Draw camera-aligned face-lock brackets without obscuring the live preview."""
    rect = pygame.Rect(display_rect)
    frame = getattr(webcam, "frame", None)
    face = getattr(webcam, "face_box", None)
    if frame is None:
        label = "CAMERA SIGNAL LOST" if not getattr(webcam, "available", False) else "WAITING FOR CAMERA FEED"
        color = (255, 84, 93)
    elif face is None:
        label = "ALIGN FACE TO RETICLE"
        color = (255, 192, 82)
    else:
        label = "FACE LOCK // TARGET ACQUIRED"
        color = (71, 255, 171)

    draw_text(surface, label, 11, (rect.x + 18, rect.y + 16),
              color, mono=True, bold=True)
    if frame is None or face is None:
        # Keep a minimal corner reticle active while the camera acquires a face.
        cx, cy = rect.right - 35, rect.y + 25
        pulse = 5 + int((math.sin(time.monotonic() * 7) + 1) * 2)
        pygame.draw.circle(surface, color, (cx, cy), pulse, 1)
        pygame.draw.line(surface, color, (cx - 12, cy), (cx - 7, cy), 1)
        pygame.draw.line(surface, color, (cx + 7, cy), (cx + 12, cy), 1)
        return False

    try:
        source_h, source_w = frame.shape[:2]
        x, y, w, h = [int(value) for value in face]
        area = rect.inflate(-12, -12)
        sx, sy = area.w / max(1, source_w), area.h / max(1, source_h)
        target = pygame.Rect(
            area.x + int(x * sx), area.y + int(y * sy),
            max(1, int(w * sx)), max(1, int(h * sy))
        ).inflate(12, 12).clip(area)
        if target.w < 16 or target.h < 16:
            return False

        corner = max(8, min(22, min(target.w, target.h) // 4))
        edges = [
            ((target.left, target.top), (target.left + corner, target.top)),
            ((target.left, target.top), (target.left, target.top + corner)),
            ((target.right, target.top), (target.right - corner, target.top)),
            ((target.right, target.top), (target.right, target.top + corner)),
            ((target.left, target.bottom), (target.left + corner, target.bottom)),
            ((target.left, target.bottom), (target.left, target.bottom - corner)),
            ((target.right, target.bottom), (target.right - corner, target.bottom)),
            ((target.right, target.bottom), (target.right, target.bottom - corner)),
        ]
        for start, end in edges:
            pygame.draw.line(surface, color, start, end, 3)
        pygame.draw.circle(surface, color, (target.right - 5, target.top + 5), 3)
        return True
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        # A malformed camera frame should not interrupt the escape room.
        return False


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



def draw_intrusion_monitor(surface, rect, t=0.0, *, silhouette=True, compact=False, timer_text=None):
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

        if timer_text:
            timer_box = pygame.Rect(sx + 16, sy + 17, 174, 70)
            pygame.draw.rect(surface, (2, 18, 11), timer_box)
            pygame.draw.rect(surface, (65, 255, 147), timer_box, 2)
            pygame.draw.line(surface, (65, 255, 147),
                             (timer_box.x + 7, timer_box.y + 5),
                             (timer_box.x + 48, timer_box.y + 5), 2)
            draw_text(surface, "TIME REMAINING", 9,
                      (timer_box.centerx, timer_box.y + 9), (119, 211, 144),
                      align="midtop", mono=True, bold=True)
            draw_text(surface, str(timer_text), 23,
                      (timer_box.centerx, timer_box.y + 43), (164, 255, 184),
                      align="center", mono=True, bold=True)

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
        glyphs = ("0", "1", "7", "X", "A", "F", "C", "E", "M", "K", ":", "/", "<", ">", "#", "$")
        for x in range(10, WIDTH, 28):
            speed = 55 + (x * 17) % 125
            offset = int((self.time * speed + x * 31) % (HEIGHT + 180))
            length = 8 + ((x // 28) % 9)
            column = x // 28
            for j in range(length):
                yy = (offset - j * 22) % (HEIGHT + 40) - 20
                intensity = clamp(160 - j * 15, 35, 160)
                is_red = (column % 17 == 0) and j < 4
                col = (255, intensity // 3, intensity // 3) if is_red else (35, intensity, 88)
                # Stable glyphs move through the rain instead of flickering into new characters
                # every rendered frame, preserving readability and a calmer cinematic texture.
                glyph = glyphs[(column * 7 + j * 11) % len(glyphs)]
                draw_text(surface, glyph, 13, (x, yy), col, mono=True, align="center")

        # Stable diagnostic lines drift behind gameplay; time moves the panels, not their text.
        terminal_messages = (
            "ACCESSING SECURITY CORE...",
            "AUTH_CHANNEL::MKBS_2.0",
            "DECRYPT /████/████/████",
            "INTRUSION TRACE // 97%",
            "FIREWALL NODE // BREACHED",
            "ROOT SESSION // UNKNOWN",
            "WARNING // SYSTEM INTEGRITY",
        )
        for k, message in enumerate(terminal_messages):
            y = 110 + k * 95
            drift = int(math.sin(self.time * 0.7 + k) * 35)
            draw_text(surface, message, 12, (18 + drift, y), (43, 128, 99), mono=True)

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


class AudioDirector:
    """Original procedural sci-fi audio: no external files, with safe silent fallback."""

    EFFECTS = {
        # Quiet tactile UI click; success and unlock cues remain the loudest short effects.
        "click": (0.060, 0.065), "keypress": (0.045, 0.045), "confirm": (0.31, 0.22),
        "puzzle": (0.78, 0.28), "unlock": (1.04, 0.30),
        "transition": (0.34, 0.18), "error": (0.36, 0.20),
        "intrusion": (1.32, 0.28), "tick": (0.095, 0.14),
        "urgent_tick": (0.16, 0.18), "heartbeat": (0.43, 0.14),
        "victory": (1.82, 0.34),
    }

    def __init__(self):
        self.app = None
        self.enabled = True
        self.game_paused = False
        self.available = False
        self.master_volume = 0.78
        self.sounds = {}
        self.effect_base_volumes = {}
        self.ambient_sound = None
        self.ambient_base_volume = 0.82
        self.ambient_channel = None
        self.ambient_texture_sound = None
        self.ambient_texture_base_volume = 0.34
        self.ambient_texture_channel = None
        self.ambient_requested = True
        self.settings_path = DATA_DIR / "audio_settings.json"
        self.stage = 0
        self.last_countdown_second = None
        self.last_alarm_marker = None
        self.last_heartbeat_second = None
        self._ambient_level_cache = None
        self._ambient_texture_level_cache = None
        self._last_played = {}
        self._load_preferences()
        self._build()
        if not self.enabled and pygame.mixer.get_init():
            pygame.mixer.pause()

    def _load_preferences(self):
        """Load sound preferences without making a missing/corrupt file fatal."""
        try:
            settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if not isinstance(settings, dict):
                return
            self.enabled = bool(settings.get("enabled", self.enabled))
            self.master_volume = clamp(float(settings.get("master_volume", self.master_volume)),
                                       0.25, 1.0)
            self.ambient_requested = bool(settings.get("ambient_enabled", self.ambient_requested))
        except (OSError, ValueError, TypeError):
            pass

    def _save_preferences(self):
        """Persist user audio preferences atomically; read-only folders remain safe."""
        payload = {
            "enabled": bool(self.enabled),
            "master_volume": round(clamp(float(self.master_volume), 0.25, 1.0), 2),
            "ambient_enabled": bool(self.ambient_requested),
        }
        temporary_path = self.settings_path.with_suffix(self.settings_path.suffix + ".tmp")
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary_path.replace(self.settings_path)
        except (OSError, ValueError, TypeError):
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def bind_app(self, app):
        self.app = app

    @staticmethod
    def _add_note(wave, t, start, duration, frequency, amplitude, decay=5.0, glide=0.0):
        active = (t >= start) & (t < start + duration)
        if not np.any(active):
            return
        local = t[active] - start
        phase = 2.0 * np.pi * (frequency * local + 0.5 * glide * local * local)
        attack = np.minimum(1.0, local / 0.010)
        release = np.clip((duration - local) / 0.045, 0.0, 1.0)
        envelope = attack * np.exp(-decay * local) * release
        wave[active] += amplitude * envelope * (
            np.sin(phase) + 0.19 * np.sin(phase * 2.0) + 0.045 * np.sin(phase * 3.01)
        )

    def _wave_to_sound(self, wave, volume, *, gain=19000.0, stereo_width=0.0):
        mixer = pygame.mixer.get_init()
        if not mixer:
            return None
        sample_rate, sample_format, channels = mixer
        if sample_format != -16 or channels < 1:
            return None
        mono = np.asarray(np.clip(np.asarray(wave, dtype=np.float32) * gain, -32767, 32767),
                          dtype=np.int16)
        if channels > 1:
            phase = np.sin(2.0 * np.pi * 0.25 * np.arange(len(mono), dtype=np.float32) / sample_rate)
            frames = np.repeat(mono[:, None], channels, axis=1)
            frames[:, 0] = np.asarray(np.clip(mono.astype(np.float32) * (1 + stereo_width * phase),
                                               -32767, 32767), dtype=np.int16)
            frames[:, 1] = np.asarray(np.clip(mono.astype(np.float32) * (1 - stereo_width * phase),
                                               -32767, 32767), dtype=np.int16)
            samples = np.ascontiguousarray(frames)
        else:
            samples = np.ascontiguousarray(mono)
        try:
            sound = pygame.sndarray.make_sound(samples)
            sound.set_volume(float(volume))
            return sound
        except (pygame.error, ValueError, TypeError):
            return None

    def _build_effect(self, name, sample_rate):
        duration, volume = self.EFFECTS[name]
        count = max(1, int(sample_rate * duration))
        t = np.arange(count, dtype=np.float32) / float(sample_rate)
        wave = np.zeros(count, dtype=np.float32)

        if name == "click":
            self._add_note(wave, t, 0.0, 0.047, 1120, 0.19, decay=74, glide=-680)
            wave += np.sin(2 * np.pi * 3150 * t) * np.exp(-t * 145) * 0.018
        elif name == "keypress":
            # A low-level glassy tick for typed codes, throttled to avoid a typewriter effect.
            self._add_note(wave, t, 0.0, 0.031, 1740, 0.12, decay=102, glide=-520)
            wave += np.sin(2 * np.pi * 2480 * t) * np.exp(-t * 180) * 0.009
        elif name == "confirm":
            for start, freq, amp in ((0.0, 659.25, 0.23), (0.060, 880.0, 0.18), (0.13, 1046.5, 0.16)):
                self._add_note(wave, t, start, 0.22, freq, amp, decay=6.5)
        elif name == "puzzle":
            for start, freq, amp in ((0.0, 523.25, 0.23), (0.15, 659.25, 0.21),
                                     (0.31, 783.99, 0.19), (0.47, 1046.5, 0.15)):
                self._add_note(wave, t, start, 0.43, freq, amp, decay=3.3)
            self._add_note(wave, t, 0.06, 0.42, 130.81, 0.10, decay=8.0)
        elif name == "unlock":
            self._add_note(wave, t, 0.0, 0.65, 82.41, 0.18, decay=7.0, glide=18)
            for start, freq, amp in ((0.035, 220.0, 0.21), (0.18, 329.63, 0.19),
                                     (0.34, 440.0, 0.17), (0.52, 659.25, 0.15),
                                     (0.67, 880.0, 0.11)):
                self._add_note(wave, t, start, 0.47, freq, amp, decay=4.5)
            self._add_note(wave, t, 0.0, 0.19, 58.27, 0.11, decay=18, glide=-55)
        elif name == "transition":
            self._add_note(wave, t, 0.015, 0.22, 392.0, 0.17, decay=8)
            self._add_note(wave, t, 0.13, 0.21, 523.25, 0.13, decay=9)
        elif name == "error":
            self._add_note(wave, t, 0.0, 0.23, 196.0, 0.22, decay=4.8, glide=-185)
            self._add_note(wave, t, 0.075, 0.24, 146.83, 0.17, decay=5.0, glide=-80)
            self._add_note(wave, t, 0.01, 0.21, 73.42, 0.10, decay=7.5)
        elif name == "intrusion":
            swell = np.minimum(1.0, t / 0.36) * np.clip((duration - t) / 0.20, 0, 1)
            wave += swell * (
                0.18 * np.sin(2 * np.pi * (43.0 * t + 5.6 * t * t))
                + 0.10 * np.sin(2 * np.pi * 61.74 * t)
                + 0.065 * np.sin(2 * np.pi * 87.31 * t)
            )
            self._add_note(wave, t, 0.72, 0.49, 247.0, 0.15, decay=2.4, glide=-105)
            self._add_note(wave, t, 0.94, 0.31, 123.47, 0.10, decay=4.0, glide=-25)
        elif name == "tick":
            self._add_note(wave, t, 0.0, 0.071, 740.0, 0.20, decay=42, glide=-120)
        elif name == "urgent_tick":
            self._add_note(wave, t, 0.0, 0.095, 520.0, 0.20, decay=25, glide=-80)
            self._add_note(wave, t, 0.045, 0.095, 880.0, 0.14, decay=30, glide=-160)
        elif name == "heartbeat":
            # Soft low-frequency double pulse; suspenseful without a harsh alarm tone.
            for start, duration, frequency, amplitude in (
                (0.00, 0.17, 68.0, 0.28), (0.19, 0.22, 52.0, 0.22)
            ):
                active = (t >= start) & (t < start + duration)
                local = t[active] - start
                swell = np.maximum(
                    0.0, np.sin(np.pi * np.clip(local / duration, 0.0, 1.0))
                ) ** 1.5
                wave[active] += amplitude * swell * (
                    np.sin(2.0 * np.pi * (frequency * local - 13.0 * local * local))
                    + 0.20 * np.sin(2.0 * np.pi * frequency * 2.0 * local)
                )
        elif name == "victory":
            for start, freq, amp in (
                (0.02, 392.0, 0.20), (0.20, 523.25, 0.19), (0.41, 659.25, 0.18),
                (0.65, 783.99, 0.17), (0.94, 1046.5, 0.16), (1.15, 1318.51, 0.12)
            ):
                self._add_note(wave, t, start, 0.66, freq, amp, decay=2.9)
            self._add_note(wave, t, 0.63, 0.85, 130.81, 0.12, decay=2.0)
            self._add_note(wave, t, 0.80, 0.82, 196.0, 0.09, decay=2.4)

        edge = min(max(1, int(sample_rate * 0.008)), count // 2)
        if edge > 1:
            ramp = np.linspace(0.0, 1.0, edge, dtype=np.float32)
            wave[:edge] *= ramp
            wave[-edge:] *= ramp[::-1]
        return self._wave_to_sound(wave, volume, gain=19000.0, stereo_width=0.025)

    def _build_ambient(self, sample_rate):
        """Build an eight-second seamless, layered cyber-thriller ambience loop."""
        duration = 8.0
        t = np.arange(int(sample_rate * duration), dtype=np.float32) / float(sample_rate)

        # A sub drone, fifth, and upper harmonics create weight without a loud alarm.
        breath = 0.78 + 0.22 * np.sin(2 * np.pi * 0.125 * t)
        low_bed = (
            0.17 * np.sin(2 * np.pi * 55.0 * t)
            + 0.115 * np.sin(2 * np.pi * 82.5 * t + 0.12)
            + 0.068 * np.sin(2 * np.pi * 110.0 * t + 0.35)
            + 0.028 * np.sin(2 * np.pi * 165.0 * t + 0.64)
        )
        wave = breath * low_bed

        # A softly moving, in-tune upper pad and a restrained four-note signal motif.
        shimmer_phase = 2 * np.pi * 220.0 * t + 1.25 * np.sin(2 * np.pi * 0.125 * t)
        shimmer_envelope = 0.68 + 0.32 * np.sin(2 * np.pi * 0.25 * t + 0.4)
        wave += 0.034 * np.sin(shimmer_phase) * shimmer_envelope
        wave += 0.016 * np.sin(2 * np.pi * 330.0 * t + 0.8 * np.sin(2 * np.pi * 0.125 * t))

        # Quiet plucked notes add forward motion; their tails end before the loop seam.
        motif = (164.81, 146.83, 123.47, 146.83)
        for index, start in enumerate((0.18, 2.18, 4.18, 6.18)):
            self._add_note(wave, t, start, 0.62, motif[index], 0.055, decay=4.2)
        for start, frequency in ((0.82, 659.25), (4.82, 587.33)):
            self._add_note(wave, t, start, 0.36, frequency, 0.020, decay=6.3)

        # Lower volume is deliberate: puzzle tones and spoken teamwork must stay clear.
        return self._wave_to_sound(wave, 0.82, gain=12500.0, stereo_width=0.11)

    def _build_ambient_texture(self, sample_rate):
        """Generate a restrained radio-static layer with a seamless eight-second loop."""
        duration = 8.0
        count = max(1, int(sample_rate * duration))
        t = np.arange(count, dtype=np.float32) / float(sample_rate)

        # Interpolated, deterministic noise avoids a harsh broadband hiss. Matching
        # endpoint anchors keeps the loop seam quiet rather than producing a click.
        rng = np.random.default_rng(2048)
        anchor_count = 901
        anchors = rng.normal(0.0, 1.0, anchor_count).astype(np.float32)
        anchors[-1] = anchors[0]
        noise = np.interp(
            np.arange(count, dtype=np.float32),
            np.linspace(0, count - 1, anchor_count, dtype=np.float32),
            anchors,
        ).astype(np.float32)
        noise -= float(np.mean(noise))
        noise_peak = max(1e-6, float(np.max(np.abs(noise))))
        noise /= noise_peak

        # Slow swells plus narrow, soft transmission chirps: texture, not a loud alarm.
        swell = 0.22 + 0.78 * np.power(
            0.5 + 0.5 * np.sin(2.0 * np.pi * 0.25 * t + np.pi / 2.0), 4
        )
        wave = noise * swell * 0.042
        for start, frequency, glide in (
            (0.72, 780.0, -125.0),
            (2.72, 610.0, 90.0),
            (4.72, 860.0, -180.0),
            (6.72, 540.0, 115.0),
        ):
            self._add_note(wave, t, start, 0.15, frequency, 0.032,
                           decay=12.0, glide=glide)

        # Keep the loop mathematically closed at its output samples.
        wave[-1] = wave[0]
        return self._wave_to_sound(wave, 0.42, gain=15000.0, stereo_width=0.04)

    def _build(self):
        try:
            mixer = pygame.mixer.get_init()
            if not mixer:
                return
            sample_rate, sample_format, _channels = mixer
            if sample_format != -16:
                return
            pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
            for name in self.EFFECTS:
                sound = self._build_effect(name, sample_rate)
                if sound is not None:
                    self.sounds[name] = sound
                    self.effect_base_volumes[name] = self.EFFECTS[name][1]
            self.ambient_sound = self._build_ambient(sample_rate)
            self.ambient_texture_sound = self._build_ambient_texture(sample_rate)
            self.ambient_channel = pygame.mixer.Channel(15)
            self.ambient_texture_channel = pygame.mixer.Channel(14)
            self.available = bool(self.sounds)
            self._apply_volume()
        except (pygame.error, ValueError, TypeError, RuntimeError):
            self.sounds = {}
            self.ambient_sound = None
            self.ambient_channel = None
            self.ambient_texture_sound = None
            self.ambient_texture_channel = None
            self.available = False

    def play(self, name):
        if not self.enabled:
            return False
        sound = self.sounds.get(name)
        if sound is None:
            return False
        now = time.monotonic()
        cooldown = (
            0.28 if name == "error"
            else 0.045 if name == "keypress"
            else 0.12 if name == "click"
            else 0.10 if name in ("confirm", "tick")
            else 0.0
        )
        if now - self._last_played.get(name, -1000.0) < cooldown:
            return False
        self._last_played[name] = now
        try:
            sound.play()
            return True
        except pygame.error:
            return False

    def start_ambient(self):
        self.ambient_requested = True
        if self.game_paused or not self.enabled:
            return
        try:
            if self.ambient_channel is not None and self.ambient_sound is not None:
                if not self.ambient_channel.get_busy():
                    self.ambient_channel.play(self.ambient_sound, loops=-1, fade_ms=900)
            if self.ambient_texture_channel is not None and self.ambient_texture_sound is not None:
                if not self.ambient_texture_channel.get_busy():
                    self.ambient_texture_channel.play(
                        self.ambient_texture_sound, loops=-1, fade_ms=1200
                    )
            self._set_ambient_level(force=True)
        except pygame.error:
            pass

    def stop_ambient(self):
        self.ambient_requested = False
        channels = (self.ambient_channel, self.ambient_texture_channel)
        for channel in channels:
            if channel is None:
                continue
            try:
                channel.fadeout(650) if self.enabled else channel.stop()
            except pygame.error:
                pass

    def _ambient_target_level(self, remaining_seconds=None):
        # Duck the ambience during the frequency puzzle so the clue tones stay crystal clear.
        if self.stage == 8:
            return 0.085

        level = 0.36 if self.stage in (9, 11) else 0.29
        if remaining_seconds is not None:
            remaining = max(0, int(remaining_seconds))
            if remaining <= 30:
                level = max(level, 0.48)
            elif remaining <= 60:
                level = max(level, 0.44)
            elif remaining <= 180:
                level = max(level, 0.40)
            elif remaining <= 300:
                level = max(level, 0.34)
        return level

    def _ambient_texture_target_level(self, remaining_seconds=None):
        # The radio bed gets quieter during the listening cipher and gently busier near timeout.
        if self.stage == 8:
            return 0.025
        level = 0.13 if self.stage in (9, 11) else 0.105
        if remaining_seconds is not None:
            remaining = max(0, int(remaining_seconds))
            if remaining <= 30:
                level = max(level, 0.20)
            elif remaining <= 60:
                level = max(level, 0.17)
            elif remaining <= 180:
                level = max(level, 0.145)
        return level

    def _set_ambient_level(self, remaining_seconds=None, *, force=False):
        level = self._ambient_target_level(remaining_seconds)
        texture_level = self._ambient_texture_target_level(remaining_seconds)
        if self.ambient_channel is not None and (force or level != self._ambient_level_cache):
            try:
                self.ambient_channel.set_volume(level)
                self._ambient_level_cache = level
            except pygame.error:
                pass
        if self.ambient_texture_channel is not None and (
            force or texture_level != self._ambient_texture_level_cache
        ):
            try:
                self.ambient_texture_channel.set_volume(texture_level)
                self._ambient_texture_level_cache = texture_level
            except pygame.error:
                pass

    def _apply_volume(self):
        """Apply the master level to synthesized effects and ambient audio."""
        self.master_volume = clamp(float(self.master_volume), 0.25, 1.0)
        for name, sound in self.sounds.items():
            try:
                sound.set_volume(self.effect_base_volumes.get(name, 0.18) * self.master_volume)
            except pygame.error:
                pass
        if self.ambient_sound is not None:
            try:
                self.ambient_sound.set_volume(self.ambient_base_volume * self.master_volume)
            except pygame.error:
                pass
        if self.ambient_texture_sound is not None:
            try:
                self.ambient_texture_sound.set_volume(
                    self.ambient_texture_base_volume * self.master_volume
                )
            except pygame.error:
                pass
        self._ambient_level_cache = None
        self._ambient_texture_level_cache = None
        self._set_ambient_level(force=True)
        if self.app is not None:
            later = getattr(getattr(self.app, "stage_manager", None), "later", None)
            if later is not None:
                if getattr(later, "sound", None) is not None:
                    try:
                        later.sound.set_volume(0.24 * self.master_volume)
                    except pygame.error:
                        pass
                channel = getattr(later, "music_channel", None)
                if channel is not None:
                    try:
                        # The music Sound already carries its own mix level; Channel volume
                        # is reserved for the master control so volume does not get multiplied twice.
                        channel.set_volume(self.master_volume)
                    except pygame.error:
                        pass

    def adjust_volume(self, delta):
        old = self.master_volume
        self.master_volume = round(clamp(old + float(delta), 0.25, 1.0), 2)
        if self.master_volume != old:
            self._apply_volume()
            self._save_preferences()
        return self.master_volume

    def toggle_ambient(self):
        # Keep the finale's celebratory arrangement clean; the suspense drone stays off there.
        if self.stage >= 12:
            self.stop_ambient()
            return False
        if self.ambient_requested:
            self.stop_ambient()
            self._save_preferences()
            return False
        self.start_ambient()
        self._save_preferences()
        return True

    def set_stage(self, stage):
        self.stage = int(stage)
        if self.stage >= 12:
            self.stop_ambient()
        elif self.ambient_requested:
            self.start_ambient()
            self._set_ambient_level()

    def start_game(self):
        self.last_countdown_second = None
        # Respect the user's saved ambience choice instead of silently re-enabling it.
        if self.ambient_requested:
            self.start_ambient()
        if self.enabled:
            self.play("intrusion")

    def update(self, remaining_seconds, stage):
        stage = int(stage)
        remaining = max(0, int(remaining_seconds))
        if stage >= 12:
            self.last_countdown_second = None
            self.last_alarm_marker = None
            self.last_heartbeat_second = None
            return

        self._set_ambient_level(remaining)
        # Clear checkpoints rather than a constant alarm during the full hour.
        if remaining in (300, 180, 60) and remaining != self.last_alarm_marker:
            self.last_alarm_marker = remaining
            self.play("urgent_tick" if remaining == 60 else "tick")

        # Soft double pulses add tension during the last minute, then yield to
        # the precise final-ten-second countdown beeps.
        if 10 < remaining <= 60 and remaining % 10 == 0 and remaining != self.last_heartbeat_second:
            self.last_heartbeat_second = remaining
            self.play("heartbeat")

        if 1 <= remaining <= 10 and remaining != self.last_countdown_second:
            self.last_countdown_second = remaining
            self.play("urgent_tick" if remaining <= 3 else "tick")
        elif remaining > 10:
            self.last_countdown_second = None

    def toggle(self):
        self.enabled = not self.enabled
        try:
            if pygame.mixer.get_init():
                if self.enabled:
                    pygame.mixer.unpause()
                    if self.ambient_requested:
                        self.start_ambient()
                    if self.app and getattr(self.app, "state", "") == "game":
                        if self.app.stage_manager.stage == 12:
                            later = self.app.stage_manager.later
                            if later.music_sound is None:
                                later._start_celebration_music()
                            elif later.music_channel is not None and not later.music_channel.get_busy():
                                later.music_channel.play(later.music_sound, loops=-1)
                else:
                    pygame.mixer.pause()
                # Changing sound settings while the mission is paused must never unpause playback.
                if self.game_paused:
                    pygame.mixer.pause()
        except (pygame.error, AttributeError, RuntimeError):
            pass
        self._save_preferences()
        return self.enabled

    def set_paused(self, paused):
        """Pause/resume every mixer channel while respecting master mute."""
        self.game_paused = bool(paused)
        if not pygame.mixer.get_init():
            return
        try:
            if self.game_paused or not self.enabled:
                pygame.mixer.pause()
            else:
                pygame.mixer.unpause()
                if self.ambient_requested and self.stage < 12:
                    self.start_ambient()
        except pygame.error:
            pass

    def draw_status(self, surface, draw_text, width, height):
        if not self.available:
            label, color = "AUDIO OFFLINE  //  GAME STILL PLAYABLE", (127, 147, 148)
        elif self.enabled:
            ambience = "AMBIENCE ON" if self.ambient_requested else "AMBIENCE OFF"
            label = f"SOUND {int(self.master_volume * 100)}%  //  F7 {ambience}  F8 MUTE  F9/F10 VOLUME"
            color = (77, 190, 139)
        else:
            label, color = "SOUND MUTED  //  F8 UNMUTE", (255, 107, 111)
        draw_text(surface, label, 9, (width - 28, height - 24), color,
                  align="bottomright", mono=True)

    def stop(self):
        self.stop_ambient()
        for channel in (self.ambient_channel, self.ambient_texture_channel):
            if channel is not None:
                try:
                    channel.stop()
                except pygame.error:
                    pass


class Webcam:
    def __init__(self):
        self.cap = None
        self.frame = None
        self.face_box = None
        self.available = False
        self.last_error = None
        self.face_detector = None
        self._read_failures = 0
        self._next_reconnect_at = 0.0
        try:
            detector_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            candidate = cv2.CascadeClassifier(detector_path)
            if not candidate.empty():
                self.face_detector = candidate
            else:
                self.last_error = "OpenCV face detector could not be loaded."
        except (cv2.error, AttributeError, OSError) as exc:
            self.last_error = str(exc)
        self._open()

    def _open(self):
        """Try the Windows DirectShow backend first, then OpenCV's platform default."""
        candidates = []
        try:
            candidates.append(cv2.VideoCapture(0, cv2.CAP_DSHOW))
        except Exception as exc:
            self.last_error = str(exc)

        # CAP_DSHOW is Windows-specific. The generic backend is a necessary fallback
        # for laptops using another camera stack, virtual cameras, and non-Windows smoke tests.
        try:
            candidates.append(cv2.VideoCapture(0))
        except Exception as exc:
            self.last_error = str(exc)

        for candidate in candidates:
            try:
                if candidate is not None and candidate.isOpened():
                    self.cap = candidate
                    self.available = True
                    self.last_error = None
                    self._read_failures = 0
                    self._next_reconnect_at = 0.0
                    return
                if candidate is not None:
                    candidate.release()
            except Exception as exc:
                self.last_error = str(exc)
                try:
                    if candidate is not None:
                        candidate.release()
                except Exception:
                    pass

        self.cap = None
        self.available = False
        self._read_failures = 0
        self._next_reconnect_at = time.monotonic() + 3.0
        if not self.last_error:
            self.last_error = "No usable webcam backend opened camera index 0."

    def read(self, detect_face=True):
        if not self.available or self.cap is None:
            self.frame = None
            self.face_box = None
            # Retry camera discovery sparingly so a late USB camera or reconnect can recover.
            if time.monotonic() >= getattr(self, "_next_reconnect_at", 0.0):
                self._open()
            if not self.available or self.cap is None:
                return None
        try:
            ok, frame = self.cap.read()
        except (cv2.error, AttributeError, RuntimeError) as exc:
            self.last_error = str(exc)
            ok, frame = False, None
        if not ok or frame is None:
            # Never leave an old frame eligible for registration or presence verification.
            self.frame = None
            self.face_box = None
            self._read_failures = getattr(self, "_read_failures", 0) + 1
            if self._read_failures >= 3:
                failed_cap = self.cap
                self.cap = None
                self.available = False
                self._read_failures = 0
                self._next_reconnect_at = time.monotonic() + 3.0
                if not self.last_error:
                    self.last_error = "Camera read failed repeatedly; reconnect scheduled."
                try:
                    if failed_cap is not None:
                        failed_cap.release()
                except Exception:
                    pass
            return None
        self._read_failures = 0
        frame = cv2.flip(frame, 1)
        self.frame = frame
        if detect_face:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Reuse the cascade instead of reloading its XML file for every video frame.
            faces = ()
            if self.face_detector is not None:
                try:
                    faces = self.face_detector.detectMultiScale(
                        gray, 1.15, 5, minSize=(90, 90)
                    )
                except cv2.error as exc:
                    self.last_error = str(exc)
            self.face_box = max(faces, key=lambda b: b[2] * b[3]) if len(faces) else None
        else:
            # The dance finale needs only frame-to-frame motion, not face detection.
            self.face_box = None
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
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.cap = None
        self.available = False
        self.frame = None
        self.face_box = None


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
        for task in self.tasks:
            task.bind_app(self.app)
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
        if not 0 <= self.current_task_index < len(self.tasks):
            return None
        return self.tasks[self.current_task_index]

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

    def begin_task_clear(self):
        """Hold the solved task on screen long enough for the team to feel the win."""
        if self.phase == "task_clear":
            return
        task = self.current_task
        if task is None or not task.done:
            return
        task.feedback_text = "TASK VERIFIED // ACCESS GRANTED"
        task.feedback_until = time.monotonic() + 0.95
        task.feedback_success = True
        self.phase = "task_clear"
        self.phase_started = time.monotonic()
        self.app.audio.play("puzzle")

    def advance(self):
        self.assigned_player += 1
        self.current_task_index += 1
        if self.assigned_player >= len(self.app.players):
            self.app.stage_message = "SECURITY CHAIN CLEARED"
            self.app.stage_manager.goto(6)
            return
        self.begin_verification()

    def update(self, dt):
        if self.phase == "verify":
            self.app.webcam.read()
        elif self.phase == "task_clear":
            if time.monotonic() - self.phase_started >= 0.92:
                self.advance()
        elif self.phase == "task" and self.current_task:
            task = self.current_task
            if isinstance(task, OilCatchTask):
                task.update_and_collide(dt, WIDTH, HEIGHT)
            else:
                task.update(dt)
            # Update-driven tasks must also enter the success beat without another click.
            if task.done:
                self.begin_task_clear()

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

            draw_face_lock(surface, self.app.webcam, cam_rect)

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

        if self.phase in ("task", "task_clear") and task:
            player_name = getattr(player, "name", "UNKNOWN") if player else "UNKNOWN"
            draw_text(surface,
                      f"PLAYER {self.assigned_player + 1:02d}  //  {player_name}",
                      13, (WIDTH / 2, 30), (255, 193, 78),
                      align="center", mono=True, bold=True)
            task.draw(surface, draw_text, rounded_panel, glow_circle, pygame, WIDTH, HEIGHT, t)

            if self.phase == "task" and task.feedback_text and time.monotonic() < task.feedback_until:
                feedback_rect = pygame.Rect(WIDTH // 2 - 250, 142, 500, 36)
                accent = (74, 255, 170) if task.feedback_success else (255, 79, 93)
                rounded_panel(surface, feedback_rect, (2, 10, 13, 235), accent, 8, 2)
                draw_text(surface, task.feedback_text, 14, feedback_rect.center,
                          accent, align="center", mono=True, bold=True)

            if self.phase == "task_clear":
                veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                veil.fill((0, 5, 7, 154))
                surface.blit(veil, (0, 0))
                panel = pygame.Rect(WIDTH // 2 - 350, HEIGHT // 2 - 120, 700, 240)
                rounded_panel(surface, panel, (2, 12, 13, 246), (62, 255, 163), 18, 3)
                pygame.draw.line(surface, (255, 79, 79),
                                 (panel.x + 18, panel.y + 17),
                                 (panel.x + 115, panel.y + 17), 2)
                draw_text(surface, "SECURITY NODE CAPTURED", 13,
                          (panel.centerx, panel.y + 35), (80, 225, 147),
                          align="center", mono=True, bold=True)
                draw_text(surface, "ACCESS GRANTED", 42,
                          (panel.centerx, panel.y + 91), (245, 255, 249),
                          align="center", mono=True, bold=True)
                task_name = fit_text(task.name.upper(), 18, panel.w - 50, mono=True, bold=True)
                draw_text(surface, task_name, 18,
                          (panel.centerx, panel.y + 137), (255, 186, 104),
                          align="center", mono=True, bold=True)
                draw_text(surface,
                          f"PLAYER {self.assigned_player + 1:02d} / {max(1, len(self.app.players)):02d}  //  NEXT LOCK INITIALIZING",
                          11, (panel.centerx, panel.y + 177), (106, 171, 142),
                          align="center", mono=True)
                # Team progress makes a multi-player round feel like a coordinated operation.
                total = max(1, len(self.app.players))
                bar_x, bar_y, segment_w, gap = panel.x + 105, panel.bottom - 32, 30, 8
                total_w = total * segment_w + (total - 1) * gap
                bar_x = panel.centerx - total_w // 2
                for index in range(total):
                    rr = pygame.Rect(bar_x + index * (segment_w + gap), bar_y, segment_w, 5)
                    color = (64, 237, 145) if index <= self.assigned_player else (27, 56, 45)
                    pygame.draw.rect(surface, color, rr)

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
                self.begin_task_clear()


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
            self.app.audio.play("transition" if previous_stage == 1 else "unlock")

        completion_message = str(self.app.stage_message or "").upper()
        clear_markers = (
            "COLLAPSED", "CLEARED", "CRACKED", "SECURED", "DECRYPTED",
            "ACCEPTED", "VERIFIED", "STABLE"
        )
        if (previous_stage >= 3 and stage == previous_stage + 1
                and any(marker in completion_message for marker in clear_markers)):
            elapsed = max(0.0, time.monotonic() - self.app.stage_started_at)
            speed_bonus = int(60 * max(0.0, 1.0 - min(elapsed, 180.0) / 180.0))
            self.app.last_score_gain = 150 + speed_bonus
            self.app.mission_xp += self.app.last_score_gain
            self.app.stages_cleared += 1
            self.app.last_cleared_stage = previous_stage
        else:
            self.app.last_score_gain = 0

        self.stage = stage
        self.app.audio.set_stage(stage)
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
        unlock_titles = {
            1: "INTRUSION ACTIVE // REGISTER THE TEAM",
            2: "TEAM ROSTER SEALED",
            3: "OIL CIPHER CRACKED",
            4: "PHYSICAL PUZZLE VERIFIED",
            5: "SECURITY CHAIN CLEARED",
            6: "DARK PROTOCOL CRACKED",
            7: "SERVER CORE SECURED",
            8: "FREQUENCY DECODED",
            9: "INVERSION OVERRIDE ACCEPTED",
            10: "MEMORY MATRIX VERIFIED",
            11: "QUANTUM CURRENT STABLE",
        }
        title = unlock_titles.get(
            self.transition_from, f"PROTOCOL {self.transition_from:02d} CLEARED"
        )
        draw_text(surface, fit_text(title, 30, panel.w - 54, mono=True, bold=True), 30,
                  (panel.centerx, panel.y + 76), (245, 255, 249),
                  align="center", mono=True, bold=True)
        draw_text(surface, f"NEXT // PROTOCOL {stage:02d} UNLOCKED", 12,
                  (panel.centerx, panel.y + 112), (255, 174, 105),
                  align="center", mono=True, bold=True)
        if self.app.last_score_gain > 0:
            draw_text(surface,
                      f"+{self.app.last_score_gain:03d} XP  //  TEAM SCORE {self.app.mission_xp:05d}",
                      14, (panel.centerx, panel.y + 141), (83, 255, 168),
                      align="center", mono=True, bold=True)
            stage_label = self.app.stage_names.get(stage, "UNKNOWN SIGNAL")
            draw_text(surface, fit_text(stage_label.upper(), 12, panel.w - 62, mono=True, bold=True),
                      12, (panel.centerx, panel.y + 162), (255, 174, 105),
                      align="center", mono=True, bold=True)
        else:
            stage_label = self.app.stage_names.get(stage, "UNKNOWN SIGNAL")
            draw_text(surface, fit_text(stage_label.upper(), 15, panel.w - 62, mono=True, bold=True),
                      15, (panel.centerx, panel.y + 145), (255, 174, 105),
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
        draw_intrusion_monitor(surface, display_rect, elapsed, silhouette=True,
                               timer_text=self.app.timer_string())

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

        draw_face_lock(surface, self.app.webcam, cam_rect)

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
        self.audio = AudioDirector()
        self.audio.bind_app(self)

        self.state = "setup"
        self.paused = False
        self.pause_started_at = None
        self.paused_frame = None
        self.paused_remaining = None
        self.stage_manager = StageManager(self)
        self.stage_started_at = time.monotonic()
        self.mission_xp = 0
        self.stages_cleared = 0
        self.last_score_gain = 0
        self.last_cleared_stage = 0
        self.mistakes = 0

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
        self.state = "game"
        self.audio.start_game()
        self.stage_manager.goto(1)

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
    def _pause_layout(self):
        panel = pygame.Rect(WIDTH // 2 - 390, HEIGHT // 2 - 270, 780, 540)
        return {
            "panel": panel,
            "resume": pygame.Rect(panel.x + 52, panel.y + 205, panel.w - 104, 60),
            "sound": pygame.Rect(panel.x + 52, panel.y + 285, 320, 54),
            "ambience": pygame.Rect(panel.x + 408, panel.y + 285, 320, 54),
            "volume_down": pygame.Rect(panel.x + 52, panel.y + 360, 145, 50),
            "volume_up": pygame.Rect(panel.right - 197, panel.y + 360, 145, 50),
        }

    def pause_game(self):
        """Freeze the mission without losing the current puzzle or its remaining time."""
        if self.state != "game" or self.paused:
            return False
        self.paused_remaining = self.remaining_seconds
        self.paused_frame = screen.copy()
        self.pause_started_at = time.monotonic()
        self.paused = True
        self.audio.set_paused(True)
        return True

    @staticmethod
    def _shift_timestamp(obj, attr, delta):
        if obj is None or not hasattr(obj, attr):
            return
        value = getattr(obj, attr)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            setattr(obj, attr, value + delta)

    def resume_game(self):
        """Shift wall-clock deadlines by the pause duration so puzzles truly stop."""
        if not self.paused:
            return False
        now = time.monotonic()
        elapsed = max(0.0, now - (self.pause_started_at or now))

        self.game_started_at = (self.game_started_at + elapsed
                                if self.game_started_at is not None else None)
        self.stage_started_at += elapsed
        self._shift_timestamp(self.stage_manager, "transition_started_at", elapsed)

        # These are monotonic deadlines. Shift them together so no puzzle times out
        # or skips audio notes after a long pause.
        later = self.stage_manager.later
        for attr in (
            "phase_started", "next_beep_at", "wrong_until", "memory_started",
            "memory_retry_at", "quantum_started", "quantum_done_at", "dance_started",
            "victory_started", "countdown_started", "debrief_started",
            "lifeline_feedback_until",
        ):
            self._shift_timestamp(later, attr, elapsed)

        stage5 = self.stage_manager.stage5
        self._shift_timestamp(stage5, "phase_started", elapsed)
        for task in stage5.tasks:
            for attr in (
                "started", "deadline", "preview_until", "feedback_until",
                "flash_until", "hide_until", "reveal_until", "wrong_until",
                "next_flash_at", "animation_started", "expires_at",
            ):
                self._shift_timestamp(task, attr, elapsed)

        # Do not shift Stage 4's started_at: it uses the simulation clock, which
        # is stopped while paused. The finale's frozen mission timer is unchanged.
        self.paused = False
        self.pause_started_at = None
        self.paused_frame = None
        self.paused_remaining = None
        self.audio.set_paused(False)
        return True

    def handle_pause_event(self, event):
        if not self.paused:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.resume_game()
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            layout = self._pause_layout()
            if layout["resume"].collidepoint(event.pos):
                self.resume_game()
                return True
            if layout["sound"].collidepoint(event.pos):
                enabled = self.audio.toggle()
                self.stage_message = "SOUND DESIGN ACTIVE" if enabled else "SOUND MUTED"
                return True
            if layout["ambience"].collidepoint(event.pos):
                enabled = self.audio.toggle_ambient()
                self.stage_message = "AMBIENT DRONE ENABLED" if enabled else "AMBIENT DRONE DISABLED"
                return True
            if layout["volume_down"].collidepoint(event.pos):
                level = self.audio.adjust_volume(-0.08)
                self.stage_message = f"SOUND LEVEL // {int(level * 100)}%"
                return True
            if layout["volume_up"].collidepoint(event.pos):
                level = self.audio.adjust_volume(0.08)
                self.stage_message = f"SOUND LEVEL // {int(level * 100)}%"
                return True
        return True

    def draw_pause_overlay(self, surface):
        layout = self._pause_layout()
        panel = layout["panel"]
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((0, 4, 7, 188))
        surface.blit(veil, (0, 0))
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 2.6)
        rounded_panel(surface, panel, (2, 10, 14, 252), (42, int(170 + 65 * pulse), 128), 24, 2)
        pygame.draw.line(surface, (255, 67, 79),
                         (panel.x + 26, panel.y + 20), (panel.x + 142, panel.y + 20), 2)
        pygame.draw.line(surface, (64, 255, 177),
                         (panel.right - 142, panel.bottom - 20), (panel.right - 26, panel.bottom - 20), 2)
        draw_text(surface, "MISSION CONTROL // SIMULATION FROZEN", 12,
                  (panel.centerx, panel.y + 37), (75, 227, 160),
                  align="center", mono=True, bold=True)
        draw_text(surface, "המשימה בהשהיה", 42, (panel.centerx, panel.y + 94),
                  (239, 250, 247), align="center", bold=True)
        label = self.stage_names.get(self.stage_manager.stage, "MISSION SETUP")
        draw_text(surface, fit_text(label.upper(), 16, panel.w - 100, mono=True, bold=True),
                  16, (panel.centerx, panel.y + 139), (255, 183, 103),
                  align="center", mono=True, bold=True)
        remaining = self.paused_remaining if self.paused_remaining is not None else self.remaining_seconds
        draw_text(surface, f"TIMER FROZEN  //  {remaining // 60:02d}:{remaining % 60:02d} REMAINING",
                  13, (panel.centerx, panel.y + 172), (128, 166, 166),
                  align="center", mono=True)

        self._draw_pause_button(surface, layout["resume"], "המשך במשימה  /  RESUME", (63, 255, 178), primary=True)
        sound_label = "SOUND: ON  [F8]" if self.audio.enabled else "SOUND: OFF  [F8]"
        ambient_label = "AMBIENCE: ON  [F7]" if self.audio.ambient_requested else "AMBIENCE: OFF  [F7]"
        self._draw_pause_button(surface, layout["sound"], sound_label,
                                (66, 218, 166) if self.audio.enabled else (255, 99, 109))
        self._draw_pause_button(surface, layout["ambience"], ambient_label,
                                (66, 218, 166) if self.audio.ambient_requested else (111, 133, 138))
        self._draw_pause_button(surface, layout["volume_down"], "−  VOLUME [F9]", (100, 190, 175))
        self._draw_pause_button(surface, layout["volume_up"], "+  VOLUME [F10]", (100, 190, 175))
        draw_text(surface, f"MASTER VOLUME  //  {int(self.audio.master_volume * 100)}%",
                  12, (panel.centerx, panel.y + 385), (179, 208, 204),
                  align="center", mono=True, bold=True)
        draw_text(surface, "ESC / ENTER / SPACE  RESUME     •     CTRL+ALT+SHIFT+ESC  EMERGENCY EXIT",
                  10, (panel.centerx, panel.bottom - 36), (103, 136, 141),
                  align="center", mono=True)

    @staticmethod
    def _draw_pause_button(surface, rect, label, accent, primary=False):
        hover = rect.collidepoint(pygame.mouse.get_pos())
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 7.5)
        border = tuple(clamp(c + (26 if hover else 0), 0, 255) for c in accent)
        rounded_panel(surface, rect, (5, 24, 27) if (hover or primary) else (4, 14, 18),
                      border, 12, 2 if (hover or primary) else 1)
        if hover:
            x = rect.x + 8 + int((time.monotonic() * 185) % max(1, rect.w - 16))
            pygame.draw.line(surface, border, (x, rect.y + 9), (x, rect.bottom - 9), 2)
        draw_text(surface, label, 17 if rect.w > 200 else 13,
                  rect.center, (237, 250, 246), align="center", bold=True)

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
        self.audio.play("puzzle")
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
                if not self.cipher_digits:
                    # Clear the previous denial when a fresh code attempt begins;
                    # this lets every repeated wrong submission receive its own feedback.
                    self.stage_message = ""
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

    def _rejection_signature(self):
        """Read puzzle error text so newly rejected inputs receive one clear audio cue."""
        signature = {}
        keywords = (
            "DENIED", "REJECTED", "FAILURE", "WRONG", "ERROR", "TIMEOUT",
            "שגיאה", "שגוי", "לא מדויק", "לא ניתן", "תחילה פתרו", "חייב להגיע"
        )
        message = str(self.stage_message or "")
        signature["stage_message"] = message if any(
            word in message.upper() or word in message for word in keywords
        ) else ""
        sources = [
            ("roster", self, ("roster_error",)),
            ("stage4", self.stage_manager.stage4, ("error",)),
            ("stage7", self.stage_manager.stage7, ("error",)),
            ("later", self.stage_manager.later, ("error", "memory_error", "quantum_error")),
        ]
        task = self.stage_manager.stage5.current_task
        if task is not None:
            sources.append(("stage5_task", task, ("error", "feedback", "message")))
        for prefix, obj, attrs in sources:
            for attr in attrs:
                value = getattr(obj, attr, "")
                if isinstance(value, str):
                    signature[f"{prefix}.{attr}"] = value
        return signature

    def handle_game_event(self, event):
        if self.stage_manager.later.handle_lifeline(event, WIDTH, HEIGHT):
            return

        stage_before = self.stage_manager.stage
        errors_before = self._rejection_signature()
        if (event.type == pygame.KEYDOWN and getattr(event, "unicode", "")
                and event.unicode.isprintable() and not event.unicode.isspace()):
            self.audio.play("keypress")
        if stage_before == 2:
            self.handle_roster_event(event)
        elif stage_before == 3:
            self.handle_stage3_event(event)
        elif stage_before == 4:
            self.stage_manager.stage4.handle(event, pygame, WIDTH, HEIGHT)
        elif stage_before == 5:
            self.stage_manager.stage5.handle(event)
        elif stage_before == 6:
            self.stage_manager.stage6.handle(event, pygame, WIDTH, HEIGHT)
        elif stage_before == 7:
            self.stage_manager.stage7.handle(event, pygame, WIDTH, HEIGHT)
        elif 8 <= stage_before <= 12:
            self.stage_manager.later.handle(event, WIDTH, HEIGHT)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.running = False

        if self.stage_manager.stage == stage_before:
            errors_after = self._rejection_signature()
            if any(value and value != errors_before.get(key, "")
                   for key, value in errors_after.items()):
                self.audio.play("error")
                self.mistakes += 1

    def handle_window_event(self, event):
        """Handle OS-level window events before puzzle controllers see them."""
        if event.type == pygame.QUIT:
            self.running = False
            return True
        focus_lost = getattr(pygame, "WINDOWFOCUSLOST", None)
        if (focus_lost is not None and event.type == focus_lost
                and self.state == "game" and not self.paused):
            self.pause_game()
            return True
        return False

    def handle_secret_keys(self, event):
        """Consume global audio, pause, and operator shortcuts before stage input."""
        if event.type != pygame.KEYDOWN:
            return False
        mods = getattr(event, "mod", pygame.key.get_mods())

        # Emergency exit must take priority over the ordinary Escape-to-pause control.
        exit_pressed = (
            (mods & pygame.KMOD_CTRL)
            and (mods & pygame.KMOD_ALT)
            and (mods & pygame.KMOD_SHIFT)
            and event.key == pygame.K_ESCAPE
        )
        if exit_pressed:
            self.running = False
            return True

        if event.key == pygame.K_F8:
            enabled = self.audio.toggle()
            self.stage_message = "SOUND DESIGN ACTIVE" if enabled else "SOUND MUTED"
            return True
        if event.key == pygame.K_F7:
            enabled = self.audio.toggle_ambient()
            self.stage_message = "AMBIENT DRONE ENABLED" if enabled else "AMBIENT DRONE DISABLED"
            return True
        if event.key == pygame.K_F9:
            level = self.audio.adjust_volume(-0.08)
            self.stage_message = f"SOUND LEVEL // {int(level * 100)}%"
            return True
        if event.key == pygame.K_F10:
            level = self.audio.adjust_volume(0.08)
            self.stage_message = f"SOUND LEVEL // {int(level * 100)}%"
            return True

        if event.key == pygame.K_ESCAPE and self.state == "game":
            if self.paused:
                self.resume_game()
            else:
                self.pause_game()
            return True

        skip_pressed = (
            (mods & pygame.KMOD_CTRL)
            and (mods & pygame.KMOD_SHIFT)
            and event.key == pygame.K_RIGHT
        )
        if skip_pressed and self.state == "game" and not self.paused:
            if self.stage_manager.stage < 12:
                self.stage_manager.goto(self.stage_manager.stage + 1)
            return True
        return False

    def update(self, dt):
        if self.paused:
            return
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
            self.audio.update(self.remaining_seconds, self.stage_manager.stage)
            self.stage_manager.later.lifeline_update()

    def draw(self):
        if self.paused:
            if self.paused_frame is not None:
                screen.blit(self.paused_frame, (0, 0))
            else:
                screen.fill((1, 5, 8))
            self.draw_pause_overlay(screen)
            self.audio.draw_status(screen, draw_text, WIDTH, HEIGHT)
            pygame.display.flip()
            return
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

        self.audio.draw_status(screen, draw_text, WIDTH, HEIGHT)
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if self.handle_window_event(event):
                    if not self.running:
                        break
                    continue
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not self.paused:
                    self.audio.play("click")
                if self.handle_secret_keys(event):
                    if not self.running:
                        break
                    continue
                if self.state == "setup":
                    self.handle_setup_event(event)
                elif self.paused:
                    self.handle_pause_event(event)
                else:
                    self.handle_game_event(event)

            self.update(dt)
            self.draw()

        self.stage_manager.later._stop_mic()
        self.audio.stop()
        self.webcam.release()
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    EscapeRoomApp().run()
