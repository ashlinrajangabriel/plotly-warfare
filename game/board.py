"""The map: a W x H square grid of terrain tiles (row 0 is the top)."""

CODES = {
    "D": "deep_sea", "S": "shallow_water", "C": "coast", "P": "plains", "F": "forest",
    "H": "hills", "M": "mountain", "T": "port", "Y": "city", "N": "tunnel",
    "L": "flooded_zone", "O": "flood_plain", "R": "coral_reef", "U": "sulphur_zone",
    "K": "high_current", "X": "tank_trap", "W": "road", "B": "bridge", "A": "airfield", "Q": "barracks", "J": "training_camp", "Z": "factory",
}

NAMES = {
    "deep_sea": "Deep sea", "shallow_water": "Shallow water", "coast": "Coast", "plains": "Plains",
    "forest": "Forest", "hills": "Hills", "mountain": "Mountain", "port": "Port", "city": "City",
    "tunnel": "Tunnel", "flooded_zone": "Flooded zone", "flood_plain": "Flood plain (may flood)",
    "coral_reef": "Coral reef", "sulphur_zone": "Sulphur zone", "high_current": "High current",
    "tank_trap": "Tank trap", "crater": "Crater", "road": "Causeway road", "bridge": "Bridge", "barricade": "Barricade", "airfield": "Airfield", "barracks": "Barracks", "training_camp": "Training camp", "factory": "Factory",
    "trench": "Trench", "camp": "Camp", "ruins": "Ruins", "river": "River", "crater": "Crater", "boulders": "Boulders",
}

# Blue (humans) hold the west, Red (AI) the east, a contested sea in between.
ROWS = [
    "PHMMPCWWWWBBWWWWCPMM",   # the only land route between the two halves: a causeway with a bridge
    "PAHFPCSDDKDDDDDSCAFH",   # an airfield for each side at B2 and R2
    "PFFPYCSDDDDRRDDSCYPF",
    "POPPTCSDDKKDDDDSCTPP",
    "PQXPPCSSDDDDUUDSSCQP",   # barracks at B5 and S5
    "HMNMPCSDDDSSDDDDSCPH",
    "PPFPPCSDDCPCDDDSCPPP",
    "PPPPPCSDSCPFCSDDSCPP",
    "PLOPPCSDDSCPCSDDSCPP",
    "PJPPYCSDKDDSSDDDSCYP",   # a training camp at B10
    "PFPPPCSDKKDDDDDRSCPJ",   # and one at T11
    "PPHPTCSDDDDDDRRDSCTP",
    "PHMZPCSMMHDDHMMMSCZM",   # factories at D13 and S13; the southern strait (cols K-L): both supply convoys must pass through it
    "HMMPPCSMMHDDHMMMSCHM",
]


PHONETIC = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliet",
            "Kilo", "Lima", "Mike", "November", "Oscar", "Papa", "Quebec", "Romeo", "Sierra", "Tango"]


def ref(c, r):
    """Grid reference in radio style: column letter name plus row number, e.g. Charlie-7."""
    return f"{PHONETIC[c]}-{r + 1}"


class Board:
    def __init__(self, rows=ROWS):
        self.height = len(rows)
        self.width = len(rows[0])
        assert all(len(r) == self.width for r in rows), "map rows must all have the same length"
        self.grid = [[CODES[ch] for ch in row] for row in rows]

    def terrain(self, c, r):
        return self.grid[r][c]

    def inside(self, c, r):
        return 0 <= c < self.width and 0 <= r < self.height
