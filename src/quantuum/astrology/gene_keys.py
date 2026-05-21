"""Gene Keys — Activation Sequence calculator.

Ported from genekeys.ts. Uses the same 64-gate wheel as Human Design.
Each gate maps to a Shadow / Gift / Siddhi triplet from Richard Rudd's
"The Gene Keys". The four primary spheres of the Activation Sequence are:

  Life's Work  = Personality Sun  (gate + line)
  Evolution    = Personality Earth
  Radiance     = Design Sun
  Purpose      = Design Earth
"""

from __future__ import annotations

from dataclasses import dataclass

from .human_design import HumanDesignChart

HEXAGRAMS: list[dict] = [
    {"gate": 1, "name": "The Creative", "shadow": "Entropy", "gift": "Freshness", "siddhi": "Beauty"},
    {"gate": 2, "name": "Higher Direction", "shadow": "Dislocation", "gift": "Orientation", "siddhi": "Unity"},
    {"gate": 3, "name": "Innocence", "shadow": "Chaos", "gift": "Innovation", "siddhi": "Innocence"},
    {"gate": 4, "name": "Forgiveness", "shadow": "Intolerance", "gift": "Understanding", "siddhi": "Forgiveness"},
    {"gate": 5, "name": "Eternity", "shadow": "Impatience", "gift": "Patience", "siddhi": "Timelessness"},
    {"gate": 6, "name": "Path of Peace", "shadow": "Conflict", "gift": "Diplomacy", "siddhi": "Peace"},
    {"gate": 7, "name": "Virtue", "shadow": "Division", "gift": "Guidance", "siddhi": "Virtue"},
    {"gate": 8, "name": "Diamond Style", "shadow": "Mediocrity", "gift": "Style", "siddhi": "Exquisiteness"},
    {"gate": 9, "name": "Power of Focus", "shadow": "Inertia", "gift": "Determination", "siddhi": "Invincibility"},
    {"gate": 10, "name": "Naturalness", "shadow": "Self-Obsession", "gift": "Naturalness", "siddhi": "Being"},
    {"gate": 11, "name": "The Light Bringer", "shadow": "Obscurity", "gift": "Idealism", "siddhi": "Light"},
    {"gate": 12, "name": "Vocabulary of Light", "shadow": "Vanity", "gift": "Discrimination", "siddhi": "Purity"},
    {"gate": 13, "name": "Way of the Lover", "shadow": "Discord", "gift": "Discernment", "siddhi": "Empathy"},
    {"gate": 14, "name": "Radiance of Wealth", "shadow": "Compromise", "gift": "Competence", "siddhi": "Bounteousness"},
    {"gate": 15, "name": "Flowering of Life", "shadow": "Dullness", "gift": "Magnetism", "siddhi": "Florescence"},
    {"gate": 16, "name": "Magical Genius", "shadow": "Indifference", "gift": "Versatility", "siddhi": "Mastery"},
    {"gate": 17, "name": "The Eye", "shadow": "Opinion", "gift": "Far-sightedness", "siddhi": "Omniscience"},
    {"gate": 18, "name": "Healing Mind", "shadow": "Judgement", "gift": "Integrity", "siddhi": "Perfection"},
    {"gate": 19, "name": "Future Human", "shadow": "Co-Dependence", "gift": "Sensitivity", "siddhi": "Sacrifice"},
    {"gate": 20, "name": "Sacred Om", "shadow": "Superficiality", "gift": "Self-Assurance", "siddhi": "Presence"},
    {"gate": 21, "name": "Noble Way", "shadow": "Control", "gift": "Authority", "siddhi": "Valor"},
    {"gate": 22, "name": "Grace", "shadow": "Dishonor", "gift": "Graciousness", "siddhi": "Grace"},
    {"gate": 23, "name": "Alchemy", "shadow": "Complexity", "gift": "Simplicity", "siddhi": "Quintessence"},
    {"gate": 24, "name": "The Silent Way", "shadow": "Addiction", "gift": "Invention", "siddhi": "Silence"},
    {"gate": 25, "name": "Myth of Sacred Wounding", "shadow": "Constriction", "gift": "Acceptance", "siddhi": "Universal Love"},
    {"gate": 26, "name": "Heart of the Trickster", "shadow": "Pride", "gift": "Artfulness", "siddhi": "Invisibility"},
    {"gate": 27, "name": "Selfless Self", "shadow": "Selfishness", "gift": "Altruism", "siddhi": "Selflessness"},
    {"gate": 28, "name": "The Game Player", "shadow": "Purposelessness", "gift": "Totality", "siddhi": "Immortality"},
    {"gate": 29, "name": "Leap into the Void", "shadow": "Half-heartedness", "gift": "Commitment", "siddhi": "Devotion"},
    {"gate": 30, "name": "Crowned with Light", "shadow": "Desire", "gift": "Lightness", "siddhi": "Rapture"},
    {"gate": 31, "name": "Sound that Heals", "shadow": "Arrogance", "gift": "Leadership", "siddhi": "Humility"},
    {"gate": 32, "name": "Ancestral Reverence", "shadow": "Failure", "gift": "Preservation", "siddhi": "Veneration"},
    {"gate": 33, "name": "Final Revelation", "shadow": "Forgetting", "gift": "Mindfulness", "siddhi": "Revelation"},
    {"gate": 34, "name": "Strength of the Divine Beast", "shadow": "Force", "gift": "Strength", "siddhi": "Majesty"},
    {"gate": 35, "name": "Wormholes & Miracles", "shadow": "Hunger", "gift": "Adventure", "siddhi": "Boundlessness"},
    {"gate": 36, "name": "Becoming Human", "shadow": "Turbulence", "gift": "Humanity", "siddhi": "Compassion"},
    {"gate": 37, "name": "The Family Alchemist", "shadow": "Weakness", "gift": "Equality", "siddhi": "Tenderness"},
    {"gate": 38, "name": "The Warrior of Light", "shadow": "Struggle", "gift": "Perseverance", "siddhi": "Honor"},
    {"gate": 39, "name": "The Tension of Awakening", "shadow": "Provocation", "gift": "Dynamism", "siddhi": "Liberation"},
    {"gate": 40, "name": "Will of Divinity", "shadow": "Exhaustion", "gift": "Resolve", "siddhi": "Divine Will"},
    {"gate": 41, "name": "Prime Emanation of Love", "shadow": "Fantasy", "gift": "Anticipation", "siddhi": "Emanation"},
    {"gate": 42, "name": "Letting Go", "shadow": "Expectation", "gift": "Detachment", "siddhi": "Celebration"},
    {"gate": 43, "name": "Breakthrough", "shadow": "Deafness", "gift": "Insight", "siddhi": "Epiphany"},
    {"gate": 44, "name": "Karmic Relationships", "shadow": "Interference", "gift": "Teamwork", "siddhi": "Synarchy"},
    {"gate": 45, "name": "Cosmic Communion", "shadow": "Dominance", "gift": "Synergy", "siddhi": "Communion"},
    {"gate": 46, "name": "Ecstasy of Embodiment", "shadow": "Seriousness", "gift": "Delight", "siddhi": "Ecstasy"},
    {"gate": 47, "name": "Transmutation", "shadow": "Oppression", "gift": "Transmutation", "siddhi": "Transfiguration"},
    {"gate": 48, "name": "The Wondrous", "shadow": "Inadequacy", "gift": "Resourcefulness", "siddhi": "Wisdom"},
    {"gate": 49, "name": "Changing the World from Within", "shadow": "Reaction", "gift": "Revolution", "siddhi": "Rebirth"},
    {"gate": 50, "name": "Cosmic Order", "shadow": "Corruption", "gift": "Equilibrium", "siddhi": "Harmony"},
    {"gate": 51, "name": "Initiative & Awakening", "shadow": "Agitation", "gift": "Initiative", "siddhi": "Awakening"},
    {"gate": 52, "name": "The Stillpoint", "shadow": "Stress", "gift": "Restraint", "siddhi": "Stillness"},
    {"gate": 53, "name": "Evolving the Past", "shadow": "Immaturity", "gift": "Expansion", "siddhi": "Superabundance"},
    {"gate": 54, "name": "The Serpent Path", "shadow": "Greed", "gift": "Aspiration", "siddhi": "Ascension"},
    {"gate": 55, "name": "The Dragonfly's Dream", "shadow": "Victimization", "gift": "Freedom", "siddhi": "Freedom"},
    {"gate": 56, "name": "Divine Indulgence", "shadow": "Distraction", "gift": "Enrichment", "siddhi": "Intoxication"},
    {"gate": 57, "name": "Gentle Wind", "shadow": "Unease", "gift": "Intuition", "siddhi": "Clarity"},
    {"gate": 58, "name": "Joy that Heals", "shadow": "Dissatisfaction", "gift": "Vitality", "siddhi": "Bliss"},
    {"gate": 59, "name": "Devotion's Gateway", "shadow": "Dishonesty", "gift": "Intimacy", "siddhi": "Transparency"},
    {"gate": 60, "name": "Realizing Possibility", "shadow": "Limitation", "gift": "Realism", "siddhi": "Justice"},
    {"gate": 61, "name": "Holy Sanctum", "shadow": "Psychosis", "gift": "Inspiration", "siddhi": "Sanctity"},
    {"gate": 62, "name": "Language of Light", "shadow": "Intellect", "gift": "Precision", "siddhi": "Impeccability"},
    {"gate": 63, "name": "After Completion", "shadow": "Doubt", "gift": "Inquiry", "siddhi": "Truth"},
    {"gate": 64, "name": "Divine Imagination", "shadow": "Confusion", "gift": "Imagination", "siddhi": "Illumination"},
]

