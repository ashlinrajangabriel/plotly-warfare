# Fleet & Armor — You Are the General (Plotly + WebLLM Strategy Game)

A real-time strategy game on interactive **Plotly maps**. The war is between two **fictional nations: Ladooo (you, in the west) and Candooo (the AI, in the east)**. No real country, alliance or people are meant. **You are the General of Ladooo.** Every soldier, ship, tank, diver and spy is an **AI agent** who talks to you over radio. You ask for status, they report problems with choices, you decide, and you watch them carry it out. You can chat with any agent at any time, send **Morse code**, call **reinforcements**, and send a **spy** behind enemy lines. Candooo is run by an **AI General** with its own agents, playing by the same fog-of-war rules.

Unit and symbol styles are original and realistic in feel, and the tactical map symbols are the game's own (they do not copy any alliance's standard).

## Tech stack (strict)

| Layer | Tech | Notes |
|---|---|---|
| Game logic / state | **Python 3.10+** (standard library only) | Rules, real-time clock, combat, fog of war, agents, radio, Morse |
| Server | Python `http.server` (stdlib) | Page, JSON API, Server-Sent Events (`/api/events`). No Flask/FastAPI |
| Maps / UI | **Plotly** (`plotly` Python package + Plotly.js) | Maps, units, icons, territory tint, clicks, hovers, animation |
| Agent voices | **WebLLM** (`@mlc-ai/web-llm`, loaded in the browser) | Optional open conversation with agents; runs locally on WebGPU |
| Sound | Web Audio API (browser built-in) | All sounds synthesized in the browser: no files, no licenses |
| Glue | Plain vanilla JavaScript | No React/Vue/jQuery |

**Not allowed:** any other framework. Python dependency list is just `plotly`. Docker runs everything.

## How you play

1. **Ask for status** ("Status of all units") or wait. Agents report on their own too: contacts, damage, low ammo, arrival, losses (`MAYDAY`).
2. **Reports come with a problem and choices.** Example: *"Titan-1 reports: Contact! Battleship at Lima-13, 5 tiles away."* Choose *Engage*, *Hold fire and observe*, or *Withdraw*. You have 45 seconds; if you do not answer, the unit holds on its own.
3. **Agents execute and you watch** on the Home map and the Enemy intel map.
4. **Talk to them.** Address one unit, several, or all:
   - `Anvil-1 move to Echo-6`, `all hold fire`, `Rifle-1 fall back`, `Neptune-1 engage`
   - questions: `status`, `ammo`, `where are you`, `what do you see`
   - anything else is open conversation. With the optional **AI voice (WebLLM)** the agent answers in character from the facts it knows. WebLLM only talks; orders always go through the same validated commands, so a model can never cheat.
5. **Morse code.** Type text or dots and dashes, and the game shows exactly what was sent and received, as letters and as Morse. Units understand Morse orders and answer `ROGER` in Morse. The `▶` button (or the *sound* checkbox) plays the beeps.
6. **Territory.** Land you hold is tinted **green**, enemy land **red**, whoever holds the nearest port or city. Capturing an objective flips the land around it.

## How the war is won or lost

A **War status** panel always shows the balance and why. Four measures, weighted: ports and cities held (40%), land held (20%), fighting strength (30%), fuel and food (10%). It says *winning / even / losing / lost*, names your strongest and weakest measure, and a *How the war is won or lost* checklist lists the victory conditions and the ways you can lose.

**You win by:** total takeover (capture every enemy port and city and cross over into the enemy half), destroying every enemy unit, or starving the enemy: if Candooo has no fuel and no food for 90 seconds its army collapses.
**You lose by:** the same things happening to you, or by **conceding**.

### The strait: fuel and food
Fuel and food reach each side through a narrow **strait in the south** (columns K–L). Each side has its own dotted lane. A **supply convoy** (a real ship, with its own agent, `Convoy-1`) sails through every 70 seconds and delivers 25 fuel and 25 food. Units burn supplies all the time.
- If a convoy is **blocked** (enemy ships, mines, your own traffic), `Convoy-1` reports and offers: *wait*, *send the nearest warship to clear the way*, or *turn back*.
- When supplies run low, **units respond late**: orders reach them 4 s late under 30%, 10 s under 10%, 15 s at zero, and ships and troops slow down. The same happens to Candooo, so cutting its lane is a real strategy.

### The last resort
Nuclear weapons are the last resort and the game treats them gravely.
- **Hidden silos:** two sites are placed at random each game and are not shown. Units that pass near pick up clues: a *rumour* within 7 tiles (heavy trucks and guards to the north-east...), an *approximate area* within 4 (fences, vents, warning signs), a *confirmed silo* within 2. Spies sense it from 3 tiles further.
- **Cannot be aimed.** A silo cannot target anybody. It ruins **every unit within 4 tiles of itself, yours and the enemy's**, and turns the land into craters. Nobody is spared.
- **Only when the war is lost** (balance under 25%), only with a confirmed silo, and only if one of your units is within 3 tiles to arm it. Then a 15-second countdown, a public danger zone, and the detonation. The war ends as **Mutual ruin**: you conceded after the last strike, and it is a defeat *but not in dishonour*.
- You can always **concede** instead.

