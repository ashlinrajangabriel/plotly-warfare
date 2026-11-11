"""AI personas: when the General types "AI take over", the staff run the whole government and the war until "I take over".

  GENERAL-STAFF  plays the war (the same heuristic General that plays Candooo) and answers every field report
  PRESIDENT      keeps the government standing: pay, purge corrupt officers, crack down, deal with plots
  INTEL-CHIEF    runs the covert war against the enemy government
  ECONOMY-MIN    builds factories, buys units with production points, sets the export policy
  FOREIGN-MIN    courts the neighbours, sells arms, calls in allied help

The ministers also run Candooo's economy and foreign policy (quietly). Everything goes through the same calls the General's
own buttons use, so the AI plays by the same rules and the same cooldowns.
"""
from . import agents, ai_red, homefront, industry, rules, world
from .board import ref as grid

OTHER = {"blue": "red", "red": "blue"}
ON_WORDS = ("ai take over", "ai takeover", "ai take control", "ai plays for me", "ai play for me", "autopilot on", "ai take command", "let the ai play")
OFF_WORDS = ("i take over", "i take control", "i take command", "autopilot off", "manual control", "my command", "give me control", "i will play")
REPORT_ORDER = ["masks", "flood_out", "clear_mine", "rebuild", "scramble", "aa_free", "escort", "arrest", "rtb", "engage", "conserve", "fight_on",
                "press_on", "hold", "avoid", "wait", "withdraw", "fallback", "extract", "turn_back"]
WEAK_ORDER = ["withdraw", "fallback", "rtb", "extract"]


def recognise(text):
    """'AI take over' -> True, 'I take over' -> False, anything else -> None."""
    low = " ".join(text.lower().replace(".", " ").replace("!", " ").replace(",", " ").split())
    if any(low == w or low.startswith(w + " ") or low.endswith(" " + w) or f" {w} " in f" {low} " for w in OFF_WORDS):
        return False
    if any(w in low for w in ON_WORDS):
        return True
    return None


def set_autopilot(game, on):
    if game.autopilot == on:
        return
    game.autopilot = on
    if on:
        game.think_until = 0.0                                   # the staff does not need time to think: the clock must keep running
    side = game.human
    if on:
        agents.radio(game, side, "in", "GENERAL-STAFF", "Understood, sir. The staff has command. President, intelligence chief, economy and foreign ministers are all on the job. "
                     "Type 'I take over' when you want it back.")
        game.say("AI TAKE OVER: the staff is playing for Ladooo.")
        game.add_sfx("chime")
    else:
        agents.radio(game, side, "in", "GENERAL-STAFF", "Command is yours again, sir. All stations, the General is back.")
        game.say("The General took command back from the staff.")
        game.add_sfx("chime")
    game.bump()


def tick(game):
    """Called every tick."""
    if game.winner:
        return
    red = OTHER[game.human]
    if game.t < game.passive_until and not game.autopilot:     # the other side's ministers wait while it is passive too
        return
    if game.t % 15 == 3:
        _economy(game, red, speak=False)
    if game.t % 30 == 7:
        _foreign(game, red, speak=False)
        _red_politics(game, red)
    if not game.autopilot:
        return
    me = game.human
    ai_red.think(game, me)                                       # the staff plays the war
    _answer_reports(game, me)
    if game.t % 20 == 5:
        _president(game, me)
    if game.t % 25 == 11:
        _intel(game, me)
    if game.t % 15 == 3:
        _economy(game, me)
    if game.t % 30 == 7:
        _foreign(game, me)


def _red_politics(game, red):
    """Candooo's foreign minister also plays the shadow war: designates our forces as militants, accuses us, and calls its allies in."""
    from . import occupation
    me = game.human
    if game.t < 120:
        return
    if not game.designated[red] and (occupation.justified(game, red) or game.t > 450):
        msg = occupation.designate(game, red)
        _say(game, me, "HQ-Radio", "NEWS: Candooo has designated Ladooo's armed forces a militant group. " + ("Its allies may now join in." if world.allies(game, red) else ""))
    if "invasion" not in {c for s, c in game.accused if s == red} and occupation.evidence(game, red, "invasion"):
        occupation.accuse(game, red, "invasion")
        _say(game, me, "HQ-Radio", "NEWS: Candooo accuses Ladooo of invading its territory and appeals to the neighbours. Sanctions fall on us.")
    if game.designated[red]:
        for nid in world.allies(game, red):
            out = occupation.ally_strike(game, red, nid)
            if "struck" in out:
                _say(game, me, "HQ-Radio", "ENEMY ALLIED STRIKE: " + out)
                game.add_sfx("alarm")
                break


def _say(game, side, who, text, speak=True):
    if speak and side == game.human:
        agents.radio(game, side, "in", who, text)


def _answer_reports(game, side):
    for rep in list(game.reports):
        if game.t - rep["t"] < 2:                                # a moment to read, like a person
            continue
        u = game.unit_by_id(rep["uid"])
        ids = [o["id"] for o in rep["options"]]
        if rep["kind"] == "plot":
            h = game.home[side]
            pick = "pay_off" if h["economy"] >= 40 and h["corruption"] < 60 else "arrest"
        else:
            weak = u is not None and u.hp * 2 <= u.max_hp
            pick = next((o for o in (WEAK_ORDER if weak else []) + REPORT_ORDER if o in ids), ids[0])
        label = next(o["label"] for o in rep["options"] if o["id"] == pick)
        _say(game, side, "GENERAL-STAFF", f"{rep['callsign']}: {label}.")
        game.choose(side, rep["id"], pick)


