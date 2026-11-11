"""Every unit is an agent that talks to its General over radio.

The human General can: ask for status, receive reports that need a decision (problem + choices),
give orders by chat ("Anvil-1 move to Echo-6", "all hold fire") or by Morse code, and just talk.
This module is the built-in rule-based voice. The browser can swap in WebLLM for open conversation
(see `llm_request`), but orders always go through the same validated commands here.
"""
import math
import random
import re
import time

from . import morse, rules
from .board import PHONETIC
from .board import ref as grid
from .units import ABILITIES, ATTACK, CALLSIGN, MISSILE_TYPES, STATS, VISION

CALLSIGNS = set(CALLSIGN.values())

# Seconds the General has to decide before the unit acts on its own. Urgent matters have short fuses.
REPORT_TTL = {"contact": 40, "damaged": 45, "airraid": 20, "gas": 15, "flood": 30, "bingo": 25, "plot": 40}   # urgent kinds (game seconds)
DEFAULT_TTL = 60
DECISION_WINDOW = {"scramble": 40, "masks": 40, "evacuate": 60, "flood_out": 40, "rtb": 60, "engage": 60, "hold": 30, "conserve": 30, "withdraw": 90, "fallback": 90, "fight_on": 30, "clear_mine": 80,
                   "rebuild": 90, "extract": 120, "wait": 120, "escort": 120, "turn_back": 5}
SHAKEN_SECS = 15         # an unanswered contact or damage report leaves the unit caught unprepared this long
CONTACT_COOLDOWN = 30    # do not report the same enemy again within this many seconds
MAX_OPEN_CONTACTS = 3
REF_RE = re.compile(r"\b(" + "|".join(p.lower() for p in PHONETIC) + r")[\s-]?(\d{1,2})\b")
ACK_POOL = {
    "calm": ["Copy that.", "Roger that.", "Wilco."],
    "eager": ["Roger that, sir!", "Copy, moving now!", "Wilco, on it!"],
    "cautious": ["Copy that, proceeding with caution.", "Roger. Eyes open.", "Understood, wilco."],
}


# ---------- radio log ----------
def radio(game, side, direction, who, text, kind="voice", morse_text=None):
    """Log one radio message. direction: 'in' = heard by the General, 'out' = sent by the General."""
    game.seq += 1
    entry = dict(id=game.seq, t=game.t, side=side, dir=direction, who=who, text=text, kind=kind,
                 morse=morse_text if morse_text is not None else morse.encode(text))
    game.radio.append(entry)
    del game.radio[:-200]
    return entry


def say(game, u, text, kind="voice", urgent=False):
    """A unit speaks to the General. Answers take a moment (more if supplies are short); emergencies do not wait."""
    if u.team == game.human:
        game.queue_radio(0 if urgent else game.reply_delay(u), u.callsign, text, kind)


def ack(u, what=""):
    """A radio acknowledgement in the unit's own manner: 'Copy that. Moving to Echo-6, ETA 40 sec.'"""
    phrase = random.Random(u.id + what).choice(ACK_POOL[u.temperament])
    return f"{phrase} {what}." if what else phrase


def clock(u, c, r):
    """Where (c, r) lies relative to the way the unit faces, as a clock position: 12 = dead ahead, 3 = right."""
    rel = (math.degrees(math.atan2(r - u.r, c - u.c)) - u.heading) % 360
    return int(round(rel / 30)) % 12 or 12


def hit_report(game, u, friendly=False):
    """The unit tells the General it is being hit. Friendly fire and sinking get their own calls."""
    if friendly and game.t - u.note_at >= 6:
        u.note_at = game.t
        say(game, u, "Friendly fire! Friendly fire! Check your fire, sir! Taking hit, HP %d/%d." % (u.hp, u.max_hp), urgent=True)
    elif game.t - u.note_at >= 6:
        u.note_at = game.t
        say(game, u, f"Taking hit! HP {u.hp}/{u.max_hp}.", urgent=True)
    if u.stats["domain"] == "sea" and u.hp * 4 <= u.max_hp and "sinking" not in u.flags:
        u.flags.add("sinking")
        say(game, u, f"We're sinking! CODE RED, CODE RED! Requesting extraction at {grid(u.c, u.r)}.", urgent=True)
        game.add_sfx("alarm")


def missile_alert(game, launcher, c, r):
    """An enemy missile is inbound near our units: radar warning with the time to impact."""
    if launcher.team == game.human:
        return
    near = [u for u in own_units(game, game.human) if abs(u.c - c) + abs(u.r - r) <= 3]
    if near:
        radio(game, game.human, "in", "HQ-Radio", f"CODE RED! CODE RED! Inbound missile, impact {grid(c, r)} in 6 sec. "
              f"{', '.join(u.callsign for u in near[:3])}: move clear!")
        game.add_sfx("alarm")


# ---------- small helpers ----------
def parse_ref(board, text):
    m = REF_RE.search(text.lower())
    if not m:
        return None
    c, r = [p.lower() for p in PHONETIC].index(m.group(1)), int(m.group(2)) - 1
    return (c, r) if board.inside(c, r) else None


NUM_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "niner": 9, "fife": 5}


def normalize(text):
    """Make spoken or sloppy text readable by the command parser: 'anvil one' -> 'Anvil-1', 'echo seven' -> 'echo 7'."""
    words = re.sub(r"\b(" + "|".join(NUM_WORDS) + r")\b", lambda m: str(NUM_WORDS[m.group(1).lower()]), text, flags=re.I)
    names = "|".join(sorted({c for c in CALLSIGNS}, key=len, reverse=True))
    return re.sub(r"\b(" + names + r")[\s-]+(\d{1,2})\b", lambda m: f"{m.group(1).capitalize()}-{m.group(2)}", words, flags=re.I)