## M9: line of sight and elevation

Ground and sea observers can no longer see through a hill. Every tile has a **height** (relief) and an **obstruction** (what stands on it):

| Terrain | Relief | Obstruction | Effect |
|---|---|---|---|
| Hills | +2 | 0 | high ground: **+1 tile of sight**, blocks the view of lower ground behind it |
| Mountains, tunnel portals | +4 | 0 | **+2 tiles of sight**, block nearly everything behind them |
| Forest, city | 0 | 2 | trees and buildings block the view for anyone on the flat behind them |
| Ruins, barracks, training camp, barricade | 0 | 1.5 / 1.2 / 0.6 / 0.5 | smaller blockers |

- **Seeing.** A line is drawn from the observer's eye (relief + 1.2) to the target (relief + 1.0); anything between that stands higher than the line blocks it. So an observer on hills (eye 3.2) sees over a forest (2) but not over a mountain (4). Fog of war, the "spotted" list, contacts and reports all use this; the dim tiles on the map are now the real shadows behind ridges and woods. Aircraft look down over everything and are seen over everything, and a UAV is the best way to see behind a ridge.
- **Shooting.** Direct fire (rifles, tank guns, ships' guns, coastal guns, fighters on ground targets) needs a clear line: a tank two tiles away behind a forest cannot fire, and a unit ordered to attack walks round until it has a clear view. **Artillery, missiles and bombers fire on whatever a spotter sees**, over hills and trees. Anti-air looks up and is not blocked.
- **The General is told.** Contact reports say `Line of sight: clear. We hold the high ground (+2)`, or `BLOCKED by the terrain at Echo-6 ... artillery and missiles can still fire on it because it has been spotted`, and the option lines say when a unit is in range but cannot see its target. Hovering any tile now says what the ground does to sight. The selected unit's *Vision* includes the high-ground bonus.
- Still simple: sight is a straight line over tile heights; there is no night, smoke, fog or weather effect on visibility, and no hull-down or reverse-slope tactics.

## M10: AI take over, neighbours, factories, airlift, infiltration (single view)

**One window.** The home map is fitted to the window (with the four neighbouring countries drawn as coloured strips round it).
The **Enemy intel** map now sits at the top of the right-hand column, always visible; *expand* lays it over the home map.

**AI take over / I take over.** Type either in the chat (or press the button). While the staff plays, `GENERAL-STAFF` runs the war with the
same heuristic General that plays Candooo (and answers every field report after a few seconds, choosing by simple rules: wounded units
withdraw, gas means masks, and so on), `PRESIDENT` keeps the government up (pay, purge, crack down, plots), `INTEL-CHIEF` runs covert
operations (markets, fund, leak, coup when their stability is low), `ECONOMY-MIN` builds factories, spends production points and sets the
export policy, and `FOREIGN-MIN` courts neighbours, sells arms and uses allied help. They use the same calls and cooldowns as your buttons.
Candooo's economy and foreign ministers play quietly in the same way.

**Neighbours (`game/world.py`).** Altheia (west, friendly to Ladooo), Brevik (east, friendly to Candooo), Corvane (north, neutral) and Dunmark (south).
Each has a relation with both sides (0-100). Diplomacy, aid and defence sales raise it (warming to one side cools the other a little);
a failing government or a winning army moves it too. At 70 a neighbour is an **ally**: it will airlift infantry to your airfield, share
intelligence, or send a volunteer brigade. Under 20 it is **hostile**: militants cross the border into your rear (a `BORDER ALERT`).

**Factories, exports and defence sales (`game/industry.py`).** Each side starts with one factory (tile `Z`). A Builder can build more
(up to 5; costs economy). Each extra factory adds production points and +6% firepower to every weapon (up to +30%), and tops up magazines.
The export policy trades goods against stores: *keep at home* (more production, weaker markets), *balanced*, *export heavily*
(stronger markets and friendlier partners, but fuel and food leave and production falls). Production points buy units (arms orders) or are
sold to a neighbour as a *defence sale* (money and goodwill).

**Airlift (`game/airlift.py`).** A transport helicopter carries two soldiers. *Load* takes the nearest soldiers aboard; *Drop* flies to a tile
you click and puts them down (an insertion behind the lines, or a reserve for a defence), then flies home; *Extract* flies to a wounded
soldier anywhere, takes him aboard, patches him up (+50%) and lands him at the nearest airfield. If the helicopter is shot down,
everyone aboard is lost. Chat works too: "load troops", "drop at Echo-6", "extract Rifle-1". Ordinary extraction requests now bring a free
transport helicopter when there is one. Candooo also airlifts raiders into your rear.

**Infiltration and coups on the map.** Enemy units spotted inside your half are ringed: **orange dashed = militants** (irregulars that hide and
raid barracks, camps and factories; they have their own icon now), **red = enemy military** (regular commandos, a new stealth unit). They are
listed in the *Infiltration* panel. Each capital shows a crown with its stability; below 25 it pulses red **COUP WATCH**, an officers' plot
pulses yellow, and a coup shows a magenta **COUP** burst with an alarm.

**Also fixed:** aircraft were blocked by ground units sitting on their route; they now fly over them.

**Honest simplifications.** Neighbours act through buttons and the staff, not as agents with their own armies; relations are one number per side;
production points are one pool (no factory logistics or goods flowing through the strait); the staff's rules are simple heuristics and will not
out-think a careful human; a helicopter can be shot at but flies a straight route (no terrain-hugging); militants are a unit type, not a hidden
population.

## M11: historical patterns replayed (levels 13 to 16), designation and resettlement

All nations stay fictional. Each level's briefing says "Inspired by" a pattern; nothing claims what happened in any real country.
Levels 1 to 4 now carry an "Inspired by" line too.

| Level | Pattern | What you do |
|---|---|---|
| 13 The Palace Raid | a night helicopter raid that seizes a head of state and a spouse in their capital | airlift commandos in, hold the tile beside each principal 4 s with no armed guard next to them (detained), load both, land them at our airfield |
| 14 Cartel Money | a government whose markets were propped up by cartels, later the same cartels named as the reason for allied action | cartel money keeps Candooo's economy at 45 or more until 2 allied strikes land; collect evidence, designate, strike with allies, crack the home front |
| 15 The Pretext | wars justified by public charges of nuclear weapons or invasion | accuse the enemy: with evidence (a confirmed silo, enemy units seen in our half) neighbours warm and sanctions hit them; without it you are exposed and sanctioned |
| 16 The Quiet Test | a secret test hidden from satellites; a leader and scientists lost in a mountain crash; a successor pushing on; an assassination attempt at a summit stopped by foreign intelligence; a leader found dead abroad | follows a timeline (panel shows done and scheduled events): decide to investigate the crash or press on, prepare the test (90 s) and run the cover story during satellite windows, keep 2 neighbours at relation 50 or more so their services warn you before the summit, hold the government through the succession crisis |

**Designation and resettlement (`game/occupation.py`, any level).** *Designate the enemy as a militant group* lets allies strike with you; it is cheap when their
militants or commandos really operate in your rear, and costly (stability, neutral neighbours) when it is a pretext. *Resettle* a captured, cleared area:
inclusive (slow, calms it, +economy) or forced (fast, +economy, but unrest, condemnation and rebel cells rise there).

**Gaps closed since.** The campaign now also carries up to 2 factories, veteran units (one per star, up to 3) and +2 economy per resettled area. Candooo's foreign minister
designates our forces as militants, accuses us of invading, and calls its allies in for strikes on our units. In the raid, principals call for help (guards run to them) and back away
until raiders are beside them. Satellites follow two orbits (Eye-1 every 70 s, Eye-2 every 110 s; the panel shows who is overhead and when the next pass is). A successful test gives us +10% firepower
and shakes enemy morale. Scripted headlines (the "news" level key) now run in levels 10, 14 and 15. Levels 13 is fought at night, levels 7 and 11 have a day-night cycle (ground and sea units see one tile less in the dark).
Units under fire are briefly suppressed (slower to fire). "AI take over" with Candooo's AI already makes a spectator mode (AI against AI).

**Last gaps closed.** Tanks have armour facing (a hit from ahead does 20% less, from behind 30% more). A lite chain of command: "north command / centre command / south command / air command / naval command, <order>" goes to a sector commander who passes it to every unit in that sector and reports how many took it. Candooo now prepares and runs its own nuclear test (around 5:00 to 6:30; a spy or UAV within 4 tiles of its remote site exposes it, otherwise our troops are shaken and its weapons count for 10% more). Scripted headlines now run in every historical level (5 to 12, 14, 15, 16). Night also cuts the sight of aircraft (UAVs and spies are unaffected).

**Not done, on purpose.** A larger map: the 20x14 grid, lanes, capitals, airfields and many scripted positions are hard-wired throughout the engine, UI and 16 levels, so resizing it would be a rewrite and a regression risk. Everything else on the earlier lists is in.

## M8: scenarios inspired by history (fictional nations)

Levels 5 to 12 take patterns from real conflicts and coups and play them as Ladooo against Candooo. **No real country is named in the game.** Each level states what inspired it (in general terms), has its own goal, and adds one rule that changes how you must think. The table below is the design record of what each one draws on; it is only here in this README.

| Level | In-game name | Pattern it draws on (design note) | What is different |
|---|---|---|---|
| 5 | War of Attrition | a long modern land war of trenches, mines, drones and artillery with sanctions on the aggressor (the 2022 war in Ukraine) | pre-dug trenches, extra drones and artillery, **sanctions pull Candooo's whole economy down all game**; win by 2 cities or by cracking its home front (stability under 35, which you can only read with a spy) |
| 6 | Strait Crisis | tanker wars and mine threats at a chokepoint (the Gulf and the Strait of Hormuz, US and Iran) | convoys come every 50 s, **a convoy lifts your markets 3 times as much and a loss hurts 3 times as much**, fast boats, mines and missiles; need 4 convoys, allow 1 |
| 7 | Eastern Offensive | the 1941 advance that outran its supply and met mud and frost (Germany and the USSR) | a stronger army and the first move, but **winter at 7:00**: ground units 60% slower, fuel burn +50%; finish before it |
| 8 | Highland Standoff | the 2020 mountain border clashes (India and China) | **restraint**: shooting first, when the enemy has not fired in 30 s, costs stability and markets and makes headlines; hold three ridge posts to the end; the enemy waits 2 minutes |
| 9 | Border Crisis | the 2019 crisis of air strikes and missile threats between nuclear-armed rivals (India and Pakistan) | **escalation meter**: each missile adds 12; at 50 markets panic on both sides, at 100 both governments lose 15 stability; both sides know where the last resort lies |
| 10 | Palace Intrigue | the Syrian coups of 1949 and the 1960s, officers replacing governments one after another | a **coup war**: politics runs 2.5 times faster, you start with four spies and extra intelligence points, officers plot against you, and a coup is the only way to win |
| 11 | Rebels in the Rear | Sahel and West African juntas that fell to officers while fighting rebels with a thin, corrupt army | high corruption, rebels keep appearing, **officers' plots** (arrest or pay them off, or ignore and lose 12 stability); survive 12 minutes with stability above 20 and 3 of 4 cities |
| 12 | Streets and Barracks | Myanmar in 2021 and Bangladesh in 2024: mass protests, and whether the army will fire on the crowds | unrest starts high; **three crackdowns within two minutes and the army refuses**: stability -25 and every unit's morale -20; stay in power for 10 minutes |

Intelligence work against another country's stability (funding an opposition, leaking scandals, hitting markets, backing a coup) is available from level 2 and is the main tool of level 10. These are only game mechanics: nothing here describes how to do such things in the real world.

## M7: air power, support, hazards, the home front, and decisions with numbers

- **Air force.** Fighter, bomber, attack helicopter, UAV, transport and medevac helicopters, one airfield for each side (B2 and R2). Aircraft fly over any terrain, burn **fuel** while airborne (`BINGO` report at 35%, a crash at 0) and refuel, rearm and mend when they land on their own airfield. A **strike flies out and flies home by itself** (drawn as a dashed flight path out and a dotted line home; airborne aircraft are drawn larger with a shadow). Only fighters, attack helicopters and anti-air can hit aircraft; anti-air hits nothing else. Bombers drop on a tile and its neighbours (friend and foe), must be ordered, and carry 2 bombs. A fighter is faster than one tile a second; UAVs see 7 tiles and spot hidden units from 3.
- **Support.** *Medics* heal adjacent units; *supply trucks* top up adjacent units' ammo; a *medevac helicopter* cuts extraction from 45 to 20 s.
- **Hazards with response timers.** *Air raid* (20 s: scramble fighters or free the anti-air), *gas* (15 s: `GAS GAS GAS`, masks on or move out upwind; masks stop the damage but slow units by half and cut sight by a tile), *flood* (30 s warning before a flood plain floods; vehicles on it are stranded and hurt), *BINGO fuel* (25 s). Ignore one and the unit takes the hit.
- **Barracks and training camps.** A barracks trains a free rifle squad every 90 s for whoever holds it (up to 6 squads; corruption slows it); drilling 20 s on your own training camp makes a unit a **veteran** (+2 HP, +25% damage). Both can be captured (rebels too).
- **Rebels.** Hidden cells appear in your rear (levels 3 and 4): three armed men who hide, hold fire and spring on whoever comes close, then go for your barracks. Only spotted from 1 tile, or 3 tiles by a UAV or a spy. An informant's tip can point to them.
- **Morale.** Hits and nearby deaths shake units; a shaken unit (under 30) shoots at 60%, reports `Morale is breaking`, and under 12 breaks and runs home. Rest and friendly ground recover it. Hungry troops and a shaky government lower it.
- **Combat assessment before you decide.** Every contact, damage, bingo and gas report now carries a briefing and a one-line consequence under each choice: **visibility** (distance, our sight, whether it has seen us, cover), the **exchange of fire** (damage per second each way, time to kill, who lasts longer, the ratio), **reach** (in range now, or tiles to close and the ETA), **weapon choice** (which of your guns is best and how far away), **in line or crossfire** (how many of your guns can bear and from how many degrees apart), and for withdrawals the **ETA to safe ground and whether the enemy could catch you**.
- **Groups, not single units.** A tank unit is drawn as a group of four tanks, artillery as three guns; each loss takes one picture away. Squads march with a step and a sway, guns fire in ragged volleys, tanks shudder as they move.
- **The whole map is visible.** The lie of the land is public, so the enemy half is shown clearly (lightly fogged); only who is where, and who holds what, stays hidden. The Enemy intel map is a small strip at the top that you can expand; the Home map gets the space.
- **Sound fixes.** Missiles now roar while they climb and whistle as they fall (as long as the real flight time). With *speak radio* on, Morse messages are read out too, and the voice queue no longer cuts a line short.

### The home front (levels 2 to 4)
Governments fall at home as often as armies fall in the field, and in this game too. Each side has **government stability**, **markets and economy**, **corruption** and **unrest**, with named causes you can see:
- Supply convoys feed the economy; lost ports, lost units and lost convoys hurt markets and stability; shortages and corruption raise unrest; a shaky government (stability under 40) caps its army's morale.
- **Corruption** skims convoy cargo (up to half), slows reinforcements and barracks, and erodes stability.
- You can act: *Purge corrupt officers*, *Raise pay and rations*, *Crack down on protests*, each a trade-off.
- **Intelligence operations** (each living spy earns an intelligence point every 30 s): *Fund their opposition*, *Leak a corruption scandal*, *Hit their markets*, and *Back a coup*, which only works if their stability is low (best under 30); a failed plot is exposed and hurts you. Candooo does the same to you from time to time.
- **How it ends:** stability under 10 for 20 s is a **coup d'état**; economy under 5 for 45 s is an **economic collapse**. Either ends the war for that side. Headlines tell the story. You only see Candooo's numbers (roughly) while a spy is alive.

### What is still simplified (honest list)
Positions are tiles, not metres; line of sight and height are simple (see M9); no suppression, ammunition types or armour facing; no night or weather beyond the storm; units are not truly commanded through a chain (one General talks to every unit); supply is two meters, not depots and trucks; air defence and air combat are one-step; civilians and refugees are not modelled; the AI General is simple. The next realism steps I would take are line of sight and elevation, suppression, and a real chain of command with staff officers.

## Levels, pace and decisions (M6)

- **Levels, so a game ends.** Pick one in the *Mission* box. Each has a goal, a time limit and a star rating.
  1. **Skirmish** (10 min, small forces, enemy holds back for 90 s): capture 2 enemy ports or cities.
  2. **Strait Control** (12 min): get 3 convoys through and let at most 1 of theirs through.
  3. **Total Takeover** (20 min): the full war.
  4. **The Last Resort** (25 min): the full war against a stronger Candooo, with short supplies.
  If time runs out the war is decided on points (balance 65% or more is a victory on points, 35% or less a defeat, otherwise a stalemate). **Stars:** 1 for winning, +1 for winning in 70% of the time or less, +1 for good decisions (60% or more succeeded) with an average response of 25 s or less. Winning offers the next level.
- **Not too fast.** The game starts at ½× (also ¼×, 1×, 2×, 4×) and urgent reports have longer fuses (contact 40 s, damage 45 s, others 60 s of game time). While an urgent report is open the **clock waits** for you (15, 30 or 60 real seconds, or off) and says *Time to decide*. **Hover a report** and rings on both maps show where it is and where the enemy is; click the callsign to select the unit.
- **Too slow has a price you can see.** If a contact or damage report runs out, the enemy gets a free hit: the radio calls the damage (`No orders! We took 6 damage, HP 9 to 3/12`), and if the unit dies, `LOST: Anvil-1 is DEAD. It waited for orders that came too late`.
- **Outcome of every decision.** Choices from reports are judged later, on the radio and in the *Decisions* list: `OUTCOME of 'Engage the tank': SUCCESS. Anvil-1 destroyed the tank.` or `FAILURE: Rifle-1 was hit anyway (3 HP lost).` Engage, hold fire, fight on, fall back, clear a mine, rebuild the bridge, extraction and convoy choices are all rated.
- **Withdrawing heals.** A unit that has been out of the fight for 8 s recovers 1 HP every 5 s on a friendly port, city or camp, and 1 HP every 10 s within 2 tiles of one. The damage flag clears once it is healthy again, so it can report again later.
- **Barricades.** Block the road for vehicles (infantry can climb over, slowly). Builders and diggers build them (8 s); tanks, infantry, builders and diggers can breach them (6 s); a shell blows them apart. The causeway has two in levels 2 to 4.
- **Traps.** *Ambush*: units hide (spotted only from 1 tile) and hold fire until an enemy walks close or one of them is hit, then every ambusher nearby fires at once for **double damage** for 8 s. *Lure*: a bait unit goes toward the enemy until it is seen, then runs to the trap tile where your ambushers wait; Candooo's tanks chase what they see. Buttons on the selected unit, or chat: `tanks set an ambush`, `Neptune-1 lure the enemy to Hotel-5`.
- **Orders are understood far more widely.** Move (`go to`, `send`, `proceed`, `advance`, `deploy`, `sail`, `drive`, or just `Anvil-1 Echo-6`), attack by grid (`fire on Lima-7`) or by kind (`attack the tank`), `capture the nearest port`, `stop`, `hold position`, `fall back` / `run`, `breach`, `build a barricade`, `dig in`, `help`. You can address a whole kind (`all tanks hold fire`, `destroyers fall back`, `engineers dig in`) and use spoken forms (`anvil one`, `echo seven`). Anything not understood now gets a helpful answer listing what the unit understands, never silence.
- **Clicking fixed.** The map now works out the tile from where you click, instead of waiting for Plotly's hover event (quick clicks, touch and some browsers were missed). A script error I had introduced also stopped the page from loading for a short while; it is fixed.

## Live scenarios and the AI General (M6)

- **Scenarios and intel from chat.** Ask `HQ scenario informant`, `HQ scenario defector`, `HQ scenario storm`, or ask a unit (`Ghost-1, any rumours?`). Informants bring a **rumour with a marker** at a fuzzy spot on the map; it may be true or false, and it is settled when a unit sees the spot (`The tip checks out` or `False alarm`) or it goes cold after 150 s. A *defector* gives away three enemy positions; a *storm* slows ships and makes shots miss more for 90 s. One tip in five points to a hidden silo. Random events happen every two to three minutes, and on-demand ones have a 60 s cooldown. The server makes every fact from the real game state; a language model can only put words to it.
- **WebLLM plays Candooo's General.** Press *Let WebLLM play Candooo's General (new tab)* (or open `?role=general`), load the model and press *Start playing*. That tab sees only Candooo's fog of war, asks the model for JSON orders every 9 s, and the server checks every order (own units only, legal actions only, visible targets, grid references) before anything happens. Unreadable or illegal plans are refused with a reason and the scripted general fills the gaps (it slows to every 12 s while a model leads). Keep the plans in their own tab so you do not see them; the enemy's radio is only heard when your spy **intercepts** it (shown as Morse). Close the tab and the script takes over again.
- **Agents remember** their last few exchanges and know their nearest friends and the recent radio, so a conversation holds together.
- A 0.5B model is small. In a real test it needed about 70 s for its first plan and copied the example order it was given (the prompt now uses placeholders). Expect modest play; a larger WebLLM model can be set in `glue.js` (`enableLLM`).

## Radio realism, response time and sound

- **Real radio talk.** Units say *Copy that*, *Roger that*, *Wilco*, *Say again*, with ETAs (`Moving to Echo-6, ETA 40 sec`), and call contacts by clock position (`Contact at my two o'clock`; a nearby friend gets `Heads up, hostile at your seven!`). Contact reports end with *Point me to the target.* Emergencies are called in at once: `Taking hit! HP 7/10`, `Friendly fire! Check your fire!` (missile splash on your own troops), `We're sinking! CODE RED!`, `MAYDAY MAYDAY` when a unit is lost, `CODE RED! Inbound missile, impact Echo-5 in 6 sec` (radar warning), and `Extraction at Hotel-11, ETA 45 sec`.
- **Extraction.** A damaged unit can request extraction: it holds still, is picked up after 45 s, and rejoins at the nearest friendly port or city 30 s later, patched up to at least half health. Say it in chat too: `Anvil-1 request extraction`.
- **Answers take time.** Replies to your orders and status requests arrive after 1 to 5 seconds (eager units are quick, cautious ones slower, and low supplies add lag), so the net sounds staggered, not instant. Emergencies are never delayed.
- **Your response time counts.** Urgent reports have short fuses: a *contact* report 20 s, a *damaged* report 25 s, others 45 s. Miss one and the unit is **caught unprepared**: it cannot move or fire for 15 s and takes +50% damage. The panel shows your average response time, how many reports you answered and how many were too late.
- **Sound (all synthesized in the browser).** Tick *sound effects* for gunfire, cannon, hits, explosions, missile launch, convoy chime, the CODE RED siren, radio squelch, Morse beeps and the nuclear blast, panned left or right by where it happens. Tick *speak radio* to hear incoming messages read aloud in the browser's own voices (each unit's temperament sets its pitch and speed). **🔊 test** plays them all.
- **Voice input.** The 🎤 button uses the browser's speech recognition if it has one, and spoken forms are understood (`anvil one move to echo seven`). Typing works everywhere.
- **AI voice (WebLLM)** reads what you type or say and answers open conversation in character. It cannot give itself orders.

