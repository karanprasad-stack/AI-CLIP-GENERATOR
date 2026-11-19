"""Roman Hindi lexicon, phonetic contractions, and spelling normalization rules."""

from typing import Dict, Set, Tuple, List, Optional

# Core spoken Roman Hindi markers
ROMAN_HINDI_MARKERS: Set[str] = {
    "bhai", "bhaiya", "abe", "arey", "arre", "yaar", "kya", "kyu", "kyun", "kyon",
    "kaise", "kaisa", "kaisi", "mera", "meri", "mere", "tera", "teri", "tere",
    "mujhe", "tujhe", "hume", "usko", "isko", "unko", "inko", "isse", "usse",
    "idhar", "udhar", "kaha", "kahan", "kidhar", "jahan", "yaha", "yahan", "waha", "wahan",
    "dekh", "dekho", "dekha", "dekhna", "bata", "batao", "bataya", "bol", "bolo", "bola", "boli",
    "tha", "thi", "the", "hai", "hain", "ho", "hoon", "nahi", "nahin", "na", "mat",
    "haan", "accha", "acha", "bas", "ekdum", "bilkul", "sahi", "galat", "kuch", "kuchh",
    "abhi", "phir", "fir", "kyunki", "lekin", "magar", "par", "aur", "toh", "to",
    "chal", "chalo", "chala", "ruk", "ruko", "ruka", "aao", "jao", "gaya", "gayi", "gaye",
    "banda", "bande", "log", "wala", "wali", "wale", "karo", "karega", "karegi", "karna",
    "kar", "raha", "rahe", "rahi", "kr", "rha", "rhe", "rhi", "liye", "bhi", "sirf",
    "pata", "lagta", "lagti", "lagte", "samajh", "aaya", "aayi", "aaye", "diya", "diyo",
    "ye", "yeh", "woh", "wo", "hua", "hui", "hue",
}

# Direct 1-to-1 token normalization (informal shorthand -> clear spoken Roman Hindi)
ROMAN_HINDI_SPELLINGS: Dict[str, str] = {
    # Verbs and common roots
    "kr": "kar",
    "rha": "raha",
    "rhi": "rahi",
    "rhe": "rahe",
    "bta": "bata",
    "btao": "batao",
    "btaya": "bataya",
    "btana": "batana",
    "smjh": "samajh",
    "smjha": "samajha",
    "smjho": "samajho",
    "acha": "accha",
    "achha": "accha",
    "kyu": "kyu",
    "kyun": "kyun",
    "kyon": "kyun",
    "kuchh": "kuch",
    "kch": "kuch",
    "nahin": "nahi",
    "nhi": "nahi",
    "bhot": "bahut",
    "bhut": "bahut",
    "pehle": "pehle",
    "phle": "pehle",
    "fir": "phir",
    "lkin": "lekin",
    "arre": "arey",
    "aree": "arey",
    "kro": "karo",
    "krega": "karega",
    "kregi": "karegi",
    "krna": "karna",
    "hogya": "ho gaya",
    "hogyi": "ho gayi",
    "krlia": "kar liya",
    "aara": "aa raha",
    "jara": "ja raha",
    "dekhra": "dekh raha",
    "yha": "yahan",
    "wha": "wahan",
    "kha": "kahan",
    "sb": "sab",
    "tb": "tab",
    "ab": "ab",
    "mze": "maze",
    "dost": "bhai",
}

# Multi-token compound contractions: (token_1, token_2, ...) -> [norm_1, norm_2, ...]
MULTI_TOKEN_CONTRACTIONS: Dict[Tuple[str, ...], List[str]] = {
    ("kr", "rha"): ["kar", "raha"],
    ("kr", "rhi"): ["kar", "rahi"],
    ("kr", "rhe"): ["kar", "rahe"],
    ("kr", "raha"): ["kar", "raha"],
    ("kr", "rahi"): ["kar", "rahi"],
    ("kr", "rahe"): ["kar", "rahe"],
    ("ho", "rha"): ["ho", "raha"],
    ("ho", "rhi"): ["ho", "rahi"],
    ("ho", "rhe"): ["ho", "rahe"],
    ("aa", "rha"): ["aa", "raha"],
    ("ja", "rha"): ["ja", "raha"],
    ("dekh", "rha"): ["dekh", "raha"],
    ("bol", "rha"): ["bol", "raha"],
    ("mat", "kr"): ["mat", "kar"],
    ("kya", "kr"): ["kya", "kar"],
    ("kya", "hua"): ["kya", "hua"],
    ("one", "tap"): ["one", "tap"],
    ("1", "tap"): ["one", "tap"],
    ("one", "hp"): ["one", "HP"],
    ("1", "hp"): ["one", "HP"],
    ("low", "hp"): ["low", "HP"],
    ("spike", "down"): ["Spike", "down"],
    ("spock", "down"): ["Spike", "down"],
}


def is_roman_hindi_word(word: str) -> bool:
    """Checks whether the cleaned word matches known Roman Hindi vocabulary."""
    clean = word.lower().strip(".,!?:;\"'()[]{}")
    return clean in ROMAN_HINDI_MARKERS or clean in ROMAN_HINDI_SPELLINGS


def normalize_roman_hindi_token(token: str) -> Tuple[str, bool]:
    """
    Normalizes single Roman Hindi token spelling if recognized.
    Returns (normalized_word, changed).
    """
    raw_lower = token.lower()
    clean = raw_lower.strip(".,!?:;\"'()[]{}")
    if not clean:
        return token, False

    # Extract leading/trailing punctuation
    leading = ""
    trailing = ""
    for ch in token:
        if ch in ".,!?:;\"'({[":
            leading += ch
        else:
            break
    for ch in reversed(token):
        if ch in ".,!?:;\"')}]":
            trailing = ch + trailing
        else:
            break

    if clean in ROMAN_HINDI_SPELLINGS:
        norm = ROMAN_HINDI_SPELLINGS[clean]
        # Preserve original capitalization style if word started uppercase
        if token and token[0].isupper() and not norm.startswith("ho "):
            norm = norm.capitalize()
        return leading + norm + trailing, True

    return token, False