def label_for(game, to):
    """Radio name of the addressee: a callsign, or ALL."""
    u = game.unit_by_id(to) if to and to != "all" else None
    return u.callsign if u else (to.upper() if to and to != "all" else "ALL")


def own_units(game, side):
    return [u for u in game.units if u.team == side and u.hp > 0]


def spotted_near(game, u, extra=2):
    seen = game.detected[u.team]
    return sorted((e for e in game.units if e.id in seen and rules.dist(u, e) <= VISION[u.type] + extra), key=lambda e: rules.dist(u, e))


def nearest_own_objective(game, u):
    objs = [p for p, o in game.objectives.items() if o["owner"] == u.team]
    return min(objs, key=lambda p: abs(p[0] - u.c) + abs(p[1] - u.r), default=None)


def sitrep(game, u):
    near = spotted_near(game, u)
    line = f"HP {u.hp}/{u.max_hp}, ammo {u.ammo}, at {grid(u.c, u.r)}, {game.status(u).lower()}"
    if u.air:
        line += f", fuel {int(100 * u.fuel / u.max_fuel)}%"
    if u.mask:
        line += ", mask on"
    if u.hold_fire:
        line += ", weapons held"
    line += f". {len(near)} contact{'s' if len(near) != 1 else ''} in sight." if near else ". Nothing in sight."
    return line


def nearest_airfield(game, u):
    fields = game.airfields(u.team)
    return min(fields, key=lambda p: abs(p[0] - u.c) + abs(p[1] - u.r), default=None)


def pull_back(game, side, u):
    """Order the unit to the nearest friendly port or city (aircraft: their own airfield). Returns a reply."""
    if u.air:
        p = nearest_airfield(game, u)
        if not p:
            return "No airfield to land at, sir"
        if p == (u.c, u.r):
            return "Already on the airfield, sir"
        game.order_move(side, u, *p)
        if game.notice[side]:
            msg, game.notice[side] = game.notice[side], ""
            return msg
        u.arrive_note = True
        return ack(u, f"Returning to base at {grid(*p)}, ETA {game.eta(u, u.path)} sec, fuel {int(u.fuel)}")
    p = nearest_own_objective(game, u)
    if not p or (p == (u.c, u.r)):
        return "No safer place to fall back to, sir"
    game.order_move(side, u, *p)
    if game.notice[side]:
        msg, game.notice[side] = game.notice[side], ""
        return msg
    u.arrive_note = True
    return ack(u, f"Falling back to {grid(*p)}, ETA {game.eta(u, u.path)} sec")


# ---------- reports that need a decision ----------
def open_report(game, u, kind, text, options, eid=None, pos=None):
    game.seq += 1
    ttl = REPORT_TTL.get(kind, DEFAULT_TTL)
    foe = game.unit_by_id(eid) if eid else None
    game.reports.append(dict(id=game.seq, t=game.t, uid=u.id, callsign=u.callsign, kind=kind, text=text,
                             options=options, eid=eid, pos=pos, expires=game.t + ttl,
                             at=[u.c, u.r], foe=[foe.c, foe.r] if foe else (list(pos) if pos else None)))
    if kind in REPORT_TTL and game.pause_on_report:      # give the General real time to read the map before the clock runs on
        game.think_until = max(game.think_until, time.monotonic() + game.think_secs)
    say(game, u, text + " Request orders.", urgent=True)


def late_hit(game, u, rep):
    """The General was too slow: the enemy gets a free strike. Say exactly what it cost, and call it if the unit is dead."""
    if rep["kind"] == "gas":                       # nobody masked up in time
        hp0 = u.hp
        game._hit("Chemical cloud (no masks in time)", u, 3, None)
        game.say(f"{u.label} was gassed: no orders in time. It took 3 damage.")
        if u.hp > 0:
            say(game, u, f"GAS! No masks! We took 3 damage, HP {hp0} to {u.hp}/{u.max_hp}!", urgent=True)
        else:
            radio(game, game.human, "in", "HQ-Radio", f"LOST: {u.callsign} is DEAD, gassed while waiting for the order to mask up.")
        return
    foe = game.unit_by_id(rep.get("eid")) if rep.get("eid") else None
    if foe is None:
        foe = min((e for e in game.units if e.team != u.team and e.hp > 0), key=lambda e: rules.dist(u, e), default=None)
    near = foe is not None and rules.dist(u, foe) <= 6
    dmg = max(2, rules.damage(foe, u, game.board)) if (foe and near and ATTACK[foe.type][0] > 0) else 2
    dmg = math.ceil(dmg * 1.5)
    hp0 = u.hp
    game._hit(f"{foe.label if near else 'The enemy'} (no orders came)", u, dmg, foe.team if foe else None)
    game.say(f"{u.label} was caught unprepared: no orders in time. It took {dmg} damage.")
    if u.hp > 0:
        say(game, u, f"No orders! Caught unprepared! We took {dmg} damage, HP {hp0} to {u.hp}/{u.max_hp}!", urgent=True)
    else:
        radio(game, game.human, "in", "HQ-Radio", f"LOST: {u.callsign} is DEAD. It waited for orders that came too late ({dmg} damage on a unit with {hp0} HP).")
        game.add_sfx("alarm")