## What works now (milestones M1–M4b)

- Terrain map with 24 terrain and hazard tiles, grid references (A–T, 1–14, `Charlie-7`), a land **causeway with a bridge** on the north edge (the only land route between the halves; the sea is crossed by ships), and the southern strait.
- 36 units (18 per side). Real-time clock (pause, 1×/2×/4×), orders, pathfinding, automatic fire, ammo, 6-second missile flight with a danger zone, capture, win checks.
- **Engineers and spies:** *divers* feel out hidden mines within 3 tiles and clear them (shown working, with a progress bar), *minesweepers* too; *miners* and *mine layers* plant hidden mines; *diggers* dig trenches; *builders* rebuild a destroyed bridge (a missile hit turns a bridge into a river, cutting the causeway) or build a camp; *spies* are stealthy (spotted only from 1 tile), sense enemies within 5 tiles and report them to you **by Morse** every few seconds. Hidden mines hurt (6 damage) whoever steps on them; units walk round mines they know about. Orders: buttons for the selected unit, or chat (`Mole-1 dig in`, `Frogman-1 clear mines`, `Sapper-1 plant a mine`, `Beaver-1 rebuild the bridge`).
- **Reinforcements** (limited): *Paratroopers* by air (1 call, 20 s, 2 infantry at a tile in our land), *Naval squadron* by sea (1 call, 30 s, a destroyer at a water tile in our waters), *Armoured convoy* by land (2 calls, 40 s, a tank and infantry at the nearest port or city). Panel buttons, or chat (`reinforcements air to Delta-7`, `reinforcements by land`).
- **Fog of war** with two maps per side (Home and Enemy intel), aging contacts, a Realistic / Tactical symbols toggle, referee view.
- **Agents:** every unit has a callsign (`Anvil-1`, `Neptune-1`, ...) and a temperament (calm, eager, cautious) that colours its replies. Reports with choices, status, chat orders, hold fire / weapons free, fall back, `MAYDAY` on losses.
- **Radio and Morse** log with sent and received traffic and synthesized beeps.
- **Territory tint** (green ours, red theirs).
- **Candooo's AI General** that spots, advances on objectives, fires missiles, plants mines, digs in, clears mines, rebuilds bridges and calls its armoured convoy, under the same fog and the same supply rules.
- **War status**, the strait with supply convoys, late responses, hidden silos with clues, the last resort and conceding (above).
- Optional **WebLLM voice** (button in the panel). Tested: the small Qwen 0.5B model loads and answers in character. It is tiny, so answers can be loose.

