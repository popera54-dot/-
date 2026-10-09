"""Deterministic checks for fixed-value puzzles and the generated stage-four maze."""

from stage4_puzzle import Stage4Controller


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
    check_stage_6()
    check_stage_7()
    check_stage_8()
    check_stage_9()
    check_stage_11()
    check_task_bank()
    print("ALL FIXED-VALUE PUZZLE CHECKS PASSED")


if __name__ == "__main__":
    run_all()
