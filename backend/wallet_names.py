"""Readable wallet codenames ("Cobalt Heron") derived from the address.

Mirrors frontend/src/utils/walletName.js exactly (same word lists, same hash) so a wallet has
the same name in Telegram as in the app; tests/test_wallet_names.py checks the two agree.
Block0's 16 + 16 words come first; the longer lists and FNV-1a keep the ~500 tracked wallets
from sharing names.
"""

ADJECTIVES = (
    "Silent", "Golden", "Crimson", "Azure", "Feral", "Lucid", "Iron", "Neon",
    "Velvet", "Rogue", "Amber", "Cobalt", "Onyx", "Solar", "Frost", "Ember",
    "Arctic", "Ashen", "Autumn", "Blazing", "Bold", "Brisk", "Bronze", "Calm",
    "Cedar", "Cerulean", "Cinder", "Clever", "Cloudy", "Copper", "Coral", "Cosmic",
    "Crystal", "Dapper", "Desert", "Distant", "Drifting", "Dusky", "Dusty", "Eager",
    "Electric", "Emerald", "Fabled", "Fierce", "Fleet", "Flint", "Gentle", "Gilded",
    "Glacial", "Granite", "Gusty", "Hazel", "Hazy", "Hidden", "Hollow", "Indigo",
    "Ivory", "Jade", "Jolly", "Keen", "Lively", "Lunar", "Magnetic", "Maple",
    "Marble", "Mellow", "Midnight", "Misty", "Mossy", "Mystic", "Nimble", "Noble",
    "Northern", "Oaken", "Obsidian", "Ochre", "Opal", "Orchid", "Pale", "Patient",
    "Pearl", "Plucky", "Polar", "Prism", "Quartz", "Quick", "Quiet", "Radiant",
    "Rainy", "Rapid", "Rosy", "Ruby", "Russet", "Rustic", "Sable", "Saffron",
    "Sandy", "Sapphire", "Scarlet", "Serene", "Sienna", "Silver", "Slate", "Sly",
    "Smoky", "Snowy", "Sonic", "Spry", "Starlit", "Steady", "Stellar", "Stoic",
    "Stormy", "Sturdy", "Sunny", "Swift", "Tawny", "Teal", "Tidal", "Timber",
    "Topaz", "Tranquil", "Twilight", "Umber", "Verdant", "Violet", "Vivid", "Wandering",
    "Wild", "Wily", "Windy", "Winter", "Wise", "Woolly", "Zesty", "Hushed",
)

NOUNS = (
    "Fox", "Whale", "Falcon", "Wolf", "Orca", "Hawk", "Viper", "Lynx",
    "Raven", "Shark", "Otter", "Puma", "Heron", "Mako", "Koi", "Crane",
    "Albatross", "Antelope", "Badger", "Barracuda", "Beaver", "Beetle", "Bison", "Bittern",
    "Bobcat", "Buffalo", "Caribou", "Cheetah", "Cobra", "Condor", "Cormorant", "Cougar",
    "Coyote", "Crow", "Curlew", "Dingo", "Dolphin", "Dragonfly", "Eagle", "Egret",
    "Elk", "Ferret", "Finch", "Gannet", "Gazelle", "Gecko", "Gibbon", "Grouse",
    "Gull", "Hare", "Hedgehog", "Hornet", "Ibis", "Iguana", "Jackal", "Jay",
    "Kestrel", "Kingfisher", "Kite", "Koala", "Lark", "Lemur", "Leopard", "Lion",
    "Llama", "Lobster", "Magpie", "Manta", "Mantis", "Marlin", "Marten", "Meerkat",
    "Mink", "Mongoose", "Moose", "Moth", "Narwhal", "Newt", "Nightjar", "Ocelot",
    "Oriole", "Osprey", "Owl", "Panda", "Panther", "Parrot", "Pelican", "Penguin",
    "Petrel", "Pheasant", "Pike", "Plover", "Puffin", "Quail", "Rabbit", "Raccoon",
    "Reindeer", "Robin", "Sailfish", "Salmon", "Sandpiper", "Seal", "Skylark", "Sparrow",
    "Squid", "Stag", "Starling", "Stingray", "Stork", "Swallow", "Swan", "Swordfish",
    "Tapir", "Tern", "Tiger", "Toucan", "Trout", "Tuna", "Turtle", "Walrus",
    "Wasp", "Weasel", "Wolverine", "Woodpecker", "Wren", "Yak", "Zebra", "Pika",
)

_M = 0xFFFFFFFF


def _fnv1a(s: str) -> int:
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & _M
    return h


def _fmix(h: int) -> int:
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & _M
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & _M
    h ^= h >> 16
    return h


def codename(address: str) -> str:
    """'Adjective Noun' for a wallet address (case and surrounding spaces ignored)."""
    s = str(address or "").strip().lower()
    if not s:
        return ""
    h = _fnv1a(s)
    return f"{ADJECTIVES[_fmix(h ^ 0x9E3779B9) % len(ADJECTIVES)]} {NOUNS[_fmix(h ^ 0x7F4A7C15) % len(NOUNS)]}"


def short_address(address: str) -> str:
    s = str(address or "")
    return f"{s[:6]}…{s[-4:]}" if len(s) > 12 else s


def wallet_label(address: str) -> str:
    """Codename with the short address after it, for alert texts: 'Cobalt Heron (0x1234…abcd)'."""
    return f"{codename(address)} ({short_address(address)})" if address else ""
