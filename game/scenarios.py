"""Starting unit placement: (type, team, column, row)."""
from .units import STATS, Unit

DEFAULT = [
    # Blue (humans, west) - faces east
    ("minelayer", "blue", 6, 4), ("minesweeper", "blue", 6, 2), ("destroyer", "blue", 7, 6),
    ("submarine", "blue", 7, 8), ("cruiser", "blue", 7, 10), ("battleship", "blue", 6, 12),
    ("infantry", "blue", 3, 3), ("tank", "blue", 3, 6), ("artillery", "blue", 2, 9),
    ("infantry", "blue", 3, 11), ("coastal_gun", "blue", 4, 5), ("missile_launcher", "blue", 2, 7),
    ("missile_silo", "blue", 1, 11),
    ("diver", "blue", 6, 3), ("digger", "blue", 3, 4), ("builder", "blue", 3, 8), ("miner", "blue", 3, 9), ("spy", "blue", 3, 10),
    ("fighter", "blue", 1, 1), ("bomber", "blue", 0, 1), ("attack_helicopter", "blue", 0, 2), ("uav", "blue", 2, 2),
    ("medevac_helicopter", "blue", 2, 1), ("transport_helicopter", "blue", 1, 0),
    ("anti_air", "blue", 3, 2), ("medic", "blue", 1, 6), ("supply_truck", "blue", 1, 7), ("commando", "blue", 3, 11),
    # Candooo (AI, east) - faces west
    ("minelayer", "red", 14, 4), ("minesweeper", "red", 13, 2), ("destroyer", "red", 13, 6),
    ("submarine", "red", 13, 8), ("cruiser", "red", 12, 10), ("battleship", "red", 14, 10),
    ("infantry", "red", 18, 3), ("tank", "red", 17, 6), ("artillery", "red", 19, 9),
    ("infantry", "red", 18, 11), ("coastal_gun", "red", 18, 5), ("missile_launcher", "red", 18, 7),
    ("missile_silo", "red", 19, 11),
    ("diver", "red", 15, 3), ("digger", "red", 17, 4), ("builder", "red", 18, 8), ("miner", "red", 18, 10), ("spy", "red", 17, 10),
    ("fighter", "red", 17, 1), ("bomber", "red", 18, 1), ("attack_helicopter", "red", 19, 2), ("uav", "red", 16, 2),
    ("medevac_helicopter", "red", 18, 2), ("transport_helicopter", "red", 19, 1),
    ("anti_air", "red", 16, 3), ("medic", "red", 18, 6), ("supply_truck", "red", 19, 7), ("commando", "red", 19, 4),
]

# Hidden mines at the start: (column, row, owner). Sea mines sit in the channels, land mines on the causeway.
MINES = [(8, 6, "red"), (8, 9, "red"), (14, 5, "blue"), (14, 8, "blue"), (12, 0, "red"), (7, 0, "blue")]


def build_units(placement=DEFAULT):
    counts = {}
    units = []
    for t, team, c, r in placement:
        counts[(team, t)] = counts.get((team, t), 0) + 1
        units.append(Unit(id=f"{team[0]}-{t}-{counts[(team, t)]}", type=t, team=team, c=c, r=r, hp=STATS[t]["hp"]))
    return units
