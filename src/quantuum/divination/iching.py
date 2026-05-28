import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Hexagram:
    number: int           # 1..64
    name_en: str          # e.g. "The Creative"
    name_pinyin: str      # e.g. "Qian"
    trigram_above: str
    trigram_below: str
    judgment: str         # 1-3 sentences
    image: str            # 1-3 sentences
    lines: tuple[str, ...]   # exactly 6 line statements, bottom->top


@dataclass(frozen=True)
class CastResult:
    lines: tuple[int, ...]
    changing_indices: tuple[int, ...]
    primary_id: int
    transformed_id: int | None


HEXAGRAMS: dict[int, Hexagram] = {
    1: Hexagram(
        number=1, name_en="The Creative", name_pinyin="Qian",
        trigram_above="heaven", trigram_below="heaven",
        judgment="The Creative works sublime success, furthering through perseverance.",
        image="The movement of heaven is full of power. Thus the superior person makes himself strong and untiring.",
        lines=(
            "Nine at the beginning: Hidden dragon. Do not act.",
            "Nine in the second place: Dragon appearing in the field. It furthers one to see the great man.",
            "Nine in the third place: All day long the superior person is creatively active. At nightfall his mind is still beset with cares. Danger. No blame.",
            "Nine in the fourth place: Wavering flight over the depths. No blame.",
            "Nine in the fifth place: Flying dragon in the heavens. It furthers one to see the great man.",
            "Nine at the top: Arrogant dragon will have cause to repent.",
        ),
    ),
    2: Hexagram(
        number=2, name_en="The Receptive", name_pinyin="Kun",
        trigram_above="earth", trigram_below="earth",
        judgment="The Receptive brings about sublime success, furthering through the perseverance of a mare.",
        image="The earth's condition is receptive devotion. Thus the superior person who has breadth of character carries the outer world.",
        lines=(
            "Six at the beginning: When there is hoarfrost underfoot, solid ice is not far off.",
            "Six in the second place: Straight, square, great. Without purpose, yet nothing remains unfurthered.",
            "Six in the third place: Hidden lines. One is able to remain persevering. Seek not works but bring to completion.",
            "Six in the fourth place: A tied-up sack. No blame, no praise.",
            "Six in the fifth place: A yellow lower garment brings supreme good fortune.",
            "Six at the top: Dragons fight in the meadow. Their blood is black and yellow.",
        ),
    ),
    3: Hexagram(
        number=3, name_en="Difficulty at the Beginning", name_pinyin="Zhun",
        trigram_above="water", trigram_below="thunder",
        judgment="Difficulty at the Beginning works supreme success, furthering through perseverance. Nothing should be undertaken. It furthers one to appoint helpers.",
        image="Clouds and thunder: the image of Difficulty at the Beginning. Thus the superior person brings order out of confusion.",
        lines=(
            "Nine at the beginning: Hesitation and hindrance. It furthers one to remain persevering. It furthers one to appoint helpers.",
            "Six in the second place: Difficulties pile up. Horse and wagon part. She is not a robber; she wants to woo. The maiden perseveres and does not pledge herself.",
            "Six in the third place: Whoever hunts deer without the forester only loses his way in the forest. The superior person understands and gives up the chase.",
            "Six in the fourth place: Horse and wagon part. Strive for union. To go brings good fortune. Everything acts to further.",
            "Nine in the fifth place: Difficulties in blessing. A little perseverance brings good fortune. Great perseverance brings misfortune.",
            "Six at the top: Horse and wagon part. Bloody tears flow.",
        ),
    ),
    4: Hexagram(
        number=4, name_en="Youthful Folly", name_pinyin="Meng",
        trigram_above="mountain", trigram_below="water",
        judgment="Youthful Folly has success. It is not I who seek the young fool; the young fool seeks me. At the first oracle I inform him. If he asks two or three times, it is importunity.",
        image="A spring wells up at the foot of the mountain: the image of Youth. Thus the superior person fosters his character by thoroughness in all he does.",
        lines=(
            "Six at the beginning: To make a fool develop, it furthers one to apply discipline. The fetters should be removed. To go on in this way brings humiliation.",
            "Nine in the second place: To bear with fools in kindliness brings good fortune. To know how to take women brings good fortune. The son is capable of taking charge of the household.",
            "Six in the third place: Take not a maiden who, when she sees a man of bronze, loses possession of herself. Nothing furthers.",
            "Six in the fourth place: Entangled folly brings humiliation.",
            "Six in the fifth place: Childlike folly brings good fortune.",
            "Nine at the top: In punishing folly, it does not further one to commit transgressions. The only thing that furthers is to prevent transgressions.",
        ),
    ),
    5: Hexagram(
        number=5, name_en="Waiting (Nourishment)", name_pinyin="Xu",
        trigram_above="water", trigram_below="heaven",
        judgment="Waiting: if you are sincere, you have light and success. Perseverance brings good fortune. It furthers one to cross the great water.",
        image="Clouds rise up to heaven: the image of Waiting. Thus the superior person eats and drinks, is joyous and of good cheer.",
        lines=(
            "Nine at the beginning: Waiting in the meadow. It furthers one to abide in what endures. No blame.",
            "Nine in the second place: Waiting on the sand. There is some gossip. The outcome is good.",
            "Nine in the third place: Waiting in the mud brings about the arrival of the enemy.",
            "Six in the fourth place: Waiting in blood. Get out of the pit.",
            "Nine in the fifth place: Waiting at meat and drink. Perseverance brings good fortune.",
            "Six at the top: One falls into the pit. Three uninvited guests arrive. Honor them, and in the end there will be good fortune.",
        ),
    ),
    6: Hexagram(
        number=6, name_en="Conflict", name_pinyin="Song",
        trigram_above="heaven", trigram_below="water",
        judgment="Conflict: you are sincere and are being obstructed. A cautious halt halfway brings good fortune. Going through to the end brings misfortune.",
        image="Heaven and water go their opposite ways: the image of Conflict. Thus in all his transactions the superior person carefully considers the beginning.",
        lines=(
            "Six at the beginning: If one does not perpetuate the affair, there is a little gossip. In the end, good fortune comes.",
            "Nine in the second place: One cannot engage in conflict; one returns home, gives way. The people of his town, three hundred households, remain free of guilt.",
            "Six in the third place: To nourish oneself on ancient virtue induces perseverance. Danger, but good fortune in the end.",
            "Nine in the fourth place: One cannot engage in conflict. One turns back and submits to fate, changes one's attitude, and finds peace in perseverance. Good fortune.",
            "Nine in the fifth place: To contend before him brings supreme good fortune.",
            "Nine at the top: Even if by chance a leather belt is bestowed on one, by the end of a morning it will have been snatched away three times.",
        ),
    ),
    7: Hexagram(
        number=7, name_en="The Army", name_pinyin="Shi",
        trigram_above="earth", trigram_below="water",
        judgment="The Army. The army needs perseverance and a strong man. Good fortune without blame.",
        image="In the middle of the earth is water: the image of the Army. Thus the superior person increases his masses by generosity toward the people.",
        lines=(
            "Six at the beginning: An army must set forth in proper order. If the order is not good, misfortune threatens.",
            "Nine in the second place: In the midst of the army. Good fortune. No blame. The king bestows a triple decoration.",
            "Six in the third place: Perchance the army carries corpses in the wagon. Misfortune.",
            "Six in the fourth place: The army retreats. No blame.",
            "Six in the fifth place: There is game in the field. It furthers one to catch it. Without blame. Let the eldest lead the army.",
            "Six at the top: The great prince issues commands, founds states, vests families with fiefs. Inferior people should not be employed.",
        ),
    ),
    8: Hexagram(
        number=8, name_en="Holding Together (Union)", name_pinyin="Bi",
        trigram_above="water", trigram_below="earth",
        judgment="Holding Together brings good fortune. Inquire of the oracle once again whether you possess sublimity, constancy, and perseverance; then there is no blame.",
        image="On the earth is water: the image of Holding Together. Thus the kings of antiquity bestowed the different states as fiefs and cultivated friendly relations with the feudal lords.",
        lines=(
            "Six at the beginning: Hold to him in truth and loyalty; this is without blame. Truth, like a full earthen bowl: thus in the end good fortune comes from without.",
            "Six in the second place: Hold to him inwardly. Perseverance brings good fortune.",
            "Six in the third place: You hold together with the wrong people.",
            "Six in the fourth place: Hold to him outwardly also. Perseverance brings good fortune.",
            "Nine in the fifth place: Manifestation of holding together. In the hunt the king uses beaters on three sides only and foregoes game that runs off in front. The citizens need no warning. Good fortune.",
            "Six at the top: He finds no head for holding together. Misfortune.",
        ),
    ),
    9: Hexagram(
        number=9, name_en="The Taming Power of the Small", name_pinyin="Xiao Xu",
        trigram_above="wind", trigram_below="heaven",
        judgment="The Taming Power of the Small has success. Dense clouds, no rain from our western region.",
        image="The wind drives across heaven: the image of the Taming Power of the Small. Thus the superior person refines the outward aspect of his nature.",
        lines=(
            "Nine at the beginning: Return to the way. How could there be blame in this? Good fortune.",
            "Nine in the second place: He allows himself to be drawn into returning. Good fortune.",
            "Nine in the third place: The spokes burst out of the wagon wheels. Man and wife roll their eyes.",
            "Six in the fourth place: If you are sincere, blood vanishes and fear gives way. No blame.",
            "Nine in the fifth place: If you are sincere and loyally attached, you enrich your neighbor.",
            "Nine at the top: The rain comes, there is rest. This is due to the lasting effect of character. Perseverance brings the woman into danger. The moon is nearly full.",
        ),
    ),
    10: Hexagram(
        number=10, name_en="Treading (Conduct)", name_pinyin="Lu",
        trigram_above="heaven", trigram_below="lake",
        judgment="Treading upon the tail of the tiger. It does not bite the man. Success.",
        image="Heaven above, the lake below: the image of Treading. Thus the superior person discriminates between high and low and thereby fortifies the thinking of the people.",
        lines=(
            "Nine at the beginning: Simple conduct. Progress without blame.",
            "Nine in the second place: Treading a smooth, level course. The perseverance of a dark man brings good fortune.",
            "Six in the third place: A one-eyed man is able to see, a lame man is able to tread. He treads on the tail of the tiger. The tiger bites the man. Misfortune.",
            "Nine in the fourth place: He treads on the tail of the tiger. Caution and circumspection lead ultimately to good fortune.",
            "Nine in the fifth place: Resolute conduct. Perseverance with awareness of danger.",
            "Nine at the top: Look to your conduct and weigh the favorable signs. When everything is fulfilled, supreme good fortune comes.",
        ),
    ),
    11: Hexagram(
        number=11, name_en="Peace", name_pinyin="Tai",
        trigram_above="earth", trigram_below="heaven",
        judgment="Peace. The small departs, the great approaches. Good fortune. Success.",
        image="Heaven and earth unite: the image of Peace. Thus the ruler divides and completes the course of heaven and earth; he furthers and regulates the gifts of heaven and earth.",
        lines=(
            "Nine at the beginning: When ribbon grass is pulled up, the sod comes with it. Each according to his kind. Undertakings bring good fortune.",
            "Nine in the second place: Bearing with the uncultured in gentleness, fording the river with resolution, not neglecting what is distant, not regarding one's companions: thus one may manage to walk in the middle.",
            "Nine in the third place: No plain not followed by a slope. No going not followed by a return. He who remains persevering in danger is without blame. Do not complain about this truth; enjoy the good fortune you still possess.",
            "Six in the fourth place: He flutters down, not boasting of his wealth, together with his neighbor, guileless and sincere.",
            "Six in the fifth place: The sovereign I gives his daughter in marriage. This brings blessing and supreme good fortune.",
            "Six at the top: The wall falls back into the moat. Use no army now. Make your commands known within your own town. Perseverance brings humiliation.",
        ),
    ),
    12: Hexagram(
        number=12, name_en="Standstill (Stagnation)", name_pinyin="Pi",
        trigram_above="heaven", trigram_below="earth",
        judgment="Standstill. Evil people do not further the perseverance of the superior person. The great departs; the small approaches.",
        image="Heaven and earth do not unite: the image of Standstill. Thus the superior person falls back upon his inner worth in order to escape the difficulties.",
        lines=(
            "Six at the beginning: When ribbon grass is pulled up, the sod comes with it. Each according to his kind. Perseverance brings good fortune and success.",
            "Six in the second place: They bear and endure; this means good fortune for inferior people. The standstill serves to help the great man to attain success.",
            "Six in the third place: They bear shame.",
            "Nine in the fourth place: He who acts at the command of the highest remains without blame. Those of like mind partake of the blessing.",
            "Nine in the fifth place: Standstill is giving way. Good fortune for the great man. What if it should fail, what if it should fail? In this way he ties it to a cluster of mulberry shoots.",
            "Nine at the top: The standstill comes to an end. First standstill, then good fortune.",
        ),
    ),
    13: Hexagram(
        number=13, name_en="Fellowship with Men", name_pinyin="Tong Ren",
        trigram_above="heaven", trigram_below="fire",
        judgment="Fellowship with men in the open. Success. It furthers one to cross the great water. The perseverance of the superior person furthers.",
        image="Heaven together with fire: the image of Fellowship with Men. Thus the superior person organizes the clans and makes distinctions between things.",
        lines=(
            "Nine at the beginning: Fellowship with men at the gate. No blame.",
            "Six in the second place: Fellowship with men in the clan. Humiliation.",
            "Nine in the third place: He hides weapons in the thicket; he climbs the high hill in front of it. For three years he does not rise up.",
            "Nine in the fourth place: He climbs up on his wall; he cannot attack. Good fortune.",
            "Nine in the fifth place: Men bound in fellowship first weep and lament, but afterward they laugh. After great struggles they succeed in meeting.",
            "Nine at the top: Fellowship with men in the meadow. No remorse.",
        ),
    ),
    14: Hexagram(
        number=14, name_en="Possession in Great Measure", name_pinyin="Da You",
        trigram_above="fire", trigram_below="heaven",
        judgment="Possession in Great Measure: supreme success.",
        image="Fire in heaven above: the image of Possession in Great Measure. Thus the superior person curbs evil and furthers good, and thereby obeys the benevolent will of heaven.",
        lines=(
            "Nine at the beginning: No relationship with what is harmful; there is no blame in this. If one remains conscious of difficulty, one remains without blame.",
            "Nine in the second place: A big wagon for loading. One may undertake something. No blame.",
            "Nine in the third place: A prince offers it to the Son of Heaven. A petty man cannot do this.",
            "Nine in the fourth place: He makes a difference between himself and his neighbor. No blame.",
            "Six in the fifth place: He whose truth is accessible, yet dignified, has good fortune.",
            "Nine at the top: From heaven comes his good fortune and blessing. Nothing that does not further.",
        ),
    ),
    15: Hexagram(
        number=15, name_en="Modesty", name_pinyin="Qian",
        trigram_above="earth", trigram_below="mountain",
        judgment="Modesty creates success. The superior person carries things through.",
        image="Within the earth, a mountain: the image of Modesty. Thus the superior person reduces that which is too much and augments that which is too little.",
        lines=(
            "Six at the beginning: A superior person modest about his modesty may cross the great water. Good fortune.",
            "Six in the second place: Modesty that comes to expression. Perseverance brings good fortune.",
            "Nine in the third place: A superior person of merit, modest and to the end. Good fortune.",
            "Six in the fourth place: Nothing that does not further modesty in movement.",
            "Six in the fifth place: No boasting of wealth before one's neighbor. It is favorable to attack with force. Nothing that does not further.",
            "Six at the top: Modesty that comes to expression. It is favorable to set armies marching to chastise one's own city and one's country.",
        ),
    ),
    16: Hexagram(
        number=16, name_en="Enthusiasm", name_pinyin="Yu",
        trigram_above="thunder", trigram_below="earth",
        judgment="Enthusiasm. It furthers one to install helpers and to set armies marching.",
        image="Thunder comes resounding out of the earth: the image of Enthusiasm. Thus the ancient kings made music in order to honor merit, and offered it with splendor to the Supreme Deity.",
        lines=(
            "Six at the beginning: Enthusiasm that expresses itself brings misfortune.",
            "Six in the second place: Firm as a rock. Not a whole day. Perseverance brings good fortune.",
            "Six in the third place: Enthusiasm that looks upward creates remorse. Hesitation brings remorse.",
            "Nine in the fourth place: The source of enthusiasm. He achieves great things. Doubt not. You gather friends around you as a hair clasp gathers the hair.",
            "Six in the fifth place: Persistently ill and still does not die.",
            "Six at the top: Deluded enthusiasm. But if after completion one changes, there is no blame.",
        ),
    ),
    17: Hexagram(
        number=17, name_en="Following", name_pinyin="Sui",
        trigram_above="lake", trigram_below="thunder",
        judgment="Following has supreme success. Perseverance furthers. No blame.",
        image="Thunder in the middle of the lake: the image of Following. Thus the superior person at nightfall goes indoors for rest and recuperation.",
        lines=(
            "Nine at the beginning: The standard is changing. Perseverance brings good fortune. To go out of the door in company produces deeds.",
            "Six in the second place: If one clings to the little boy, one loses the strong man.",
            "Six in the third place: If one clings to the strong man, one loses the little boy. Through following one finds what one seeks. It furthers one to remain persevering.",
            "Nine in the fourth place: Following creates success. Perseverance brings misfortune. To go one's way with sincerity brings clarity. How could there be blame in this?",
            "Nine in the fifth place: Sincere in the good. Good fortune.",
            "Six at the top: He meets with firm allegiance and is still further bound. The king introduces him to the Western Mountain.",
        ),
    ),
    18: Hexagram(
        number=18, name_en="Work on What Has Been Spoiled (Decay)", name_pinyin="Gu",
        trigram_above="mountain", trigram_below="wind",
        judgment="Work on what has been spoiled has supreme success. It furthers one to cross the great water. Before the starting point, three days. After the starting point, three days.",
        image="The wind blows low on the mountain: the image of Decay. Thus the superior person stirs up the people and strengthens their spirit.",
        lines=(
            "Six at the beginning: Setting right what has been spoiled by the father. If there is a son, no blame rests upon the departed father. Danger, but in the end good fortune.",
            "Nine in the second place: Setting right what has been spoiled by the mother. One must not be too persevering.",
            "Nine in the third place: Setting right what has been spoiled by the father. There will be a little remorse but no great blame.",
            "Six in the fourth place: Tolerating what has been spoiled by the father. In continuing one sees humiliation.",
            "Six in the fifth place: Setting right what has been spoiled by the father. One meets with praise.",
            "Nine at the top: He does not serve kings and princes, sets himself higher goals.",
        ),
    ),
    19: Hexagram(
        number=19, name_en="Approach", name_pinyin="Lin",
        trigram_above="earth", trigram_below="lake",
        judgment="Approach has supreme success. Perseverance furthers. When the eighth month comes, there will be misfortune.",
        image="The earth above the lake: the image of Approach. Thus the superior person is inexhaustible in his will to teach, and without limits in his tolerance and protection of the people.",
        lines=(
            "Nine at the beginning: Joint approach. Perseverance brings good fortune.",
            "Nine in the second place: Joint approach. Good fortune. Everything furthers.",
            "Six in the third place: Comfortable approach. Nothing that would further. If one is induced to grieve over it, one becomes free of blame.",
            "Six in the fourth place: Complete approach. No blame.",
            "Six in the fifth place: Wise approach. This is right for a great prince. Good fortune.",
            "Six at the top: Greathearted approach. Good fortune. No blame.",
        ),
    ),
    20: Hexagram(
        number=20, name_en="Contemplation (View)", name_pinyin="Guan",
        trigram_above="wind", trigram_below="earth",
        judgment="Contemplation. The ablution has been made, but not yet the offering. Full of trust they look up to him.",
        image="The wind blows over the earth: the image of Contemplation. Thus the kings of old visited the regions of the world, contemplated the people, and gave them instruction.",
        lines=(
            "Six at the beginning: Boy-like contemplation. For an inferior person, no blame. For a superior person, humiliation.",
            "Six in the second place: Contemplation through the crack of the door. Furthering for the perseverance of a woman.",
            "Six in the third place: Contemplation of my life decides the choice between advance and retreat.",
            "Six in the fourth place: Contemplation of the light of the kingdom. It furthers one to exert influence as the guest of a king.",
            "Nine in the fifth place: Contemplation of my life. The superior person is without blame.",
            "Nine at the top: Contemplation of his life. The superior person is without blame.",
        ),
    ),
    21: Hexagram(
        number=21, name_en="Biting Through", name_pinyin="Shi He",
        trigram_above="fire", trigram_below="thunder",
        judgment="Biting Through has success. It is favorable to let justice be administered.",
        image="Thunder and lightning: the image of Biting Through. Thus the kings of former times made firm the laws through clearly defined penalties.",
        lines=(
            "Nine at the beginning: His feet are fastened in the stocks so that his toes disappear. No blame.",
            "Six in the second place: Bites through tender meat, so that his nose disappears. No blame.",
            "Six in the third place: Bites on old dried meat and strikes on something poisonous. Slight humiliation. No blame.",
            "Nine in the fourth place: Bites on dried gristly meat. Receives metal arrows. It furthers one to be mindful of difficulties and to be persevering. Good fortune.",
            "Six in the fifth place: Bites on dried lean meat. Receives yellow gold. Perseveringly aware of danger. No blame.",
            "Nine at the top: His neck is fastened in the wooden cangue so that his ears disappear. Misfortune.",
        ),
    ),
    22: Hexagram(
        number=22, name_en="Grace", name_pinyin="Bi",
        trigram_above="mountain", trigram_below="fire",
        judgment="Grace has success. In small matters it is favorable to undertake something.",
        image="Fire at the foot of the mountain: the image of Grace. Thus does the superior person proceed when clearing up current affairs. But he dare not decide controversial issues in this way.",
        lines=(
            "Nine at the beginning: He lends grace to his toes, leaves the carriage, and walks.",
            "Six in the second place: Lends grace to the beard on his chin.",
            "Nine in the third place: Graceful and moist. Constant perseverance brings good fortune.",
            "Six in the fourth place: Grace or simplicity? A white horse comes as if on wings. He is not a robber; he will woo at the right time.",
            "Six in the fifth place: Grace in hills and gardens. The roll of silk is meager and small. Humiliation, but in the end good fortune.",
            "Nine at the top: Simple grace. No blame.",
        ),
    ),
    23: Hexagram(
        number=23, name_en="Splitting Apart", name_pinyin="Bo",
        trigram_above="mountain", trigram_below="earth",
        judgment="Splitting Apart. It does not further one to go anywhere.",
        image="The mountain rests on the earth: the image of Splitting Apart. Thus those above can ensure their position only by giving generously to those below.",
        lines=(
            "Six at the beginning: The leg of the bed is split. Those who persevere are destroyed. Misfortune.",
            "Six in the second place: The bed is split at the edge. Those who persevere are destroyed. Misfortune.",
            "Six in the third place: He splits with them. No blame.",
            "Six in the fourth place: The bed is split up to the skin. Misfortune.",
            "Six in the fifth place: A shoal of fishes. Favor comes through the court ladies. Everything acts to further.",
            "Nine at the top: There is a large fruit still uneaten. The superior person receives a carriage. The house of the inferior person is split apart.",
        ),
    ),
    24: Hexagram(
        number=24, name_en="Return (The Turning Point)", name_pinyin="Fu",
        trigram_above="earth", trigram_below="thunder",
        judgment="Return. Success. Going out and coming in without error. Friends come without blame. To and fro goes the way. On the seventh day comes return. It furthers one to have somewhere to go.",
        image="Thunder within the earth: the image of the Turning Point. Thus the kings of antiquity closed the passes at the time of solstice.",
        lines=(
            "Nine at the beginning: Return from a short distance. No need for remorse. Great good fortune.",
            "Six in the second place: Quiet return. Good fortune.",
            "Six in the third place: Repeated return. Danger. No blame.",
            "Six in the fourth place: Walking in the midst of others, one returns alone.",
            "Six in the fifth place: Noblehearted return. No remorse.",
            "Six at the top: Missing the return. Misfortune. There is ill-fortune within and armies march without. In the end there is great defeat.",
        ),
    ),
    25: Hexagram(
        number=25, name_en="Innocence (The Unexpected)", name_pinyin="Wu Wang",
        trigram_above="heaven", trigram_below="thunder",
        judgment="Innocence. Supreme success. Perseverance furthers. If someone is not as he should be, he has misfortune.",
        image="Under heaven thunder rolls: all things attain the natural state of innocence. Thus the kings of old, rich in virtue and in harmony with the time, fostered and nourished all beings.",
        lines=(
            "Nine at the beginning: Innocent behavior brings good fortune.",
            "Six in the second place: If one does not count on the harvest while plowing, nor on the use of the ground while clearing it, it furthers one to undertake something.",
            "Six in the third place: Undeserved misfortune. The cow that was tethered by someone is the wandering man's gain, the citizen's loss.",
            "Nine in the fourth place: He who can be persevering remains without blame.",
            "Nine in the fifth place: Use no medicine in an illness incurred through no fault of your own. It will pass of itself.",
            "Nine at the top: Innocent action brings misfortune. Nothing furthers.",
        ),
    ),
    26: Hexagram(
        number=26, name_en="The Taming Power of the Great", name_pinyin="Da Xu",
        trigram_above="mountain", trigram_below="heaven",
        judgment="The Taming Power of the Great. Perseverance furthers. Not eating at home brings good fortune. It furthers one to cross the great water.",
        image="Heaven within the mountain: the image of the Taming Power of the Great. Thus the superior person acquaints himself with many sayings of antiquity and many deeds of the past.",
        lines=(
            "Nine at the beginning: Danger is at hand. It furthers one to desist.",
            "Nine in the second place: The axletrees are taken from the wagon.",
            "Nine in the third place: A good horse that follows others. Awareness of danger, with perseverance, furthers. Practice chariot driving and armed defense daily. It furthers one to have somewhere to go.",
            "Six in the fourth place: The headboard of a young bull. Great good fortune.",
            "Six in the fifth place: The tusk of a gelded boar. Good fortune.",
            "Nine at the top: One attains the way of heaven. Success.",
        ),
    ),
    27: Hexagram(
        number=27, name_en="The Corners of the Mouth (Providing Nourishment)", name_pinyin="Yi",
        trigram_above="mountain", trigram_below="thunder",
        judgment="The Corners of the Mouth. Perseverance brings good fortune. Pay heed to the providing of nourishment and to what a man seeks to fill his own mouth with.",
        image="At the foot of the mountain, thunder: the image of Providing Nourishment. Thus the superior person is careful of his words and temperate in eating and drinking.",
        lines=(
            "Nine at the beginning: You let your magic tortoise go, and look at me with the corners of your mouth drooping. Misfortune.",
            "Six in the second place: Turning to the summit for nourishment, deviating from the path to seek nourishment from the hill. Continuing to do this brings misfortune.",
            "Six in the third place: Turning away from nourishment. Perseverance brings misfortune. Do not act thus for ten years. Nothing serves to further.",
            "Six in the fourth place: Turning to the summit for provision of nourishment brings good fortune. Spying about with sharp eyes like a tiger with insatiable craving. No blame.",
            "Six in the fifth place: Turning away from the path. To remain persevering brings good fortune. One should not cross the great water.",
            "Nine at the top: The source of nourishment. Awareness of danger brings good fortune. It furthers one to cross the great water.",
        ),
    ),
    28: Hexagram(
        number=28, name_en="Preponderance of the Great", name_pinyin="Da Guo",
        trigram_above="lake", trigram_below="wind",
        judgment="Preponderance of the Great. The ridgepole sags to the breaking point. It furthers one to have somewhere to go. Success.",
        image="The lake rises above the trees: the image of Preponderance of the Great. Thus the superior person, when he stands alone, is unconcerned, and if he has to renounce the world, he is undaunted.",
        lines=(
            "Six at the beginning: To spread white rushes underneath. No blame.",
            "Nine in the second place: A dry poplar sprouts at the root. An older man takes a young wife. Everything furthers.",
            "Nine in the third place: The ridgepole sags to the breaking point. Misfortune.",
            "Nine in the fourth place: The ridgepole is braced. Good fortune. But if there are ulterior motives, it is humiliating.",
            "Nine in the fifth place: A withered poplar puts forth flowers. An older woman takes a husband. No blame. No praise.",
            "Six at the top: One must go through the water. It goes over one's head. Misfortune. No blame.",
        ),
    ),
    29: Hexagram(
        number=29, name_en="The Abysmal (Water)", name_pinyin="Kan",
        trigram_above="water", trigram_below="water",
        judgment="The Abysmal repeated. If you are sincere, you have success in your heart, and whatever you do succeeds.",
        image="Water flows on uninterruptedly and reaches its goal: the image of the Abysmal repeated. Thus the superior person walks in lasting virtue and carries on the business of teaching.",
        lines=(
            "Six at the beginning: The Abysmal repeated. In the abyss one falls into a pit. Misfortune.",
            "Nine in the second place: The abyss is dangerous. One should strive to attain small things only.",
            "Six in the third place: Forward and backward, abyss on abyss. In danger like this, pause at first and wait, otherwise you will fall into the pit in the abyss. Do not act in this way.",
            "Six in the fourth place: A jug of wine, a bowl of rice with it; earthen vessels simply handed in through the window. There is certainly no blame in this.",
            "Nine in the fifth place: The abyss is not filled to overflowing, it is filled only to the rim. No blame.",
            "Six at the top: Bound with cords and ropes, shut in between thorn-hedged prison walls: for three years one does not find the way. Misfortune.",
        ),
    ),
    30: Hexagram(
        number=30, name_en="The Clinging, Fire", name_pinyin="Li",
        trigram_above="fire", trigram_below="fire",
        judgment="The Clinging. Perseverance furthers. It brings success. Care of the cow brings good fortune.",
        image="That which is bright rises twice: the image of Fire. Thus the great person, by perpetuating this brightness, illumines the four quarters of the world.",
        lines=(
            "Nine at the beginning: The footprints run crisscross. If one is seriously intent, no blame.",
            "Six in the second place: Yellow light. Supreme good fortune.",
            "Nine in the third place: In the light of the setting sun, men either beat the pot and sing or loudly bewail the approach of old age. Misfortune.",
            "Nine in the fourth place: Its coming is sudden; it flames up, dies down, is thrown away.",
            "Six in the fifth place: Tears in floods, sighing and lamenting. Good fortune.",
            "Nine at the top: The king uses him to march forth and chastise. Then it is best to kill the leaders and take captive the followers. No blame.",
        ),
    ),
    31: Hexagram(
        number=31, name_en="Influence (Wooing)", name_pinyin="Xian",
        trigram_above="lake", trigram_below="mountain",
        judgment="Influence. Success. Perseverance furthers. To take a maiden to wife brings good fortune.",
        image="A lake on the mountain: the image of Influence. Thus the superior person encourages people to approach him by his readiness to receive them.",
        lines=(
            "Six at the beginning: The influence shows itself in the big toe.",
            "Six in the second place: The influence shows itself in the calves of the legs. Misfortune. Tarrying brings good fortune.",
            "Nine in the third place: The influence shows itself in the thighs. Holds to that which follows it. To continue is humiliating.",
            "Nine in the fourth place: Perseverance brings good fortune. Remorse disappears. If a man is agitated in mind, and his thoughts go hither and thither, only those friends on whom he fixes his conscious thoughts will follow.",
            "Nine in the fifth place: The influence shows itself in the back of the neck. No remorse.",
            "Six at the top: The influence shows itself in the jaws, cheeks, and tongue.",
        ),
    ),
    32: Hexagram(
        number=32, name_en="Duration", name_pinyin="Heng",
        trigram_above="thunder", trigram_below="wind",
        judgment="Duration. Success. No blame. Perseverance furthers. It furthers one to have somewhere to go.",
        image="Thunder and wind: the image of Duration. Thus the superior person stands firm and does not change his direction.",
        lines=(
            "Six at the beginning: Seeking duration too hastily brings misfortune persistently. Nothing that would further.",
            "Nine in the second place: Remorse disappears.",
            "Nine in the third place: He who does not give duration to his character meets with disgrace. Persistent humiliation.",
            "Nine in the fourth place: No game in the field.",
            "Six in the fifth place: Giving duration to one's character through perseverance. This is good fortune for a woman, misfortune for a man.",
            "Six at the top: Restlessness as an enduring condition brings misfortune.",
        ),
    ),
    33: Hexagram(
        number=33, name_en="Retreat", name_pinyin="Dun",
        trigram_above="heaven", trigram_below="mountain",
        judgment="Retreat. Success. In what is small, perseverance furthers.",
        image="Mountain under heaven: the image of Retreat. Thus the superior person keeps the inferior person at a distance, not angrily but with reserve.",
        lines=(
            "Six at the beginning: At the tail in retreat. This is dangerous. One must not wish to undertake anything.",
            "Six in the second place: He holds him fast with yellow oxhide. No one can tear him loose.",
            "Nine in the third place: A halted retreat is nerve-wracking and dangerous. To retain people as men- and maidservants brings good fortune.",
            "Nine in the fourth place: Voluntary retreat brings good fortune to the superior person and downfall to the inferior person.",
            "Nine in the fifth place: Friendly retreat. Perseverance brings good fortune.",
            "Nine at the top: Cheerful retreat. Everything serves to further.",
        ),
    ),
    34: Hexagram(
        number=34, name_en="The Power of the Great", name_pinyin="Da Zhuang",
        trigram_above="thunder", trigram_below="heaven",
        judgment="The Power of the Great. Perseverance furthers.",
        image="Thunder in heaven above: the image of the Power of the Great. Thus the superior person does not tread upon paths that do not accord with established order.",
        lines=(
            "Nine at the beginning: Power in the toes. Continuing brings misfortune. This is certainly true.",
            "Nine in the second place: Perseverance brings good fortune.",
            "Nine in the third place: The inferior person works through power. The superior person does not act thus. To continue is dangerous. A he-goat butts against a hedge and gets his horns entangled.",
            "Nine in the fourth place: Perseverance brings good fortune. Remorse disappears. The hedge opens; there is no entanglement. Power depends upon the axle of a big cart.",
            "Six in the fifth place: Loses the goat with ease. No remorse.",
            "Six at the top: A he-goat butts against a hedge. He cannot go backward, he cannot go forward. Nothing serves to further. If one notes the difficulty, this brings good fortune.",
        ),
    ),
    35: Hexagram(
        number=35, name_en="Progress", name_pinyin="Jin",
        trigram_above="fire", trigram_below="earth",
        judgment="Progress. The powerful prince is honored with horses in large numbers. In a single day he is granted audience three times.",
        image="The sun rises over the earth: the image of Progress. Thus the superior person himself brightens his bright virtue.",
        lines=(
            "Six at the beginning: Progressing but turned back. Perseverance brings good fortune. If one meets with no confidence, one should remain calm. No mistake.",
            "Six in the second place: Progressing but in sorrow. Perseverance brings good fortune. Then one obtains great happiness from one's ancestress.",
            "Six in the third place: All are in accord. Remorse disappears.",
            "Nine in the fourth place: Progress like a hamster. Perseverance brings danger.",
            "Six in the fifth place: Remorse disappears. Take not gain and loss to heart. Undertakings bring good fortune. Everything serves to further.",
            "Nine at the top: Making progress with the horns is permissible only for the purpose of punishing one's own city. To be conscious of danger brings good fortune. No blame. Perseverance brings humiliation.",
        ),
    ),
    36: Hexagram(
        number=36, name_en="Darkening of the Light", name_pinyin="Ming Yi",
        trigram_above="earth", trigram_below="fire",
        judgment="Darkening of the Light. In adversity it furthers one to be persevering.",
        image="The light has sunk into the earth: the image of Darkening of the Light. Thus does the superior person live with the great mass: he veils his light, yet still shines.",
        lines=(
            "Nine at the beginning: Darkening of the light during flight. He lowers his wings. The superior person does not eat for three days on his wanderings. But he has somewhere to go. The host has occasion to gossip about him.",
            "Six in the second place: The darkening of the light injures him in the left thigh. He gives aid with the strength of a horse. Good fortune.",
            "Nine in the third place: Darkening of the light during the hunt in the south. Their great leader is captured. One must not expect perseverance too soon.",
            "Six in the fourth place: He penetrates the left side of the belly. One gets at the very heart of the darkening of the light. He leaves the gate and the courtyard.",
            "Six in the fifth place: Darkening of the light as with Prince Chi. Perseverance furthers.",
            "Six at the top: Not light but darkness. First he climbed up to heaven, then he plunged into the depths of the earth.",
        ),
    ),
    37: Hexagram(
        number=37, name_en="The Family (The Clan)", name_pinyin="Jia Ren",
        trigram_above="wind", trigram_below="fire",
        judgment="The Family. The perseverance of the woman furthers.",
        image="Wind comes forth from fire: the image of the Family. Thus the superior person has substance in his words and duration in his way of life.",
        lines=(
            "Nine at the beginning: Firm seclusion within the family. Remorse disappears.",
            "Six in the second place: She should not follow her whims. She must attend within to the food. Perseverance brings good fortune.",
            "Nine in the third place: When tempers flare up in the family, too great severity brings remorse. Good fortune nonetheless. When woman and child dally and laugh it leads in the end to humiliation.",
            "Six in the fourth place: She is the treasure of the house. Great good fortune.",
            "Nine in the fifth place: As a king he approaches his family. Fear not. Good fortune.",
            "Nine at the top: His work commands respect. In the end good fortune comes.",
        ),
    ),
    38: Hexagram(
        number=38, name_en="Opposition", name_pinyin="Kui",
        trigram_above="fire", trigram_below="lake",
        judgment="Opposition. In small matters, good fortune.",
        image="Above, fire; below, the lake: the image of Opposition. Thus amid all fellowship the superior person retains his individuality.",
        lines=(
            "Nine at the beginning: Remorse disappears. If you lose your horse, do not run after it; it will come back of its own accord. When you see evil people, guard yourself against mistakes.",
            "Nine in the second place: One meets his lord in a narrow street. No blame.",
            "Six in the third place: One sees the wagon dragged back, the oxen halted, a man's hair and nose cut off. Not a good beginning, but a good end.",
            "Nine in the fourth place: Isolated through opposition, one meets a like-minded man with whom one can associate in good faith. Despite the danger, no blame.",
            "Six in the fifth place: Remorse disappears. The companion bites his way through the wrappings. If one goes to him, how could it be a mistake?",
            "Nine at the top: Isolated through opposition, one sees one's companion as a pig covered with dirt, as a wagon full of devils. First one draws a bow against him, then one lays the bow aside. He is not a robber; he will woo at the right time. As one goes, rain falls; then good fortune comes.",
        ),
    ),
    39: Hexagram(
        number=39, name_en="Obstruction", name_pinyin="Jian",
        trigram_above="water", trigram_below="mountain",
        judgment="Obstruction. The southwest furthers. The northeast does not further. It furthers one to see the great man. Perseverance brings good fortune.",
        image="Water on the mountain: the image of Obstruction. Thus the superior person turns his attention to himself and molds his character.",
        lines=(
            "Six at the beginning: Going leads to obstructions, coming meets praise.",
            "Six in the second place: The king's servant is beset by obstruction upon obstruction, but it is not his own fault.",
            "Nine in the third place: Going leads to obstructions; hence he comes back.",
            "Six in the fourth place: Going leads to obstructions, coming leads to union.",
            "Nine in the fifth place: In the midst of the greatest obstructions, friends come.",
            "Six at the top: Going leads to obstructions, coming leads to great good fortune. It furthers one to see the great man.",
        ),
    ),
    40: Hexagram(
        number=40, name_en="Deliverance", name_pinyin="Jie",
        trigram_above="thunder", trigram_below="water",
        judgment="Deliverance. The southwest furthers. If there is no longer anything where one has to go, return brings good fortune. If there is still something where one has to go, hastening brings good fortune.",
        image="Thunder and rain set in: the image of Deliverance. Thus the superior person pardons mistakes and forgives misdeeds.",
        lines=(
            "Six at the beginning: Without blame.",
            "Nine in the second place: One kills three foxes in the field and receives a yellow arrow. Perseverance brings good fortune.",
            "Six in the third place: If a man carries a burden on his back and nonetheless rides in a carriage, he thereby encourages robbers to draw near. Perseverance leads to humiliation.",
            "Nine in the fourth place: Deliver yourself from your great toe. Then the companion comes, and him you can trust.",
            "Six in the fifth place: If only the superior person can deliver himself, it brings good fortune. Thus he proves to inferior people that he is in earnest.",
            "Six at the top: The prince shoots at a hawk on a high wall. He kills it. Everything serves to further.",
        ),
    ),
    41: Hexagram(
        number=41, name_en="Decrease", name_pinyin="Sun",
        trigram_above="mountain", trigram_below="lake",
        judgment="Decrease combined with sincerity brings about supreme good fortune without blame. One may be persevering in this. It furthers one to undertake something. How is this to be carried out? One may use two small bowls for the sacrifice.",
        image="At the foot of the mountain, the lake: the image of Decrease. Thus the superior person controls his anger and restrains his instincts.",
        lines=(
            "Nine at the beginning: Going quickly when one's tasks are finished is without blame. But one must reflect on how much one may decrease others.",
            "Nine in the second place: Perseverance furthers. To undertake something brings misfortune. Without decreasing oneself, one is able to bring increase to others.",
            "Six in the third place: When three people journey together, their number decreases by one. When one man journeys alone, he finds a companion.",
            "Six in the fourth place: If a man decreases his faults, it makes the other hasten to come and rejoice. No blame.",
            "Six in the fifth place: Someone does indeed increase him. Ten pairs of tortoises cannot oppose it. Supreme good fortune.",
            "Nine at the top: If one is increased without depriving others, there is no blame. Perseverance brings good fortune. It furthers one to undertake something. One obtains servants but no longer has a separate home.",
        ),
    ),
    42: Hexagram(
        number=42, name_en="Increase", name_pinyin="Yi",
        trigram_above="wind", trigram_below="thunder",
        judgment="Increase. It furthers one to undertake something. It furthers one to cross the great water.",
        image="Wind and thunder: the image of Increase. Thus the superior person: if he sees good, he imitates it; if he has faults, he rids himself of them.",
        lines=(
            "Nine at the beginning: It furthers one to accomplish great deeds. Supreme good fortune. No blame.",
            "Six in the second place: Someone does indeed increase him; ten pairs of tortoises cannot oppose it. Constant perseverance brings good fortune. The king presents him before God. Good fortune.",
            "Six in the third place: One is enriched through unfortunate events. No blame, if you are sincere and walk in the middle, and report with a seal to the prince.",
            "Six in the fourth place: If you walk in the middle and report to the prince, he will follow. It furthers one to be used in the removal of the capital.",
            "Nine in the fifth place: If in truth you have a kind heart, ask not. Supreme good fortune. Truly, kindness will be recognized as your virtue.",
            "Nine at the top: He brings increase to no one. Indeed, someone even strikes him. He does not keep his heart constantly steady. Misfortune.",
        ),
    ),
    43: Hexagram(
        number=43, name_en="Breakthrough (Resoluteness)", name_pinyin="Guai",
        trigram_above="lake", trigram_below="heaven",
        judgment="Breakthrough. One must resolutely make the matter known at the court of the king. It must be announced truthfully. Danger. It is necessary to notify one's own city. It does not further to resort to arms. It furthers one to undertake something.",
        image="The lake has risen up to heaven: the image of Breakthrough. Thus the superior person dispenses riches downward and refrains from resting on his virtue.",
        lines=(
            "Nine at the beginning: Mighty in the forward-striding toes. When one goes and is not equal to the task, one makes a mistake.",
            "Nine in the second place: A cry of alarm. Arms at evening and at night. Fear nothing.",
            "Nine in the third place: To be powerful in the cheekbones brings misfortune. The superior person is firmly resolved. He walks alone and is caught in the rain. He is bespattered, and people murmur against him. No blame.",
            "Nine in the fourth place: There is no skin on his thighs, and walking comes hard. If a man were to let himself be led like a sheep, remorse would disappear. But if these words are heard they will not be believed.",
            "Nine in the fifth place: In dealing with weeds, firm resolution is necessary. Walking in the middle remains free of blame.",
            "Six at the top: No cry. In the end misfortune comes.",
        ),
    ),
    44: Hexagram(
        number=44, name_en="Coming to Meet", name_pinyin="Gou",
        trigram_above="heaven", trigram_below="wind",
        judgment="Coming to Meet. The maiden is powerful. One should not marry such a maiden.",
        image="Under heaven, wind: the image of Coming to Meet. Thus does the prince act when disseminating his commands and proclaiming them to the four quarters of heaven.",
        lines=(
            "Six at the beginning: It must be checked with a brake of bronze. Perseverance brings good fortune. If one lets it take its course, one experiences misfortune. Even a lean pig has it in him to rage around.",
            "Nine in the second place: There is a fish in the tank. No blame. Does not further guests.",
            "Nine in the third place: There is no skin on his thighs, and walking comes hard. If one is mindful of the danger, no great mistake.",
            "Nine in the fourth place: No fish in the tank. This leads to misfortune.",
            "Nine in the fifth place: A melon covered with willow leaves. Hidden lines. Then it drops down to one from heaven.",
            "Nine at the top: He comes to meet with his horns. Humiliation. No blame.",
        ),
    ),
    45: Hexagram(
        number=45, name_en="Gathering Together (Massing)", name_pinyin="Cui",
        trigram_above="lake", trigram_below="earth",
        judgment="Gathering Together. Success. The king approaches his temple. It furthers one to see the great man. This brings success. Perseverance furthers. To bring great offerings creates good fortune. It furthers one to undertake something.",
        image="Over the earth, the lake: the image of Gathering Together. Thus the superior person renews his weapons in order to meet the unforeseen.",
        lines=(
            "Six at the beginning: If you are sincere, but not to the end, there will sometimes be confusion, sometimes gathering together. If you call out, then after one grasp of the hand you can laugh again. Regret not. Going is without blame.",
            "Six in the second place: Letting oneself be drawn brings good fortune and remains blameless. If one is sincere, it furthers one to bring even a small offering.",
            "Six in the third place: Gathering together amid sighs. Nothing that would further. Going is without blame. Slight humiliation.",
            "Nine in the fourth place: Great good fortune. No blame.",
            "Nine in the fifth place: If in gathering together one has position, this brings no blame. If there are some who are not yet sincerely in the work, sublime and enduring perseverance is needed. Then remorse disappears.",
            "Six at the top: Lamenting and sighing, floods of tears. No blame.",
        ),
    ),
    46: Hexagram(
        number=46, name_en="Pushing Upward", name_pinyin="Sheng",
        trigram_above="earth", trigram_below="wind",
        judgment="Pushing Upward has supreme success. One must see the great man. Fear not. Departure toward the south brings good fortune.",
        image="Within the earth, wood grows: the image of Pushing Upward. Thus the superior person of devoted character heaps up small things in order to achieve something high and great.",
        lines=(
            "Six at the beginning: Pushing upward that meets with confidence brings great good fortune.",
            "Nine in the second place: If one is sincere, it furthers one to bring even a small offering. No blame.",
            "Nine in the third place: One pushes upward into an empty city.",
            "Six in the fourth place: The king offers him Mount Chi. Good fortune. No blame.",
            "Six in the fifth place: Perseverance brings good fortune. One pushes upward by steps.",
            "Six at the top: Pushing upward in the dark. It furthers one to be unremittingly persevering.",
        ),
    ),
    47: Hexagram(
        number=47, name_en="Oppression (Exhaustion)", name_pinyin="Kun",
        trigram_above="lake", trigram_below="water",
        judgment="Oppression. Success. Perseverance. The great man brings about good fortune. No blame. When one has something to say, it is not believed.",
        image="There is no water in the lake: the image of Exhaustion. Thus the superior person stakes his life on following his will.",
        lines=(
            "Six at the beginning: One sits oppressed under a bare tree and strays into a gloomy valley. For three years one sees nothing.",
            "Nine in the second place: One is oppressed while at meat and drink. The man with the scarlet knee bands is just coming. It furthers one to offer sacrifice. To set forth brings misfortune. No blame.",
            "Six in the third place: A man permits himself to be oppressed by stone, and leans on thorns and thistles. He enters his house and does not see his wife. Misfortune.",
            "Nine in the fourth place: He comes very quietly, oppressed in a golden carriage. Humiliation, but the end is reached.",
            "Nine in the fifth place: His nose and feet are cut off. Oppression at the hands of the man with the purple knee bands. Joy comes softly. It furthers one to make offerings and libations.",
            "Six at the top: He is oppressed by creeping vines. He moves uncertainly and says, 'Movement brings remorse.' If one feels remorse over this and makes a start, good fortune comes.",
        ),
    ),
    48: Hexagram(
        number=48, name_en="The Well", name_pinyin="Jing",
        trigram_above="water", trigram_below="wind",
        judgment="The Well. The town may be changed, but the well cannot be changed. It neither decreases nor increases. They come and go and draw from the well. If one gets down almost to the water and the rope does not go all the way, or the jug breaks, it brings misfortune.",
        image="Water over wood: the image of the Well. Thus the superior person encourages the people at their work and exhorts them to help one another.",
        lines=(
            "Six at the beginning: One does not drink the mud of the well. No animals come to an old well.",
            "Nine in the second place: At the wellhole one shoots fishes. The jug is broken and leaks.",
            "Nine in the third place: The well is cleaned, but no one drinks from it. This is my heart's sorrow, for one might draw from it. If the king were clear-minded, good fortune might be enjoyed in common.",
            "Six in the fourth place: The well is being lined. No blame.",
            "Nine in the fifth place: In the well there is a clear, cold spring from which one can drink.",
            "Six at the top: The well is being drawn from. Do not cover it. It brings supreme good fortune. Confidence. It is really dependable.",
        ),
    ),
    49: Hexagram(
        number=49, name_en="Revolution (Molting)", name_pinyin="Ge",
        trigram_above="lake", trigram_below="fire",
        judgment="Revolution. On your own day you are believed. Supreme success. Furthering through perseverance. Remorse disappears.",
        image="Fire in the lake: the image of Revolution. Thus the superior person sets the calendar in order and makes the seasons clear.",
        lines=(
            "Nine at the beginning: Wrapped in the hide of a yellow cow.",
            "Six in the second place: When one's own day comes, one may create revolution. Starting brings good fortune. No blame.",
            "Nine in the third place: Starting brings misfortune. Perseverance brings danger. When talk of revolution has gone the rounds three times, one may commit himself, and men will believe him.",
            "Nine in the fourth place: Remorse disappears. Men believe him. Changing the form of government brings good fortune.",
            "Nine in the fifth place: The great man changes like a tiger. Even before he questions the oracle he is believed.",
            "Six at the top: The superior person changes like a panther. The inferior man molts in the face. Starting brings misfortune. To remain persevering brings good fortune.",
        ),
    ),
    50: Hexagram(
        number=50, name_en="The Caldron", name_pinyin="Ding",
        trigram_above="fire", trigram_below="wind",
        judgment="The Caldron. Supreme good fortune. Success.",
        image="Fire over wood: the image of the Caldron. Thus the superior person consolidates his fate by making his position correct.",
        lines=(
            "Six at the beginning: A ting with legs upturned. Furthers removal of stagnating stuff. One takes a concubine for the sake of her son. No blame.",
            "Nine in the second place: There is food in the ting. My comrades are envious, but they cannot harm me. Good fortune.",
            "Nine in the third place: The handle of the ting is altered. One is impeded in his way of life. The fat of the pheasant is not eaten. Once rain falls, remorse is spent. Good fortune comes in the end.",
            "Nine in the fourth place: The legs of the ting are broken. The prince's meal is spilled and his person is soiled. Misfortune.",
            "Six in the fifth place: The ting has yellow handles, golden carrying rings. Perseverance furthers.",
            "Nine at the top: The ting has rings of jade. Great good fortune. Nothing that would not act to further.",
        ),
    ),
    51: Hexagram(
        number=51, name_en="The Arousing (Shock, Thunder)", name_pinyin="Zhen",
        trigram_above="thunder", trigram_below="thunder",
        judgment="Shock brings success. Shock comes—oh, oh! Laughing words—ha, ha! The shock terrifies for a hundred miles, and he does not let fall the sacrificial spoon and chalice.",
        image="Thunder repeated: the image of Shock. Thus in fear and trembling the superior person sets his life in order and examines himself.",
        lines=(
            "Nine at the beginning: Shock comes—oh, oh! Then follow laughing words—ha, ha! Good fortune.",
            "Six in the second place: Shock comes bringing danger. A hundred thousand times you lose your treasures and must climb the nine hills. Do not go in pursuit of them. After seven days you will get them back again.",
            "Six in the third place: Shock comes and makes one distraught. If shock spurs to action one remains free of misfortune.",
            "Nine in the fourth place: Shock is mired.",
            "Six in the fifth place: Shock goes hither and thither. Danger. However, nothing at all is lost. Yet there are things to be done.",
            "Six at the top: Shock brings ruin and terrified gazing around. Going ahead brings misfortune. If it has not yet touched one's own body but has reached one's neighbor first, there is no blame. One's comrades have something to talk about.",
        ),
    ),
    52: Hexagram(
        number=52, name_en="Keeping Still (Mountain)", name_pinyin="Gen",
        trigram_above="mountain", trigram_below="mountain",
        judgment="Keeping Still. Keeping his back still so that he no longer feels his body. He goes into his courtyard and does not see his people. No blame.",
        image="Mountains standing close together: the image of Keeping Still. Thus the superior person does not permit his thoughts to go beyond his situation.",
        lines=(
            "Six at the beginning: Keeping his toes still. No blame. Continued perseverance furthers.",
            "Six in the second place: Keeping his calves still. He cannot rescue him whom he follows. His heart is not glad.",
            "Nine in the third place: Keeping his hips still. Making his sacrum stiff. Dangerous. The heart suffocates.",
            "Six in the fourth place: Keeping his trunk still. No blame.",
            "Six in the fifth place: Keeping his jaws still. The words are well-ordered. Remorse disappears.",
            "Nine at the top: Noblehearted keeping still. Good fortune.",
        ),
    ),
    53: Hexagram(
        number=53, name_en="Development (Gradual Progress)", name_pinyin="Jian",
        trigram_above="wind", trigram_below="mountain",
        judgment="Development. The maiden is given in marriage. Good fortune. Perseverance furthers.",
        image="On the mountain, a tree: the image of Development. Thus the superior person abides in dignity and virtue, in order to improve the mores.",
        lines=(
            "Six at the beginning: The wild goose gradually draws near the shore. The young son is in danger. There is talk. No blame.",
            "Six in the second place: The wild goose gradually draws near the cliff. Eating and drinking in peace and concord. Good fortune.",
            "Nine in the third place: The wild goose gradually draws near the plateau. The man goes forth and does not return. The woman carries a child but does not bring it forth. Misfortune. It furthers one to fight off robbers.",
            "Six in the fourth place: The wild goose gradually draws near the tree. Perhaps it will find a flat branch. No blame.",
            "Nine in the fifth place: The wild goose gradually draws near the summit. For three years the woman has no child. In the end nothing can hinder her. Good fortune.",
            "Nine at the top: The wild goose gradually draws near the cloud heights. Its feathers can be used for the sacred dance. Good fortune.",
        ),
    ),
    54: Hexagram(
        number=54, name_en="The Marrying Maiden", name_pinyin="Gui Mei",
        trigram_above="thunder", trigram_below="lake",
        judgment="The Marrying Maiden. Undertakings bring misfortune. Nothing that would further.",
        image="Thunder over the lake: the image of the Marrying Maiden. Thus the superior person understands the transitory in the light of the eternity of the end.",
        lines=(
            "Nine at the beginning: The marrying maiden as a concubine. A lame man who is able to tread. Undertakings bring good fortune.",
            "Nine in the second place: A one-eyed man who is able to see. The perseverance of a solitary person furthers.",
            "Six in the third place: The marrying maiden as a slave. She marries as a concubine.",
            "Nine in the fourth place: The marrying maiden draws out the allotted time. A late marriage comes in due course.",
            "Six in the fifth place: The sovereign I gave his daughter in marriage. The embroidered garments of the princess were not as gorgeous as those of the servingmaid. The moon that is nearly full brings good fortune.",
            "Six at the top: The woman holds the basket, but there are no fruits in it. The man stabs the sheep, but no blood flows. Nothing that acts to further.",
        ),
    ),
    55: Hexagram(
        number=55, name_en="Abundance (Fullness)", name_pinyin="Feng",
        trigram_above="thunder", trigram_below="fire",
        judgment="Abundance has success. The king attains abundance. Be not sad. Be like the sun at midday.",
        image="Both thunder and lightning come: the image of Abundance. Thus the superior person decides lawsuits and carries out punishments.",
        lines=(
            "Nine at the beginning: When a man meets his destined ruler, they can be together ten days, and it is not a mistake. Going meets with recognition.",
            "Six in the second place: The curtain is of such fullness that the polestars can be seen at noon. Through going one meets with mistrust and hate. If one rouses him through truth, good fortune comes.",
            "Nine in the third place: The underbrush is of such abundance that the small stars can be seen at noon. He breaks his right arm. No blame.",
            "Nine in the fourth place: The curtain is of such fullness that the polestars can be seen at noon. He meets his ruler, who is of like kind. Good fortune.",
            "Six in the fifth place: Lines are coming, blessing and fame draw near. Good fortune.",
            "Six at the top: His house is in a state of abundance. He screens off his family. He peers through the gate and no longer perceives anyone there. For three years he sees nothing. Misfortune.",
        ),
    ),
    56: Hexagram(
        number=56, name_en="The Wanderer", name_pinyin="Lu",
        trigram_above="fire", trigram_below="mountain",
        judgment="The Wanderer. Success through smallness. Perseverance brings good fortune to the wanderer.",
        image="Fire on the mountain: the image of the Wanderer. Thus the superior person is clear-minded and cautious in imposing penalties, and does not let lawsuits drag on.",
        lines=(
            "Six at the beginning: If the wanderer busies himself with trivial things, he draws down misfortune upon himself.",
            "Six in the second place: The wanderer comes to an inn. He has his property with him. He wins the steadfastness of a young servant.",
            "Nine in the third place: The wanderer's inn burns down. He loses the steadfastness of his young servant. Danger.",
            "Nine in the fourth place: The wanderer rests in a shelter. He obtains his property and an ax. My heart is not glad.",
            "Six in the fifth place: He shoots a pheasant. It drops with the first arrow. In the end this brings both praise and office.",
            "Nine at the top: The bird's nest burns up. The wanderer laughs at first, then must needs lament and weep. Through carelessness he loses his cow. Misfortune.",
        ),
    ),
    57: Hexagram(
        number=57, name_en="The Gentle (The Penetrating, Wind)", name_pinyin="Xun",
        trigram_above="wind", trigram_below="wind",
        judgment="The Gentle. Success through what is small. It furthers one to have somewhere to go. It furthers one to see the great man.",
        image="Winds following one upon the other: the image of the Gently Penetrating. Thus the superior person spreads his commands abroad and carries out his undertakings.",
        lines=(
            "Six at the beginning: In advancing and in retreating, the perseverance of a warrior furthers.",
            "Nine in the second place: Penetration under the bed. Priests and magicians are used in great number. Good fortune. No blame.",
            "Nine in the third place: Repeated penetration. Humiliation.",
            "Six in the fourth place: Remorse vanishes. During the hunt three kinds of game are caught.",
            "Nine in the fifth place: Perseverance brings good fortune. Remorse vanishes. Nothing that does not further. No beginning, but an end. Before the change, three days. After the change, three days. Good fortune.",
            "Nine at the top: Penetration under the bed. He loses his property and his ax. Perseverance brings misfortune.",
        ),
    ),
    58: Hexagram(
        number=58, name_en="The Joyous, Lake", name_pinyin="Dui",
        trigram_above="lake", trigram_below="lake",
        judgment="The Joyous. Success. Perseverance is favorable.",
        image="Lakes resting one on the other: the image of the Joyous. Thus the superior person joins with his friends for discussion and practice.",
        lines=(
            "Nine at the beginning: Contented joyousness. Good fortune.",
            "Nine in the second place: Sincere joyousness. Good fortune. Remorse disappears.",
            "Six in the third place: Coming joyousness. Misfortune.",
            "Nine in the fourth place: Joyousness that is weighed is not at peace. After ridding himself of mistakes a man has joy.",
            "Nine in the fifth place: Sincerity toward disintegrating influences is dangerous.",
            "Six at the top: Seductive joyousness.",
        ),
    ),
    59: Hexagram(
        number=59, name_en="Dispersion (Dissolution)", name_pinyin="Huan",
        trigram_above="wind", trigram_below="water",
        judgment="Dispersion. Success. The king approaches his temple. It furthers one to cross the great water. Perseverance furthers.",
        image="The wind drives over the water: the image of Dispersion. Thus the kings of old sacrificed to the Lord and built temples.",
        lines=(
            "Six at the beginning: He brings help with the strength of a horse. Good fortune.",
            "Nine in the second place: At the dissolution he hurries to that which supports him. Remorse disappears.",
            "Six in the third place: He dissolves his self. No remorse.",
            "Six in the fourth place: He dissolves his bond with his group. Supreme good fortune. Dispersion leads in turn to accumulation. This is something that ordinary men do not think of.",
            "Nine in the fifth place: His loud cries are as dissolving as sweat. Dissolution! A king abides without blame.",
            "Nine at the top: He dissolves his blood. Departing, keeping at a distance, going out, is without blame.",
        ),
    ),
    60: Hexagram(
        number=60, name_en="Limitation", name_pinyin="Jie",
        trigram_above="water", trigram_below="lake",
        judgment="Limitation. Success. Galling limitation must not be persevered in.",
        image="Water over lake: the image of Limitation. Thus the superior person creates number and measure, and examines the nature of virtue and correct conduct.",
        lines=(
            "Nine at the beginning: Not going out of the door and the courtyard is without blame.",
            "Nine in the second place: Not going out of the gate and the courtyard brings misfortune.",
            "Six in the third place: He who knows no limitation will have cause to lament. No blame.",
            "Six in the fourth place: Contented limitation. Success.",
            "Nine in the fifth place: Sweet limitation brings good fortune. Going brings esteem.",
            "Six at the top: Galling limitation. Perseverance brings misfortune. Remorse disappears.",
        ),
    ),
    61: Hexagram(
        number=61, name_en="Inner Truth", name_pinyin="Zhong Fu",
        trigram_above="wind", trigram_below="lake",
        judgment="Inner Truth. Pigs and fishes. Good fortune. It furthers one to cross the great water. Perseverance furthers.",
        image="Wind over lake: the image of Inner Truth. Thus the superior person discusses criminal cases in order to delay executions.",
        lines=(
            "Nine at the beginning: Being prepared brings good fortune. If there are secret designs, it is disquieting.",
            "Nine in the second place: A crane calling in the shade. Its young answers it. I have a good goblet. I will share it with you.",
            "Six in the third place: He finds a comrade. Now he beats the drum, now he stops. Now he sobs, now he sings.",
            "Six in the fourth place: The moon nearly at the full. The team horse goes astray. No blame.",
            "Nine in the fifth place: He possesses truth, which links together. No blame.",
            "Nine at the top: Cockcrow penetrating to heaven. Perseverance brings misfortune.",
        ),
    ),
    62: Hexagram(
        number=62, name_en="Preponderance of the Small", name_pinyin="Xiao Guo",
        trigram_above="thunder", trigram_below="mountain",
        judgment="Preponderance of the Small. Success. Perseverance furthers. Small things may be done; great things should not be done. The flying bird brings the message: it is not well to strive upward; it is well to remain below. Great good fortune.",
        image="Thunder on the mountain: the image of Preponderance of the Small. Thus in his conduct the superior person gives preponderance to reverence. In bereavement he gives preponderance to grief. In his expenditures he gives preponderance to thrift.",
        lines=(
            "Six at the beginning: The bird meets with misfortune through flying.",
            "Six in the second place: She passes by her ancestor and meets her ancestress. He does not reach his prince and meets the official. No blame.",
            "Nine in the third place: If one is not extremely careful, somebody may come up from behind and strike him. Misfortune.",
            "Nine in the fourth place: No blame. He meets him without passing by. Going brings danger. One must be on guard. Do not act. Be constantly persevering.",
            "Six in the fifth place: Dense clouds, no rain from our western territory. The prince shoots and hits him who is in the cave.",
            "Six at the top: He passes him by, not meeting him. The flying bird leaves him behind. Misfortune. This means bad luck and injury.",
        ),
    ),
    63: Hexagram(
        number=63, name_en="After Completion", name_pinyin="Ji Ji",
        trigram_above="water", trigram_below="fire",
        judgment="After Completion. Success in small matters. Perseverance furthers. At the beginning good fortune, at the end disorder.",
        image="Water over fire: the image of the condition in After Completion. Thus the superior person takes thought of misfortune and arms himself against it in advance.",
        lines=(
            "Nine at the beginning: He brakes his wheels. He gets his tail in the water. No blame.",
            "Six in the second place: The woman loses the curtain of her carriage. Do not run after it; on the seventh day you will get it.",
            "Nine in the third place: The Illustrious Ancestor disciplines the Devil's Country. After three years he conquers it. Inferior people must not be employed.",
            "Six in the fourth place: The finest clothes turn to rags. Be careful all day long.",
            "Nine in the fifth place: The neighbor in the east who slaughters an ox does not attain as much real happiness as the neighbor in the west with his small offering.",
            "Six at the top: He gets his head in the water. Danger.",
        ),
    ),
    64: Hexagram(
        number=64, name_en="Before Completion", name_pinyin="Wei Ji",
        trigram_above="fire", trigram_below="water",
        judgment="Before Completion. Success. But if the little fox, after nearly completing the crossing, gets his tail in the water, there is nothing that would further.",
        image="Fire over water: the image of the condition before transition. Thus the superior person is careful in the differentiation of things, so that each finds its place.",
        lines=(
            "Six at the beginning: He gets his tail in the water. Humiliating.",
            "Nine in the second place: He brakes his wheels. Perseverance brings good fortune.",
            "Six in the third place: Before completion, attack brings misfortune. It furthers one to cross the great water.",
            "Nine in the fourth place: Perseverance brings good fortune. Remorse disappears. Shock, thus to discipline the Devil's Country. For three years, great realms are rewarded.",
            "Six in the fifth place: Perseverance brings good fortune. No remorse. The light of the superior person is true. Good fortune.",
            "Nine at the top: There is drinking of wine in genuine confidence. No blame. But if one wets his head, he loses it, in truth.",
        ),
    ),
}

