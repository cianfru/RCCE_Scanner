// Readable wallet identity: a made-up "Adjective Noun" codename and a gradient avatar, both
// derived from the address, so a wallet reads as "Cobalt Heron" instead of a hex string.
// Same idea as Block0's wallet codenames (its 16 + 16 words come first in each list), with
// longer lists and a better hash so the ~500 tracked wallets rarely share a name.
// backend/wallet_names.py mirrors this exactly (lists and hash); its test checks parity.

export const ADJECTIVES = [
  // Block0
  "Silent", "Golden", "Crimson", "Azure", "Feral", "Lucid", "Iron", "Neon",
  "Velvet", "Rogue", "Amber", "Cobalt", "Onyx", "Solar", "Frost", "Ember",
  // Added
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
];

export const NOUNS = [
  // Block0
  "Fox", "Whale", "Falcon", "Wolf", "Orca", "Hawk", "Viper", "Lynx",
  "Raven", "Shark", "Otter", "Puma", "Heron", "Mako", "Koi", "Crane",
  // Added
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
];

// 32-bit FNV-1a over the lowercase address, then a murmur3 finaliser so every bit mixes.
function fnv1a(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}
function fmix(h) {
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b) >>> 0;
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35) >>> 0;
  h ^= h >>> 16;
  return h >>> 0;
}
const norm = a => String(a || "").trim().toLowerCase();

// The address's seed, and independent 32-bit draws from it (one salt per use).
export const walletSeed = address => fnv1a(norm(address));
export const draw = (seed, salt) => fmix((seed ^ salt) >>> 0);

// Three independent draws per address: adjective, noun, avatar.
export function walletHashes(address) {
  const h = walletSeed(address);
  return [draw(h, 0x9e3779b9), draw(h, 0x7f4a7c15), draw(h, 0x94d049bb)];
}

export function codename(address) {
  if (!address) return "";
  const [a, n] = walletHashes(address);
  return `${ADJECTIVES[a % ADJECTIVES.length]} ${NOUNS[n % NOUNS.length]}`;
}

export const shortAddr = a => {
  const s = String(a || "");
  return s.length > 12 ? `${s.slice(0, 6)}…${s.slice(-4)}` : s;
};

// Display names for the wallets shown together: a codename that two wallets in this view share
// gets the address's last characters ("Cobalt Heron ·3fa2"), the fewest that tell them apart.
export function viewNames(addresses) {
  const uniq = [...new Set((addresses || []).filter(Boolean).map(norm))];
  const groups = new Map();
  for (const a of uniq) {
    const n = codename(a);
    if (!groups.has(n)) groups.set(n, []);
    groups.get(n).push(a);
  }
  const out = new Map();
  for (const [n, list] of groups) {
    if (list.length === 1) { out.set(list[0], n); continue; }
    let k = 4;
    while (k < 40 && new Set(list.map(a => a.slice(-k))).size < list.length) k++;
    for (const a of list) out.set(a, `${n} ·${a.slice(-k)}`);
  }
  return out;
}

// One name from a viewNames map, falling back to the plain codename.
export const nameIn = (names, address) => (names && names.get(norm(address))) || codename(address);

// Chart tags for the wallets shown together: the codename's initials ("Arctic Mako" is "AM"),
// numbered when two wallets in the view share them ("AM", "AM2").
export function markerTags(addresses) {
  const out = new Map(), used = new Map();
  for (const a of (addresses || []).filter(Boolean).map(norm)) {
    if (out.has(a)) continue;
    const base = codename(a).split(" ").map(w => w[0]).join("");
    const k = (used.get(base) || 0) + 1;
    used.set(base, k);
    out.set(a, k === 1 ? base : `${base}${k}`);
  }
  return out;
}
