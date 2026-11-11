"""Unit definitions. Starting values; balance them here."""
from dataclasses import dataclass, field

# domain: "sea" or "land". move = speed (a tile of cost 1 takes 6/move seconds). range = attack range in tiles.
STATS = {
    "minesweeper":      dict(hp=6,  move=3, range=1,  domain="sea",  label="Minesweeper"),
    "minelayer":        dict(hp=6,  move=2, range=0,  domain="sea",  label="Mine layer"),
    "destroyer":        dict(hp=10, move=4, range=2,  domain="sea",  label="Destroyer"),
    "cruiser":          dict(hp=14, move=3, range=3,  domain="sea",  label="Cruiser"),
    "battleship":       dict(hp=20, move=2, range=4,  domain="sea",  label="Battleship"),
    "submarine":        dict(hp=8,  move=3, range=2,  domain="sea",  label="Submarine"),
    "infantry":         dict(hp=6,  move=2, range=1,  domain="land", label="Infantry"),
    "tank":             dict(hp=12, move=3, range=2,  domain="land", label="Tank"),
    "artillery":        dict(hp=8,  move=1, range=4,  domain="land", label="Artillery"),
    "coastal_gun":      dict(hp=14, move=0, range=3,  domain="land", label="Coastal gun"),
    "missile_launcher": dict(hp=8,  move=2, range=8,  domain="land", label="Missile launcher"),
    "missile_silo":     dict(hp=25, move=0, range=12, domain="land", label="Missile silo"),
    # engineers, spy and the supply convoy
    "diver":            dict(hp=4,  move=1, range=0,  domain="sea",  label="Diver"),
    "digger":           dict(hp=6,  move=2, range=0,  domain="land", label="Digger"),
    "builder":          dict(hp=6,  move=2, range=0,  domain="land", label="Builder"),
    "miner":            dict(hp=6,  move=2, range=0,  domain="land", label="Miner"),
    "spy":              dict(hp=4,  move=2, range=0,  domain="land", label="Spy"),
    "supply_ship":      dict(hp=8,  move=2, range=0,  domain="sea",  label="Supply convoy"),
    # air power, air defence and support (M7)
    "fighter":              dict(hp=6,  move=10, range=3, domain="air",  label="Fighter"),
    "bomber":               dict(hp=10, move=6,  range=1, domain="air",  label="Bomber"),
    "attack_helicopter":    dict(hp=8,  move=6,  range=2, domain="air",  label="Attack helicopter"),
    "transport_helicopter": dict(hp=8,  move=5,  range=0, domain="air",  label="Transport helicopter"),
    "medevac_helicopter":   dict(hp=8,  move=5,  range=0, domain="air",  label="Medevac helicopter"),
    "uav":                  dict(hp=3,  move=5,  range=0, domain="air",  label="UAV"),
    "anti_air":             dict(hp=8,  move=2,  range=4, domain="land", label="Anti-air"),
    "medic":                dict(hp=6,  move=3,  range=0, domain="land", label="Medic"),
    "supply_truck":         dict(hp=8,  move=3,  range=0, domain="land", label="Supply truck"),
    "rebel":                dict(hp=4,  move=2,  range=1, domain="land", label="Rebels"),     # hidden irregulars behind our lines
    "vip":                  dict(hp=4,  move=2,  range=0, domain="land", label="Principal"),   # a head of state or spouse (raid levels)
    "commando":             dict(hp=5,  move=3,  range=1, domain="land", label="Commandos"),  # regular special forces that infiltrate
}
AIR_TYPES = {"fighter", "bomber", "attack_helicopter", "transport_helicopter", "medevac_helicopter", "uav"}
FUEL = {"fighter": 90, "bomber": 120, "attack_helicopter": 100, "transport_helicopter": 120, "medevac_helicopter": 120, "uav": 160}   # seconds aloft

