import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    id: str            # canonical id
    name: str          # English name (Rider-Waite-Smith)
    arcana: str        # "major" | "minor"
    suit: str | None   # "wands" | "cups" | "swords" | "pentacles" | None
    number: int | None
    upright: tuple[str, ...]   # 3-5 keywords
    reversed: tuple[str, ...]  # 3-5 keywords


@dataclass(frozen=True)
class CardDraw:
    card: Card
    reversed: bool
    position: str  # "past" | "present" | "future"


TAROT_DECK: list[Card] = [
    # ===== Major Arcana (22) =====
    Card(
        id="major_00_fool",
        name="The Fool",
        arcana="major", suit=None, number=0,
        upright=("beginnings", "innocence", "leap of faith", "spontaneity"),
        reversed=("recklessness", "naivety", "hesitation"),
    ),
    Card(
        id="major_01_magician",
        name="The Magician",
        arcana="major", suit=None, number=1,
        upright=("manifestation", "willpower", "skill", "focus"),
        reversed=("manipulation", "blocked talent", "wasted skill"),
    ),
    Card(
        id="major_02_high_priestess",
        name="The High Priestess",
        arcana="major", suit=None, number=2,
        upright=("intuition", "mystery", "inner knowledge", "stillness"),
        reversed=("secrets", "repressed intuition", "disconnection"),
    ),
    Card(
        id="major_03_empress",
        name="The Empress",
        arcana="major", suit=None, number=3,
        upright=("fertility", "abundance", "nurturing", "nature"),
        reversed=("dependence", "creative block", "neglect"),
    ),
    Card(
        id="major_04_emperor",
        name="The Emperor",
        arcana="major", suit=None, number=4,
        upright=("authority", "structure", "stability", "leadership"),
        reversed=("rigidity", "tyranny", "loss of control"),
    ),
    Card(
        id="major_05_hierophant",
        name="The Hierophant",
        arcana="major", suit=None, number=5,
        upright=("tradition", "belief", "conformity", "spiritual guidance"),
        reversed=("rebellion", "dogmatism", "unorthodoxy"),
    ),
    Card(
        id="major_06_lovers",
        name="The Lovers",
        arcana="major", suit=None, number=6,
        upright=("love", "union", "alignment", "choice"),
        reversed=("disharmony", "imbalance", "misaligned values"),
    ),
    Card(
        id="major_07_chariot",
        name="The Chariot",
        arcana="major", suit=None, number=7,
        upright=("willpower", "victory", "determination", "control"),
        reversed=("lack of control", "aggression", "directionlessness"),
    ),
    Card(
        id="major_08_strength",
        name="Strength",
        arcana="major", suit=None, number=8,
        upright=("courage", "patience", "inner strength", "compassion"),
        reversed=("self-doubt", "weakness", "raw instinct"),
    ),
    Card(
        id="major_09_hermit",
        name="The Hermit",
        arcana="major", suit=None, number=9,
        upright=("introspection", "solitude", "guidance", "soul searching"),
        reversed=("isolation", "loneliness", "withdrawal"),
    ),
    Card(
        id="major_10_wheel_of_fortune",
        name="Wheel of Fortune",
        arcana="major", suit=None, number=10,
        upright=("luck", "cycles", "destiny", "turning point"),
        reversed=("bad luck", "resistance to change", "breaking cycles"),
    ),
    Card(
        id="major_11_justice",
        name="Justice",
        arcana="major", suit=None, number=11,
        upright=("fairness", "truth", "law", "cause and effect"),
        reversed=("injustice", "dishonesty", "bias"),
    ),
    Card(
        id="major_12_hanged_man",
        name="The Hanged Man",
        arcana="major", suit=None, number=12,
        upright=("suspension", "sacrifice", "new perspective", "letting go"),
        reversed=("stalling", "resistance", "indecision"),
    ),
    Card(
        id="major_13_death",
        name="Death",
        arcana="major", suit=None, number=13,
        upright=("endings", "transition", "transformation", "letting go"),
        reversed=("resistance to change", "stagnation", "inability to move on"),
    ),
    Card(
        id="major_14_temperance",
        name="Temperance",
        arcana="major", suit=None, number=14,
        upright=("balance", "moderation", "patience", "purpose"),
        reversed=("imbalance", "excess", "lack of harmony"),
    ),
    Card(
        id="major_15_devil",
        name="The Devil",
        arcana="major", suit=None, number=15,
        upright=("bondage", "addiction", "materialism", "shadow self"),
        reversed=("release", "independence", "reclaiming power"),
    ),
    Card(
        id="major_16_tower",
        name="The Tower",
        arcana="major", suit=None, number=16,
        upright=("upheaval", "revelation", "chaos", "sudden change"),
        reversed=("averted disaster", "delayed crisis", "inner disruption"),
    ),
    Card(
        id="major_17_star",
        name="The Star",
        arcana="major", suit=None, number=17,
        upright=("hope", "inspiration", "serenity", "renewal"),
        reversed=("despair", "lack of faith", "disconnection"),
    ),
    Card(
        id="major_18_moon",
        name="The Moon",
        arcana="major", suit=None, number=18,
        upright=("illusion", "fear", "the unconscious", "confusion"),
        reversed=("clarity emerging", "releasing fear", "repressed emotion"),
    ),
    Card(
        id="major_19_sun",
        name="The Sun",
        arcana="major", suit=None, number=19,
        upright=("joy", "success", "vitality", "positivity"),
        reversed=("temporary depression", "inner child blocks", "over-optimism"),
    ),
    Card(
        id="major_20_judgement",
        name="Judgement",
        arcana="major", suit=None, number=20,
        upright=("reflection", "reckoning", "awakening", "absolution"),
        reversed=("self-doubt", "harsh judgment", "ignoring the call"),
    ),
    Card(
        id="major_21_world",
        name="The World",
        arcana="major", suit=None, number=21,
        upright=("completion", "integration", "accomplishment", "wholeness"),
        reversed=("incompletion", "shortcuts", "delays"),
    ),

    # ===== Wands (14) =====
    Card(
        id="wands_01",
        name="Ace of Wands",
        arcana="minor", suit="wands", number=1,
        upright=("inspiration", "new venture", "creative spark", "potential"),
        reversed=("delays", "lack of motivation", "creative block"),
    ),
    Card(
        id="wands_02",
        name="Two of Wands",
        arcana="minor", suit="wands", number=2,
        upright=("planning", "future vision", "progress", "decisions"),
        reversed=("fear of unknown", "lack of planning", "stagnation"),
    ),
    Card(
        id="wands_03",
        name="Three of Wands",
        arcana="minor", suit="wands", number=3,
        upright=("expansion", "foresight", "overseas opportunity", "enterprise"),
        reversed=("obstacles", "delays in plans", "lack of foresight"),
    ),
    Card(
        id="wands_04",
        name="Four of Wands",
        arcana="minor", suit="wands", number=4,
        upright=("celebration", "harmony", "homecoming", "community"),
        reversed=("lack of support", "transition", "home conflict"),
    ),
    Card(
        id="wands_05",
        name="Five of Wands",
        arcana="minor", suit="wands", number=5,
        upright=("conflict", "competition", "tension", "diversity"),
        reversed=("avoiding conflict", "compromise", "inner tension"),
    ),
    Card(
        id="wands_06",
        name="Six of Wands",
        arcana="minor", suit="wands", number=6,
        upright=("victory", "public recognition", "progress", "self-confidence"),
        reversed=("ego", "fall from grace", "lack of recognition"),
    ),
    Card(
        id="wands_07",
        name="Seven of Wands",
        arcana="minor", suit="wands", number=7,
        upright=("challenge", "perseverance", "defensiveness", "standing firm"),
        reversed=("overwhelmed", "giving up", "self-doubt"),
    ),
    Card(
        id="wands_08",
        name="Eight of Wands",
        arcana="minor", suit="wands", number=8,
        upright=("speed", "movement", "swift action", "alignment"),
        reversed=("delays", "frustration", "scattered energy"),
    ),
    Card(
        id="wands_09",
        name="Nine of Wands",
        arcana="minor", suit="wands", number=9,
        upright=("resilience", "persistence", "last stand", "boundary"),
        reversed=("exhaustion", "giving up", "paranoia"),
    ),
    Card(
        id="wands_10",
        name="Ten of Wands",
        arcana="minor", suit="wands", number=10,
        upright=("burden", "extra responsibility", "overextension", "struggle"),
        reversed=("delegation", "releasing burden", "collapse"),
    ),
    Card(
        id="wands_page",
        name="Page of Wands",
        arcana="minor", suit="wands", number=None,
        upright=("exploration", "enthusiasm", "free spirit", "new ideas"),
        reversed=("scattered energy", "procrastination", "immaturity"),
    ),
    Card(
        id="wands_knight",
        name="Knight of Wands",
        arcana="minor", suit="wands", number=None,
        upright=("action", "adventure", "impulsiveness", "energy"),
        reversed=("recklessness", "hot-headedness", "burnout"),
    ),
    Card(
        id="wands_queen",
        name="Queen of Wands",
        arcana="minor", suit="wands", number=None,
        upright=("courage", "confidence", "determination", "warmth"),
        reversed=("jealousy", "overbearing", "insecurity"),
    ),
    Card(
        id="wands_king",
        name="King of Wands",
        arcana="minor", suit="wands", number=None,
        upright=("visionary", "bold", "entrepreneur", "natural leader"),
        reversed=("impulsiveness", "overbearing", "ineffective"),
    ),

    # ===== Cups (14) =====
    Card(
        id="cups_01",
        name="Ace of Cups",
        arcana="minor", suit="cups", number=1,
        upright=("new love", "compassion", "emotional beginning", "intuition"),
        reversed=("emotional loss", "blocked feelings", "emptiness"),
    ),
    Card(
        id="cups_02",
        name="Two of Cups",
        arcana="minor", suit="cups", number=2,
        upright=("partnership", "mutual attraction", "connection", "harmony"),
        reversed=("imbalance", "broken communication", "tension"),
    ),
    Card(
        id="cups_03",
        name="Three of Cups",
        arcana="minor", suit="cups", number=3,
        upright=("celebration", "friendship", "community", "joy"),
        reversed=("overindulgence", "gossip", "isolation"),
    ),
    Card(
        id="cups_04",
        name="Four of Cups",
        arcana="minor", suit="cups", number=4,
        upright=("contemplation", "apathy", "missed opportunity", "re-evaluation"),
        reversed=("motivation", "new possibilities", "emerging from withdrawal"),
    ),
    Card(
        id="cups_05",
        name="Five of Cups",
        arcana="minor", suit="cups", number=5,
        upright=("loss", "grief", "disappointment", "regret"),
        reversed=("acceptance", "moving on", "finding peace"),
    ),
    Card(
        id="cups_06",
        name="Six of Cups",
        arcana="minor", suit="cups", number=6,
        upright=("nostalgia", "childhood", "innocence", "reunion"),
        reversed=("living in the past", "naivety", "unrealistic"),
    ),
    Card(
        id="cups_07",
        name="Seven of Cups",
        arcana="minor", suit="cups", number=7,
        upright=("fantasy", "illusion", "wishful thinking", "choices"),
        reversed=("clarity", "sobering reality", "decisiveness"),
    ),
    Card(
        id="cups_08",
        name="Eight of Cups",
        arcana="minor", suit="cups", number=8,
        upright=("withdrawal", "walking away", "seeking deeper meaning", "disappointment"),
        reversed=("avoidance", "fear of moving on", "hopelessness"),
    ),
    Card(
        id="cups_09",
        name="Nine of Cups",
        arcana="minor", suit="cups", number=9,
        upright=("contentment", "wish fulfilled", "satisfaction", "gratitude"),
        reversed=("materialism", "dissatisfaction", "overindulgence"),
    ),
    Card(
        id="cups_10",
        name="Ten of Cups",
        arcana="minor", suit="cups", number=10,
        upright=("harmony", "bliss", "family", "fulfillment"),
        reversed=("broken home", "disconnection", "misaligned values"),
    ),
    Card(
        id="cups_page",
        name="Page of Cups",
        arcana="minor", suit="cups", number=None,
        upright=("curiosity", "sensitivity", "new feelings", "intuitive message"),
        reversed=("emotional immaturity", "creative block", "escapism"),
    ),
    Card(
        id="cups_knight",
        name="Knight of Cups",
        arcana="minor", suit="cups", number=None,
        upright=("romanticism", "charm", "creativity", "following the heart"),
        reversed=("moodiness", "unrealistic", "jealousy"),
    ),
    Card(
        id="cups_queen",
        name="Queen of Cups",
        arcana="minor", suit="cups", number=None,
        upright=("compassion", "care", "empathy", "emotional security"),
        reversed=("emotional insecurity", "co-dependency", "martyrdom"),
    ),
    Card(
        id="cups_king",
        name="King of Cups",
        arcana="minor", suit="cups", number=None,
        upright=("emotional balance", "diplomacy", "compassionate authority", "wisdom"),
        reversed=("emotional manipulation", "moodiness", "withdrawal"),
    ),

    # ===== Swords (14) =====
    Card(
        id="swords_01",
        name="Ace of Swords",
        arcana="minor", suit="swords", number=1,
        upright=("clarity", "breakthrough", "truth", "mental force"),
        reversed=("confusion", "brutality", "unclear thinking"),
    ),
    Card(
        id="swords_02",
        name="Two of Swords",
        arcana="minor", suit="swords", number=2,
        upright=("indecision", "stalemate", "blocked emotions", "difficult choice"),
        reversed=("indecision lifted", "confusion", "information overload"),
    ),
    Card(
        id="swords_03",
        name="Three of Swords",
        arcana="minor", suit="swords", number=3,
        upright=("heartbreak", "sorrow", "grief", "painful truth"),
        reversed=("recovery", "forgiveness", "healing pain"),
    ),
    Card(
        id="swords_04",
        name="Four of Swords",
        arcana="minor", suit="swords", number=4,
        upright=("rest", "restoration", "contemplation", "recuperation"),
        reversed=("restlessness", "burnout", "re-entering struggle"),
    ),
    Card(
        id="swords_05",
        name="Five of Swords",
        arcana="minor", suit="swords", number=5,
        upright=("defeat", "conflict", "betrayal", "hollow victory"),
        reversed=("reconciliation", "moving past conflict", "regret"),
    ),
    Card(
        id="swords_06",
        name="Six of Swords",
        arcana="minor", suit="swords", number=6,
        upright=("transition", "moving on", "healing", "calmer waters"),
        reversed=("resistance", "unfinished business", "stuck in turmoil"),
    ),
    Card(
        id="swords_07",
        name="Seven of Swords",
        arcana="minor", suit="swords", number=7,
        upright=("deception", "strategy", "theft", "getting away with it"),
        reversed=("confession", "coming clean", "conscience"),
    ),
    Card(
        id="swords_08",
        name="Eight of Swords",
        arcana="minor", suit="swords", number=8,
        upright=("restriction", "limitation", "self-imprisonment", "powerlessness"),
        reversed=("release", "seeing the truth", "reclaiming power"),
    ),
    Card(
        id="swords_09",
        name="Nine of Swords",
        arcana="minor", suit="swords", number=9,
        upright=("anxiety", "worry", "fear", "despair"),
        reversed=("inner turmoil", "releasing anxiety", "hope"),
    ),
    Card(
        id="swords_10",
        name="Ten of Swords",
        arcana="minor", suit="swords", number=10,
        upright=("painful endings", "betrayal", "rock bottom", "crisis"),
        reversed=("recovery", "regeneration", "resisting the inevitable"),
    ),
    Card(
        id="swords_page",
        name="Page of Swords",
        arcana="minor", suit="swords", number=None,
        upright=("curiosity", "vigilance", "new ideas", "mental agility"),
        reversed=("haste", "cunning", "all talk no action"),
    ),
    Card(
        id="swords_knight",
        name="Knight of Swords",
        arcana="minor", suit="swords", number=None,
        upright=("ambition", "action", "drive", "quick thinking"),
        reversed=("recklessness", "impatience", "rushing"),
    ),
    Card(
        id="swords_queen",
        name="Queen of Swords",
        arcana="minor", suit="swords", number=None,
        upright=("clear thinking", "independence", "direct communication", "sharp mind"),
        reversed=("coldness", "cruelty", "bitterness"),
    ),
    Card(
        id="swords_king",
        name="King of Swords",
        arcana="minor", suit="swords", number=None,
        upright=("intellectual power", "authority", "truth", "ethical clarity"),
        reversed=("manipulation", "abuse of power", "irrational thinking"),
    ),

    # ===== Pentacles (14) =====
    Card(
        id="pentacles_01",
        name="Ace of Pentacles",
        arcana="minor", suit="pentacles", number=1,
        upright=("new opportunity", "abundance", "manifestation", "prosperity"),
        reversed=("missed opportunity", "poor planning", "financial instability"),
    ),
    Card(
        id="pentacles_02",
        name="Two of Pentacles",
        arcana="minor", suit="pentacles", number=2,
        upright=("balance", "adaptability", "time management", "juggling priorities"),
        reversed=("disorganization", "imbalance", "overwhelmed"),
    ),
    Card(
        id="pentacles_03",
        name="Three of Pentacles",
        arcana="minor", suit="pentacles", number=3,
        upright=("teamwork", "collaboration", "skill", "mastery"),
        reversed=("disharmony", "lack of teamwork", "poor quality"),
    ),
    Card(
        id="pentacles_04",
        name="Four of Pentacles",
        arcana="minor", suit="pentacles", number=4,
        upright=("security", "conservation", "control", "stability"),
        reversed=("greed", "materialism", "self-protection"),
    ),
    Card(
        id="pentacles_05",
        name="Five of Pentacles",
        arcana="minor", suit="pentacles", number=5,
        upright=("hardship", "poverty", "insecurity", "worry"),
        reversed=("recovery", "spiritual poverty", "improvement"),
    ),
    Card(
        id="pentacles_06",
        name="Six of Pentacles",
        arcana="minor", suit="pentacles", number=6,
        upright=("generosity", "charity", "giving and receiving", "shared wealth"),
        reversed=("selfishness", "debt", "power and domination"),
    ),
    Card(
        id="pentacles_07",
        name="Seven of Pentacles",
        arcana="minor", suit="pentacles", number=7,
        upright=("patience", "long-term view", "investment", "assessment"),
        reversed=("impatience", "poor returns", "lack of reward"),
    ),
    Card(
        id="pentacles_08",
        name="Eight of Pentacles",
        arcana="minor", suit="pentacles", number=8,
        upright=("diligence", "skill development", "craftsmanship", "dedication"),
        reversed=("perfectionism", "lack of focus", "mediocrity"),
    ),
    Card(
        id="pentacles_09",
        name="Nine of Pentacles",
        arcana="minor", suit="pentacles", number=9,
        upright=("abundance", "luxury", "self-sufficiency", "financial independence"),
        reversed=("financial dependence", "overinvestment", "superficiality"),
    ),
    Card(
        id="pentacles_10",
        name="Ten of Pentacles",
        arcana="minor", suit="pentacles", number=10,
        upright=("wealth", "inheritance", "family legacy", "long-term success"),
        reversed=("financial failure", "family disputes", "loss of legacy"),
    ),
    Card(
        id="pentacles_page",
        name="Page of Pentacles",
        arcana="minor", suit="pentacles", number=None,
        upright=("ambition", "diligence", "new beginnings", "opportunity"),
        reversed=("lack of progress", "procrastination", "learn from failure"),
    ),
    Card(
        id="pentacles_knight",
        name="Knight of Pentacles",
        arcana="minor", suit="pentacles", number=None,
        upright=("hard work", "routine", "responsibility", "methodical"),
        reversed=("boredom", "feeling stuck", "perfectionism"),
    ),
    Card(
        id="pentacles_queen",
        name="Queen of Pentacles",
        arcana="minor", suit="pentacles", number=None,
        upright=("nurturing", "practical", "providing financially", "down-to-earth"),
        reversed=("self-centeredness", "jealousy", "smothering"),
    ),
    Card(
        id="pentacles_king",
        name="King of Pentacles",
        arcana="minor", suit="pentacles", number=None,
        upright=("abundance", "security", "discipline", "dependability"),
        reversed=("greed", "materialism", "financial ruin"),
    ),
]

