"""A scripted timeline of events for a historical scenario (level kind "timeline"), told with fictional nations.

Pattern: a country keeps a nuclear test secret from foreign satellites. The story, in game time:

  crash      the Prime Minister and the chief weapons scientists are lost in an air crash over the high mountains. Cause unclear.
  successor  the new Prime Minister orders the long-planned test to go ahead (a decision: investigate the crash first, or press on)
  satellites foreign satellites pass over the test site in short windows: any prep work seen in a window gives it away
  test       the test happens after 90 s of preparation. Seen: sanctions and condemnation. Unseen: the world learns afterwards.
  summit     the Prime Minister goes abroad to a summit. An assassination attempt is planned. If two foreign services we are
             on good terms with (relation 50+) pass on warnings, it is stopped; one warning halves the damage; none and he is killed
  found_dead after the summit the Prime Minister is found dead in a neighbouring country: cause disputed. A succession crisis tests the government.

Nothing here claims what happened in any real country; it is a game timeline built from a pattern.
"""
from . import agents, homefront, world
from .board import ref as grid

PREP_SECS = 90
COVER_SECS = 25
COVER_CD = 35
SAT_FIRST = 150
ORBITS = (dict(name="Eye-1", period=70, length=20, phase=SAT_FIRST), dict(name="Eye-2", period=110, length=15, phase=SAT_FIRST + 30))


def sat_active(game, ahead=0):
    """Is a foreign satellite over the test site (in `ahead` seconds)? Each one follows its own orbit."""
    t = game.t + ahead
    tl = game.tl
    if tl and t < tl["sat_until"]:
        return True
    return any(t >= o["phase"] and (t - o["phase"]) % o["period"] < o["length"] for o in ORBITS)

EVENTS = {
    "crash": dict(at=90, title="Air crash in the mountains", known=False),
    "successor": dict(at=130, title="The successor decides", known=False),
    "test": dict(at=0, title="The test", known=False),
    "summit": dict(at=520, title="Summit abroad", known=True),
    "found_dead": dict(at=640, title="Prime Minister found dead abroad", known=False),
}


def setup(game, lv):
    game.tl = None
    keys = lv.get("timeline") or []
    if not keys:
        return
    game.tl = dict(keys=list(keys), done={}, stage="idle", prep=0, seen=0, cover_until=0, cover_cd=0, sat_until=0, next_sat=SAT_FIRST,
                   tested=False, detected=False, summit="", dead=False, pending=None)


def _say(game, text, alert=False):
    game.say(text)
    agents.radio(game, game.human, "in", "HQ-Radio", text)
    if alert:
        game.add_sfx("alarm")


def _any_unit(game):
    mine = [u for u in game.units if u.team == game.human and u.hp > 0 and u.type != "supply_ship"]
    return mine[0] if mine else None