## Planned

### More units
| Unit | What it does |
|---|---|
| **Medic / Supply truck** | Heal, resupply ammo and fuel; MEDEVAC |
| **Air units** | Fighter, bomber, attack helicopter, transport and medevac helicopters, UAV |
| **Divers (more)** | Inspect hulls, sabotage enemy ships |
| **Diggers (more)** | Dig tunnels |

### Clearing challenges
More problems as reports with choices: a flooded plain, a gas cloud (*mask up*), a pinned unit (*reinforce*), a mined channel (*send divers*, *go around*, *call air support*). Choices have trade-offs in time, risk and resources.

### Animation and physics (M5, done)
Everything stays inside Plotly's own SVG (no canvas, no extra library), as you chose. Both maps (Home and Enemy intel) animate, and fog is respected: the server only sends shots and explosions you can see; unseen big bangs arrive as a distant rumble.
- **Movement:** units glide from tile to tile with ease-in and ease-out (they accelerate and brake), turn smoothly to their heading, and ships bob on the swell. Ships leave a fading wake, vehicles kick up dust.
- **Shells and missiles:** guns flash and send a tracer; cannons, artillery and battleships fire a shell on an arc with a smoke trail; missiles climb in a high arc over their 6 seconds of flight and leave a vapour trail; hits spark, explosions burn and smoke, and the nuclear blast whites out the map and shakes it.
- **Work:** divers raise bubbles, diggers and miners kick up dust, builders throw sparks.
- **Physics:** a random **wind** (shown in the panel, with an arrow) pushes missiles off target in proportion to their flight distance, and long shots can miss and splash a tile away (a short-range shot never misses). **High currents** carry idle ships one tile east every 6 seconds.
- Still approximations: positions stay on the tile grid (movement is animated between tiles), so there is no continuous ship inertia on the server.

