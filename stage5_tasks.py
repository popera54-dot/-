from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass


@dataclass
class TaskResult:
    completed: bool = False
    failed: bool = False
    message: str = ""


class TaskBase:
    name = "UNKNOWN"

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.started = time.monotonic()
        self.done = False

    def reset(self):
        self.started = time.monotonic()
        self.done = False

    def update(self, dt):
        pass

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        raise NotImplementedError

    def handle(self, event, pygame, width, height):
        return TaskResult()

    def result(self):
        return TaskResult(completed=self.done)


def draw_hanukkah_symbol(surface, symbol, center, size, pygame):
    """Draw crisp vector symbols so Windows font/emoji support cannot break a puzzle."""
    x, y = int(center[0]), int(center[1])
    s = max(6, int(size))
    line = max(2, s // 7)
    palette = {
        "menorah": (84, 255, 209),
        "jug": (255, 195, 86),
        "flame": (255, 91, 108),
        "star": (109, 181, 255),
    }
    color = palette.get(symbol, (84, 255, 209))
    dark = (6, 23, 28)

    if symbol == "jug":
        body = pygame.Rect(x - int(s * .48), y - int(s * .30), int(s * .96), int(s * .72))
        pygame.draw.ellipse(surface, dark, body)
        pygame.draw.ellipse(surface, color, body, line)
        neck = pygame.Rect(x - int(s * .18), y - int(s * .62), int(s * .36), int(s * .34))
        pygame.draw.rect(surface, dark, neck, border_radius=max(2, s // 8))
        pygame.draw.rect(surface, color, neck, line, border_radius=max(2, s // 8))
        pygame.draw.arc(surface, color, (x - int(s * .74), y - int(s * .08), int(s * .54), int(s * .48)),
                        math.radians(270), math.radians(90), line)
    elif symbol == "flame":
        outer = [(x, y - s // 2), (x - s // 3, y + s // 8),
                 (x - s // 5, y + s // 2), (x + s // 4, y + s // 2),
                 (x + s // 3, y), (x + s // 8, y - s // 6)]
        pygame.draw.polygon(surface, color, outer)
        inner = [(x, y - s // 6), (x - s // 7, y + s // 5),
                 (x + s // 8, y + s // 3), (x + s // 5, y + s // 12)]
        pygame.draw.polygon(surface, (255, 226, 146), inner)
    elif symbol == "menorah":
        base_y = y + s // 3
        stem_top = y - s // 3
        pygame.draw.line(surface, color, (x, base_y), (x, stem_top), line)
        pygame.draw.line(surface, color, (x - s // 2, base_y), (x + s // 2, base_y), line)
        for offset in (-s // 2, -s // 4, 0, s // 4, s // 2):
            branch_top = y - (s // 4 if offset == 0 else s // 10)
            pygame.draw.line(surface, color, (x + offset, base_y), (x + offset, branch_top), line)
            pygame.draw.line(surface, (255, 194, 78),
                             (x + offset, branch_top), (x + offset, branch_top - max(3, s // 9)), line)
            pygame.draw.circle(surface, (255, 194, 78),
                               (x + offset, branch_top - max(3, s // 9)), max(2, line))
    elif symbol == "star":
        r = s // 2
        top = (x, y - r)
        left_upper = (x - r, y - r // 3)
        right_upper = (x + r, y - r // 3)
        left_lower = (x - r * 3 // 4, y + r)
        right_lower = (x + r * 3 // 4, y + r)
        pygame.draw.polygon(surface, dark, [top, right_lower, left_upper])
        pygame.draw.polygon(surface, dark, [top, left_lower, right_upper])
        pygame.draw.polygon(surface, color, [top, right_lower, left_upper], line)
        pygame.draw.polygon(surface, color, [top, left_lower, right_upper], line)
    else:
        pygame.draw.circle(surface, color, (x, y), max(3, s // 3), line)


class FirewallMazeTask(TaskBase):
    name = "Firewall Maze"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.grid = [
            "###########",
            "#S#     #E#",
            "# # ### # #",
            "#   #     #",
            "### # #####",
            "#   #     #",
            "# ### ### #",
            "#     #   #",
            "###########",
        ]
        self.player = [1, 1]

    def handle(self, event, pygame, width, height):
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN
        ):
            dx, dy = 0, 0
            if event.key == pygame.K_LEFT:
                dx = -1
            elif event.key == pygame.K_RIGHT:
                dx = 1
            elif event.key == pygame.K_UP:
                dy = -1
            elif event.key == pygame.K_DOWN:
                dy = 1
            nx, ny = self.player[0] + dx, self.player[1] + dy
            if self.grid[ny][nx] != "#":
                self.player = [nx, ny]
                if self.grid[ny][nx] == "E":
                    self.done = True
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        cell = min(58, int(min(width * .52, height * .58) / len(self.grid[0])))
        ox = width // 2 - (len(self.grid[0]) * cell) // 2
        oy = height // 2 - (len(self.grid) * cell) // 2 + 30
        draw_text(surface, "FIREWALL MAZE", 18, (width / 2, 80), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, "נווטו את החנוכייה דרך חומת האש בלי לגעת בקירות.", 18,
                  (width / 2, 115), (160, 184, 188), align="center")
        for y, row in enumerate(self.grid):
            for x, ch in enumerate(row):
                rr = pygame.Rect(ox + x * cell, oy + y * cell, cell - 3, cell - 3)
                if ch == "#":
                    pygame.draw.rect(surface, (15, 47, 48), rr, border_radius=8)
                    pygame.draw.rect(surface, (52, 194, 157), rr, 1, border_radius=8)
                else:
                    pygame.draw.rect(surface, (5, 15, 20), rr, border_radius=8)
                if ch == "E":
                    glow_circle(surface, rr.center, 18, (255, 193, 61), 16)
                    draw_text(surface, "יציאה", 9, rr.center, (255, 218, 130), align="center", mono=True)
        px, py = self.player
        cx = ox + px * cell + cell // 2
        cy = oy + py * cell + cell // 2
        glow_circle(surface, (cx, cy), 18, (65, 255, 206), 18)
        pygame.draw.circle(surface, (65, 255, 206), (cx, cy), 11, 2)
        # Menorah glyph
        pygame.draw.line(surface, (230, 190, 98), (cx, cy + 8), (cx, cy - 12), 3)
        pygame.draw.line(surface, (230, 190, 98), (cx - 12, cy - 2), (cx + 12, cy - 2), 3)


class OilCatchTask(TaskBase):
    name = "Oil Catch"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.catches = 0
        self.basket_x = 0.5
        self.items = []
        for i in range(7):
            self.items.append([
                self.rng.uniform(.16, .84),
                self.rng.uniform(-.8, -.05),
                self.rng.uniform(.16, .30),
            ])

    def update(self, dt):
        for item in self.items:
            item[1] += item[2] * dt * .35
            if item[1] > 1.05:
                item[0] = self.rng.uniform(.16, .84)
                item[1] = self.rng.uniform(-.6, -.05)
                item[2] = self.rng.uniform(.16, .30)

    def handle(self, event, pygame, width, height):
        if event.type == pygame.MOUSEMOTION:
            self.basket_x = max(.08, min(.92, event.pos[0] / width))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.basket_x = max(.08, min(.92, event.pos[0] / width))
        return self.result()

    def update_and_collide(self, dt, width, height):
        self.update(dt)
        basket_screen_y = .82
        # Falling-object state is drawn at screen_y = .18 + state_y * .65.
        # Convert the basket's screen location back into that state coordinate.
        catch_y = (basket_screen_y - .18) / .65
        for item in self.items:
            # Stop on the fifth catch so simultaneous overlaps never produce 6/5.
            if self.catches >= 5:
                break
            # Match the rendered basket width and its upper catch zone.
            if catch_y - .07 < item[1] < catch_y + .02 and abs(item[0] - self.basket_x) < .045:
                self.catches += 1
                item[1] = -0.1
                item[0] = self.rng.uniform(.15, .85)
                if self.catches == 5:
                    self.done = True
                    break

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "OIL CATCH", 18, (width / 2, 70), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, f"פכים שנאספו {self.catches}/5", 17, (width / 2, 108),
                  (255, 200, 96), align="center", mono=True, bold=True)
        area = pygame.Rect(width * .12, height * .16, width * .76, height * .68)
        pygame.draw.rect(surface, (4, 13, 18), area, border_radius=24)
        pygame.draw.rect(surface, (34, 82, 83), area, 1, border_radius=24)
        for item in self.items:
            x = int(width * item[0])
            y = int(height * (.18 + item[1] * .65))
            glow_circle(surface, (x, y), 20, (255, 194, 63), 11)
            pygame.draw.circle(surface, (178, 130, 52), (x, y), 14)
            pygame.draw.rect(surface, (230, 180, 76), (x - 9, y - 4, 18, 8), 2, border_radius=3)
        bx = int(width * self.basket_x)
        by = int(height * .82)
        pygame.draw.arc(surface, (90, 255, 214), (bx - 48, by - 34, 96, 62),
                        math.radians(0), math.radians(180), 5)
        pygame.draw.line(surface, (90, 255, 214), (bx - 42, by - 6), (bx + 42, by - 6), 4)


class SymbolMatrixTask(TaskBase):
    name = "Symbol Matrix"

    SYMBOLS = ["menorah", "jug", "flame"]

    def __init__(self, rng=None):
        super().__init__(rng)
        counts = sorted(
            ((self.rng.randint(7, 12), s) for s in self.SYMBOLS),
            key=lambda pair: pair[0],
        )
        # Guarantee one unique majority while keeping the puzzle random.
        base_count, _ = counts[-1]
        adjusted = {s: n for n, s in counts}
        top_symbol = counts[-1][1]
        adjusted[top_symbol] = min(17, base_count + 3)
        self.counts = adjusted
        self.target = top_symbol
        self.grid = [
            symbol
            for symbol, count in self.counts.items()
            for _ in range(count)
        ]
        self.rng.shuffle(self.grid)

    def handle(self, event, pygame, width, height):
        if event.type == pygame.KEYDOWN:
            mapping = {pygame.K_1: self.SYMBOLS[0], pygame.K_2: self.SYMBOLS[1], pygame.K_3: self.SYMBOLS[2]}
            if event.key in mapping:
                if mapping[event.key] == self.target:
                    self.done = True
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "SYMBOL MATRIX", 18, (width / 2, 70), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, "בחרו את הסמל שמופיע הכי הרבה פעמים.", 18,
                  (width / 2, 108), (160, 184, 188), align="center")
        cols = 6
        cell = 85
        ox = width / 2 - cols * cell / 2
        oy = 165
        for i, symbol in enumerate(self.grid):
            x = i % cols
            y = i // cols
            rr = pygame.Rect(ox + x * cell, oy + y * 72, cell - 10, 60)
            rounded_panel(surface, rr, (5, 16, 21), (34, 77, 78), 12, 1)
            draw_hanukkah_symbol(surface, symbol, rr.center, 31, pygame)
        for i, symbol in enumerate(self.SYMBOLS):
            rr = pygame.Rect(width / 2 - 210 + i * 150, height - 125, 130, 55)
            rounded_panel(surface, rr, (7, 18, 23), (70, 190, 165), 12, 2)
            draw_text(surface, str(i + 1), 17, (rr.x + 24, rr.centery),
                      (255, 194, 78), align="center", mono=True, bold=True)
            draw_hanukkah_symbol(surface, symbol, (rr.centerx + 20, rr.centery), 26, pygame)


class WordDecryptTask(TaskBase):
    name = "Word Decrypt"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.words = ["מכבים", "סביבון"]
        self.answer = self.rng.choice(self.words)
        self.scrambled = list(self.answer)
        self.rng.shuffle(self.scrambled)
        self.input_text = ""

    def handle(self, event, pygame, width, height):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            elif event.key == pygame.K_RETURN:
                if self.input_text.strip() == self.answer:
                    self.done = True
                else:
                    self.input_text = ""
            elif event.unicode and len(self.input_text) < 12 and event.unicode.isprintable():
                self.input_text += event.unicode
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "WORD DECRYPT", 18, (width / 2, 72), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, " ".join(self.scrambled), 38, (width / 2, 210),
                  (255, 197, 88), align="center", bold=True)
        draw_text(surface, "הקלד את המילה הנכונה ולחץ ENTER", 18, (width / 2, 275),
                  (185, 202, 205), align="center")
        rr = pygame.Rect(width / 2 - 250, 340, 500, 74)
        rounded_panel(surface, rr, (5, 14, 20), (57, 215, 181), 14, 2)
        draw_text(surface, self.input_text or "__________", 30, rr.center,
                  (230, 243, 244), align="center", mono=True)


class CyberMemoryTask(TaskBase):
    name = "Cyber Memory"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.values = ["jug", "jug", "flame", "flame", "menorah", "menorah", "star", "star"]
        self.rng.shuffle(self.values)
        self.revealed = [False] * 8
        self.matched = [False] * 8
        self.first = None
        self.second = None
        self.lock_until = 0

    def handle(self, event, pygame, width, height):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and time.monotonic() >= self.lock_until:
            ox = width / 2 - 320
            oy = 190
            cell_w, cell_h = 150, 130
            col = int((event.pos[0] - ox) / cell_w)
            row = int((event.pos[1] - oy) / cell_h)
            if 0 <= col < 4 and 0 <= row < 2:
                idx = row * 4 + col
                if not self.matched[idx] and not self.revealed[idx]:
                    self.revealed[idx] = True
                    if self.first is None:
                        self.first = idx
                    elif self.second is None and idx != self.first:
                        self.second = idx
                        if self.values[self.first] == self.values[self.second]:
                            self.matched[self.first] = self.matched[self.second] = True
                            self.revealed[self.first] = self.revealed[self.second] = True
                            self.first = self.second = None
                            if all(self.matched):
                                self.done = True
                        else:
                            self.lock_until = time.monotonic() + 0.65
        return self.result()

    def update(self, dt):
        if self.second is not None and time.monotonic() >= self.lock_until:
            self.revealed[self.first] = self.revealed[self.second] = False
            self.first = self.second = None

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "CYBER MEMORY", 18, (width / 2, 72), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, "מצאו את ארבעת זוגות הסמלים התואמים.", 17,
                  (width / 2, 108), (165, 190, 193), align="center")
        for i in range(8):
            x, y = i % 4, i // 4
            rr = pygame.Rect(width / 2 - 320 + x * 160, 185 + y * 145, 145, 125)
            matched = self.matched[i]
            rounded_panel(surface, rr, (13, 29, 32) if matched else (4, 14, 20),
                          (255, 195, 88) if matched else (46, 88, 91), 16, 2)
            if self.revealed[i] or matched:
                draw_hanukkah_symbol(surface, self.values[i], rr.center, 48, pygame)
            else:
                draw_text(surface, "?", 38, rr.center, (77, 255, 210), align="center", mono=True, bold=True)


class ColorCodeTask(TaskBase):
    name = "Color Code Hack"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.colors = [
            ("אדום", (232, 54, 72)),
            ("כחול", (60, 137, 255)),
            ("צהוב", (255, 197, 62)),
        ]
        self.order = [1, 2, 0]  # כחול -> צהוב -> אדום, מהקר לחם
        self.cursor = 0

    def handle(self, event, pygame, width, height):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(3):
                rr = pygame.Rect(width / 2 - 250 + i * 175, height * .62, 145, 90)
                if rr.collidepoint(event.pos):
                    if i == self.order[self.cursor]:
                        self.cursor += 1
                        if self.cursor == 3:
                            self.done = True
                    else:
                        self.cursor = 0
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "COLOR CODE HACK", 18, (width / 2, 72), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, "הפעילו את הצבעים מהקר ביותר אל החם ביותר.", 18,
                  (width / 2, 110), (190, 204, 206), align="center")
        for i, (label, col) in enumerate(self.colors):
            rr = pygame.Rect(width / 2 - 250 + i * 175, height * .62, 145, 90)
            pygame.draw.rect(surface, (8, 19, 23), rr, border_radius=18)
            pygame.draw.circle(surface, col, rr.center, 28)
            draw_text(surface, label, 13, (rr.centerx, rr.bottom - 16),
                      (229, 238, 240), align="center", mono=True, bold=True)


class TriviaTask(TaskBase):
    name = "Cyber Trivia"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.question = "כמה ימים נמשך נס פך השמן לפי המסורת?"
        self.options = ["3", "7", "8", "12"]
        self.answer = 2
        self.deadline = time.monotonic() + 30

    def handle(self, event, pygame, width, height):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(4):
                rr = pygame.Rect(width / 2 - 330 + (i % 2) * 340,
                                 410 + (i // 2) * 100, 300, 70)
                if rr.collidepoint(event.pos):
                    if i == self.answer:
                        self.done = True
                    else:
                        self.deadline = time.monotonic() + 30
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        left = max(0, int(self.deadline - time.monotonic()))
        draw_text(surface, "CYBER TRIVIA", 18, (width / 2, 72), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, f"{left:02d}s", 28, (width / 2, 120),
                  (255, 78, 96) if left < 8 else (255, 205, 102),
                  align="center", mono=True, bold=True)
        draw_text(surface, self.question, 25, (width / 2, 220),
                  (239, 245, 247), align="center", bold=True)
        for i, option in enumerate(self.options):
            rr = pygame.Rect(width / 2 - 330 + (i % 2) * 340,
                             410 + (i // 2) * 100, 300, 70)
            rounded_panel(surface, rr, (6, 17, 23), (49, 94, 98), 14, 2)
            draw_text(surface, option, 22, rr.center, (230, 241, 243), align="center", bold=True)


class DreidelSaysTask(TaskBase):
    name = "Dreidel Says"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.sequence = [self.rng.randrange(4) for _ in range(4)]
        self.input_index = 0
        self.preview_until = time.monotonic() + 2.3
        self.flash_index = -1

    def update(self, dt):
        now = time.monotonic()
        if now < self.preview_until:
            elapsed = 2.3 - (self.preview_until - now)
            idx = int(elapsed / .52)
            self.flash_index = self.sequence[idx] if 0 <= idx < len(self.sequence) else -1
        else:
            self.flash_index = -1

    def handle(self, event, pygame, width, height):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and time.monotonic() >= self.preview_until:
            for i in range(4):
                rr = pygame.Rect(width / 2 - 270 + i * 145, 360, 115, 115)
                if rr.collidepoint(event.pos):
                    if i == self.sequence[self.input_index]:
                        self.input_index += 1
                        if self.input_index == len(self.sequence):
                            self.done = True
                    else:
                        self.input_index = 0
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "DREIDEL SAYS", 18, (width / 2, 72), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, "חזרו על הרצף באותו הסדר.", 18, (width / 2, 108),
                  (177, 195, 198), align="center")
        for i in range(4):
            rr = pygame.Rect(width / 2 - 270 + i * 145, 360, 115, 115)
            active = i == self.flash_index
            accent = (255, 200, 78) if active else (42, 88, 92)
            rounded_panel(surface, rr, (7, 19, 23), accent, 18, 3 if active else 1)
            cx = rr.centerx
            base_y = rr.bottom - 26
            candle_color = (255, 221, 132) if active else (77, 218, 185)
            pygame.draw.line(surface, candle_color, (cx, base_y), (cx, rr.y + 48), 4)
            pygame.draw.line(surface, candle_color, (cx - 16, base_y), (cx + 16, base_y), 4)
            flame = (cx, rr.y + 36)
            flame_color = (255, 202, 86) if active else (57, 149, 135)
            pygame.draw.polygon(surface, flame_color,
                                [(flame[0], flame[1] - 10),
                                 (flame[0] - 7, flame[1] + 2),
                                 (flame[0] + 7, flame[1] + 2)])
            draw_text(surface, str(i + 1), 14, (rr.centerx, rr.bottom - 10),
                      (228, 240, 242), align="midbottom", mono=True, bold=True)


class WireCutTask(TaskBase):
    name = "Wire Cut"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.colors = ["אדום", "כחול", "צהוב", "ירוק"]
        self.correct = 3

    def handle(self, event, pygame, width, height):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(4):
                rr = pygame.Rect(width / 2 - 300 + i * 160, 400, 125, 180)
                if rr.collidepoint(event.pos):
                    if i == self.correct:
                        self.done = True
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "WIRE CUT", 18, (width / 2, 72), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, "אל תחתכו את הכבל האדום. הכבל הנכון נמצא מימין לצהוב.",
                  18, (width / 2, 120), (191, 204, 207), align="center")
        cols = [(238, 62, 74), (62, 139, 255), (253, 198, 58), (62, 221, 152)]
        for i, label in enumerate(self.colors):
            rr = pygame.Rect(width / 2 - 300 + i * 160, 400, 125, 180)
            rounded_panel(surface, rr, (5, 15, 20), (53, 85, 89), 18, 2)
            pygame.draw.line(surface, cols[i], (rr.centerx, rr.y + 30),
                             (rr.centerx, rr.bottom - 25), 12)
            draw_text(surface, label, 13, (rr.centerx, rr.bottom - 12),
                      (230, 239, 241), align="midbottom", mono=True)


class MissingLetterTask(TaskBase):
    name = "Missing Letter"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.letters = ["נ", "ג", "ה", "פ"]
        self.current = self.rng.choice(self.letters)
        self.next_swap = time.monotonic() + self.rng.uniform(.8, 1.5)
        self.flash_until = 0

    def update(self, dt):
        if time.monotonic() >= self.next_swap:
            self.current = self.rng.choice(self.letters)
            self.next_swap = time.monotonic() + self.rng.uniform(.8, 1.5)
            self.flash_until = time.monotonic() + .16

    def handle(self, event, pygame, width, height):
        if (event.type == pygame.KEYDOWN
                and time.monotonic() < self.flash_until
                and event.unicode == self.current):
            self.done = True
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "THE MISSING LETTER", 18, (width / 2, 72),
                  (80, 255, 210), align="center", mono=True, bold=True)
        draw_text(surface, "התבוננו בסביבון. הקלידו את האות ברגע שהיא מופיעה.",
                  18, (width / 2, 112), (181, 197, 200), align="center")
        cx, cy = width / 2, height / 2 + 15
        angle = t * 4.8
        pts = []
        for i in range(4):
            a = angle + i * math.tau / 4
            pts.append((cx + math.cos(a) * 170, cy + math.sin(a) * 170 * .65))
        pygame.draw.polygon(surface, (15, 40, 43), pts)
        pygame.draw.polygon(surface, (61, 200, 164), pts, 3)
        if time.monotonic() < self.flash_until:
            glow_circle(surface, (cx, cy), 110, (255, 201, 79), 18)
            draw_text(surface, self.current, 78, (cx, cy), (255, 222, 142), align="center", bold=True)
        else:
            draw_text(surface, "?", 72, (cx, cy), (87, 230, 192), align="center", mono=True, bold=True)


TASK_TYPES = [
    FirewallMazeTask,
    OilCatchTask,
    SymbolMatrixTask,
    WordDecryptTask,
    CyberMemoryTask,
    ColorCodeTask,
    TriviaTask,
    DreidelSaysTask,
    WireCutTask,
    MissingLetterTask,
]


def create_task_pool(count, seed=None):
    rng = random.Random(seed)
    classes = list(TASK_TYPES)
    rng.shuffle(classes)
    return [cls(random.Random(rng.randrange(10**9))) for cls in classes[:count]]