def evaluate_decisions(game):
    """Say how each of the General's choices turned out: success or failure."""
    for d in game.decisions:
        if d["status"] != "pending":
            continue
        u = game.unit_by_id(d["uid"])
        opt, age = d["option"], game.t - d["t"]

        def done(ok, why):
            d["status"], d["why"] = ("success" if ok else "failure"), why
            radio(game, game.human, "in", "HQ-Radio", f"OUTCOME of '{d['label']}': {'SUCCESS' if ok else 'FAILURE'}. {why}")
            game.add_sfx("chime" if ok else "alarm")

        if opt == "engage":
            foe = game.unit_by_id(d["eid"])
            if foe is None:
                done(True, f"{d['callsign']} destroyed the {d['foe_label']}." if u else "The target is gone, but we lost the attacker.")
            elif not u:
                done(False, f"{d['callsign']} was lost attacking the {d['foe_label']}.")
            elif age > DECISION_WINDOW[opt]:
                done(False, f"The {d['foe_label']} is still alive after {age} s.")
        elif opt in ("hold", "conserve", "fight_on"):
            if not u:
                done(False, f"{d['callsign']} was lost.")
            elif u.hp < d["hp0"]:
                done(False, f"{d['callsign']} was hit anyway ({d['hp0'] - u.hp} HP lost).")
            elif age >= DECISION_WINDOW[opt]:
                done(True, f"{d['callsign']} came through untouched.")
        elif opt in ("withdraw", "fallback"):
            if not u:
                done(False, f"{d['callsign']} was lost on the way back.")
            elif not u.path and age > 3:
                done(u.hp >= d["hp0"] - 1, f"{d['callsign']} reached safe ground with HP {u.hp}/{u.max_hp}." if u.hp >= d["hp0"] - 1 else f"{d['callsign']} got back badly hurt (HP {u.hp}/{u.max_hp}).")
            elif age > DECISION_WINDOW[opt]:
                done(False, f"{d['callsign']} never made it back in time.")
        elif opt == "clear_mine":
            if d["pos"] not in game.mines:
                done(True, f"The mine at {grid(*d['pos'])} is cleared.")
            elif age > DECISION_WINDOW[opt]:
                done(False, f"The mine at {grid(*d['pos'])} is still there.")
        elif opt == "rebuild":
            if not game.ruined_bridges:
                done(True, "The bridge is open again.")
            elif age > DECISION_WINDOW[opt]:
                done(False, "The bridge is still down.")
        elif opt == "extract":
            if not u and age > 3 and any(x["team"] == game.human for x in game.returning):
                done(True, f"{d['callsign']} was extracted and is on its way back.")
            elif not u and age > 3:
                done(False, f"{d['callsign']} was lost before the pick-up.")
            elif age > DECISION_WINDOW[opt]:
                done(False, "Extraction never came.")
        elif opt in ("wait", "escort", "turn_back"):
            if d["uid"] in game.delivered_ids:
                done(True, "The convoy got through and the supplies arrived.")
            elif opt == "turn_back" and age > DECISION_WINDOW[opt]:
                done(False, "The convoy turned back: this cargo is lost, wait for the next one.")
            elif not u and opt != "turn_back":
                done(False, "The convoy was destroyed.")
            elif age > DECISION_WINDOW[opt]:
                done(False, "The convoy is still stuck.")