assert set(HEXAGRAMS.keys()) == set(range(1, 65)), \
    f"missing hexagrams: {set(range(1, 65)) - set(HEXAGRAMS.keys())}"


# King Wen lookup table.
# Encoding: index = sum(bit_i << i) where bit_0 is the bottom line (line 1),
# bit_5 is the top line (line 6); yin (6 or 8) = 0, yang (7 or 9) = 1.
# Lower trigram occupies bits 0-2, upper trigram occupies bits 3-5.
# Sanity: 0b111111 -> 1 (Creative); 0b000000 -> 2 (Receptive).
_KING_WEN: dict[int, int] = {
    0b000000: 2,
    0b000001: 24,
    0b000010: 7,
    0b000011: 46,
    0b000100: 15,
    0b000101: 19,
    0b000110: 36,
    0b000111: 11,
    0b001000: 16,
    0b001001: 51,
    0b001010: 40,
    0b001011: 32,
    0b001100: 62,
    0b001101: 54,
    0b001110: 55,
    0b001111: 34,
    0b010000: 8,
    0b010001: 3,
    0b010010: 29,
    0b010011: 48,
    0b010100: 39,
    0b010101: 60,
    0b010110: 63,
    0b010111: 5,
    0b011000: 20,
    0b011001: 42,
    0b011010: 59,
    0b011011: 57,
    0b011100: 53,
    0b011101: 61,
    0b011110: 37,
    0b011111: 9,
    0b100000: 23,
    0b100001: 27,
    0b100010: 4,
    0b100011: 18,
    0b100100: 52,
    0b100101: 41,
    0b100110: 22,
    0b100111: 26,
    0b101000: 45,
    0b101001: 17,
    0b101010: 47,
    0b101011: 28,
    0b101100: 31,
    0b101101: 58,
    0b101110: 49,
    0b101111: 43,
    0b110000: 35,
    0b110001: 21,
    0b110010: 64,
    0b110011: 50,
    0b110100: 56,
    0b110101: 38,
    0b110110: 30,
    0b110111: 14,
    0b111000: 12,
    0b111001: 25,
    0b111010: 6,
    0b111011: 44,
    0b111100: 33,
    0b111101: 10,
    0b111110: 13,
    0b111111: 1,
}

