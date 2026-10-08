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
        draw_text(surface, "Navigate the menorah through the firewall.", 18,
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
                    draw_text(surface, "EXIT", 9, rr.center, (255, 218, 130), align="center", mono=True)
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
        basket_y = .82
        for item in self.items:
            if basket_y - .08 < item[1] < basket_y + .04 and abs(item[0] - self.basket_x) < .09:
                self.catches += 1
                item[1] = -0.1
                item[0] = self.rng.uniform(.15, .85)
                if self.catches >= 5:
                    self.done = True

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "OIL CATCH", 18, (width / 2, 70), (80, 255, 210),
                  align="center", mono=True, bold=True)
        draw_text(surface, f"CATCHED {self.catches}/5", 17, (width / 2, 108),
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

    SYMBOLS = ["🕎", "🫙", "🔥"]

    def __init__(self, rng=None):
        super().__init__(rng)
        self.counts = {s: self.rng.randint(7, 15) for s in self.SYMBOLS}
        self.target = max(self.counts, key=self.counts.get)
        self.grid = [self.rng.choice(self.SYMBOLS) for _ in range(30)]

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
        draw_text(surface, "Choose the symbol appearing most often.", 18,
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
            draw_text(surface, symbol, 26, rr.center, (229, 240, 241), align="center")
        for i, symbol in enumerate(self.SYMBOLS):
            rr = pygame.Rect(width / 2 - 210 + i * 150, height - 125, 130, 55)
            rounded_panel(surface, rr, (7, 18, 23), (70, 190, 165), 12, 2)
            draw_text(surface, f"{i+1}  {symbol}", 18, rr.center, (235, 247, 246), align="center")


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
        self.values = ["🫙", "🫙", "🔥", "🔥", "🕎", "🕎", "✡", "✡"]
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
        for i in range(8):
            x, y = i % 4, i // 4
            rr = pygame.Rect(width / 2 - 320 + x * 160, 185 + y * 145, 145, 125)
            matched = self.matched[i]
            rounded_panel(surface, rr, (13, 29, 32) if matched else (4, 14, 20),
                          (255, 195, 88) if matched else (46, 88, 91), 16, 2)
            if self.revealed[i] or matched:
                draw_text(surface, self.values[i], 38, rr.center, (238, 244, 245), align="center")
            else:
                draw_text(surface, "?", 38, rr.center, (77, 255, 210), align="center", mono=True, bold=True)


class ColorCodeTask(TaskBase):
    name = "Color Code Hack"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.colors = [
            ("RED", (232, 54, 72)),
            ("BLUE", (60, 137, 255)),
            ("YELLOW", (255, 197, 62)),
        ]
        self.order = [2, 1, 0]  # coldest -> hottest for this fixed challenge
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
        draw_text(surface, "Activate from the coldest color to the hottest.", 18,
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
        draw_text(surface, "Repeat the sequence.", 18, (width / 2, 108),
                  (177, 195, 198), align="center")
        for i in range(4):
            rr = pygame.Rect(width / 2 - 270 + i * 145, 360, 115, 115)
            accent = (255, 200, 78) if i == self.flash_index else (42, 88, 92)
            rounded_panel(surface, rr, (7, 19, 23), accent, 18, 3 if i == self.flash_index else 1)
            draw_text(surface, str(i + 1), 32, rr.center, (228, 240, 242), align="center", mono=True, bold=True)


class WireCutTask(TaskBase):
    name = "Wire Cut"

    def __init__(self, rng=None):
        super().__init__(rng)
        self.colors = ["RED", "BLUE", "YELLOW", "GREEN"]
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
        draw_text(surface, "Do not cut red. The correct cable is right of yellow.",
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
        if event.type == pygame.KEYDOWN and event.unicode == self.current:
            self.done = True
        return self.result()

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        draw_text(surface, "THE MISSING LETTER", 18, (width / 2, 72),
                  (80, 255, 210), align="center", mono=True, bold=True)
        draw_text(surface, "Watch the spinning dreidel. Type the letter when it appears.",
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
