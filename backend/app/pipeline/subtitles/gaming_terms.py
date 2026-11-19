"""Gaming terms, proper names, and hardware acronyms protection dictionary."""

from typing import Dict, Optional, Set

# Canonical casing for gaming actions, weapons, games, and hardware terms
PROTECTED_GAMING_TERMS: Dict[str, str] = {
    # Gaming Actions & Mechanics
    "clutch": "clutch",
    "clutched": "clutched",
    "rush": "rush",
    "push": "push",
    "camp": "camp",
    "peek": "peek",
    "peeking": "peeking",
    "jiggle peek": "jiggle peek",
    "wide peek": "wide peek",
    "one tap": "one tap",
    "onetap": "one tap",
    "1 tap": "one tap",
    "headshot": "headshot",
    "head shot": "headshot",
    "spray": "spray",
    "spray transfer": "spray transfer",
    "reload": "reload",
    "reloading": "reloading",
    "flash": "flash",
    "smoke": "smoke",
    "smoking": "smoking",
    "grenade": "grenade",
    "nade": "nade",
    "kill": "kill",
    "knock": "knock",
    "knocked": "knocked",
    "revive": "revive",
    "reviving": "reviving",
    "rez": "revive",
    "rezz": "revive",
    "loot": "loot",
    "looting": "looting",
    "zone": "zone",
    "circle": "circle",
    "damage": "damage",
    "hp": "HP",
    "one hp": "one HP",
    "1 hp": "one HP",
    "low hp": "low HP",
    "aim": "aim",
    "crosshair": "crosshair",
    "scope": "scope",
    "scoped": "scoped",
    "sniper": "sniper",
    "shotgun": "shotgun",
    "rifle": "rifle",
    "enemy": "enemy",
    "enemies": "enemies",
    "squad": "squad",
    "team": "team",
    "teammate": "teammate",
    "rank": "rank",
    "ranked": "ranked",
    "match": "match",
    "round": "round",
    "win": "win",
    "lose": "lose",
    "lag": "lag",
    "ping": "ping",
    "fps": "FPS",
    "stream": "stream",
    "chat": "chat",
    "clip": "clip",
    "ace": "ace",
    "drop": "drop",
    "flank": "flank",
    "defuse": "defuse",
    "plant": "plant",
    "bomb": "bomb",
    "spike": "Spike",
    "spike down": "Spike down",
    "spikedown": "Spike down",
    "spockdown": "Spike down",
    "retake": "retake",
    "retaking": "retaking",
    "lineup": "lineup",
    "lineups": "lineups",
    "wallbang": "wallbang",
    "wallbanged": "wallbanged",
    "flick": "flick",
    "flicked": "flicked",
    "dink": "dink",
    "dinked": "dinked",
    "whiff": "whiff",
    "whiffed": "whiffed",
    "eco": "eco",
    "force buy": "force buy",
    "thrifty": "thrifty",
    "diff": "diff",
    "diffed": "diffed",
    "bot": "bot",
    "noob": "noob",
    "pro": "pro",
    "hacker": "hacker",
    "spawn": "spawn",
    "respawn": "respawn",
    "gank": "gank",
    "heal": "heal",
    "shield": "shield",
    "gg": "GG",
    "ggs": "GGs",
    "ez": "EZ",
    "wp": "WP",
    "nt": "NT",
    "ff": "FF",
    "igl": "IGL",

    # Popular Games & Franchises
    "csgo": "CS:GO",
    "cs:go": "CS:GO",
    "cs2": "CS2",
    "counter-strike": "Counter-Strike",
    "counter strike": "Counter-Strike",
    "valorant": "Valorant",
    "gta": "GTA",
    "gta5": "GTA 5",
    "gta v": "GTA V",
    "pubg": "PUBG",
    "bgmi": "BGMI",
    "cod": "COD",
    "call of duty": "Call of Duty",
    "warzone": "Warzone",
    "minecraft": "Minecraft",
    "fortnite": "Fortnite",
    "apex": "Apex",
    "apex legends": "Apex Legends",
    "dota": "Dota",
    "dota 2": "Dota 2",
    "overwatch": "Overwatch",
    "roblox": "Roblox",
    "free fire": "Free Fire",
    "freefire": "Free Fire",

    # Weapons & Guns
    "ak": "AK",
    "ak47": "AK-47",
    "ak-47": "AK-47",
    "awp": "AWP",
    "m4": "M4",
    "m4a4": "M4A4",
    "m4a1": "M4A1-S",
    "m4a1-s": "M4A1-S",
    "deagle": "Deagle",
    "usp": "USP",
    "glock": "Glock",
    "p90": "P90",
    "mp9": "MP9",
    "vandal": "Vandal",
    "phantom": "Phantom",
    "operator": "Operator",
    "sheriff": "Sheriff",
    "ghost": "Ghost",
    "spectre": "Spectre",
    "bucky": "Bucky",
    "judge": "Judge",
    "bulldog": "Bulldog",
    "guardian": "Guardian",
    "marshal": "Marshal",
    "ares": "Ares",
    "odin": "Odin",
    "frenzy": "Frenzy",
    "classic": "Classic",

    # Valorant Agents
    "jett": "Jett",
    "reyna": "Reyna",
    "sova": "Sova",
    "cypher": "Cypher",
    "omen": "Omen",
    "killjoy": "Killjoy",
    "viper": "Viper",
    "phoenix": "Phoenix",
    "brimstone": "Brimstone",
    "sage": "Sage",
    "raze": "Raze",
    "breach": "Breach",
    "skye": "Skye",
    "yoru": "Yoru",
    "astra": "Astra",
    "kayo": "KAY/O",
    "kay/o": "KAY/O",
    "chamber": "Chamber",
    "neon": "Neon",
    "fade": "Fade",
    "harbor": "Harbor",
    "gekko": "Gekko",
    "deadlock": "Deadlock",
    "iso": "Iso",
    "clove": "Clove",
    "vyse": "Vyse",

    # Hardware & Tech Acronyms
    "rtx": "RTX",
    "gtx": "GTX",
    "gpu": "GPU",
    "cpu": "CPU",
    "ram": "RAM",
    "ssd": "SSD",
    "nvenc": "NVENC",
    "cuda": "CUDA",
    "pc": "PC",
    "hud": "HUD",
    "kd": "K/D",
    "k/d": "K/D",
}

