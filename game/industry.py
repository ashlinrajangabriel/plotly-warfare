"""Industry and trade: factories, production points, firepower, exports, defence sales and arms orders.

Each factory turns out production points (PP) over time. PP can be spent on new units (arms orders) or sold as arms to a
neighbour (a defence sale: money and goodwill). Factories also make every weapon better (firepower, up to +30%) and keep
units supplied with ammunition. The export setting trades money against home supplies:
  keep goods at home  -> more PP and fuller stores, but weaker markets
  balanced            -> neutral
  export heavily      -> strong markets (and friendlier trade partners), but fuel and food leave the country and PP fall
"""
from . import agents
from .board import ref as grid

OTHER = {"blue": "red", "red": "blue"}
MAX_FACTORIES = 5
FACTORY_COST = 6                          # economy points, paid when a builder starts the job
PRODUCTS = {"infantry": 3, "tank": 6, "artillery": 5, "anti_air": 4, "fighter": 8, "transport_helicopter": 7}
EXPORT_NAMES = ("Keep goods at home", "Balanced exports", "Export heavily")
EXPORT_ECON = (-10, 0, 12)                # shift of the economy's target
EXPORT_PP = (1.2, 1.0, .7)                # multiplier on production points
PRODUCE_SECS = 20


def setup(game):
    game.industry = {s: dict(ip=1.0 if s == game.human else 1.0, export=1, orders=[], last_sale=-99) for s in ("blue", "red")}


def factories(game, side):
    return sum(1 for f in game.facilities.values() if f["kind"] == "factory" and f["owner"] == side)


def firepower(game, side):
    """Weapon quality: +6% per factory beyond the first, at most +30%."""
    bonus = .10 if side in game.__dict__.get("deterrents", ()) else 0.0                    # a nuclear test steadies a side's own troops
    return 1.0 + min(.30, .06 * max(0, factories(game, side) - 1)) + bonus


def tick(game):
    for side in ("blue", "red"):
        ind = game.industry[side]
        n = factories(game, side)
        if game.t % 10 == 0:
            ind["ip"] = min(30.0, ind["ip"] + n * EXPORT_PP[ind["export"]])
        if n and game.t % 20 == 0:                                   # factories keep the units' magazines topped up
            for u in game.units:
                if u.team == side and u.start_ammo and u.ammo < u.start_ammo and not u.air:
                    u.ammo += 1
        if game.t % 10 == 0 and game.homefront_on:                   # export policy moves the markets
            h = game.home[side]
            h["economy"] = max(0.0, min(100.0, h["economy"] + (-.15, 0.0, .2)[ind["export"]]))
        if ind["export"] == 2 and game.t % 5 == 0:                   # fuel and food leave the country
            game.supply[side]["fuel"] = max(0.0, game.supply[side]["fuel"] - .08)
            game.supply[side]["food"] = max(0.0, game.supply[side]["food"] - .08)
        for o in [o for o in ind["orders"] if o["at"] <= game.t]:
            ind["orders"].remove(o)
            _deliver(game, side, o)


def _deliver(game, side, order):
    base = [p for p, f in game.facilities.items() if f["kind"] == "barracks" and f["owner"] == side] or \
           [p for p, o in game.objectives.items() if o["owner"] == side]
    if not base:
        return
    c, r = min(base, key=lambda p: abs(p[0] - order["c"]) + abs(p[1] - order["r"]))
    typ = order["kind"]
    spot = game.free_near(c, r, typ) if typ not in ("fighter", "transport_helicopter") else (game.airfields(side) and game.free_near(*game.airfields(side)[0], typ))
    if spot:
        u = game.new_unit(side, typ, *spot)
        if side == game.human:
            agents.radio(game, side, "in", "ECONOMY-MIN", f"Order delivered: {u.callsign} ({u.stats['label'].lower()}) at {grid(*spot)}.")
        game.add_sfx("chime") if side == game.human else None


def produce(game, side, kind):
    """Spend production points on a new unit; it arrives after PRODUCE_SECS."""
    cost = PRODUCTS.get(kind)
    if cost is None:
        return "We cannot build that."
    ind = game.industry[side]
    if factories(game, side) < 1:
        return "No factory: build one first (a builder can do it)."
    if ind["ip"] < cost:
        return f"Not enough production points ({ind['ip']:.0f} of {cost})."
    ind["ip"] -= cost
    base = [p for p, o in game.objectives.items() if o["owner"] == side]
    c, r = base[0] if base else (4, 3)
    ind["orders"].append(dict(kind=kind, at=game.t + PRODUCE_SECS, c=c, r=r))
    return f"Ordered a {kind.replace('_', ' ')} for {cost} production points. Delivery in {PRODUCE_SECS} sec."


def set_export(game, side, level):
    if level not in (0, 1, 2):
        return "Unknown export policy."
    game.industry[side]["export"] = level
    return f"Export policy: {EXPORT_NAMES[level]}."


def defence_sale(game, side, nid):
    """Sell arms to a neighbour: money now and goodwill, paid for in production points."""
    from . import homefront, world
    ind = game.industry[side]
    if factories(game, side) < 1:
        return "No factory, so nothing to sell."
    if ind["ip"] < 3:
        return f"Not enough production points ({ind['ip']:.0f} of 3)."
    if game.world[nid]["cd"].get("sale", 0) > game.t:
        return "Another sale is not ready yet."
    ind["ip"] -= 3
    game.world[nid]["cd"]["sale"] = game.t + 60
    if homefront.active(game):
        game.home[side]["economy"] = min(100, game.home[side]["economy"] + 6)
    world.shift(game, nid, side, 10)
    return f"Defence sale to {world.NEIGHBORS[nid]['name']}: economy +6, relation now {int(world.relation(game, nid, side))}."


def panel(game, side):
    ind = game.industry[side]
    return dict(factories=factories(game, side), max=MAX_FACTORIES, pp=round(ind["ip"], 1), export=ind["export"], export_names=list(EXPORT_NAMES),
                firepower=int(round((firepower(game, side) - 1) * 100)), cost=FACTORY_COST,
                products=[dict(id=k, label=k.replace("_", " ").title(), cost=c, enabled=ind["ip"] >= c and factories(game, side) >= 1) for k, c in PRODUCTS.items()],
                orders=[dict(kind=o["kind"].replace("_", " "), left=max(0, o["at"] - game.t)) for o in ind["orders"]],
                enemy_factories=factories(game, OTHER[side]) if any(u.team == side and u.type == "spy" and u.hp > 0 for u in game.units) else None)
