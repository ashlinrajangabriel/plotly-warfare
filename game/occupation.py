"""Designating a hostile force as militant, striking it with allies, and resettling cleared war-torn areas.

Both moves are tempting and both have costs, as they did in history:

  Designate   label the enemy's armed forces a militant group. Allies (relation 70+) may then join strikes on it.
              Justified (militants or commandos of theirs are active in our rear): small cost. Unjustified: intelligence
              exposes it, our government loses face, and neutral neighbours cool sharply. Their friends cool towards us either way.
  Ally strike an allied air strike on up to three spotted enemy units. Some of the survivors scatter into rebel cells.
  Resettle    settle people in a captured area once it is cleared of enemy units.
              Inclusive: slow (60 s), costs a little, calms the area and lifts the economy.
              Forced:    fast (20 s), bigger economic gain, but unrest at home, neighbours turn away, and rebel cells rise there.
"""
from . import agents, homefront, world
from .board import ref as grid

OTHER = {"blue": "red", "red": "blue"}
STRIKE_CD = 90
STRIKE_DAMAGE = 4
CLEAR_RADIUS = 2


def setup(game):
    game.designated = {"blue": False, "red": False}       # has this side labelled the other a militant group?
    game.strikes = {"blue": 0, "red": 0}                  # allied strikes carried out
    game.accused = set()                                   # (side, charge) already made
    game.settled = {}                                      # (c, r) -> {side, mode, done_at, done, raids}


def _say(game, side, text):
    game.say(text)
    if side == game.human:
        agents.radio(game, side, "in", "FOREIGN-MIN", text)


def justified(game, side):
    """Are the enemy's militants or commandos really active in our rear?"""
    mid = game.board.width // 2
    foe = OTHER[side]
    return any(u.team == foe and u.hp > 0 and u.type in ("rebel", "commando") and ((u.c < mid) if side == "blue" else (u.c >= mid)) for u in game.units)


def designate(game, side):
    if game.winner:
        return "The war is over."
    if game.designated[side]:
        return "Already designated."
    ok = justified(game, side)
    game.designated[side] = True
    foe = OTHER[side]
    for nid in world.NEIGHBORS:
        rel_foe, rel_me = world.relation(game, nid, foe), world.relation(game, nid, side)
        if rel_foe >= 70:
            world.shift(game, nid, side, -10)                     # their friends turn on us
        elif rel_me < 70:
            world.shift(game, nid, side, -3 if ok else -8)        # neutral neighbours cool
    if homefront.active(game):
        game.home[side]["stability"] = max(0, game.home[side]["stability"] - (2 if ok else 6))
    if ok:
        return ("The enemy's armed forces are designated a militant group. Their commandos and cells in our rear are the evidence. "
                "Allies may now join strikes. Their friends have cooled towards us.")
    return ("Designated, but there is no sign of their militants in our rear: intelligence calls it a pretext. Our government lost face and neutral neighbours cooled sharply. "
            "Allies may still join strikes.")


def ally_strike(game, side, nid):
    n = world.NEIGHBORS.get(nid)
    if not n:
        return "Unknown country."
    if not game.designated[side]:
        return "Designate the enemy first: allies only join strikes against a designated group."
    if world.relation(game, nid, side) < 70:
        return f"{n['name']} is not an ally (relation {int(world.relation(game, nid, side))}, needs 70)."
    left = game.world[nid]["cd"].get("strike", 0) - game.t
    if left > 0:
        return f"{n['name']}'s air force is not ready for {int(left)} sec."
    foes = [u for u in game.units if u.team == OTHER[side] and u.id in game.detected[side] and u.hp > 0 and not u.air and u.type != "supply_ship"]
    if not foes:
        return "No spotted enemy units to strike. Scout first."
    foes.sort(key=lambda u: (u.type not in ("infantry", "tank", "artillery"), u.hp))
    game.world[nid]["cd"]["strike"] = game.t + STRIKE_CD
    game.strikes[side] += 1
    hit, scattered = [], 0
    for u in foes[:3]:
        game._hit(f"{n['name']} air strike", u, STRIKE_DAMAGE, None)
        game.add_sfx("boom", u.c, u.r)
        hit.append(grid(u.c, u.r))
        if u.hp <= 0 and game.rng.random() < .3:
            spot = game.free_near(u.c, u.r, "rebel")
            if spot:
                r = game.new_unit(OTHER[side], "rebel", *spot)
                r.ambush, r.hold_fire = True, True
                scattered += 1
    for other in world.NEIGHBORS:                                    # the target's friends take note
        if other != nid and world.relation(game, other, OTHER[side]) >= 70:
            world.shift(game, other, side, -4)
    return f"{n['name']} struck {', '.join(hit)}." + (f" {scattered} survivor cell(s) scattered into the hills." if scattered else "")


def captured_areas(game, side):
    """Objectives and facilities we hold that began on the other side of the map."""
    mid = game.board.width // 2
    out = []
    for pos, o in list(game.objectives.items()) + list(game.facilities.items()):
        orig = "blue" if pos[0] < mid else "red"
        if o["owner"] == side and orig != side:
            out.append((pos, o))
    return out


def _cleared(game, side, pos):
    return not any(u.team == OTHER[side] and u.hp > 0 and abs(u.c - pos[0]) + abs(u.r - pos[1]) <= CLEAR_RADIUS and not u.air for u in game.units)