### Real-world codes and radio
The spelling alphabet (Alpha, Bravo, Charlie...) and grid references, prowords (`ROGER`, `WILCO`, `OVER`, `OUT`), `CONTACT`, `SITREP`, `SALUTE`, `9-LINE MEDEVAC`, `CBRN-1`, brevity codes (`WINCHESTER`, `BINGO`, `FOX`, `SPLASH`), `GAS GAS GAS`, MOPP levels, and the game's own tactical map symbols.

### Response time
Alerts carry countdowns (air raid 15 s, inbound missile 20 s, gas 8 s, ...). Too late means the event lands at +50% damage and the affected units lose their next action. Reports already time out after 45 s.

## Map and terrain

Ladooo (you) holds the west, Candooo the east; ships fight in the contested sea. Internally the sides are still called `blue` and `red`.

| Tile | Effect |
|---|---|
| Deep sea / Shallow water / Coast | Ships on water; coast links land and sea |
| Plains / Hills / Mountain | Mountains: infantry only; hills slow vehicles |
| Forest, Ruins, Tunnel, Trench | Cover: units here are only spotted from 2 tiles; damage reduced |
| Causeway road / Bridge | Fast land route; the bridge is a choke point (can be destroyed and rebuilt) |
| River, Boulders, Tank trap | Obstacles for vehicles |
| Camp, Airfield, Port, City | Bases; ports and cities are the objectives |
| Flood plain / Flooded zone | Dry now, may flood; floods strand vehicles |
| Coral reef | Big ships cannot enter; minesweepers and submarines can |
| Sulphur zone | Toxic water; gas plumes hide units |
| High current | Pushes ships along |
| Mine | Hidden; cleared by minesweepers and divers |

