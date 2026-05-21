from quantuum.astrology.chinese import chinese_pillars_from_local, pillar_summary


def test_anna_four_pillars_match_golden():
    bazi = chinese_pillars_from_local(1980, 6, 24, 10, 0)
    # Year: Geng-Shen (Metal Monkey) / 庚申
    assert bazi.year.full == "Geng-Shen (Metal Monkey)"
    assert bazi.year.chinese == "庚申"
    assert (bazi.year.element, bazi.year.animal, bazi.year.polarity) == ("Metal", "Monkey", "Yang")
    # Month: Ren-Wu (Water Horse) / 壬午
    assert bazi.month.full == "Ren-Wu (Water Horse)"
    assert bazi.month.chinese == "壬午"
    assert (bazi.month.element, bazi.month.animal, bazi.month.polarity) == ("Water", "Horse", "Yang")
    # Day (Self): Wu-Chen (Earth Dragon) / 戊辰
    assert bazi.day.full == "Wu-Chen (Earth Dragon)"
    assert bazi.day.chinese == "戊辰"
    assert (bazi.day.element, bazi.day.animal, bazi.day.polarity) == ("Earth", "Dragon", "Yang")
    # Hour: Ding-Si (Fire Snake) / 丁巳
    assert bazi.hour.full == "Ding-Si (Fire Snake)"
    assert bazi.hour.chinese == "丁巳"
    assert (bazi.hour.element, bazi.hour.animal, bazi.hour.polarity) == ("Fire", "Snake", "Yin")


def test_anna_pillar_summary():
    bazi = chinese_pillars_from_local(1980, 6, 24, 10, 0)
    assert pillar_summary(bazi.day) == "Yang Earth Dragon (Wu-Chen (Earth Dragon); 戊辰)"