GATE_TO_HEXAGRAM: dict[int, dict] = {h["gate"]: h for h in HEXAGRAMS}


@dataclass(frozen=True)
class GeneKeySphere:
    gate: int
    name: str
    shadow: str
    gift: str
    siddhi: str
    line: int


@dataclass(frozen=True)
class GeneKeysProfile:
    lifes_work: GeneKeySphere
    evolution: GeneKeySphere
    radiance: GeneKeySphere
    purpose: GeneKeySphere


def _enrich(gate: int, line: int) -> GeneKeySphere:
    h = GATE_TO_HEXAGRAM[gate]
    return GeneKeySphere(
        gate=h["gate"],
        name=h["name"],
        shadow=h["shadow"],
        gift=h["gift"],
        siddhi=h["siddhi"],
        line=line,
    )


def calculate_gene_keys(hd: HumanDesignChart) -> GeneKeysProfile:
    """Return the four Activation Sequence spheres from a HumanDesignChart."""
    sun = hd.personality[0]
    earth = hd.personality[1]
    d_sun = hd.design[0]
    d_earth = hd.design[1]
    return GeneKeysProfile(
        lifes_work=_enrich(sun.gate, sun.line),
        evolution=_enrich(earth.gate, earth.line),
        radiance=_enrich(d_sun.gate, d_sun.line),
        purpose=_enrich(d_earth.gate, d_earth.line),
    )