## Icons

All icons are generated by [tools/gen_icons.py](tools/gen_icons.py) into `assets/icons/` (152 SVGs, top-down, 128×128). Open `assets/icons/preview.html` to see them. They include the five new engineer and spy units, `nuke_clue` and `nuke_site` markers, and the tactical symbols (`sym_<unit>_<team>`). Still to generate: landing craft, paratrooper.

```bash
docker run --rm -v "F:\PLOTLY:/app" -w /app python:3.12-slim python tools/gen_icons.py
```

## Project structure

```
PLOTLY/
├── run.py                     # HTTP server (stdlib), clock thread, SSE, API
├── Dockerfile, requirements.txt
├── game/
│   ├── board.py               # map, terrain, grid references
│   ├── units.py               # unit stats, callsigns, vision
│   ├── rules.py               # pathfinding, terrain costs, damage and cover
│   ├── state.py               # real-time engine, fog of war, territory
│   ├── agents.py              # reports, chat orders, Morse, radio log
│   ├── morse.py               # Morse encode / decode
│   ├── ai_red.py              # Red AI General
│   └── scenarios.py           # starting units
│   ├── tactics.py             # combat assessment shown before decisions
│   ├── homefront.py           # stability, economy, corruption, covert operations, coups
│   ├── events.py              # rumours, storms, defectors, intercepts, gas, floods, rebels
│   └── levels.py              # four levels: goals, limits, stars
├── ui/                        # figure.py (Plotly), index.html, glue.js (panel, sound, speech, AI General tab), anim.js (animation)
├── tests/test_engine.py       # headless tests
├── tools/gen_icons.py
└── assets/icons/
```

