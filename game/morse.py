"""International Morse code: encode text to dots and dashes and back."""
import re

CODE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....", "I": "..",
    "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....", "6": "-....",
    "7": "--...", "8": "---..", "9": "----.", ".": ".-.-.-", ",": "--..--", "?": "..--..", "/": "-..-.", "-": "-....-",
}
REVERSE = {v: k for k, v in CODE.items()}


def encode(text):
    """'SOS NOW' -> '... --- ... / -. --- .--'  (letters separated by a space, words by ' / ')."""
    words = [w for w in re.split(r"\s+", text.upper().strip()) if w]
    return " / ".join(" ".join(CODE[ch] for ch in w if ch in CODE) for w in words if any(ch in CODE for ch in w))


def decode(morse):
    """Inverse of encode. Unknown groups become '?'."""
    out = []
    for word in re.split(r"\s*/\s*", morse.strip()):
        out.append("".join(REVERSE.get(sym, "?") for sym in word.split()))
    return " ".join(w for w in out if w)


def looks_like_morse(text):
    return bool(text.strip()) and re.fullmatch(r"[.\-/\s]+", text) is not None