def _president(game, side):
    if not homefront.active(game):
        return
    h = game.home[side]
    pick = None
    if h["stability"] < 38 and h["economy"] > 20:
        pick = "pay"
    elif h["corruption"] > 55:
        pick = "purge"
    elif h["unrest"] > 70 and h["stability"] > 25:
        pick = "crackdown"
    if pick and not homefront.cooldown_left(game, pick):
        msg = homefront.action(game, side, pick)
        _say(game, side, "PRESIDENT", f"I have ordered: {homefront.INTERNAL[pick]['label'].lower()}. {msg}")


def _intel(game, side):
    if not homefront.active(game):
        return
    foe = game.home[OTHER[side]]
    pts = game.intel_points[side]
    pick = None
    if foe["stability"] < 30 and pts >= 4:
        pick = "coup"
    elif pts >= 2 and foe["economy"] > 25:
        pick = "markets"
    elif pts >= 1 and foe["stability"] > 30:
        pick = "leak" if foe["unrest"] > 50 else "fund"
    if pick and not homefront.cooldown_left(game, pick):
        msg = homefront.action(game, side, pick)
        _say(game, side, "INTEL-CHIEF", f"Operation '{homefront.COVERT[pick]['label'].lower()}': {msg}")


def _free_site(game, side):
    cols = range(1, 6) if side == "blue" else range(14, 19)
    for r in (11, 10, 9, 12, 8, 7):
        for c in cols:
            if (game.board.terrain(c, r) in ("plains", "coast") and not game.unit_at(c, r) and (c, r) not in game.facilities
                    and (c, r) not in game.objectives and (c, r) not in game.mines):
                return c, r
    return None


def _economy(game, side, speak=True):
    ind = game.industry[side]
    h = game.home[side] if homefront.active(game) else None
    # export policy follows the markets and the stores
    sup = game.supply[side]
    want = ind["export"]
    if sup["fuel"] < 35 or sup["food"] < 35:
        want = 0
    elif h and h["economy"] < 35:
        want = 2
    elif h and h["economy"] > 70:
        want = 1
    if want != ind["export"]:
        _say(game, side, "ECONOMY-MIN", industry.set_export(game, side, want), speak)
    # a builder puts up another factory when there is money
    n = industry.factories(game, side)
    if n < 3 and (not h or h["economy"] > 40):
        site = _free_site(game, side)
        builders = [u for u in game.units if u.team == side and u.type == "builder" and u.hp > 0 and not u.job and not u.plan and not u.path]
        if site and builders:
            game.work(side, builders[0].id, "factory", site)
            _say(game, side, "ECONOMY-MIN", f"Builder sent to open a factory at {grid(*site)}.", speak)
            return
    # and spends production points on what the army lacks
    army = [u for u in game.units if u.team == side and u.hp > 0]
    tanks = sum(1 for u in army if u.type == "tank")
    want_kind = "tank" if tanks < 3 else "anti_air" if not any(u.type == "anti_air" for u in army) else "infantry"
    cost = industry.PRODUCTS[want_kind]
    if ind["ip"] >= cost + 2 and len(ind["orders"]) < 2:
        msg = industry.produce(game, side, want_kind)
        _say(game, side, "ECONOMY-MIN", msg, speak)


def _foreign(game, side, speak=True):
    if game.winner:
        return
    foe = OTHER[side]
    allies = world.allies(game, side)
    # use what allies can give
    losing = game.war_status(side)["verdict"] in ("losing", "lost") if side == game.human else False
    for nid in allies:
        for what in (("volunteers", "airlift", "intel") if losing else ("intel", "airlift")):
            if what in game.world[nid]["used"] or game.world[nid]["cd"].get(what, 0) > game.t:
                continue
            msg = world.act(game, side, nid, what)
            _say(game, side, "FOREIGN-MIN", msg, speak)
            return
    # otherwise court the neighbour that is nearest to becoming an ally and is not firmly the enemy's
    cands = sorted((n for n in world.NEIGHBORS if world.relation(game, n, side) < 70 and world.relation(game, n, side) >= world.relation(game, n, foe) - 10),
                   key=lambda n: -world.relation(game, n, side))
    for nid in cands:
        for what in ("aid", "diplomacy"):
            if game.world[nid]["cd"].get(what, 0) <= game.t:
                if homefront.active(game) and game.home[side]["economy"] < 30:
                    break
                msg = world.act(game, side, nid, what)
                _say(game, side, "FOREIGN-MIN", msg, speak)
                return
    # surplus production goes on arms sales
    if industry.factories(game, side) and game.industry[side]["ip"] >= 9 and allies + cands:
        nid = (allies + cands)[0]
        msg = world.act(game, side, nid, "sale")
        _say(game, side, "FOREIGN-MIN", msg, speak)