## Milestones

1. **M1 Board (done).**
2. **M2 Real-time core (done).**
3. **M3 Fog of war, two maps (done).**
4. **M4a General and agents (done):** reports with choices, chat and Morse orders, radio log, territory tint, AI General, land causeway.
5. **M4b Engineers, supply and the last resort (done):** divers, diggers, builders, miners, spies, mines, reinforcements, the strait with supply convoys and late responses, war status, hidden silos with clues, the last resort, conceding. Renamed the sides to Ladooo and Candooo and removed all NATO naming.
6. **M5 Animation and physics (done):** smooth movement and turning, wakes, shell and missile arcs, explosions, work particles, wind, shot dispersion, current drift, fog-aware effects (sounds were added in M4b).
7. **M6 Levels, pacing, traps and live scenarios (done):** four levels with goals, time limits and stars; slower pace with decision time; success or failure feedback; healing; barricades, ambush and lure; informants, defectors, storms and intercepts; a WebLLM-driven Candooo General in its own tab; wider command understanding.
8. **M7 Depth (done):** air power with fuel and flight paths, medics and supply trucks, gas and masks, floods, air raids and other alerts with response timers, barracks, training camps and veterans, rebels, morale, combat assessment before decisions, groups of units, the home front (stability, economy, corruption, covert operations, coups), the enemy half shown clearly.
9. **M8 Scenarios inspired by history (done, fictional nations):** levels 5 to 12: attrition with sanctions, a strait crisis, an offensive racing winter, a standoff with restraint, a missile crisis with escalation, a coup war, rebels and officers' plots, and mass protests with an army that may refuse.
10. **M9 Line of sight and elevation (done).**
11. **M10 Staff, neighbours, industry, airlift and a single view (done):** see the section below.
12. **Next ideas:** suppression and armour facing, night and weather effects on sight, a chain of command with staff officers, a larger map, and an AI-vs-AI spectator mode.

## Run

```bash
docker build -t fleet-armor .
```

```bash
docker run --rm -p 8000:8000 -v "F:\PLOTLY:/app" fleet-armor
```

Open `http://localhost:8000`. Run the tests with:

```bash
docker run --rm -v "F:\PLOTLY:/app" fleet-armor python -m unittest discover -s tests -v
```

Click **Enable AI voice (WebLLM)** to let agents hold open conversations; the first time it downloads a small model (a few hundred MB, cached afterwards) and needs a WebGPU browser.

## Open questions

1. Should the AI General also be able to find and use the last resort when it is losing?
2. Spy: today it is caught only when an enemy is next to it. Should captured spies feed you false Morse?
3. Should the enemy be able to intercept your Morse?
4. How often should flood plains flood, and is the current visible to both sides?
5. Should the strait be mineable and blockable by submarines (it already can be by any ship or mine)?