# (damage per shot, seconds between shots, starting ammo)
ATTACK = {
    "minesweeper": (1, 5, 6), "minelayer": (0, 0, 0), "destroyer": (2, 4, 25), "cruiser": (3, 5, 20),
    "battleship": (5, 8, 12), "submarine": (4, 6, 8), "infantry": (1, 3, 40), "tank": (3, 5, 20),
    "artillery": (4, 8, 12), "coastal_gun": (3, 6, 15), "missile_launcher": (10, 20, 2), "missile_silo": (12, 25, 3),
    "diver": (0, 0, 0), "digger": (0, 0, 0), "builder": (0, 0, 0), "miner": (0, 0, 0), "spy": (0, 0, 0), "supply_ship": (0, 0, 0),
    "fighter": (3, 4, 16), "bomber": (8, 10, 2), "attack_helicopter": (3, 4, 12), "transport_helicopter": (0, 0, 0),
    "medevac_helicopter": (0, 0, 0), "uav": (0, 0, 0), "anti_air": (4, 3, 20), "medic": (0, 0, 0), "supply_truck": (0, 0, 0),
    "rebel": (1, 3, 20), "commando": (2, 3, 12), "vip": (0, 0, 0),
}
MISSILE_TYPES = {"missile_launcher", "missile_silo"}

# How far (in tiles, Manhattan) a unit sees. Submarines are only spotted from 1 tile away.
VISION = {
    "minesweeper": 4, "minelayer": 3, "destroyer": 5, "cruiser": 5, "battleship": 5, "submarine": 3,
    "infantry": 3, "tank": 3, "artillery": 3, "coastal_gun": 5, "missile_launcher": 3, "missile_silo": 3,
    "diver": 3, "digger": 3, "builder": 3, "miner": 3, "spy": 4, "supply_ship": 3,
    "fighter": 5, "bomber": 4, "attack_helicopter": 5, "transport_helicopter": 4, "medevac_helicopter": 4, "uav": 7,
    "anti_air": 5, "medic": 3, "supply_truck": 3, "rebel": 3, "commando": 4, "vip": 2,
}
STEALTH = {"submarine", "spy", "diver", "rebel", "commando"}      # only spotted from 1 tile away (3 tiles by a UAV or a spy)
MILITANT_TYPES = {"rebel"}                                         # irregulars; commandos and spies are regular military infiltrators
CARRIED = {"vip", "infantry", "commando", "spy", "digger", "builder", "miner", "medic", "rebel"}   # what a helicopter can lift (two at a time)
SENSORS = {"uav", "spy"}                              # these pick out hidden units from further away

# How far a unit can feel out hidden enemy mines on its own
MINE_DETECT = {"minesweeper": 2, "diver": 3, "miner": 2, "spy": 2, "builder": 1, "digger": 1}

# Work that engineer units can do: ability id -> (button label, seconds). The unit must be allowed it (see ABILITIES).
JOBS = {"clear": ("Clear mines nearby", 6), "dig": ("Dig a trench here", 10), "plant": ("Plant a mine here", 6),
        "camp": ("Build a camp here", 12), "bridge": ("Rebuild the bridge", 15),
        "barricade": ("Build a barricade here", 8), "breach": ("Breach a barricade nearby", 6), "factory": ("Build a factory here", 20)}
ABILITIES = {"diver": ["clear"], "minesweeper": ["clear"], "digger": ["dig", "barricade", "breach"], "builder": ["bridge", "camp", "barricade", "breach", "factory"],
             "miner": ["plant", "clear"], "minelayer": ["plant"], "tank": ["breach"], "infantry": ["breach"]}
STOCK = {"miner": 6, "minelayer": 8}

CALLSIGN = {
    "minesweeper": "Sweeper", "minelayer": "Layer", "destroyer": "Neptune", "cruiser": "Trident", "battleship": "Titan",
    "submarine": "Shadow", "infantry": "Rifle", "tank": "Anvil", "artillery": "Thunder", "coastal_gun": "Bastion",
    "missile_launcher": "Lance", "missile_silo": "Citadel", "diver": "Frogman", "digger": "Mole", "builder": "Beaver",
    "miner": "Sapper", "spy": "Ghost", "supply_ship": "Convoy", "fighter": "Falcon", "bomber": "Hammer", "attack_helicopter": "Viper",
    "transport_helicopter": "Mule", "medevac_helicopter": "Angel", "uav": "Eyes", "anti_air": "Shield", "medic": "Doc", "supply_truck": "Wagon", "rebel": "Cell", "commando": "Raider", "vip": "Principal",
}
TEMPERAMENTS = ("calm", "eager", "cautious")

