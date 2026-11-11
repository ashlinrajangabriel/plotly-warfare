"""Movement, pathfinding and combat rules."""
import heapq
import math

from .units import AIR_TYPES, ATTACK, STATS

INFANTRY = dict(coast=1, plains=1, forest=1, hills=2, mountain=3, port=1, city=1, tunnel=1,
                flood_plain=1, flooded_zone=2, tank_trap=1, crater=2, road=1, bridge=1, trench=1, camp=1, river=4, barricade=3, airfield=1, barracks=1, training_camp=1, factory=1)
TRACKED = dict(coast=1, plains=1, forest=2, hills=2, port=1, city=1, tunnel=1, flood_plain=1, crater=2, road=1, bridge=1, trench=2, camp=1, airfield=1, barracks=1, training_camp=1, factory=1)
WHEELED = dict(coast=1, plains=1, forest=2, hills=3, port=1, city=1, tunnel=1, flood_plain=1, crater=3, road=1, bridge=1, trench=3, camp=1, airfield=1, barracks=1, training_camp=1, factory=1)
SHIP = dict(deep_sea=1, shallow_water=1, high_current=1, sulphur_zone=1, port=1)
SWIMMER = {**SHIP, "coral_reef": 1, "flooded_zone": 1, "coast": 1}

COST_TABLES = {
    "infantry": INFANTRY, "digger": INFANTRY, "builder": INFANTRY, "miner": INFANTRY, "spy": INFANTRY,
    "tank": TRACKED, "artillery": TRACKED, "missile_launcher": WHEELED, "anti_air": TRACKED, "medic": WHEELED, "supply_truck": WHEELED,
    "rebel": INFANTRY, "commando": INFANTRY, "vip": INFANTRY,
    "minesweeper": {**SHIP, "coral_reef": 1, "flooded_zone": 1},
    "submarine": {**SHIP, "coral_reef": 1}, "diver": SWIMMER,
    "minelayer": SHIP, "destroyer": SHIP, "cruiser": SHIP, "battleship": SHIP, "supply_ship": SHIP,
}

# Damage multiplier for the defender's terrain (lower = better cover)
COVER = dict(forest=.75, hills=.8, mountain=.6, city=.7, trench=.4, ruins=.6, tunnel=.8, barracks=.7, training_camp=.8, factory=.7)
HEAVY_VS_LAND = {"cruiser", "battleship"}                      # ships that shell land well
HEAVY_VS_SEA = {"artillery", "coastal_gun", "missile_launcher", "missile_silo"}  # land weapons that hit ships well


# ---------- line of sight and height ----------
# Ground relief (hills and mountains lift an observer) and obstruction (trees and buildings stand above the ground and block the view).
ELEV = dict(hills=2.0, mountain=4.0, tunnel=4.0)
OBST = dict(forest=2.0, city=2.0, ruins=1.5, barracks=1.2, training_camp=.6, barricade=.5, factory=1.5)
INDIRECT = {"artillery", "missile_launcher", "missile_silo", "bomber"}    # these fire on what a spotter sees, over hills and trees
EYE, TOP = 1.2, 1.0                                                      # eye height of an observer, height of the thing it looks at


def elevation(board, c, r):
    return ELEV.get(board.terrain(c, r), 0.0)