def tick(game):
    tl = getattr(game, "tl", None)
    if not tl or game.winner:
        return
    t, me = game.t, game.human
    h = game.home[me] if homefront.active(game) else None
    # scheduled events
    if "crash" in tl["keys"] and "crash" not in tl["done"] and t >= EVENTS["crash"]["at"]:
        tl["done"]["crash"] = t
        if h:
            h["stability"] = max(0, h["stability"] - 8)
            h["unrest"] = min(100, h["unrest"] + 4)
        _say(game, "NEWS: the Prime Minister and the chief weapons scientists are lost when their aircraft goes down over the high mountains. The cause is unclear: weather, a fault, or sabotage.", True)
    if "successor" in tl["keys"] and "successor" not in tl["done"] and t >= EVENTS["successor"]["at"]:
        tl["done"]["successor"] = t
        u = _any_unit(game)
        if u:
            agents.open_report(game, u, "timeline", "Sir, the new Prime Minister wants to go ahead with the test at the mountain site. The wreckage inquiry is not finished.",
                               [dict(id="tl:probe", label="Investigate the crash first (1 intelligence point; may expose a foreign hand, costs time)"),
                                dict(id="tl:press", label="Press on with the test plan")])
            tl["pending"] = True
        else:
            tl["stage"] = "ordered"
    # satellite windows once the test is ordered
    if tl["stage"] in ("ordered", "prep"):
        for o in ORBITS:
            if t >= o["phase"] and (t - o["phase"]) % o["period"] == 0:
                _say(game, f"SATELLITE: {o['name']} is passing over the test site for the next {o['length']} s. Anything under way is visible. Run the cover story.")
    # test preparation
    if tl["stage"] == "prep":
        tl["prep"] += 1
        if sat_active(game) and t >= tl["cover_until"]:
            tl["seen"] += 1
            if tl["seen"] == 1:
                _say(game, "WARNING: the satellite saw preparation at the site. One more minute of that and the secret is gone.", True)
        if tl["seen"] >= 10:
            tl["detected"] = True
        if tl["prep"] >= PREP_SECS:
            _test(game, tl)
    # summit and its aftermath
    if "summit" in tl["keys"] and "summit" not in tl["done"] and t >= EVENTS["summit"]["at"]:
        tl["done"]["summit"] = t
        _summit(game, tl)
    if "found_dead" in tl["keys"] and "found_dead" not in tl["done"] and t >= EVENTS["found_dead"]["at"]:
        tl["done"]["found_dead"] = t
        tl["dead"] = True
        if h:
            h["stability"] = max(0, h["stability"] - 10)
            h["unrest"] = min(100, h["unrest"] + 8)
        game.news.append((t, "The Prime Minister is found dead in a residence abroad. Officials of three countries give three different accounts."))
        _say(game, "NEWS: the Prime Minister was found dead in a neighbouring country after the summit. The cause is disputed. Hold the government together.", True)


def _test(game, tl):
    me = game.human
    h = game.home[me] if homefront.active(game) else None
    tl["stage"] = "done"
    tl["tested"] = True
    game.deterrents = set(game.__dict__.get("deterrents", ())) | {me}
    game.deterrent = True                                           # the test changes the war: our weapons count for more, theirs hesitate
    for u in game.units:
        if u.team != me and not u.air:
            u.morale = max(0.0, u.morale - 12)
    game.add_sfx("rumble")
    if tl["detected"]:
        game.sanctions[me] = game.sanctions.get(me, 0) + .008
        for nid in world.NEIGHBORS:
            world.shift(game, nid, me, -8)
        if h:
            h["stability"] = max(0, h["stability"] - 4)
        _say(game, "THE TEST WENT AHEAD, but the satellites had seen the preparation. Sanctions follow and neighbours condemn it.", True)
    else:
        if h:
            h["stability"] = min(100, h["stability"] + 8)
            h["economy"] = max(0, h["economy"] - 2)
        game.sanctions[me] = game.sanctions.get(me, 0) + .003
        for nid in world.NEIGHBORS:
            world.shift(game, nid, me, -3)
        _say(game, "THE TEST WENT AHEAD, unseen: the satellites were fooled by the cover activity. The world learns only afterwards. Stability up; mild sanctions follow.", True)


def _summit(game, tl):
    me = game.human
    h = game.home[me] if homefront.active(game) else None
    warners = [nid for nid in world.NEIGHBORS if world.relation(game, nid, me) >= 50]
    n = len(warners)
    names = ", ".join(world.NEIGHBORS[w]["name"] for w in warners[:2])
    if n >= 2:
        tl["summit"] = "foiled"
        _say(game, f"SUMMIT: an assassination attempt on the Prime Minister was stopped. Warnings from the intelligence services of {names} reached us in time.")
    elif n == 1:
        tl["summit"] = "wounded"
        if h:
            h["stability"] = max(0, h["stability"] - 6)
        _say(game, f"SUMMIT: an assassination attempt wounded the Prime Minister. Only one friendly service ({names}) warned us, and too late to stop it.", True)
    else:
        tl["summit"] = "killed"
        if h:
            h["stability"] = max(0, h["stability"] - 25)
            h["unrest"] = min(100, h["unrest"] + 15)
        _say(game, "SUMMIT: the Prime Minister was assassinated. No friendly service had warned us. The government is in crisis.", True)