# Two fictional nations. Internally the sides stay "blue" (you, the human General) and "red" (the AI General).
TEAM_LABEL = {"blue": "Ladooo (You)", "red": "Candooo (AI General)"}
TEAM_SHORT = {"blue": "Ladooo", "red": "Candooo"}


@dataclass
class Unit:
    id: str
    type: str
    team: str
    c: int
    r: int
    hp: int
    ammo: int = -1
    path: list = field(default_factory=list)   # [(c, r, cost), ...] still to walk
    dest: tuple = None                         # final move destination, if any
    next_step_at: float = 0                    # game time when the next step may start
    ready_at: float = 0                        # game time when the weapon is ready
    target_id: str = None                      # explicit attack order
    heading: int = 0                           # degrees, 0 = east, 90 = south
    hold_fire: bool = False                    # True = do not shoot unless ordered to
    arrive_note: bool = False                  # report "in position" when the route ends
    flags: set = field(default_factory=set)    # one-shot report markers: "damaged", "lowammo"
    start_ammo: int = 0
    job: dict = None                           # work in progress: {kind, c, r, done_at}
    plan: tuple = None                         # (kind, c, r): start this job when the route ends
    stock: int = 0                             # mines carried
    blocked_since: float = None                # since when the next step is blocked (convoys report this)
    spy_seen: set = field(default_factory=set)
    shaken_until: float = 0                    # caught unprepared: cannot act and takes +50% damage until then
    extract_at: float = None                   # extraction pick-up time, if requested
    note_at: float = -99                       # last time this unit radioed "taking hit"
    hurt_at: float = -99                       # last time this unit took damage (healing only starts after a calm spell)
    ambush: bool = False                       # lying in wait: hidden, holding fire, until the enemy comes close
    sprung_until: float = 0                    # just sprung an ambush: doubled damage until then
    lure: dict = None                          # bait mission {trap, phase}
    fuel: float = 0                            # seconds of flight left (aircraft only)
    mask: bool = False                         # gas mask on: safe from gas, but slower and sees less
    care_at: float = -99                       # last time a medic treated this unit
    mission: bool = False                      # aircraft on a strike: fly home when it is over
    vet: int = 0                               # 1 = veteran: trained, hits harder, tougher
    train_since: float = -1                    # when it started training at a training camp
    morale: float = 100.0                      # 0 to 100: low morale hurts aim, very low means it breaks and runs
    cargo: list = field(default_factory=list)  # soldiers carried by a helicopter (Unit objects, at most two)
    plan_air: dict = None                      # a helicopter's pending airlift {kind: "drop"|"pickup", c, r, uid}

    def __post_init__(self):
        if self.ammo < 0:
            self.ammo = ATTACK[self.type][2]
        self.start_ammo = self.ammo
        self.stock = STOCK.get(self.type, 0)
        self.fuel = float(FUEL.get(self.type, 0))
        self.heading = 0 if self.team == "blue" else 180

    @property
    def callsign(self):
        tail = self.id.rsplit("-", 1)[-1]
        return f"{CALLSIGN[self.type]}-{tail if tail.isdigit() else 1}"

    @property
    def temperament(self):
        return TEMPERAMENTS[sum(map(ord, self.id)) % len(TEMPERAMENTS)]

    @property
    def stats(self):
        return STATS[self.type]

    @property
    def max_hp(self):
        return self.stats["hp"] + (2 if self.vet else 0)       # veterans are tougher

    @property
    def air(self):
        return self.type in AIR_TYPES

    @property
    def max_fuel(self):
        return float(FUEL.get(self.type, 0))

    @property
    def label(self):
        return f"{TEAM_SHORT[self.team]} {self.stats['label']}"
