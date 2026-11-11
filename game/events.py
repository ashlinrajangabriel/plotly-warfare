"""Live scenarios: informants' rumours, random events (storm, defector, tip-offs) and intercepted enemy traffic.

Everything that changes the game is made here, by the server, from the real game state. The language
model only gives these things a voice, so it can colour a rumour but never invent a fact.
A rumour is a tip with a marker on the map at a fuzzy spot. It may be true or false; go and look.
"""
from . import agents
from .board import ref as grid
from .units import STATS

RUMOR_TTL = 150            # seconds before an unverified rumour fades
EVENT_RANGE = (110, 190)   # seconds between random events
ON_DEMAND_COOLDOWN = 60    # seconds between scenarios the General asks for
STORM_SECS = 90
OTHER = {"blue": "red", "red": "blue"}

TRUE_TEXT = {
    "rebel": "Villagers whisper of armed men in the hedges and ditches near {where}.",
    "launcher": "A farmer saw a long truck with a tube under netting near {where}.",
    "armor": "Villagers heard heavy tracks and engines in the fields near {where}.",
    "ship": "Fishermen say warships are lurking near {where}.",
    "artillery": "Children found fresh gun pits and shell crates near {where}.",
}
FALSE_TEXT = [
    "A sailor swears he saw a fleet near {where}. He had been drinking.",
    "Someone on the road says there is a missile base near {where}.",
    "A trader claims armoured columns gather near {where}. Nobody else has seen them.",
]


def _clamp(game, c, r):
    return min(max(c, 0), game.board.width - 1), min(max(r, 0), game.board.height - 1)


def _fuzzy(game, pos, spread=2):
    rng = game.rng
    return _clamp(game, pos[0] + rng.randint(-spread, spread), pos[1] + rng.randint(-spread, spread))