def resolve(game, side, option):
    """The General's answer to the successor's report."""
    tl = game.tl
    tl["pending"] = None
    tl["stage"] = "ordered"
    if option == "tl:probe":
        if game.intel_points[side] >= 1:
            game.intel_points[side] -= 1
        if game.rng.random() < .5:
            nid = "brevik"
            world.shift(game, nid, side, -15)
            _say(game, f"The inquiry found signs of sabotage with a foreign hand behind it. Relations with {world.NEIGHBORS[nid]['name']} fell sharply. The test plan goes ahead.")
        else:
            _say(game, "The inquiry found nothing conclusive: a fault and bad weather. The test plan goes ahead, a little late.")
        game.tl["next_sat"] = max(game.tl["next_sat"], game.t + 30)
    else:
        _say(game, "The Prime Minister presses on. The test plan goes ahead at once.")


def action(game, side, what):
    tl = game.tl
    if not tl:
        return "No timeline in this level."
    if what == "prepare":
        if tl["stage"] != "ordered":
            return "The test is not ready to prepare (or is already done)."
        tl["stage"] = "prep"
        return f"Preparation of the test begins: {PREP_SECS} s of work at the mountain site. Satellite windows will come: run the cover story during them."
    if what == "cover":
        if tl["stage"] not in ("ordered", "prep"):
            return "No cover story is needed now."
        if game.t < tl["cover_cd"]:
            return f"The cover story is not ready for {int(tl['cover_cd'] - game.t)} s."
        tl["cover_until"] = game.t + COVER_SECS
        tl["cover_cd"] = game.t + COVER_CD
        if homefront.active(game):
            game.home[side]["economy"] = max(0, game.home[side]["economy"] - 3)
        return f"Cover story running for {COVER_SECS} s: a loud military exercise and decoy trucks at the site. The satellites see what we want."
    return "Unknown."


def outcome(game):
    """(winner, reason, title) when time runs out."""
    tl = game.tl
    if not tl:
        return None
    st = game.home[game.human]["stability"] if homefront.active(game) else 100
    if tl["tested"] and st >= 25 and tl["summit"] != "killed":
        return "blue", "The test was carried out, the Prime Minister's succession held, and the government survived the crisis.", "Programme complete"
    if not tl["tested"]:
        return "red", "The test never happened before the window closed.", "Programme stalled"
    return "red", "The test was done, but the government did not survive the succession crisis.", "Succession crisis"


def panel(game):
    tl = getattr(game, "tl", None)
    if not tl:
        return None
    t = game.t
    rows = []
    for key in tl["keys"]:
        ev = EVENTS.get(key)
        if not ev:
            continue
        if key in tl["done"]:
            rows.append(dict(key=key, title=ev["title"], state="done", when=int(tl["done"][key])))
        elif ev["known"]:
            rows.append(dict(key=key, title=ev["title"], state="scheduled", when=ev["at"], left=max(0, ev["at"] - t)))
        else:
            rows.append(dict(key=key, title="?", state="unknown", when=None))
    sat_left = 0
    while sat_left < 200 and sat_active(game, sat_left):
        sat_left += 1
    orbits = []
    for o in ORBITS:
        k = (t - o["phase"]) % o["period"] if t >= o["phase"] else None
        orbits.append(dict(name=o["name"], over=k is not None and k < o["length"],
                           eta=(o["phase"] - t) if k is None else (0 if k < o["length"] else o["period"] - k)))
    return dict(orbits=orbits, deterrent=bool(getattr(game, "deterrent", False)), rows=rows, stage=tl["stage"], prep=int(100 * tl["prep"] / PREP_SECS), sat_left=int(sat_left),
                cover_left=int(max(0, tl["cover_until"] - t)),
                cover_cd=int(max(0, tl["cover_cd"] - t)), seen=tl["seen"], detected=tl["detected"], tested=tl["tested"], summit=tl["summit"], dead=tl["dead"],
                can_prepare=tl["stage"] == "ordered", can_cover=tl["stage"] in ("ordered", "prep") and t >= tl["cover_cd"])


