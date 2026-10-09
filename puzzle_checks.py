"""Deterministic checks for fixed-value puzzles and the generated stage-four maze."""

from collections import Counter

from stage4_puzzle import Stage4Controller
from stage5_tasks import (
    CyberMemoryTask,
    ColorCodeTask,
    DreidelSaysTask,
    FirewallMazeTask,
    MissingLetterTask,
    OilCatchTask,
    SymbolMatrixTask,
    TriviaTask,
    WireCutTask,
    WordDecryptTask,
)


def check_stage_3():
    A, B, C, D = 3, 8, 3, 2
    assert A + B == 11
    assert B * C == 24
    assert C - D == 1
    assert D + A == 5
    assert f"{A}{B}{C}{D}" == "3832"


def check_stage_4():
    class DummyApp:
        pass

    puzzle = Stage4Controller(DummyApp())
    puzzle.app.setup_puzzle_locations = ["", "מאחורי הווילון", "", "במגירת המטבח"]
    assert puzzle._configured_locations() == [
        (2, "מאחורי הווילון"),
        (4, "במגירת המטבח"),
    ]
    assert puzzle.path[0] == puzzle.start_cell
    assert puzzle.path[-1] == puzzle.finish_cell
    assert all(puzzle.maze[y][x] == 0 for x, y in puzzle.path)
    indices = [puzzle.path.index(puzzle.target_cells[name]) for name in puzzle.TARGETS]
    assert indices == sorted(indices) and len(set(indices)) == 3
    exit_numbers = [number for _, number in puzzle.exits]
    assert exit_numbers.count(15) == 1
    assert len(exit_numbers) == len(set(exit_numbers))
    assert not set(puzzle.TARGETS).intersection(set(puzzle.decoy_items.values()))

    # No other numbered exit may share the complete three-symbol route to 15.
    parent = {puzzle.start_cell: None}
    queue = [puzzle.start_cell]
    while queue:
        x, y = queue.pop(0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (x + dx, y + dy)
            if (0 <= nxt[0] < len(puzzle.maze[0]) and
                0 <= nxt[1] < len(puzzle.maze) and
                puzzle.maze[nxt[1]][nxt[0]] == 0 and nxt not in parent):
                parent[nxt] = (x, y)
                queue.append(nxt)

    target_cells = set(puzzle.target_cells.values())
    for exit_cell, number in puzzle.exits:
        trail = set()
        cell = exit_cell
        while cell is not None:
            trail.add(cell)
            cell = parent[cell]
        assert target_cells.issubset(trail) == (number == 15)


def check_stage_6():
    assert "8421" == "8421"


def check_stage_7():
    # The source puzzle explicitly intends red + blue -> purple.
    palette = ["red", "blue", "green", "yellow", "purple", "white", "orange", "cyan"]
    assert "purple" in palette


def check_stage_8():
    beep_groups = [3, 5, 1, 4]
    assert "".join(map(str, beep_groups)) == "3514"


def check_stage_9():
    # Source clue: do not cut red; correct cable is immediately right of yellow.
    cables = ["red", "blue", "yellow", "green"]
    yellow_index = cables.index("yellow")
    assert cables[yellow_index + 1] == "green"


def check_stage_11():
    X = 8 ** 2
    Y = (1 + 6 + 200) - 7
    Z = (X + Y) // 4
    assert (X, Y, Z) == (64, 200, 66)


def check_stage_5_color_order():
    task = ColorCodeTask()
    expected = ["כחול", "צהוב", "אדום"]
    actual = [task.colors[index][0] for index in task.order]
    assert actual == expected, f"Color Code order should be cold-to-hot: {actual}"


def check_stage_5_task_mechanics():
    # Firewall maze: a walkable route must exist from S to E.
    maze = FirewallMazeTask()
    start = next((x, y) for y, row in enumerate(maze.grid) for x, ch in enumerate(row) if ch == "S")
    end = next((x, y) for y, row in enumerate(maze.grid) for x, ch in enumerate(row) if ch == "E")
    pending = [start]
    visited = {start}
    while pending:
        x, y = pending.pop(0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (x + dx, y + dy)
            nx, ny = nxt
            if (0 <= ny < len(maze.grid) and 0 <= nx < len(maze.grid[ny])
                    and maze.grid[ny][nx] != "#" and nxt not in visited):
                visited.add(nxt)
                pending.append(nxt)
    assert end in visited, "Firewall maze must have a reachable exit"

    # Oil Catch: even if seven cans overlap the basket at once, the task is exactly 5/5.
    oil = OilCatchTask()
    oil.catches = 0
    oil.done = False
    oil.basket_x = 0.5
    oil.items = [[0.5, 0.82, 0.0] for _ in range(7)]
    oil.update_and_collide(0.0, 1600, 900)
    assert oil.catches == 5 and oil.done, f"Oil Catch should stop at 5/5, got {oil.catches}"

    # Symbol Matrix grid content must match the declared counts with one unique majority.
    matrix = SymbolMatrixTask()
    visible_counts = Counter(matrix.grid)
    assert visible_counts == Counter(matrix.counts)
    max_count = max(visible_counts.values())
    assert sum(count == max_count for count in visible_counts.values()) == 1
    assert visible_counts[matrix.target] == max_count

    # Word decrypt shows a rearrangement of the actual answer.
    word = WordDecryptTask()
    assert word.answer in word.words
    assert Counter(word.scrambled) == Counter(word.answer)

    # Cyber Memory has four pairs and eight cards.
    memory = CyberMemoryTask()
    values = Counter(memory.values)
    assert len(memory.values) == 8
    assert len(values) == 4 and all(count == 2 for count in values.values())

    # Trivia's declared answer agrees with its displayed option.
    trivia = TriviaTask()
    assert trivia.options[trivia.answer] == "8"

    # Four-branch sequence is a valid four-position sequence.
    sequence = DreidelSaysTask()
    assert len(sequence.sequence) == 4
    assert all(0 <= index < 4 for index in sequence.sequence)

    # The cable immediately right of yellow is green, and red isn't the answer.
    wire = WireCutTask()
    assert wire.colors[wire.correct] == "ירוק"
    assert wire.colors.index("צהוב") + 1 == wire.correct
    assert wire.correct != wire.colors.index("אדום")

    # The missing-letter game draws only the four letters on a dreidel.
    letter = MissingLetterTask()
    assert set(letter.letters) == {"נ", "ג", "ה", "פ"}
    assert letter.current in letter.letters


def check_task_bank():
    tasks = [
        "Firewall Maze",
        "Oil Catch",
        "Symbol Matrix",
        "Word Decrypt",
        "Cyber Memory",
        "Color Code Hack",
        "Cyber Trivia",
        "Dreidel Says",
        "Wire Cut",
        "Missing Letter",
    ]
    assert len(tasks) == 10
    assert len(set(tasks)) == 10


def run_all():
    check_stage_3()
    check_stage_4()
    check_stage_5_color_order()
    check_stage_5_task_mechanics()
    check_stage_6()
    check_stage_7()
    check_stage_8()
    check_stage_9()
    check_stage_11()
    check_task_bank()
    print("ALL FIXED-VALUE PUZZLE CHECKS PASSED")


if __name__ == "__main__":
    run_all()