assert len(TAROT_DECK) == 78, f"expected 78 cards, got {len(TAROT_DECK)}"
assert len({c.id for c in TAROT_DECK}) == 78, "duplicate card ids"

_DECK_BY_ID: dict[str, Card] = {c.id: c for c in TAROT_DECK}

_POSITIONS: tuple[str, ...] = ("past", "present", "future")


def draw_three(rng: random.Random | None = None) -> list[CardDraw]:
    """Draw three distinct cards. Each card is independently 50/50 reversed."""
    r = rng if rng is not None else random.SystemRandom()
    drawn = r.sample(TAROT_DECK, 3)
    return [
        CardDraw(card=card, reversed=bool(r.randrange(2)), position=pos)
        for card, pos in zip(drawn, _POSITIONS, strict=True)
    ]


def build_calc_md(*, question: str | None, cards: list[CardDraw]) -> str:
    """Markdown summary the LLM polishes."""
    lines: list[str] = ["# Tarot - Three-Card Spread", ""]
    if question:
        lines.append(f"**Question:** {question}")
    else:
        lines.append("**Question:** (none)")
    lines.append("")
    for d in cards:
        orient = "reversed" if d.reversed else "upright"
        kw_set = d.card.reversed if d.reversed else d.card.upright
        kw = ", ".join(kw_set)
        lines.append(f"## {d.position.capitalize()} - {d.card.name} ({orient})")
        lines.append(f"Keywords: {kw}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_calc_md_from_jsonb(draw: dict) -> str:
    """Rehydrate from the persisted draw_jsonb and reuse build_calc_md."""
    question = draw.get("question")
    cards: list[CardDraw] = []
    for entry in draw.get("cards", []):
        card_id = entry["id"]
        if card_id not in _DECK_BY_ID:
            raise KeyError(f"unknown tarot card id: {card_id}")
        cards.append(CardDraw(
            card=_DECK_BY_ID[card_id],
            reversed=bool(entry.get("reversed", False)),
            position=entry["position"],
        ))
    return build_calc_md(question=question, cards=cards)