RED_TEST_SITE = (19, 12)
RED_PREP_AT, RED_TEST_AT = 300, 390


def red_test(game):
    """Candooo prepares its own test at a remote site. Our spy or UAV close to the site while it prepares exposes it."""
    tl = getattr(game, "tl", None)
    if not tl or game.winner:
        return
    me = game.human
    foe = "red" if me == "blue" else "blue"
    rt = tl.setdefault("red", dict(stage="idle", seen=False))
    if rt["stage"] == "idle" and game.t >= RED_PREP_AT:
        rt["stage"] = "prep"
    if rt["stage"] == "prep":
        watchers = [u for u in game.units if u.team == me and u.hp > 0 and u.type in ("spy", "uav") and abs(u.c - RED_TEST_SITE[0]) + abs(u.r - RED_TEST_SITE[1]) <= 4]
        if watchers and not rt["seen"]:
            rt["seen"] = True
            game.sanctions[foe] = game.sanctions.get(foe, 0) + .008
            for nid in world.NEIGHBORS:
                world.shift(game, nid, me, 4)
            _say(game, f"INTELLIGENCE: {watchers[0].callsign} saw preparations at a remote site near {grid(*RED_TEST_SITE)}: Candooo is preparing a nuclear test. We have told the neighbours. Sanctions fall on Candooo.", True)
        if game.t >= RED_TEST_AT:
            rt["stage"] = "done"
            game.deterrents = set(game.__dict__.get("deterrents", ())) | {foe}
            game.add_sfx("rumble")
            if homefront.active(game):
                game.home[me]["stability"] = max(0, game.home[me]["stability"] - (2 if rt["seen"] else 5))
            for u in game.units:
                if u.team == me and not u.air:
                    u.morale = max(0.0, u.morale - (6 if rt["seen"] else 12))
            _say(game, "CANDOOO HAS TESTED A NUCLEAR DEVICE" + (" (we had warned of it)." if rt["seen"] else ", and we did not see it coming. Our troops are shaken.") + " Its weapons now count for more.", True)


def news_tick(game):
    """Scripted headlines for historical levels (level key `news`): (time, text, effects). Effects: stab, econ (our government), foe_stab, rel (neighbour, change)."""
    from . import levels
    items = levels.LEVELS[game.level_id].get("news") or []
    done = game.__dict__.setdefault("news_done", set())
    for i, (at, text, fx) in enumerate(items):
        if i in done or game.t < at:
            continue
        done.add(i)
        me, foe = game.human, "red" if game.human == "blue" else "blue"
        if homefront.active(game):
            game.home[me]["stability"] = max(0, min(100, game.home[me]["stability"] + fx.get("stab", 0)))
            game.home[me]["economy"] = max(0, min(100, game.home[me]["economy"] + fx.get("econ", 0)))
            game.home[foe]["stability"] = max(0, min(100, game.home[foe]["stability"] + fx.get("foe_stab", 0)))
            game.home[foe]["economy"] = max(0, min(100, game.home[foe]["economy"] + fx.get("foe_econ", 0)))
        if "rel" in fx:
            world.shift(game, fx["rel"][0], me, fx["rel"][1])
        game.news.append((game.t, text))
        _say(game, "NEWS: " + text, abs(fx.get("stab", 0)) >= 5)