def make_rumor(game, side, source=None):
    """An informant brings a tip. Returns the line the General hears."""
    foe = OTHER[side]
    enemies = [u for u in game.units if u.team == foe and u.hp > 0]
    # sometimes the tip is about the hidden silos (once per site)
    unknown = [i for i, lvl in game.nuke_level[side].items() if lvl < 2]
    if unknown and game.rng.random() < .2:
        i = game.rng.choice(unknown)
        site = game.nukes[i]
        game.nuke_level[side][i] = 2
        game.nuke_fuzzy[(side, i)] = _fuzzy(game, (site["c"], site["r"]))
        f = game.nuke_fuzzy[(side, i)]
        return f"Locals avoid a fenced hill near {grid(*f)}. Trucks come at night and nobody is allowed close. A marker is on your map."
    groups = {"rebel": [u for u in enemies if u.type == "rebel"],
              "launcher": [u for u in enemies if u.type in ("missile_launcher", "missile_silo")],
              "artillery": [u for u in enemies if u.type == "artillery"],
              "armor": [u for u in enemies if u.type == "tank"],
              "ship": [u for u in enemies if u.stats["domain"] == "sea" and u.type != "supply_ship"]}
    kinds = [k for k, v in groups.items() if v]
    if kinds and game.rng.random() >= .3:
        kind = game.rng.choice(kinds)
        e = game.rng.choice(groups[kind])
        truth, true, text = (e.c, e.r), True, TRUE_TEXT[kind]
    else:                                                       # a false tip: somewhere in the enemy half
        half = range(game.board.width // 2, game.board.width) if side == "blue" else range(0, game.board.width // 2)
        truth = (game.rng.choice(list(half)), game.rng.randrange(game.board.height))
        true, text = False, game.rng.choice(FALSE_TEXT)
    fz = _fuzzy(game, truth)
    game.seq += 1
    game.rumors.append(dict(id=game.seq, c=fz[0], r=fz[1], truth=truth, true=true, text=text.format(where=grid(*fz)),
                            side=side, made=game.t, expires=game.t + RUMOR_TTL))
    return game.rumors[-1]["text"] + " It is marked on your map. Unverified."


def resolve_rumors(game):
    """A rumour is settled when one of our units can see its marker (or it fades)."""
    for rum in list(game.rumors):
        side = rum["side"]
        if (rum["c"], rum["r"]) in game.vis[side]:
            near = any(u.team == OTHER[side] and u.hp > 0 and abs(u.c - rum["truth"][0]) + abs(u.r - rum["truth"][1]) <= 3 for u in game.units)
            game.rumors.remove(rum)
            if side == game.human:
                if rum["true"] and near:
                    agents.radio(game, side, "in", "HQ-Radio", f"The tip near {grid(rum['c'], rum['r'])} checks out: the enemy is there.")
                else:
                    agents.radio(game, side, "in", "HQ-Radio", f"False alarm near {grid(rum['c'], rum['r'])}. Nothing there now.")
        elif game.t >= rum["expires"]:
            game.rumors.remove(rum)
            if side == game.human:
                agents.radio(game, side, "in", "HQ-Radio", f"No word on the tip near {grid(rum['c'], rum['r'])}. It has gone cold.")


GAS_SECS, GAS_RADIUS = 45, 2        # a chemical cloud: how long it lasts, how wide
FLOOD_WARN, FLOOD_SECS = 30, 70     # warning time before a flood plain floods, and how long it stays flooded
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def gas_attack(game, c, r):
    """Candooo chemical shells burst at (c, r). Units inside the cloud lose health unless they wear masks."""
    import math
    game.clouds.append(dict(c=c, r=r, radius=GAS_RADIUS, until=game.t + GAS_SECS, next_drift=game.t + 10))
    game.say(f"Chemical shells burst at {grid(c, r)}. A gas cloud is spreading.")
    game.add_sfx("alarm")
    h = game.human
    near = [u for u in agents.own_units(game, h) if not u.air and abs(u.c - c) + abs(u.r - r) <= 7]
    wx, wy = game.wind
    way = COMPASS[int(round(((math.degrees(math.atan2(wy, wx)) + 90) % 360) / 45)) % 8] if (wx or wy) else "nowhere"
    text = f"GAS GAS GAS! Chemical cloud at {grid(c, r)}, drifting {way}. {len(near)} of our units are close."
    if near:
        u = min(near, key=lambda m: abs(m.c - c) + abs(m.r - r))
        agents.open_report(game, u, "gas", text, [dict(id="masks", label="Masks on for everyone near it"),
                                                  dict(id="evacuate", label="Move everyone out, upwind")], pos=(c, r))
    return text


def flood_warning(game):
    """A flood plain will flood after a warning. Vehicles caught on it are stranded and damaged."""
    tiles = [(c, r) for r in range(game.board.height) for c in range(game.board.width)
             if game.board.terrain(c, r) == "flood_plain" and not any((f["c"], f["r"]) == (c, r) for f in game.floods)]
    if not tiles:
        return "No flood plain left to flood."
    c, r = game.rng.choice(tiles)
    game.floods.append(dict(c=c, r=r, hits=game.t + FLOOD_WARN, until=game.t + FLOOD_WARN + FLOOD_SECS, stage="warning"))
    text = f"FLOOD WARNING: the plain at {grid(c, r)} will flood in {FLOOD_WARN} sec. Get vehicles off it."
    game.add_sfx("alarm")
    near = [u for u in agents.own_units(game, game.human) if not u.air and abs(u.c - c) + abs(u.r - r) <= 4]
    if near:
        u = min(near, key=lambda m: abs(m.c - c) + abs(m.r - r))
        agents.open_report(game, u, "flood", text, [dict(id="flood_out", label="Move units off the plain")], pos=(c, r))
    return text


def tick_hazards(game):
    """Gas clouds drift and burn; flood plains flood on schedule and drain later."""
    for cl in list(game.clouds):
        if game.t >= cl["until"]:
            game.clouds.remove(cl)
            if not game.clouds:
                units = [u for u in agents.own_units(game, game.human) if u.mask]
                for u in units:
                    u.mask = False
                if units:
                    agents.radio(game, game.human, "in", "HQ-Radio", f"ALL CLEAR. The gas has gone. Masks off for {len(units)} unit{'s' if len(units) != 1 else ''}.")
            continue
        if game.t >= cl["next_drift"]:
            wx, wy = game.wind
            cl["c"] = _clamp(game, cl["c"] + (1 if wx > .35 else -1 if wx < -.35 else 0), 0)[0]
            cl["r"] = _clamp(game, 0, cl["r"] + (1 if wy > .35 else -1 if wy < -.35 else 0))[1]
            cl["next_drift"] = game.t + 10
        if game.t % 3 == 0:
            for u in list(game.units):
                if u.hp > 0 and not u.air and not u.mask and abs(u.c - cl["c"]) + abs(u.r - cl["r"]) <= cl["radius"]:
                    game._hit("Chemical cloud", u, 1, None)
    for f in list(game.floods):
        if f["stage"] == "warning" and game.t >= f["hits"]:
            f["stage"] = "flooded"
            game.board.grid[f["r"]][f["c"]] = "flooded_zone"
            game.say(f"The plain at {grid(f['c'], f['r'])} flooded.")
            if game.human:
                agents.radio(game, game.human, "in", "HQ-Radio", f"The plain at {grid(f['c'], f['r'])} is flooded.")
            for u in game.units:
                if (u.c, u.r) == (f["c"], f["r"]) and not u.air and u.type in ("tank", "artillery", "missile_launcher", "anti_air", "medic", "supply_truck"):
                    u.shaken_until = game.t + 20                      # stranded in the water
                    game._hit("Flood water", u, 2, None)
                    if u.team == game.human and u.hp > 0:
                        agents.say(game, u, "Stranded in the flood! We cannot move!", urgent=True)
        elif f["stage"] == "flooded" and game.t >= f["until"]:
            game.board.grid[f["r"]][f["c"]] = "flood_plain"
            game.floods.remove(f)
            game.say(f"The flood at {grid(f['c'], f['r'])} drained.")


def rebels_rise(game, side):
    """A hidden rebel cell takes up position somewhere in this side's rear. They hide, hold fire and spring on whoever comes close,
    then go for the nearest barracks or training camp. Very hard to find: only spotted from 1 tile (3 by a UAV or a spy)."""
    foe = OTHER[side]
    mid = game.board.width // 2
    cands = [(c, r) for c in range(game.board.width) for r in range(game.board.height)
             if ((c < mid) if side == "blue" else (c >= mid)) and game.board.terrain(c, r) in ("plains", "forest", "hills", "coast", "road")
             and (c, r) not in game.vis[side]
             and all(abs(c - u.c) + abs(r - u.r) >= 4 for u in game.units if u.team == side)]
    if not cands:
        return "Rumours of unrest, but nothing we can place."
    c, r = game.rng.choice(cands)
    for _ in range(3):
        spot = game.free_near(c, r, "rebel")
        if spot:
            u = game.new_unit(foe, "rebel", *spot)
            u.ambush, u.hold_fire = True, True
    game.say(f"A rebel cell rose near {grid(c, r)}.")
    return "UNREST. Armed men are said to be hiding somewhere in our rear. Nobody can say where. A UAV or a spy may find them; or an informant."


def militants_cross(game, side, nid):
    """A hostile neighbour lets armed militants slip across the border into this side's rear."""
    from . import world
    foe = OTHER[side]
    col = 0 if side == "blue" else game.board.width - 1
    rows = [r for r in range(game.board.height) if game.board.terrain(col, r) in ("plains", "forest", "hills", "coast")]
    if not rows:
        return ""
    r = game.rng.choice(rows)
    made = 0
    for _ in range(2):
        spot = game.free_near(col, r, "rebel")
        if spot:
            u = game.new_unit(foe, "rebel", *spot)
            u.ambush, u.hold_fire = True, True
            made += 1
    if not made:
        return ""
    game.say(f"Militants crossed the border from {world.NEIGHBORS[nid]['name']} near {grid(col, r)}.")
    return f"BORDER ALERT. Militants crossed from {world.NEIGHBORS[nid]['name']} near {grid(col, r)}. They are irregulars: they hide, then strike at barracks and camps."


def scenario(game, side, kind):
    """Start a scenario for this side. Returns the HQ line."""
    if kind == "rebels":
        return rebels_rise(game, side)
    if kind == "gas":
        ground = [u for u in game.units if u.team == side and not u.air and u.type != "supply_ship"]
        if not ground:
            return "No target for the gas."
        u = game.rng.choice(ground)
        c, r = _clamp(game, u.c + game.rng.randint(-1, 1), u.r + game.rng.randint(-1, 1))
        return gas_attack(game, c, r)
    if kind == "flood":
        return flood_warning(game)
    if kind == "storm":
        game.storm_until = game.t + STORM_SECS
        sx, sy = game.rng.choice((-1, 1)), game.rng.choice((-1, 1))
        game.wind = (sx * 1.0, sy * 1.0)
        game.add_sfx("alarm")
        return f"STORM WARNING. Gales for {STORM_SECS} sec: ships slow down, shots drift and miss more. Wind now {game.wind_info()['text']}."
    if kind == "defector":
        enemies = [u for u in game.units if u.team == OTHER[side] and u.hp > 0 and u.type != "supply_ship"]
        game.rng.shuffle(enemies)
        pick = enemies[:3]
        for e in pick:
            game.intel[side][e.id] = dict(type=e.type, team=e.team, c=e.c, r=e.r, seen=game.t)
        if not pick:
            return "A defector walked in but had nothing useful."
        return ("A Candooo radio operator has defected. He gives: "
                + "; ".join(f"{STATS[e.type]['label'].upper()} AT {grid(e.c, e.r)}" for e in pick) + ". Marked as contacts.")
    if kind == "informant":
        return make_rumor(game, side)
    return "No such scenario."


def ask_scenario(game, side, kind):
    """The General asks for a scenario by chat; a cooldown stops spam."""
    if game.last_ondemand > 0 and game.t - game.last_ondemand < ON_DEMAND_COOLDOWN:
        return f"HQ is busy. Try again in {ON_DEMAND_COOLDOWN - (game.t - game.last_ondemand)} sec."
    game.last_ondemand = max(1, game.t)
    return scenario(game, side, kind)


def tick(game):
    """Called every second: rumours, storm end and the occasional random event."""
    resolve_rumors(game)
    tick_hazards(game)
    if game.storm_until and game.t >= game.storm_until:
        game.storm_until, game.wind = 0, game.wind_base
        agents.radio(game, game.human, "in", "HQ-Radio", "The storm has passed. Wind back to normal.")
    if game.t >= game.next_event_at:
        game.next_event_at = game.t + game.rng.randint(*EVENT_RANGE)
        from .levels import LEVELS
        kind = game.rng.choice(["informant", "informant", "defector", "storm"] + list(LEVELS[game.level_id].get("hazards", ())))
        if kind == "storm" and game.storm_until:
            kind = "informant"
        msg = scenario(game, game.human, kind)
        agents.radio(game, game.human, "in", "HQ-Radio", msg)


def intercept(game, text):
    """Candooo traffic is sometimes overheard (if we have a spy in the field). Shown as Morse."""
    if any(u.type == "spy" and u.hp > 0 and u.team == game.human for u in game.units) and game.rng.random() < .6:
        agents.radio(game, game.human, "in", "INTERCEPT", text.upper()[:140], kind="morse")