def scan(game):
    """Called every tick: turn what happened into radio messages and reports for the human General."""
    h = game.human
    evaluate_decisions(game)
    for rep in list(game.reports):
        if game.t >= rep["expires"]:
            game.reports.remove(rep)
            game.resp["missed"] += 1
            u = game.unit_by_id(rep["uid"])
            if rep["kind"] == "timeline":            # the successor's question went unanswered: he presses on
                from . import timeline
                timeline.resolve(game, game.human, "tl:press")
            elif rep["kind"] == "plot":              # an officers' plot nobody answered
                from . import homefront
                homefront.plot_ignored(game)
            elif u and rep["kind"] in REPORT_TTL:    # urgent and ignored: the unit is caught unprepared and takes the hit
                u.shaken_until = game.t + SHAKEN_SECS
                late_hit(game, u, rep)
            elif u:
                say(game, u, "No orders received. Holding position.", urgent=True)
    for who, label, where in game.kia:
        radio(game, h, "in", who, f"MAYDAY MAYDAY. {label} destroyed at {where}.")
    game.kia.clear()
    mine = own_units(game, h)
    for u in mine:
        if u.arrive_note and not u.path and not u.target_id:
            u.arrive_note = False
            say(game, u, f"In position at {grid(u.c, u.r)}.")
        if "damaged" not in u.flags and u.hp * 2 <= u.max_hp:
            u.flags.add("damaged")
            open_report(game, u, "damaged", f"Heavy damage, HP {u.hp}/{u.max_hp}.",
                        [dict(id="fallback", label="Fall back to the nearest friendly port or city"),
                         dict(id="extract", label="Request extraction here (ETA 45 sec)"),
                         dict(id="fight_on", label="Fight on")])
        if u.air and "bingo" not in u.flags and u.fuel <= .35 * u.max_fuel and not (u.path and u.dest in game.airfields(u.team)):
            u.flags.add("bingo")
            open_report(game, u, "bingo", f"BINGO fuel! {int(100 * u.fuel / u.max_fuel)}% left, about {int(u.fuel)} sec of flight.",
                        [dict(id="rtb", label="Return to base now"), dict(id="press_on", label="Press on with the mission")])
        if "lowammo" not in u.flags and u.type not in MISSILE_TYPES and u.start_ammo >= 6 and u.ammo * 4 <= u.start_ammo:
            u.flags.add("lowammo")
            open_report(game, u, "lowammo", f"Low on ammunition, {u.ammo} rounds left.",
                        [dict(id="conserve", label="Hold fire to conserve ammo"),
                         dict(id="fallback", label="Fall back"),
                         dict(id="fight_on", label="Keep firing")])
    # new contacts
    new = game.detected[h] - game.prev_detected
    game.prev_detected = set(game.detected[h])
    open_contacts = sum(1 for r in game.reports if r["kind"] == "contact")
    for eid in sorted(new):
        e = game.unit_by_id(eid)
        if not e or open_contacts >= MAX_OPEN_CONTACTS or game.t - game.contact_seen.get(eid, -999) < CONTACT_COOLDOWN or not mine:
            continue
        u = min(mine, key=lambda m: rules.dist(m, e))
        game.contact_seen[eid] = game.t
        if e.air:                                              # an air raid: its own alert with its own answers
            opts = []
            if any(f.type == "fighter" and f.hp > 0 and f.ammo > 0 for f in mine):
                opts.append(dict(id="scramble", label="Scramble fighters to intercept"))
            if any(f.type == "anti_air" for f in mine):
                opts.append(dict(id="aa_free", label="Anti-air: weapons free on it"))
            opts.append(dict(id="hold", label="Take cover and hold fire"))
            open_report(game, u, "airraid", f"AIR RAID! {STATS[e.type]['label']} at my {clock(u, e.c, e.r)} o'clock, {grid(e.c, e.r)}, {rules.dist(u, e)} tiles. "
                        "Hostile aircraft overhead soon!", opts, eid=eid)
            game.add_sfx("alarm")
            open_contacts += 1
            continue
        opts = []
        if rules.can_hit(u, e) and u.ammo > 0 and (u.stats["move"] > 0 or rules.in_range(u, e)):
            opts.append(dict(id="engage", label=f"Engage the {STATS[e.type]['label'].lower()}"))
        if not u.hold_fire:
            opts.append(dict(id="hold", label="Hold fire and observe"))
        opts.append(dict(id="withdraw", label="Withdraw to the nearest friendly port or city"))
        open_report(game, u, "contact",
                    f"Contact! {STATS[e.type]['label']} at my {clock(u, e.c, e.r)} o'clock, {grid(e.c, e.r)}, {rules.dist(u, e)} tiles. "
                    "Point me to the target.", opts, eid=eid)
        open_contacts += 1
        for friend in mine:                                   # warn a nearby friend who may not have seen it
            if friend.id != u.id and rules.dist(friend, e) <= 4:
                radio(game, h, "in", u.callsign, f"{friend.callsign}, heads up: hostile {STATS[e.type]['label'].lower()} at your {clock(friend, e.c, e.r)}!")
                break
    scan_engineering(game, mine_units=mine_units(game))


def mine_units(game):
    return own_units(game, game.human)


def scan_engineering(game, mine_units):
    """Reports about mines, a destroyed bridge and blocked supply convoys."""
    h = game.human
    for uid, pos in game.new_mines[h]:
        u = game.unit_by_id(uid)
        if u and not any(r["kind"] == "mine" and r.get("pos") == pos for r in game.reports):
            workers = [w for w in mine_units if "clear" in ABILITIES.get(w.type, [])]
            opts = [dict(id="avoid", label="Mark it and steer round it")]
            if workers:
                opts.insert(0, dict(id="clear_mine", label=f"Clear it ({min(workers, key=lambda w: rules.dist(w, u)).callsign} goes)"))
            open_report(game, u, "mine", f"Mine found at {grid(*pos)}!", opts, pos=pos)
    game.new_mines[h].clear()
    if game.bridge_event:
        pos, game.bridge_event = game.bridge_event, None
        radio(game, h, "in", "HQ-Radio", f"The bridge at {grid(*pos)} was destroyed. The causeway is cut.")
        builders = [w for w in mine_units if w.type == "builder"]
        if builders:
            b = min(builders, key=lambda w: abs(w.c - pos[0]) + abs(w.r - pos[1]))
            open_report(game, b, "bridge", f"The bridge at {grid(*pos)} is down. I can rebuild it in about 15 s.",
                        [dict(id="rebuild", label="Rebuild the bridge"), dict(id="leave", label="Leave it for now")])
    for u in mine_units:
        if u.type != "supply_ship" or "blocked" in u.flags or u.blocked_since is None or game.t - u.blocked_since < 8:
            continue
        u.flags.add("blocked")
        opts = [dict(id="wait", label="Wait for the strait to clear"), dict(id="escort", label="Send the nearest warship to clear the way"),
                dict(id="turn_back", label="Turn back and try the next convoy")]
        open_report(game, u, "convoy", "The strait is blocked. Fuel and food are held up.", opts)


# ---------- clues about hidden last-resort sites ----------
def nuke_clue(game, u, level, site, fuzzy):
    dx, dy = site["c"] - u.c, site["r"] - u.r
    way = ("north" if dy < -1 else "south" if dy > 1 else "") + ("east" if dx > 1 else "west" if dx < -1 else "")
    if level == 1:
        say(game, u, f"Sir, heavy trucks and armed guards keep passing {('to the ' + way) if way else 'near here'}. Could be nothing, could be something big.")
    elif level == 2:
        say(game, u, f"Strange fences, cooling vents and warning signs somewhere around {grid(*fuzzy)}. Something is buried there.")
    else:
        say(game, u, f"CONFIRMED. Hardened silo at {grid(site['c'], site['r'])}, nuclear markings. It cannot be aimed, sir. Whatever it does, it does to everyone near it.")