assert len(_KING_WEN) == 64


def _lines_to_pattern(lines: tuple[int, ...]) -> int:
    pat = 0
    for i, v in enumerate(lines):
        if v in (7, 9):
            pat |= 1 << i
    return pat


def _transform(lines: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(
        7 if v == 6 else 8 if v == 9 else v
        for v in lines
    )


def cast_three_coins(rng: random.Random | None = None) -> "CastResult":
    r = rng if rng is not None else random.SystemRandom()
    lines = tuple(
        sum(r.choice((2, 3)) for _ in range(3))
        for _ in range(6)
    )
    changing = tuple(i for i, v in enumerate(lines) if v in (6, 9))
    primary_id = _KING_WEN[_lines_to_pattern(lines)]
    transformed_id: int | None = None
    if changing:
        transformed_id = _KING_WEN[_lines_to_pattern(_transform(lines))]
    return CastResult(
        lines=lines, changing_indices=changing,
        primary_id=primary_id, transformed_id=transformed_id,
    )


def build_calc_md(*, question: str | None, cast: CastResult) -> str:
    primary = HEXAGRAMS[cast.primary_id]
    out: list[str] = ["# I-Ching - Three-Coin Cast", ""]
    if question:
        out.append(f"**Question:** {question}")
    else:
        out.append("**Question:** (none)")
    out += ["", f"## Primary Hexagram {primary.number}: {primary.name_en} ({primary.name_pinyin})"]
    out += [f"Trigrams: {primary.trigram_above} above, {primary.trigram_below} below", ""]
    out += ["**Judgment:**", primary.judgment, "", "**Image:**", primary.image, ""]
    if cast.changing_indices:
        out.append("## Changing Lines")
        for idx in cast.changing_indices:
            out.append(f"- Line {idx + 1} (bottom is 1): {primary.lines[idx]}")
        out.append("")
        if cast.transformed_id is not None:
            t = HEXAGRAMS[cast.transformed_id]
            out += [f"## Becomes Hexagram {t.number}: {t.name_en} ({t.name_pinyin})"]
            out += ["**Judgment:**", t.judgment, ""]
    return "\n".join(out).rstrip() + "\n"


def build_calc_md_from_jsonb(draw: dict) -> str:
    primary_id = draw["primary_id"]
    if primary_id not in HEXAGRAMS:
        raise KeyError(f"unknown hexagram id: {primary_id}")
    transformed_id = draw.get("transformed_id")
    if transformed_id is not None and transformed_id not in HEXAGRAMS:
        raise KeyError(f"unknown transformed hexagram id: {transformed_id}")
    cast = CastResult(
        lines=tuple(draw["lines"]),
        changing_indices=tuple(draw.get("changing_indices", [])),
        primary_id=primary_id, transformed_id=transformed_id,
    )
    return build_calc_md(question=draw.get("question"), cast=cast)
