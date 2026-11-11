"""Builds the interactive Plotly figures for one side's browser tab.

Two views per side, both honest about fog of war (hidden things are never sent to the browser):
  "home"   your units, terrain you know, enemies you can see right now
  "enemy"  intel picture: aging enemy contacts (tactical symbols), your units as small symbols
Referee ("referee" side) gets one full-truth map.

Tile (c, r) is the square x in [c, c+1], y in [H-r-1, H-r]; row 0 is at the top.
Icons are layout images served from /icon/<name>.svg.
"""
import json
import math

import plotly.graph_objects as go
import plotly.io as pio

from game import homefront, rules, world
from game.board import NAMES, PHONETIC
from game.state import INTEL_TTL
from game.units import STATS, TEAM_LABEL


def _hp_color(frac):
    return "#4cd964" if frac > .6 else "#f2c230" if frac > .3 else "#ff3b30"


MARGIN = 1.5                                        # tiles of neighbouring countries drawn round the map
ALIAS = {}                                          # (rebels now have their own icon so the General can tell militants from the army)
GROUP ={"tank": 4, "artillery": 3, "missile_launcher": 2, "anti_air": 2, "supply_truck": 3, "medic": 2, "infantry": 2,
         "rebel": 2, "fighter": 3, "bomber": 2, "attack_helicopter": 2}                # how many pictures a full-strength unit is drawn as
PATTERNS = {1: [(0, 0)], 2: [(-.2, -.16), (.2, .16)], 3: [(-.22, -.2), (.22, -.12), (0, .22)], 4: [(-.22, -.22), (.22, -.2), (-.2, .22), (.22, .2)]}


def _sight_note(terrain):
    """A tooltip line about what this ground does to sight: high ground sees further, trees and buildings block the view."""
    e, o = rules.ELEV.get(terrain, 0.0), rules.OBST.get(terrain, 0.0)
    bits = []
    if e:
        bits.append(f"high ground (+{e:g}): units here see {int(e // 2)} tile{'s' if e // 2 != 1 else ''} further; blocks the view of lower ground behind it")
    if o:
        bits.append(f"blocks the view of anyone behind it (height {o:g})")
    return f"<br><i>{'; '.join(bits)}</i>" if bits else ""


def _members(u):
    """How many pictures a unit is drawn as: a full tank unit is four tanks, and each loss takes one away."""
    full = GROUP.get(u.type, 1)
    return max(1, min(full, math.ceil(full * max(0, u.hp) / u.max_hp)))


def _icon(typ, team, heading, sym, uid=None):
    """Icon URL. The unit id rides along so the browser can find the picture and animate it (move, turn)
    smoothly; icons always face east and the browser turns them by the heading sent in layout.meta."""
    typ = ALIAS.get(typ, typ)
    base = f"/icon/sym_{typ}_{team}.svg" if sym == "tac" else f"/icon/{typ}_{team}.svg"
    return f"{base}?u={uid}&k=1" if uid else base