def choose(game, side, report_id, option_id):
    rep = next((r for r in game.reports if r["id"] == report_id), None)
    if not rep or option_id not in {o["id"] for o in rep["options"]}:
        return
    game.reports.remove(rep)
    game.resp["answered"] += 1
    game.resp["total"] += game.t - rep["t"]            # how long the General took to decide
    u = game.unit_by_id(rep["uid"])
    if not u:
        return
    label = next(o["label"] for o in rep["options"] if o["id"] == option_id)
    radio(game, side, "out", u.callsign, label)
    if not any(r["kind"] in REPORT_TTL for r in game.reports):
        game.think_until = 0.0                                  # nothing urgent left: the clock runs again
    if option_id in DECISION_WINDOW:                            # remember it, to say later whether it worked
        foe = game.unit_by_id(rep["eid"]) if rep.get("eid") else None
        game.decisions.append(dict(id=rep["id"], t=game.t, uid=u.id, callsign=u.callsign, option=option_id, label=label, eid=rep.get("eid"),
                                   foe_label=STATS[foe.type]["label"].lower() if foe else "target", hp0=u.hp, pos=rep.get("pos"), status="pending", why=""))
        del game.decisions[:-40]
    if option_id == "engage":
        e = game.unit_by_id(rep["eid"])
        if e and e.id in game.detected[side]:
            game.order_attack(side, u, e)
            reply = game.notice[side] or ack(u, f"Engaging the {STATS[e.type]['label'].lower()}")
            game.notice[side] = ""
        else:
            reply = "Target lost, sir. Holding"
    elif option_id in ("hold", "conserve"):
        u.hold_fire, u.target_id = True, None
        reply = ack(u, "Holding fire")
    elif option_id in ("withdraw", "fallback"):
        reply = pull_back(game, side, u)
    elif option_id == "extract":
        game.request_extraction(side, u)
        return
    elif option_id.startswith("tl:"):
        from . import timeline
        timeline.resolve(game, side, option_id)
        return
    elif option_id in ("arrest", "pay_off"):
        from . import homefront
        radio(game, side, "in", "HQ-Radio", homefront.plot_resolve(game, option_id))
        return
    elif option_id == "rtb":
        reply = pull_back(game, side, u)
    elif option_id == "press_on":
        reply = ack(u, "Pressing on, but the tank is getting low")
    elif option_id == "masks":
        n = game.mask_up(side, True)
        reply = ack(u, f"Masks on for {n} unit{'s' if n != 1 else ''}")
    elif option_id == "evacuate":
        n = game.evacuate_gas(side)
        reply = ack(u, f"Moving {n} unit{'s' if n != 1 else ''} out, upwind")
    elif option_id == "flood_out":
        n = game.evacuate_flood(side)
        reply = ack(u, f"Moving {n} unit{'s' if n != 1 else ''} off the plain")
    elif option_id == "scramble":
        foe = game.unit_by_id(rep.get("eid"))
        jets = [f for f in own_units(game, side) if f.type == "fighter" and f.ammo > 0]
        if foe and jets and foe.id in game.detected[side]:
            f = min(jets, key=lambda m: rules.dist(m, foe))
            game.order_attack(side, f, foe)
            say(game, f, game.notice[side] or ack(f, f"Scrambling to intercept the {STATS[foe.type]['label'].lower()}"), urgent=True)
            game.notice[side] = ""
            return
        reply = "No fighter can reach it, sir"
    elif option_id == "aa_free":
        guns = [g for g in own_units(game, side) if g.type == "anti_air"]
        for g in guns:
            g.hold_fire = False
        reply = ack(u, f"Anti-air weapons free: {len(guns)} battery" + ("" if len(guns) == 1 else "s"))
    elif option_id == "clear_mine":
        pos = rep["pos"]
        workers = [w for w in own_units(game, side) if "clear" in ABILITIES.get(w.type, [])]
        if workers:
            w = min(workers, key=lambda m: abs(m.c - pos[0]) + abs(m.r - pos[1]))
            game.work(side, w.id, "clear")
            return
        reply = "Nobody here can clear it, sir"
    elif option_id == "avoid":
        reply = ack(u, "Marked. We will steer round it")
    elif option_id == "rebuild":
        game.work(side, u.id, "bridge")
        return
    elif option_id in ("wait", "leave"):
        reply = ack(u, "Waiting")
        u.flags.discard("blocked")
    elif option_id == "turn_back":
        u.hp = 0
        radio(game, side, "in", u.callsign, "Turning back. The cargo will go with the next convoy.")
        return
    elif option_id == "escort":
        near_foes = sorted((e for e in game.units if e.id in game.detected[side] and rules.dist(u, e) <= 6), key=lambda e: rules.dist(u, e))
        ships = [s for s in own_units(game, side) if s.stats["domain"] == "sea" and ATTACK[s.type][0] > 0]
        if near_foes and ships:
            s = min(ships, key=lambda m: rules.dist(m, near_foes[0]))
            game.order_attack(side, s, near_foes[0])
            say(game, s, game.notice[side] or ack(s, f"Engaging the {STATS[near_foes[0].type]['label'].lower()} to clear the strait"))
            game.notice[side] = ""
            return
        else:
            reply = "Nothing visible to shoot, sir. Probably a mine. Send divers or a minesweeper"
    else:                                              # fight_on
        u.hold_fire = False
        reply = ack(u, "Fighting on")
    say(game, u, reply)