# Single-word keys for fast set lookup
GAMING_TERMS_SET: Set[str] = set(PROTECTED_GAMING_TERMS.keys())


def is_gaming_term(word: str) -> bool:
    """Checks if a normalized word is in the gaming vocabulary."""
    clean = word.lower().strip(".,!?:;\"'()[]{}")
    return clean in GAMING_TERMS_SET


def get_canonical_gaming_term(word: str) -> Optional[str]:
    """Returns the canonical casing of a gaming term if matched, else None."""
    clean = word.lower().strip(".,!?:;\"'()[]{}")
    if clean in PROTECTED_GAMING_TERMS:
        canonical = PROTECTED_GAMING_TERMS[clean]
        # Preserve trailing punctuation
        trailing = ""
        for char in reversed(word):
            if char in ".,!?:;":
                trailing = char + trailing
            else:
                break
        return canonical + trailing
    return None


def is_acronym_or_proper_name(word: str) -> bool:
    """Checks whether the token represents an acronym or known game title."""
    clean = word.lower().strip(".,!?:;\"'()[]{}")
    if clean in PROTECTED_GAMING_TERMS:
        canonical = PROTECTED_GAMING_TERMS[clean]
        # If uppercase or Titlecase
        return canonical.isupper() or (len(canonical) > 1 and canonical[0].isupper() and canonical != canonical.lower())
    return False