def build(game, side, view="home", sym="real"):
    truth = side not in ("blue", "red")
    b = game.board
    W, H = b.width, b.height
    everything = {(c, r) for c in range(W) for r in range(H)}
    vis = everything if truth else game.vis[side]
    expl = everything if truth else game.explored[side]
    detected = {u.id for u in game.units} if truth else game.detected[side]
    shown = [u for u in game.units if truth or u.team == side or u.id in detected]
    contacts = [] if truth else game.contacts(side)
    images, shapes = [], []

    def img(source, c, r, layer="above", size=1.0, dx=0.0, dy=0.0, opacity=1.0, center=False):
        d = dict(source=source, xref="x", yref="y", sizex=size, sizey=size, layer=layer, sizing="stretch", opacity=opacity)
        if center:
            d.update(x=c + .5, y=H - r - .5, xanchor="center", yanchor="middle")
        else:
            d.update(x=c + dx, y=H - r - 1 + dy, xanchor="left", yanchor="bottom")
        return d

    # terrain: only tiles this side has ever seen
    for r in range(H):
        for c in range(W):
            # the lie of the land is on every map; what stays hidden is who is where and who holds what
            images.append(img(f"/icon/{b.terrain(c, r)}.svg", c, r, "below"))

    # objective flags (owner as last known)
    for pos, o in game.objectives.items():
        owner = o["owner"] if truth else game.obj_known[side].get(pos)
        if owner and pos in expl:
            images.append(img(f"/icon/hq_flag_{owner}.svg", pos[0], pos[1], size=.42, dx=.02, dy=.56))

    if not truth:
        route, targets, danger = game.highlights(side)
        for c, r in route:
            images.append(img("/icon/move_highlight.svg", c, r))
        for c, r in targets + danger:
            images.append(img("/icon/attack_highlight.svg", c, r))

    # mines we know about (our own, and enemy ones we found) and what we know of the hidden last-resort sites
    for c, r in game.visible_mines(side):
        if (c, r) in expl:
            images.append(img("/icon/mine.svg" if truth or game.mines.get((c, r)) == side else "/icon/mine_revealed.svg", c, r, size=.5, dx=.25, dy=.25))
    for c, r, lvl in game.nuke_markers(side):
        images.append(img("/icon/nuke_site.svg" if lvl == 3 else "/icon/nuke_clue.svg", c, r, size=.85 if lvl == 3 else 1.0, dx=.075 if lvl == 3 else 0, dy=.075 if lvl == 3 else 0))
    for cl in game.clouds:                       # chemical clouds (seen when any tile of the cloud is in sight)
        cells = {(cl["c"] + dc, cl["r"] + dr) for dc in range(-cl["radius"], cl["radius"] + 1) for dr in range(-cl["radius"], cl["radius"] + 1)
                 if abs(dc) + abs(dr) <= cl["radius"]}
        if truth or cells & vis:
            for c, r in cells:
                if b.inside(c, r) and (truth or (c, r) in expl):
                    images.append(img("/icon/gas_cloud.svg", c, r, opacity=.75))
    for fl in game.floods:                       # flood warnings are public: the plain will flood at the time shown
        if fl["stage"] == "warning" and (truth or (fl["c"], fl["r"]) in expl):
            images.append(img("/icon/flood_warning.svg", fl["c"], fl["r"], size=.8, dx=.1, dy=.1))
    for rum in game.rumors:                      # unverified tips from informants
        if truth or rum["side"] == side:
            images.append(img("/icon/rumor.svg", rum["c"], rum["r"], size=.85, dx=.075, dy=.075))
    if not truth:
        for a in game.arrivals:
            if a["team"] == side:
                images.append(img("/icon/move_highlight.svg", a["c"], a["r"]))

    meta_units = []                  # what the browser animates: id, tile, heading, current job, is it a ship
    ghost_text = dict(x=[], y=[], text=[])
    if view == "enemy":
        for u in game.units:           # own forces as small friendly symbols
            if u.team == side:
                images.append(img(_icon(u.type, u.team, 0, "tac", u.id), u.c, u.r, size=.62, center=True))
                meta_units.append(dict(id=u.id, c=u.c, r=u.r, h=0, j=u.job["kind"] if u.job else None, ship=u.stats["domain"] == "sea"))
        for u in shown:                # enemies seen right now
            if u.team != side:
                images.append(img(_icon(u.type, u.team, 0, "tac", u.id), u.c, u.r, size=.9, center=True))
                meta_units.append(dict(id=u.id, c=u.c, r=u.r, h=0, j=None, ship=u.stats["domain"] == "sea"))
        for k in contacts:             # remembered contacts fade with age
            fade = max(.3, 1 - .7 * k["age"] / INTEL_TTL)
            images.append(img(_icon(k["type"], k["team"], 0, "tac"), k["c"], k["r"], size=.9, center=True, opacity=fade))
            ghost_text["x"].append(k["c"] + .5)
            ghost_text["y"].append(H - k["r"] - .08)
            ghost_text["text"].append(f"{k['age']}s")
    else:
        for u in shown:
            n = _members(u) if sym != "tac" else 1                  # a tank unit is a group of tanks; losses thin it out
            for i, (ox, oy) in enumerate(PATTERNS[n]):
                size = .96 if n == 1 else (.62 if n == 2 else .54)
                d = img(_icon(u.type, u.team, u.heading, sym, u.id), u.c, u.r, size=size, center=True)
                d["x"] += ox
                d["y"] += oy
                images.append(d)
            meta_units.append(dict(id=u.id, c=u.c, r=u.r, h=u.heading if sym != "tac" else 0, t=u.type, n=n, mv=bool(u.path),
                                   j=u.job["kind"] if u.job and (truth or u.team == side) else None, ship=u.stats["domain"] == "sea",
                                   air=u.air, up=u.air and not (game.board.terrain(u.c, u.r) == "airfield" and not u.path)))
            if u.air and (truth or u.team == side) and sym != "tac" and (u.path or u.dest):          # the flight path out, and the way home
                pts = [(u.c + .5, H - u.r - .5)] + [(c_ + .5, H - r_ - .5) for c_, r_, _ in u.path[-1:]]
                if len(pts) > 1:
                    shapes.append(dict(type="path", path="M" + "L".join(f"{x},{y}" for x, y in pts), layer="above",
                                       line=dict(color="rgba(130,200,255,.85)", width=2, dash="dash")))
                fields = game.airfields(u.team)
                if fields and u.mission:
                    home = min(fields, key=lambda p: abs(p[0] - u.c) + abs(p[1] - u.r))
                    shapes.append(dict(type="path", path=f"M{u.c + .5},{H - u.r - .5}L{home[0] + .5},{H - home[1] - .5}", layer="above",
                                       line=dict(color="rgba(160,160,160,.55)", width=1.5, dash="dot")))
            frac = max(0, u.hp) / u.max_hp
            y0 = H - u.r - 1 + .04
            shapes.append(dict(type="rect", x0=u.c + .12, x1=u.c + .88, y0=y0, y1=y0 + .07, fillcolor="#111", line_width=0, layer="above"))
            shapes.append(dict(type="rect", x0=u.c + .12, x1=u.c + .12 + .76 * frac, y0=y0, y1=y0 + .07, fillcolor=_hp_color(frac), line_width=0, layer="above"))
            if u.job and (truth or u.team == side):     # work in progress: blue bar along the top of the tile
                done = min(1.0, (game.t - u.job["start"]) / max(1, u.job["done_at"] - u.job["start"]))
                yt = H - u.r - .16
                shapes.append(dict(type="rect", x0=u.c + .12, x1=u.c + .88, y0=yt, y1=yt + .07, fillcolor="#111", line_width=0, layer="above"))
                shapes.append(dict(type="rect", x0=u.c + .12, x1=u.c + .12 + .76 * done, y0=yt, y1=yt + .07, fillcolor="#4aa3ff", line_width=0, layer="above"))

    for e in game.effects:
        if (e["c"], e["r"]) in vis:
            images.append(img("/icon/explosion.svg", e["c"], e["r"]))

    sel = None if truth else game.selected(side)
    if sel:
        images.append(img("/icon/selected_ring.svg", sel.c, sel.r))
        tgt = game.unit_by_id(sel.target_id) if sel.target_id else None
        if tgt:
            images.append(img("/icon/selected_ring.svg", tgt.c, tgt.r))

    path = "".join(f"M0,{y}H{W}" for y in range(H + 1)) + "".join(f"M{x},0V{H}" for x in range(W + 1))
    shapes.append(dict(type="path", path=path, line=dict(color="rgba(0,0,0,.35)", width=1), layer="above"))
    # the strait and each side's supply lane (public knowledge): green = ours, red = theirs
    me = "blue" if truth else side
    for lane_side, tiles in game.lanes.items():
        pts = [(c + .5, H - r - .5) for c, r in tiles if (c, r) in expl or truth]
        if len(pts) > 1:
            shapes.append(dict(type="path", path="M" + "L".join(f"{x},{y}" for x, y in pts),
                               line=dict(color="rgba(46,204,113,.75)" if lane_side == me else "rgba(231,76,60,.75)", width=2, dash="dot"), layer="above"))

    M = 0 if view == "enemy" else MARGIN
    annotations = [dict(x=11, y=H - 12.5, text="STRAIT", showarrow=False, font=dict(size=10, color="#9fd0f0"), xanchor="center")]
    alerts = []                                  # pulsing rings the browser draws: infiltrators, coup watch, coup
    infil = {}
    if M:
        cols = world.map_colors(game, me)
        spy = truth or any(u.team == me and u.type == "spy" and u.hp > 0 for u in game.units)
        strips = {"altheia": (-M, 0, 0, H, -90), "brevik": (W, W + M, 0, H, 90), "corvane": (0, W, H, H + M, 0), "dunmark": (0, W, -M, 0, 0)}
        for nid, (x0, x1, y0, y1, ang) in strips.items():
            n = world.NEIGHBORS[nid]
            rel = world.relation(game, nid, me)
            shapes.append(dict(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=cols[nid], line=dict(color="rgba(255,255,255,.18)", width=1), layer="below"))
            label = f"{n['name'].upper()} · {world.stance(rel)} {int(rel)}"
            if rel < 20:
                label = "⚠ " + label
            if spy and not truth:
                label += f" (they: {int(world.relation(game, nid, 'red' if me == 'blue' else 'blue'))})"
            annotations.append(dict(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=label, showarrow=False, textangle=ang,
                                    font=dict(size=11, color="#ffd0ca" if rel < 20 else "#d8f3e2" if rel >= 70 else "#cfd8e0")))
        # infiltration: enemy units inside our half. Militants (irregulars) pulse orange and dashed, military infiltrators solid red
        if not truth:
            for u, kind in world.infiltrators(game, me):
                infil[(u.c, u.r)] = kind
                alerts.append(dict(c=u.c, r=u.r, color="#ff9f1c" if kind == "militant" else "#ff3b30", dash="5 4" if kind == "militant" else "", w=2.5,
                                   r0=.5, r1=.4, period=1100))
        # the seat of government: green when firm, amber when shaky, a pulsing red "coup watch" when it could fall, magenta when it fell
        if homefront.active(game):
            for s, (cc, cr) in world.CAPITAL.items():
                st = game.home[s]["stability"]
                known = truth or s == me or spy
                if game.coup and game.coup["side"] == s:
                    alerts.append(dict(c=cc, r=cr, color="#ff2bd6", dash="", w=4, r0=.7, r1=1.6, period=700))
                    annotations.append(dict(x=cc + .5, y=H - cr + .25, text="<b>COUP</b>", showarrow=False, font=dict(size=14, color="#ff2bd6"), bgcolor="rgba(20,24,29,.8)"))
                elif known and st < 25:
                    alerts.append(dict(c=cc, r=cr, color="#ff3b30", dash="", w=3.5, r0=.6, r1=.9, period=800))
                    annotations.append(dict(x=cc + .5, y=H - cr + .25, text="<b>COUP WATCH</b>", showarrow=False, font=dict(size=10, color="#ff6b5e"), bgcolor="rgba(20,24,29,.7)"))
                elif known and st < 45:
                    alerts.append(dict(c=cc, r=cr, color="#f2c230", dash="3 3", w=2, r0=.55, r1=.2, period=1600))
                if known and not (game.coup and game.coup["side"] == s):
                    annotations.append(dict(x=cc + .5, y=H - cr - .95, text="♛" + (f" {int(st)}" if known else ""), showarrow=False,
                                            font=dict(size=11, color="#6fb1ff" if s == "blue" else "#ff7d6e")))
            if game.plot_active and not truth:
                alerts.append(dict(c=world.CAPITAL[me][0], r=world.CAPITAL[me][1], color="#ffd23f", dash="2 3", w=3, r0=.7, r1=.5, period=900))

    # hover/click layer: one invisible marker per tile
    at = {(u.c, u.r): u for u in shown}
    tips = {(r_["c"], r_["r"]): r_ for r_ in game.rumors if truth or r_["side"] == side}
    ghosts = {(k["c"], k["r"]): k for k in contacts} if view == "enemy" else {}
    xs, ys, cd, txt = [], [], [], []
    for r in range(H):
        for c in range(W):
            head = f"<b>{PHONETIC[c]}-{r + 1}</b>  "
            if (c, r) not in expl:
                line = head + NAMES[b.terrain(c, r)] + "<br><i>(not scouted: we do not know who is here or who holds it)</i>"
            else:
                line = head + NAMES[b.terrain(c, r)] + _sight_note(b.terrain(c, r))
                o = game.objectives.get((c, r))
                if o:
                    owner = o["owner"] if truth else game.obj_known[side].get((c, r))
                    line += f"<br>Held by {TEAM_LABEL[owner]}" if owner else "<br>Owner unknown"
                    if o["capturer"] and (truth or (c, r) in vis):
                        line += f" · being captured {o['progress']}/8"
                u = at.get((c, r))
                if u:
                    line += (f"<br>{TEAM_LABEL[u.team]} {u.stats['label']}<br>HP {u.hp}/{u.max_hp}  Ammo {u.ammo}  Speed {u.stats['move']}  Range {u.stats['range']}"
                             + (f"  Fuel {int(100 * u.fuel / u.max_fuel)}%" if u.air else "") + (f"  Morale {int(u.morale)}" if (truth or u.team == side) else "")
                             + ("  ★ veteran" if u.vet else "") + ("  [gas mask on]" if u.mask else "")
                             + f"<br>{game.status(u) if (truth or u.team == side) else 'Spotted'}")
                    if (c, r) in infil:
                        line += ("<br><b style='color:#ff9f1c'>INFILTRATOR: militants</b> (irregulars, they hide and raid barracks and camps)" if infil[(c, r)] == "militant"
                                 else "<br><b style='color:#ff3b30'>INFILTRATOR: enemy military</b> (regular special forces behind our lines)")
                fac = game.facilities.get((c, r))
                if fac:
                    line += f"<br>{NAMES[fac['kind']]} · {TEAM_LABEL[fac['owner']] if (truth or (c, r) in vis or fac['owner'] == side) else 'owner unknown'}"
                k = ghosts.get((c, r))
                if k:
                    line += f"<br>Contact: {TEAM_LABEL[k['team']]} {STATS[k['type']]['label']}<br>Last seen {k['age']} s ago"
                tip = tips.get((c, r))
                if tip:
                    line += f"<br>Rumour (unverified): {tip['text']}"
                if not truth and (c, r) not in vis:
                    line += "<br><i>(out of sight)</i>"
            xs.append(c + .5)
            ys.append(H - r - .5)
            cd.append([c, r])
            txt.append(line)
    hover = go.Scatter(x=xs, y=ys, mode="markers", customdata=cd, hovertext=txt, hoverinfo="text",
                       marker=dict(size=30, color="rgba(0,0,0,0)"), showlegend=False)

    # fog heatmap: 0 visible, 1 remembered but not visible now, 2 never seen
    z = [[0 if (c, r) in vis else 1 if (c, r) in expl else 2 for c in range(W)] for r in range(H - 1, -1, -1)]
    fog = go.Heatmap(x=[c + .5 for c in range(W)], y=[rr + .5 for rr in range(H)], z=z, zmin=0, zmax=2, showscale=False, hoverinfo="skip",
                     colorscale=[[0, "rgba(0,0,0,0)"], [.5, "rgba(8,12,24,.45)"], [1, "rgba(8,12,24,.62)"]], xgap=0, ygap=0)
    # territory tint: ours green, enemy red (mild), for the tiles this side knows
    terr = game.territory(side)
    zt = [[{"own": 1, "enemy": 2}.get(terr.get((c, r)), 0) for c in range(W)] for r in range(H - 1, -1, -1)]
    tint = go.Heatmap(x=[c + .5 for c in range(W)], y=[rr + .5 for rr in range(H)], z=zt, zmin=0, zmax=2, showscale=False, hoverinfo="skip",
                      colorscale=[[0, "rgba(0,0,0,0)"], [.5, "rgba(46,204,113,.20)"], [1, "rgba(231,76,60,.22)"]], xgap=0, ygap=0)
    traces = [tint, fog, hover]
    if ghost_text["x"]:
        traces.append(go.Scatter(x=ghost_text["x"], y=ghost_text["y"], mode="text", text=ghost_text["text"], hoverinfo="skip",
                                 textfont=dict(color="#ffd0ca", size=10), showlegend=False))

    fig = go.Figure(traces)
    tick = dict(tickfont=dict(size=10, color="#8fa1b3"), ticks="", showgrid=False, zeroline=False, showline=False, fixedrange=True)
    fig.update_layout(
        images=images, shapes=shapes, margin=dict(l=18, r=2, t=16, b=2), dragmode=False, hovermode="closest",
        paper_bgcolor="#14181d", plot_bgcolor="#14181d", uirevision="keep",
        xaxis=dict(range=[-M, W + M], tickvals=[c + .5 for c in range(W)], ticktext=[chr(65 + c) for c in range(W)], side="top", constrain="domain", **tick),
        yaxis=dict(range=[-M, H + M], tickvals=[H - r - .5 for r in range(H)], ticktext=[str(r + 1) for r in range(H)], scaleanchor="x", scaleratio=1, **tick),
        hoverlabel=dict(bgcolor="#1f2630", font=dict(color="#e8edf2", size=13)),
        annotations=annotations,
        meta=dict(units=meta_units, W=W, H=H, M=M, wind=game.wind_info(), alerts=alerts),
    )
    return json.loads(pio.to_json(fig))