# ---------- chat and Morse ----------
GROUPS = {   # words that address a whole kind of unit: "all tanks hold fire", "destroyers fall back"
    "tank": {"tank"}, "tanks": {"tank"}, "armour": {"tank"}, "armor": {"tank"},
    "infantry": {"infantry"}, "riflemen": {"infantry"}, "soldiers": {"infantry"}, "troops": {"infantry"},
    "artillery": {"artillery"}, "guns": {"artillery", "coastal_gun"},
    "destroyer": {"destroyer"}, "destroyers": {"destroyer"}, "cruiser": {"cruiser"}, "cruisers": {"cruiser"},
    "battleship": {"battleship"}, "battleships": {"battleship"}, "submarine": {"submarine"}, "submarines": {"submarine"}, "subs": {"submarine"},
    "divers": {"diver"}, "diver": {"diver"}, "builders": {"builder"}, "builder": {"builder"}, "diggers": {"digger"}, "digger": {"digger"},
    "miners": {"miner"}, "sappers": {"miner"}, "spies": {"spy"}, "spy": {"spy"}, "launchers": {"missile_launcher"}, "missiles": {"missile_launcher", "missile_silo"},
    "convoys": {"supply_ship"}, "convoy": {"supply_ship"}, "minesweepers": {"minesweeper"}, "minelayers": {"minelayer"},
    "ships": {"destroyer", "cruiser", "battleship", "submarine", "minesweeper", "minelayer"}, "fleet": {"destroyer", "cruiser", "battleship", "submarine"},
    "navy": {"destroyer", "cruiser", "battleship", "submarine", "minesweeper", "minelayer"},
    "army": {"tank", "infantry", "artillery", "missile_launcher"}, "ground": {"tank", "infantry", "artillery"},
    "engineers": {"diver", "digger", "builder", "miner", "minesweeper", "minelayer"},
}
HELP = ("I understand: move to <grid>, attack <target or grid>, capture <port>, hold fire / fire at will, stop, fall back, dig in, "
        "ambush, lure to <grid>, clear mines, plant mines, rebuild the bridge, build a barricade, breach, build a factory, extraction, status, ammo, where are you. "
        "To a transport helicopter: load troops, drop at <grid>, extract <callsign>. To everyone: 'AI take over' / 'I take over'.")


SECTORS = {"north": (0, 4), "centre": (5, 9), "center": (5, 9), "south": (10, 13)}


def sector_command(game, side, low):
    """'north command, hold fire' goes to a sector commander, who passes it to every unit of ours in that band of rows
    ('air command' and 'naval command' work too). Returns (units, commander name) or None."""
    for word, (lo, hi) in SECTORS.items():
        if re.search(r"\b" + word + r" command\b", low):
            return [u for u in own_units(game, side) if lo <= u.r <= hi], f"{word.upper()}-CMD"
    if re.search(r"\bair command\b", low):
        return [u for u in own_units(game, side) if u.air], "AIR-CMD"
    if re.search(r"\b(naval|sea) command\b", low):
        return [u for u in own_units(game, side) if u.stats["domain"] == "sea"], "NAVAL-CMD"
    return None


def addressed(game, side, to, text):
    """Which units a message is for, and whether it is a broadcast. Callsigns, kinds of unit ('all tanks'), or everyone."""
    mine = own_units(game, side)
    low = text.lower()
    if to and to != "all":
        picked = [u for u in mine if u.id == to or u.callsign.lower() == to.lower()]
        if picked:
            return picked, False
    named = [u for u in mine if u.callsign.lower() in low]
    if named:
        return named, False
    kinds = set().union(*(types for word, types in GROUPS.items() if re.search(r"\b" + word + r"\b", low))) if any(
        re.search(r"\b" + w + r"\b", low) for w in GROUPS) else set()
    if kinds:
        picked = [u for u in mine if u.type in kinds]
        if picked:
            return picked, len(picked) > 1
    if to == "all" or re.search(r"\b(all|everyone|all units|all stations)\b", low):
        return mine, True
    return [], False


def has(low, *words):
    """True if any of the words or phrases appears as whole words ('how are you' must not match 'how are your')."""
    return any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in words)


def _tell(game, side, u, reply_ok):
    """If the order was refused (the game left a notice), say why; otherwise give the acknowledgement."""
    if game.notice[side]:
        msg, game.notice[side] = game.notice[side], ""
        return msg
    return reply_ok