def sight_bonus(board, c, r):
    """High ground sees further: +1 tile on hills, +2 on mountains."""
    return int(elevation(board, c, r) // 2)


def tiles_between(a, b):
    """Tiles strictly between two tiles on a straight line (Bresenham)."""
    (c0, r0), (c1, r1) = a, b
    dc, dr = abs(c1 - c0), abs(r1 - r0)
    sc, sr = (1 if c1 > c0 else -1), (1 if r1 > r0 else -1)
    err, c, r, out = dc - dr, c0, r0, []
    while (c, r) != (c1, r1):
        e2 = 2 * err
        if e2 > -dr:
            err -= dr
            c += sc
        if e2 < dc:
            err += dc
            r += sr
        if (c, r) != (c1, r1):
            out.append((c, r))
    return out


def has_los(board, a, b):
    """Can an observer at tile a see tile b? Anything between that stands higher than the line of sight blocks it."""
    mids = tiles_between(a, b)
    if not mids:
        return True
    eye = elevation(board, *a) + EYE
    top = elevation(board, *b) + TOP
    n = len(mids) + 1
    for i, (c, r) in enumerate(mids):
        line_h = eye + (top - eye) * (i + 1) / n
        t = board.terrain(c, r)
        if ELEV.get(t, 0.0) + OBST.get(t, 0.0) > line_h:
            return False
    return True


def blocker(board, a, b):
    """The first tile that blocks the view from a to b, or None."""
    mids = tiles_between(a, b)
    eye = elevation(board, *a) + EYE
    top = elevation(board, *b) + TOP
    n = len(mids) + 1
    for i, (c, r) in enumerate(mids):
        t = board.terrain(c, r)
        if ELEV.get(t, 0.0) + OBST.get(t, 0.0) > eye + (top - eye) * (i + 1) / n:
            return (c, r)
    return None


def step_cost(unit_type, terrain):
    """Movement cost to enter a tile, or None if the unit cannot enter it. Aircraft fly over anything."""
    if unit_type in AIR_TYPES:
        return 1
    return COST_TABLES.get(unit_type, {}).get(terrain)


def dist(a, b):
    """Manhattan distance between two things with .c and .r."""
    return abs(a.c - b.c) + abs(a.r - b.r)


def find_path(board, units, unit, goal, allow_goal_occupied=False, avoid=()):
    """Cheapest route to `goal` (c, r) as [(c, r, cost), ...] excluding the start, or None.
    `avoid` = tiles the unit knows are mined (it walks round them)."""
    # aircraft only collide with aircraft (they fly over everyone else); ground and sea units ignore aircraft overhead
    flying = unit.type in AIR_TYPES
    occupied = {(u.c, u.r) for u in units if u.id != unit.id and (u.type in AIR_TYPES) == flying}
    if not flying:
        occupied |= set(avoid)
    elif not allow_goal_occupied and any((u.c, u.r) == goal for u in units if u.id != unit.id):
        return None                                      # an aircraft cannot come to rest on top of somebody
    start = (unit.c, unit.r)
    best = {start: 0}
    prev = {}
    heap = [(0, start)]
    while heap:
        cost, cur = heapq.heappop(heap)
        if cur == goal:
            break
        if cost > best.get(cur, math.inf):
            continue
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (cur[0] + dc, cur[1] + dr)
            if not board.inside(*nxt):
                continue
            if nxt in occupied and not (allow_goal_occupied and nxt == goal):
                continue
            step = step_cost(unit.type, board.terrain(*nxt))
            if step is None or cost + step >= best.get(nxt, math.inf):
                continue
            best[nxt] = cost + step
            prev[nxt] = (cur, step)
            heapq.heappush(heap, (cost + step, nxt))
    if goal not in prev:
        return None
    path, cur = [], goal
    while cur != start:
        p, step = prev[cur]
        path.append((cur[0], cur[1], step))
        cur = p
    path.reverse()
    return path


def can_hit(attacker, defender):
    """Whether the attacker's weapon can damage the defender at all."""
    if ATTACK[attacker.type][0] <= 0 or defender.type == "vip":
        return False                                     # nobody shoots the principals
    d = defender.stats["domain"]
    if attacker.type == "anti_air":
        return d == "air"                                # air defence shoots only at aircraft
    if d == "air":
        return attacker.type in ("fighter", "attack_helicopter")   # nothing else on the ground or sea can reach a flying target
    if attacker.type == "submarine":
        return d == "sea"
    if attacker.type == "bomber":
        return True
    return True


def in_range(attacker, defender):
    return dist(attacker, defender) <= attacker.stats["range"]


def facing_factor(attacker, defender):
    """Armour is thickest at the front: a tank hit from ahead takes 20% less, from behind 30% more. Only tanks have this."""
    if defender.type != "tank":
        return 1.0
    dc, dr = attacker.c - defender.c, attacker.r - defender.r
    if dc == 0 and dr == 0:
        return 1.0
    bearing = math.degrees(math.atan2(dr, dc)) % 360
    diff = abs((bearing - defender.heading + 180) % 360 - 180)
    return .8 if diff <= 60 else 1.3 if diff >= 120 else 1.0


def damage(attacker, defender, board):
    """Damage of one hit: base * domain modifier * defender's terrain cover (at least 1)."""
    base = ATTACK[attacker.type][0]
    a, d = attacker.stats["domain"], defender.stats["domain"]
    mult = 1.0
    if d == "air":
        return max(1, base)                                   # no cover in the sky
    if a == "land" and d == "sea" and attacker.type not in HEAVY_VS_SEA:
        mult = .5
    elif a == "sea" and d == "land" and attacker.type not in HEAVY_VS_LAND:
        mult = .6
    elif a == "air" and attacker.type == "fighter":
        mult = .6                                             # a fighter's guns are built for the sky
    mult *= COVER.get(board.terrain(defender.c, defender.r), 1.0)
    mult *= facing_factor(attacker, defender)
    return max(1, round(base * mult))


def secs_per_cost(unit):
    m = unit.stats["move"]
    return 6 / m if m else math.inf