def resettle(game, side, pos, mode):
    if mode not in ("inclusive", "forced"):
        return "Unknown way of settling."
    areas = dict(captured_areas(game, side))
    if pos not in areas:
        return "We do not hold a captured area there."
    if pos in game.settled:
        return "People are already settling there."
    if not _cleared(game, side, pos):
        return f"Enemy units are still within {CLEAR_RADIUS} tiles of {grid(*pos)}. Clear the area first."
    if homefront.active(game) and mode == "inclusive":
        game.home[side]["economy"] = max(0, game.home[side]["economy"] - 3)
    game.settled[pos] = dict(side=side, mode=mode, done_at=game.t + (60 if mode == "inclusive" else 20), done=False, raids=0, next_raid=game.t + 60)
    return f"Resettlement of {grid(*pos)} begun ({'inclusive, 60 s' if mode == 'inclusive' else 'forced, 20 s'})."


def _rebel_near(game, side, pos):
    spot = game.free_near(pos[0], pos[1], "rebel")
    if spot:
        r = game.new_unit(OTHER[side], "rebel", *spot)
        r.ambush, r.hold_fire = True, True
        return True
    return False


def tick(game):
    if game.t % 5:
        return
    for pos, s in list(game.settled.items()):
        side = s["side"]
        if (game.objectives.get(pos) or game.facilities.get(pos) or {}).get("owner") != side:
            del game.settled[pos]                                  # lost again: the settlers flee
            continue
        h = game.home[side] if homefront.active(game) else None
        if not s["done"] and game.t >= s["done_at"]:
            s["done"] = True
            if s["mode"] == "inclusive":
                if h:
                    h["economy"] = min(100, h["economy"] + 5)
                    h["stability"] = min(100, h["stability"] + 2)
                    h["unrest"] = max(0, h["unrest"] - 2)
                _say(game, side, f"Resettlement of {grid(*pos)} is done: local councils sit with the settlers, markets reopen. Economy +5, stability +2.")
            else:
                if h:
                    h["economy"] = min(100, h["economy"] + 8)
                    h["unrest"] = min(100, h["unrest"] + 8)
                    h["stability"] = max(0, h["stability"] - 3)
                for nid in world.NEIGHBORS:
                    world.shift(game, nid, side, -4 if world.relation(game, nid, side) >= 70 else -10)
                for _ in range(2):
                    _rebel_near(game, side, pos)
                _say(game, side, f"Forced resettlement of {grid(*pos)} is done. Economy +8, but the displaced took up arms, neighbours condemn it and unrest is up.")
        elif s["done"] and s["mode"] == "forced" and s["raids"] < 3 and game.t >= s["next_raid"]:
            s["next_raid"] = game.t + 60
            if game.rng.random() < .5 and _rebel_near(game, side, pos):
                s["raids"] += 1
                _say(game, side, f"Militants from the displaced population appeared near {grid(*pos)}.")


def panel(game, side):
    strikes = []
    for nid, n in world.NEIGHBORS.items():
        if world.relation(game, nid, side) >= 70:
            left = game.world[nid]["cd"].get("strike", 0) - game.t
            strikes.append(dict(nid=nid, name=n["name"], enabled=game.designated[side] and left <= 0,
                                why="designate first" if not game.designated[side] else f"ready in {int(left)} s" if left > 0 else ""))
    areas = []
    for pos, o in captured_areas(game, side):
        s = game.settled.get(pos)
        clear = _cleared(game, side, pos)
        areas.append(dict(c=pos[0], r=pos[1], pos=grid(*pos), kind=o["kind"],
                          status=("settled (" + s["mode"] + ")" if s["done"] else f"settling ({s['mode']}, {max(0, int(s['done_at'] - game.t))} s)") if s else "",
                          can=(s is None and clear), why="" if clear else "enemy units nearby"))
    charges = [dict(id=k, label=v, done=(side, k) in game.accused, evidence=evidence(game, side, k)) for k, v in CHARGES.items()]
    return dict(designated=game.designated[side], justified=justified(game, side), strikes=strikes, areas=areas, charges=charges, nstrikes=game.strikes[side])


CHARGES = {"nukes": "Accuse the enemy of building nuclear weapons", "invasion": "Accuse the enemy of invading us"}


def evidence(game, side, charge):
    mid = game.board.width // 2
    foe = OTHER[side]
    if charge == "nukes":
        return any(game.nuke_level[side].get(i, 0) >= 3 and ((s["c"] >= mid) if side == "blue" else (s["c"] < mid)) for i, s in enumerate(game.nukes))
    if charge == "invasion":
        return any(u.team == foe and u.hp > 0 and u.id in game.detected[side] and not u.air and u.type not in ("rebel", "supply_ship")
                   and ((u.c < mid) if side == "blue" else (u.c >= mid)) for u in game.units)
    return False


def accuse(game, side, charge):
    """Blame the enemy country publicly. Backed by evidence the world sides with us; without it we are exposed."""
    if charge not in CHARGES:
        return "Unknown charge."
    if game.winner:
        return "The war is over."
    if (side, charge) in game.accused:
        return "That charge has already been made."
    ok = evidence(game, side, charge)
    game.accused.add((side, charge))
    foe = OTHER[side]
    what = "building nuclear weapons" if charge == "nukes" else "invading our territory"
    if ok:
        for nid in world.NEIGHBORS:
            if world.relation(game, nid, foe) < 70:
                world.shift(game, nid, side, 6)
        if homefront.active(game):
            game.home[foe]["stability"] = max(0, game.home[foe]["stability"] - 3)
        game.sanctions[foe] = game.sanctions.get(foe, 0) + .006
        return f"The charge of {what} is backed by our evidence. Neighbours warm to us and sanctions fall on the enemy."
    for nid in world.NEIGHBORS:
        world.shift(game, nid, side, -12)
    if homefront.active(game):
        game.home[side]["stability"] = max(0, game.home[side]["stability"] - 8)
    game.sanctions[side] = game.sanctions.get(side, 0) + .006
    return f"The charge of {what} could not be backed up. We are exposed: our stability fell, neighbours turned away and sanctions fall on us."
