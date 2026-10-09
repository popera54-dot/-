
from __future__ import annotations

import math
import random
from collections import deque


class Stage4Controller:
    """Visual maze + physical-piece board for Stage 4."""

    ICONS = ("dreidel", "jug", "menorah", "candle", "star", "coin", "flame", "oil_drop")
    TARGETS = ("dreidel", "jug", "menorah")
    EXIT_NUMBERS = (7, 11, 18, 23, 31, 42, 55, 64, 72, 88)

    def __init__(self, app):
        self.app = app
        self.phase = "solve"
        self.location_scroll = 0
        self.maze = []
        self.path = []
        self.target_cells = {}
        self.exits = []
        self.started_at = 0.0
        self.maze_cols = 31
        self.maze_rows = 19
        self.start_cell = (1, 1)
        self.finish_cell = None
        self.maze_rect = None
        self.complete_button = None
        self.route_answer = ""
        self.route_verified = False
        self.puzzle_confirmed = False
        self.route_input_active = False
        self.route_input_rect = None
        self.route_verify_button = None
        self.error = ""
        self._generation_attempt = 0
        self.generate_puzzle()

    def start(self):
        self.phase = "solve"
        self.location_scroll = 0
        self.started_at = self.app.background.time
        self.route_answer = ""
        self.route_verified = False
        self.puzzle_confirmed = False
        self.route_input_active = False
        self.error = ""
        self.generate_puzzle()

    def update(self, dt):
        self.started_at = self.app.background.time

    def generate_puzzle(self):
        cols, rows = self.maze_cols, self.maze_rows
        self.maze = [[1 for _ in range(cols)] for _ in range(rows)]
        start = self.start_cell
        self.maze[start[1]][start[0]] = 0

        stack = [start]
        while stack:
            x, y = stack[-1]
            candidates = []
            for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
                nx, ny = x + dx, y + dy
                if 1 <= nx < cols - 1 and 1 <= ny < rows - 1 and self.maze[ny][nx] == 1:
                    candidates.append((nx, ny))
            if not candidates:
                stack.pop()
                continue
            nx, ny = random.choice(candidates)
            self.maze[(y + ny) // 2][(x + nx) // 2] = 0
            self.maze[ny][nx] = 0
            stack.append((nx, ny))

        dist = {start: 0}
        parent = {}
        q = deque([start])
        while q:
            cell = q.popleft()
            x, y = cell
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (x + dx, y + dy)
                if not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                    continue
                if self.maze[nxt[1]][nxt[0]] != 0 or nxt in dist:
                    continue
                dist[nxt] = dist[cell] + 1
                parent[nxt] = cell
                q.append(nxt)

        leaves = []
        for (x, y), d in dist.items():
            degree = sum(
                0 <= x + dx < cols and 0 <= y + dy < rows
                and self.maze[y + dy][x + dx] == 0
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
            if degree == 1 and (x, y) != start:
                leaves.append((d, (x, y)))

        leaves.sort(reverse=True)
        self.finish_cell = leaves[0][1] if leaves else max(dist, key=dist.get)

        path = [self.finish_cell]
        while path[-1] != start:
            path.append(parent[path[-1]])
        self.path = list(reversed(path))

        picks = []
        for ratio in (0.24, 0.52, 0.78):
            idx = max(2, min(len(self.path) - 3, int(len(self.path) * ratio)))
            while idx in picks:
                idx += 1
                if idx >= len(self.path) - 2:
                    idx = 2
            picks.append(idx)
        self.target_cells = {
            item: self.path[idx] for item, idx in zip(self.TARGETS, picks)
        }

        rng = random.Random(random.randint(1, 2_000_000_000))
        floors = list(dist.keys())
        blocked = set(self.target_cells.values()) | {start, self.finish_cell}
        decoy_types = ("candle", "star", "coin", "flame", "oil_drop")
        rng.shuffle(floors)
        self.decoy_items = {}
        for cell in floors:
            if cell in blocked or cell in self.decoy_items:
                continue
            if rng.random() < 0.20:
                self.decoy_items[cell] = rng.choice(decoy_types)
            if len(self.decoy_items) >= 22:
                break

        # Only the 15 exit may have a route that passes through all three target symbols.
        target_cells = set(self.target_cells.values())
        safe_other_leaves = []
        for _, candidate in leaves:
            if candidate == self.finish_cell:
                continue
            candidate_path = [candidate]
            while candidate_path[-1] != start:
                candidate_path.append(parent[candidate_path[-1]])
            if not target_cells.issubset(set(candidate_path)):
                safe_other_leaves.append(candidate)
            if len(safe_other_leaves) >= 9:
                break

        # Keep the maze visually rich with 10 exits while ensuring no decoy
        # exit's path contains all three required symbols. Some random perfect
        # mazes place too many dead ends after the third symbol, so regenerate
        # rather than shipping a map with too few choices.
        if len(safe_other_leaves) < 9 and self._generation_attempt < 30:
            self._generation_attempt += 1
            self.generate_puzzle()
            return

        self._generation_attempt = 0
        self.exits = [(self.finish_cell, 15)]
        for cell, number in zip(safe_other_leaves[:9], self.EXIT_NUMBERS):
            self.exits.append((cell, number))

    def _draw_icon(self, surface, name, center, scale, pygame):
        x, y = center
        s = max(4, int(scale))
        line = (74, 255, 208)
        glow = (38, 210, 176)

        if name == "dreidel":
            points = [(x, y - s), (x + s, y), (x, y + s), (x - s, y)]
            pygame.draw.polygon(surface, (10, 34, 38), points)
            pygame.draw.polygon(surface, line, points, 2)
            pygame.draw.line(surface, line, (x, y - s), (x, y - int(s * 1.6)), 2)
        elif name == "jug":
            body = pygame.Rect(x - s, y - int(s * .45), 2 * s, int(s * 1.25))
            pygame.draw.ellipse(surface, (10, 31, 35), body)
            pygame.draw.ellipse(surface, line, body, 2)
            neck = pygame.Rect(x - int(s * .32), y - s, int(s * .64), int(s * .45))
            pygame.draw.rect(surface, line, neck, 2, border_radius=3)
        elif name == "menorah":
            pygame.draw.line(surface, line, (x, y + s), (x, y - s), 2)
            pygame.draw.line(surface, line, (x - s, y + s), (x + s, y + s), 2)
            for dx in (-s, -s // 2, 0, s // 2, s):
                top = y - int(s * .55) if dx == 0 else y - int(s * .15)
                pygame.draw.line(surface, line, (x + dx, y + s), (x + dx, top), 2)
                pygame.draw.circle(surface, glow, (x + dx, top - 3), max(2, s // 4))
        elif name == "candle":
            pygame.draw.rect(surface, (12, 34, 38), (x - s // 3, y - s, 2 * s // 3, 2 * s))
            pygame.draw.rect(surface, line, (x - s // 3, y - s, 2 * s // 3, 2 * s), 2)
            pygame.draw.circle(surface, (255, 194, 78), (x, y - s - 4), max(3, s // 3))
        elif name == "star":
            pts = []
            for i in range(10):
                a = -math.pi / 2 + i * math.pi / 5
                r = s if i % 2 == 0 else s * .42
                pts.append((x + math.cos(a) * r, y + math.sin(a) * r))
            pygame.draw.polygon(surface, (10, 34, 38), pts)
            pygame.draw.polygon(surface, line, pts, 2)
        elif name == "coin":
            pygame.draw.circle(surface, (10, 34, 38), (x, y), s)
            pygame.draw.circle(surface, line, (x, y), s, 2)
            pygame.draw.circle(surface, glow, (x, y), max(2, int(s * .45)), 1)
        elif name == "flame":
            pygame.draw.polygon(surface, (255, 194, 78),
                                [(x, y + s), (x - s // 2, y), (x, y - s), (x + s // 2, y)])
        else:
            pygame.draw.circle(surface, (255, 194, 78), (x, y), s)
            pygame.draw.circle(surface, line, (x, y), s, 2)

    def _draw_maze(self, surface, panel, pygame, t, draw_text):
        inner = panel.inflate(-34, -105)
        self.maze_rect = inner
        cell_w = inner.w / self.maze_cols
        cell_h = inner.h / self.maze_rows

        pygame.draw.rect(surface, (2, 9, 13), inner, border_radius=16)
        for y in range(self.maze_rows):
            for x in range(self.maze_cols):
                r = pygame.Rect(
                    inner.x + int(x * cell_w),
                    inner.y + int(y * cell_h),
                    max(2, int(cell_w + 1)),
                    max(2, int(cell_h + 1)),
                )
                pygame.draw.rect(surface, (32, 106, 95) if self.maze[y][x] else (7, 22, 27), r)

        def center(cell):
            x, y = cell
            return (
                int(inner.x + (x + .5) * cell_w),
                int(inner.y + (y + .5) * cell_h),
            )

        sx, sy = center(self.start_cell)
        pygame.draw.circle(surface, (50, 255, 204), (sx, sy),
                           max(6, int(min(cell_w, cell_h) * .34)), 2)
        draw_text(surface, "START", 9, (sx, sy - int(cell_h * .8)),
                  (57, 255, 204), align="center", mono=True, bold=True)

        for cell, icon in self.decoy_items.items():
            self._draw_icon(surface, icon, center(cell), min(cell_w, cell_h) * .25, pygame)

        for item, cell in self.target_cells.items():
            p = center(cell)
            pulse = .55 + .45 * math.sin(t * 4.0 + p[0] * .01)
            rr = max(7, int(min(cell_w, cell_h) * (.34 + pulse * .07)))
            pygame.draw.circle(surface, (255, 194, 78), p, rr + 4, 1)
            self._draw_icon(surface, item, p, min(cell_w, cell_h) * .30, pygame)

        for cell, number in self.exits:
            p = center(cell)
            is_main = number == 15
            c = (255, 66, 84) if is_main else (98, 165, 159)
            pygame.draw.circle(surface, (8, 27, 32), p,
                               max(7, int(min(cell_w, cell_h) * .36)))
            pygame.draw.circle(surface, c, p,
                               max(7, int(min(cell_w, cell_h) * .36)), 1)
            if is_main:
                pygame.draw.circle(surface, c, p,
                                   max(4, int(min(cell_w, cell_h) * .22)))
            draw_text(surface, str(number), max(10, int(min(cell_w, cell_h) * .45)),
                      p, (245, 248, 249) if is_main else c,
                      align="center", mono=True, bold=True)

        scan = (math.sin(t * .55) + 1.0) * .5
        scan_x = inner.left + int(inner.w * scan)
        pygame.draw.line(surface, (52, 221, 177),
                         (scan_x, inner.top), (scan_x, inner.bottom), 2)

    def _configured_locations(self):
        """Return non-empty location labels with their original physical-piece numbers."""
        return [
            (index + 1, value.strip())
            for index, value in enumerate(self.app.setup_puzzle_locations)
            if value.strip()
        ]

    def _draw_location_board(self, surface, panel, pygame, draw_text, rounded_panel):
        rounded_panel(surface, panel, (4, 13, 19, 245), (43, 100, 100), 24, 2)
        draw_text(surface, "PHYSICAL PUZZLE // PIECES", 13,
                  (panel.centerx, panel.y + 24), (72, 255, 209),
                  align="center", mono=True, bold=True)
        draw_text(surface, "מצא את כל החלקים  •  הרכב את הפאזל  •  48", 18,
                  (panel.centerx, panel.y + 54), (235, 243, 245),
                  align="center", bold=True)

        blueprint = pygame.Rect(panel.centerx - 90, panel.y + 84, 180, 70)
        rounded_panel(surface, blueprint, (3, 20, 24), (255, 194, 78), 16, 1)
        draw_text(surface, "48", 44, blueprint.center,
                  (255, 218, 120), align="center", mono=True, bold=True)

        locs = self._configured_locations()
        draw_text(surface, f"{len(locs):02d} PIECES CONFIGURED", 10,
                  (panel.x + 20, panel.y + 168), (118, 149, 153), mono=True)

        self.route_input_rect = pygame.Rect(panel.x + 18, panel.y + 181, 142, 40)
        rounded_panel(surface, self.route_input_rect, (2, 13, 18),
                      (255, 194, 78) if self.route_input_active else (45, 91, 90), 10, 2)
        draw_text(surface, self.route_answer or "__", 22, self.route_input_rect.center,
                  (255, 218, 120), align="center", mono=True, bold=True)

        self.route_verify_button = pygame.Rect(self.route_input_rect.right + 10,
                                                self.route_input_rect.y,
                                                min(170, panel.w - 210), 40)
        rounded_panel(surface, self.route_verify_button,
                      (8, 27, 30), (67, 255, 205) if self.route_verified else (63, 124, 116), 10, 2)
        draw_text(surface, "יציאה 15 ✓" if self.route_verified else "בדיקת יציאה",
                  13, self.route_verify_button.center,
                  (93, 255, 209) if self.route_verified else (226, 238, 238),
                  align="center", bold=True)
        if self.error:
            draw_text(surface, self.error, 11,
                      (panel.x + 18, panel.y + 225), (255, 75, 91), bold=True)

        list_top = panel.y + 245
        row_h = 38
        visible = max(1, int((panel.bottom - 28 - list_top) / row_h))
        self.location_scroll = max(0, min(max(0, len(locs) - visible), self.location_scroll))

        if not locs:
            draw_text(surface, "אין מיקומים מוגדרים בלוח הבקרה", 16,
                      (panel.centerx, list_top + 35), (255, 76, 91),
                      align="center", bold=True)
            return

        for row in range(visible):
            idx = row + self.location_scroll
            if idx >= len(locs):
                break
            y = list_top + row * row_h
            rr = pygame.Rect(panel.x + 16, y, panel.w - 32, row_h - 6)
            rounded_panel(surface, rr, (5, 22, 27), (30, 71, 75), 9, 1)
            piece_number, value = locs[idx]
            draw_text(surface, f"חלק {piece_number:02d}", 11,
                      (rr.x + 10, rr.centery), (255, 194, 78),
                      align="midleft", mono=True, bold=True)
            preview = value if len(value) <= 52 else value[:49] + "..."
            draw_text(surface, preview, 13, (rr.x + 95, rr.centery),
                      (226, 235, 237), align="midleft")

        if len(locs) > visible:
            draw_text(surface, "גלגלת העכבר = גלילה", 9,
                      (panel.centerx, panel.bottom - 10),
                      (92, 128, 133), align="midbottom", mono=True)

    def draw(self, surface, draw_text, rounded_panel, glow_circle, pygame, width, height, t):
        self.app.background.draw(surface)
        self.app.stage_manager.draw_stage_chip(surface)

        draw_text(surface, "STAGE 04 // VISUAL TRACE + PHYSICAL SEARCH", 14,
                  (width / 2, 76), (255, 60, 80), align="center", mono=True, bold=True)
        draw_text(surface, "מבוך חנוכה + פאזל 48", 42,
                  (width / 2, 117), (241, 248, 250), align="center", bold=True)
        draw_text(surface, "מצאו בעיניים את המסלול היחיד שעובר דרך 3 הפריטים למעלה ומגיע ליציאה 15",
                  16, (width / 2, 153), (147, 170, 175), align="center")

        left_x = 30
        left_w = int(width * .48)
        right_x = int(width * .51)
        right_w = int(width * .47)

        target_panel = pygame.Rect(left_x, 174, left_w, 84)
        rounded_panel(surface, target_panel, (4, 13, 18, 245), (60, 100, 98), 20, 1)
        slot_w = target_panel.w / 3
        labels = ("סביבון", "כד שמן", "חנוכייה")
        for i, (item, label) in enumerate(zip(self.TARGETS, labels)):
            slot = pygame.Rect(target_panel.x + int(i * slot_w), target_panel.y + 6,
                               int(slot_w - 6), target_panel.h - 12)
            rounded_panel(surface, slot, (5, 21, 25), (31, 63, 67), 14, 1)
            self._draw_icon(surface, item, (int(slot.x + 34), slot.centery), 12, pygame)
            draw_text(surface, label.upper(), 12, (slot.x + 58, slot.centery - 5),
                      (247, 249, 249), align="midleft", bold=True)
            draw_text(surface, f"TARGET // 0{i + 1}", 9, (slot.x + 58, slot.centery + 12),
                      (91, 255, 210), align="midleft", mono=True)

        maze_panel = pygame.Rect(left_x, 272, left_w, height - 334)
        rounded_panel(surface, maze_panel, (3, 11, 15, 245), (43, 100, 100), 22, 2)
        self._draw_maze(surface, maze_panel, pygame, t, draw_text)

        right_panel = pygame.Rect(right_x, 174, right_w, height - 236)
        self._draw_location_board(surface, right_panel, pygame, draw_text, rounded_panel)

        self.complete_button = pygame.Rect(right_x, height - 52, right_w, 40)
        hovered = self.complete_button.collidepoint(pygame.mouse.get_pos())
        if not self.route_verified:
            button_label = "פתרו את המבוך והקלידו 15"
            button_color = (75, 112, 112)
        elif not self.puzzle_confirmed:
            button_label = "אשרו שהפאזל הפיזי 48 הורכב"
            button_color = (255, 194, 78)
        else:
            button_label = "החידה הושלמה // ממשיכים"
            button_color = (65, 255, 195)
        rounded_panel(surface, self.complete_button,
                      (14, 27, 31) if not hovered else (16, 40, 43),
                      button_color, 12, 2)
        draw_text(surface, button_label, 14, self.complete_button.center,
                  (255, 223, 133), align="center", bold=True)

        draw_text(surface, "EYES ONLY  •  המסלול אינו מסומן  •  הפתרון מתבצע בחדר",
                  10, (right_x, height - 12),
                  (89, 120, 125), mono=True)

    def _verify_route_answer(self):
        if self.route_answer == "15":
            self.route_verified = True
            self.error = ""
        else:
            self.route_verified = False
            self.error = "המסלול הנכון חייב להגיע ליציאה 15."
            self.route_answer = ""

    def handle(self, event, pygame, width, height):
        if event.type == pygame.KEYDOWN and self.route_input_active:
            if event.key == pygame.K_BACKSPACE:
                self.route_answer = self.route_answer[:-1]
            elif event.key == pygame.K_RETURN:
                self._verify_route_answer()
                self.route_input_active = False
            elif event.unicode.isdigit() and len(self.route_answer) < 2:
                self.route_answer += event.unicode
            return

        if event.type == pygame.MOUSEWHEEL:
            right_panel = pygame.Rect(int(width * .51), 174, int(width * .47), height - 236)
            if right_panel.collidepoint(pygame.mouse.get_pos()):
                locs = [x.strip() for x in self.app.setup_puzzle_locations if x.strip()]
                visible = max(1, int((right_panel.bottom - 28 - (right_panel.y + 245)) / 38))
                self.location_scroll = max(0, min(max(0, len(locs) - visible),
                                                  self.location_scroll - event.y))
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.route_input_rect and self.route_input_rect.collidepoint(event.pos):
                self.route_input_active = True
                return
            if self.route_verify_button and self.route_verify_button.collidepoint(event.pos):
                self._verify_route_answer()
                self.route_input_active = False
                return
            if self.complete_button and self.complete_button.collidepoint(event.pos):
                if not self.route_verified:
                    self.error = "תחילה פתרו את המסלול והקלידו 15."
                    return
                if not self.puzzle_confirmed:
                    self.puzzle_confirmed = True
                    self.error = ""
                    return
                self.phase = "complete"
                self.app.stage_message = "STAGE 04 CLEARED  //  15 + 48 CONFIRMED"
                self.app.stage_manager.goto(5)