def run_command(game, side, u, text):
    """Try to read the text as an order or question for this unit. Returns the reply, or None if not understood."""
    low = text.lower()
    tgt = parse_ref(game.board, text)
    if has(low, "help", "commands", "what can you do", "what do you understand"):
        return HELP
    if has(low, "hold fire", "cease fire", "hold your fire", "dont shoot", "don't shoot"):
        u.hold_fire, u.target_id = True, None
        return ack(u, "Holding fire")
    if has(low, "fire at will", "weapons free", "open fire", "free fire"):
        u.hold_fire = False
        return ack(u, "Weapons free")
    if has(low, "fall back", "retreat", "withdraw", "pull back", "run", "go home", "return to base"):
        return pull_back(game, side, u)
    if u.type in ("transport_helicopter", "medevac_helicopter") and has(low, "load", "load troops", "pick up", "pickup", "extract", "extraction", "airlift", "drop", "insert", "land troops", "unload"):
        if has(low, "drop", "insert", "land troops", "unload", "airlift") and tgt:
            game.airlift_say(side, u, "drop", tgt)
            return ""
        who = next((x for x in game.units if x.team == side and x.callsign.lower() in low), None)
        game.airlift_say(side, u, "extract" if has(low, "extract", "extraction") else "load", (who.c, who.r) if who else None, who.id if who else None)
        return ""
    if has(low, "extraction", "extract", "pick up", "evacuate"):
        game.request_extraction(side, u)
        return ""                                   # request_extraction() calls it in over the radio
    if has(low, "return to base", "rtb", "land at base", "land now", "come home", "refuel"):
        return pull_back(game, side, u)
    if has(low, "masks off", "mask off", "gas masks off", "take off your mask", "all clear"):
        u.mask = False
        return ack(u, "Mask off")
    if has(low, "mask up", "masks on", "mask on", "gas masks", "gas mask", "put on your mask", "gas gas gas"):
        u.mask = True
        return ack(u, "Mask on. Slower, and I can't see as far")
    if has(low, "ambush", "lie in wait", "set a trap", "set trap", "wait in hiding", "hide and wait"):
        return game.set_ambush(side, u)
    if has(low, "lure", "bait", "decoy", "draw them", "attract", "drive them into", "lead them"):
        if not tgt:
            return "Where is the trap, sir? Give a grid reference, e.g. 'lure the enemy to Echo-7'"
        return game.start_lure(side, u, tgt)
    for words, kind in ((("clear mines", "clear the mines", "clear mine", "clear the mine", "sweep for mines", "demine"), "clear"),
                        (("breach", "blow the barricade", "clear the barricade", "remove the barricade"), "breach"),
                        (("build a barricade", "build barricade", "barricade", "block the road", "fortify the road"), "barricade"),
                        (("dig in", "dig a trench", "dig", "trench", "fortify"), "dig"),
                        (("plant mines", "plant a mine", "lay mines", "lay a mine", "plant mine", "lay mine", "mine the"), "plant"),
                        (("rebuild the bridge", "build the bridge", "build bridge", "fix the bridge", "repair the bridge"), "bridge"),
                        (("build a camp", "build camp", "set up camp"), "camp"),
                        (("build a factory", "build factory", "new factory", "set up a factory"), "factory")):
        if has(low, *words):
            game.work(side, u.id, kind, tgt)
            return ""                                  # work() reports for itself over the radio
    if has(low, "stop", "halt", "stand by", "hold position", "hold here", "stay put", "stay there", "hold"):
        u.path, u.dest, u.target_id, u.plan = [], None, None, None
        return ack(u, "Holding position")
    if has(low, "capture", "take", "secure", "seize", "occupy") and (tgt or has(low, "port", "city", "objective", "harbour", "harbor", "town")):
        goals = [p for p, o in game.objectives.items() if o["owner"] != u.team and game.obj_known[side].get(p) != side]
        if tgt in game.objectives:
            goal = tgt
        elif goals:
            goal = min(goals, key=lambda p: abs(p[0] - u.c) + abs(p[1] - u.r))
        else:
            return "I know of no enemy port or city to take, sir"
        game.order_move(side, u, *goal)
        u.arrive_note = True
        return _tell(game, side, u, ack(u, f"Moving to capture the {game.objectives[goal]['kind']} at {grid(*goal)}, ETA {game.eta(u, u.path)} sec"))
    if has(low, "attack", "fire on", "fire at", "engage", "shoot", "hit", "destroy", "strike", "kill"):
        if tgt and not has(low, "nearest"):
            e = game.unit_at(*tgt)
            if not e or e.team == u.team or e.id not in game.detected[side]:
                return f"I see nothing at {grid(*tgt)}, sir"
        else:
            kinds = [t for w, ts in GROUPS.items() if has(low, w) for t in ts if t != u.type or has(low, "my")]
            near = [e for e in spotted_near(game, u, extra=6) if rules.can_hit(u, e) and (not kinds or e.type in kinds)]
            e = near[0] if near else None
            if not e:
                return "No target in sight, sir"
        game.order_attack(side, u, e)
        return _tell(game, side, u, ack(u, f"Engaging the {STATS[e.type]['label'].lower()} at {grid(e.c, e.r)}"))
    if tgt and (has(low, "move", "go", "proceed", "advance", "head", "send", "to", "deploy", "relocate", "march", "sail", "drive", "defend", "guard", "scout", "position")
                or len(low.split()) <= 3):
        game.order_move(side, u, *tgt)
        if not game.notice[side]:
            u.arrive_note = True
        return _tell(game, side, u, ack(u, f"Moving to {grid(*tgt)}, ETA {game.eta(u, u.path)} sec"))
    if has(low, "status", "report", "sitrep", "how are you"):
        return sitrep(game, u)
    if has(low, "ammo", "ammunition"):
        return f"{u.ammo} rounds left"
    if has(low, "where are you", "where", "position"):
        return f"At {grid(u.c, u.r)}, {game.board.terrain(u.c, u.r).replace('_', ' ')}"
    if has(low, "see", "contact", "contacts", "enemy", "spot"):
        near = spotted_near(game, u)
        return ("In sight: " + "; ".join(f"{STATS[e.type]['label']} at {grid(e.c, e.r)}" for e in near[:4])) if near else "Nothing in sight"
    return None


def try_reinforce(game, side, text):
    """'reinforcements air to Delta-7', 'call naval support to Hotel-9', 'reinforcements by land' -> HQ arranges it."""
    low = text.lower()
    if not has(low, "reinforcements", "reinforcement", "reinforce", "support"):
        return False
    kind = ("air" if has(low, "air", "paratroops", "paratroopers", "helicopter") else
            "sea" if has(low, "sea", "water", "waterway", "naval", "boat", "ship") else
            "land" if has(low, "land", "ground", "convoy", "armour", "armor", "road") else None)
    if not kind:
        radio(game, side, "in", "HQ-Radio", "Which support, sir: air, sea or land?")
        return True
    tgt = parse_ref(game.board, text)
    msg = game.reinforce(side, kind, *(tgt or (None, None)))
    if not msg.startswith(("Paratroopers", "Naval", "Armoured")):
        radio(game, side, "in", "HQ-Radio", msg)
    return True


SCENARIOS = (("storm", ("storm", "gale", "bad weather")), ("defector", ("defector", "defect", "deserter")),
             ("informant", ("informant", "rumour", "rumours", "rumor", "rumors", "locals", "tip off", "tip-off", "heard anything",
                            "anything strange", "word on the street")))


def try_scenario(game, side, text, to):
    """'HQ scenario storm', 'give me a defector', 'Ghost-1 any rumours?' -> the server runs a real scenario from the game state."""
    from . import events                     # imported here: events uses this module too
    low = text.lower()
    for kind, words in SCENARIOS:
        if not has(low, *words):
            continue
        if kind != "informant" and not has(low, "scenario", "hq", "give me", "bring me", "arrange", "need"):
            continue
        msg = events.ask_scenario(game, side, kind)
        targets, broadcast = addressed(game, side, to, text)
        if targets and not broadcast and kind == "informant":
            say(game, targets[0], msg, urgent=True)
        else:
            radio(game, side, "in", "HQ-Radio", msg)
        return True
    return False


def llm_request(game, u, text):
    """Everything a language model needs to answer as this agent (facts only; it cannot give itself orders)."""
    near = "; ".join(f"{STATS[e.type]['label']} at {grid(e.c, e.r)}" for e in spotted_near(game, u)[:5]) or "none"
    facts = (f"Callsign {u.callsign}, a {STATS[u.type]['label']}. Temperament: {u.temperament}. Position {grid(u.c, u.r)}, "
             f"HP {u.hp}/{u.max_hp}, ammo {u.ammo}, current order: {game.status(u)}. Enemies in sight: {near}.")
    friends = "; ".join(f"{f.callsign} at {grid(f.c, f.r)}" for f in sorted((x for x in own_units(game, u.team) if x.id != u.id),
                                                                           key=lambda x: rules.dist(u, x))[:3]) or "none"
    recent = " | ".join(f"{e['who']}: {e['text']}" for e in game.radio[-4:] if e["side"] == u.team and e["kind"] == "voice")
    facts += f" Nearest friends: {friends}. Recent radio: {recent or 'quiet'}. We hold {sum(1 for o in game.objectives.values() if o['owner'] == u.team)} of {len(game.objectives)} ports and cities."
    system = ("You are a soldier in a wargame speaking by radio to your General. Stay in character, use brief military radio "
              "style, at most two short sentences. Use only the facts below. Never invent positions, numbers or orders, and "
              "never claim to have done something the facts do not show. If asked something you cannot know, say so briefly. "
              "Facts: " + facts)
    return dict(agent=u.id, callsign=u.callsign, system=system, user=text)


def chat(game, side, to, text, llm=False):
    """The General talks to one agent, several, or all. Returns an LLM request dict when open conversation is wanted."""
    text = normalize(text.strip()[:240])
    if not text:
        return None
    radio(game, side, "out", label_for(game, to), text)
    from . import personas
    switch = personas.recognise(text)
    if switch is not None and side == game.human:
        personas.set_autopilot(game, switch)
        return None
    if try_reinforce(game, side, text) or try_scenario(game, side, text, to):
        return None
    sc = sector_command(game, side, text.lower())
    if sc:
        units, who = sc
        if not units:
            radio(game, side, "in", who, "Sir, I have nobody in my sector.")
            return None
        done = 0
        for u in units:
            reply = run_command(game, side, u, text)
            if reply is not None:
                done += 1
                if reply:
                    say(game, u, reply)
        radio(game, side, "in", who, f"Orders passed to {done} of {len(units)} units in the sector." if done else "Sir, I could not turn that into an order. Say 'help'.")
        return None
    targets, broadcast = addressed(game, side, to, text)
    if not targets:
        radio(game, side, "in", "HQ-Radio", "Say which unit, sir. Use a callsign like Anvil-1, or 'all'.")
        return None
    handled = False
    for u in targets:
        reply = run_command(game, side, u, text)
        if reply is not None:
            if reply:
                say(game, u, reply)
            handled = True
    if handled:
        return None
    if broadcast:
        radio(game, side, "in", "HQ-Radio", "All stations copy, but no order understood. " + HELP)
        return None
    if llm:
        return llm_request(game, targets[0], text)
    say(game, targets[0], "Say again, sir? I did not catch an order. Say 'help' and I will list what I understand.")
    return None


def chat_reply(game, side, uid, text):
    """A language-model answer for one agent, added to the radio log (text only; it never executes anything)."""
    u = game.unit_by_id(uid)
    text = re.sub(r"\s+", " ", text).strip()[:240]
    if u and u.team == side and text:
        say(game, u, text)


def send_morse(game, side, raw, to="all"):
    """The General sends Morse (typed as dots and dashes, or as plain text we encode). Agents answer in Morse too."""
    raw = raw.strip()[:300]
    if not raw:
        return
    if morse.looks_like_morse(raw):
        text, code = morse.decode(raw), re.sub(r"\s+", " ", raw)
    else:
        text, code = raw.upper(), morse.encode(raw)
    radio(game, side, "out", label_for(game, to), text, kind="morse", morse_text=code)
    if try_reinforce(game, side, text) or try_scenario(game, side, text, to):
        radio(game, side, "in", "HQ-Radio", "ROGER", kind="morse")
        return
    targets, _ = addressed(game, side, to, text)
    if not targets:
        radio(game, side, "in", "HQ-Radio", "?", kind="morse")
        return
    ok = False
    for u in targets:
        reply = run_command(game, side, u, text)
        if reply is not None:
            radio(game, side, "in", u.callsign, "ROGER", kind="morse")
            ok = True
    if not ok:
        radio(game, side, "in", "HQ-Radio", "?", kind="morse")
