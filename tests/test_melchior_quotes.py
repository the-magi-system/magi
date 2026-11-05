"""Verbatim quotes and figures are checked by program (plan 9, Task 8; design 22.9.1)."""
import unicodedata
from decimal import Decimal

from tests.util import REPO_ROOT

SOURCES = REPO_ROOT / "tests" / "fixtures" / "sources"
CASH = ("截至2026-06-30，合并现金及等价物约15.436601十亿韩元，短期金融产品136.000000十亿；借款约34.869582十亿，"
        "租赁负债约1.991556十亿。")
DIVIDEND = "H1现金流股息支付约7.486679十亿韩元，对应FY2025分红；H1没有新购库存股现金支出。"
UNIT = "(단위 : 원)"


def node24_text():
    from engine.fetch import decode, html_to_text
    return html_to_text(decode((SOURCES / "dart-node24.body").read_bytes(), "text/html; charset=utf-8")[0])


def test_a_quote_must_appear_after_whitespace_is_unified():
    from engine.melchior.quotes import quote_in
    source = "Revenue in the second quarter\nof 2026 was $382.5　million, an increase of 90%."
    assert quote_in("Revenue in the second quarter of 2026 was $382.5 million", source)
    assert not quote_in("Revenue in the third quarter of 2026 was $382.5 million", source)
    assert not quote_in("$382.5", source)  # shorter than 8 characters once normalised


def test_korean_quotes_are_compared_after_normalisation():
    from engine.melchior.quotes import quote_in
    sentence = "기말현금및현금성자산 15,436,600,653"
    assert quote_in(unicodedata.normalize("NFD", sentence), unicodedata.normalize("NFC", sentence) + " 원")
    assert quote_in("현금성자산 １５，４３６", "기말현금및현금성자산 15,436,600,653")


def test_common_english_forms_are_recognised():
    from engine.melchior.quotes import check_figures, parse_amount
    claim = "Revenue was $382.5 million"
    quote = "Total revenue was $382.5 million, or $382,500 thousand, against 382.50 a year earlier at 382.5"
    source = f"Results. {quote}."
    for fragment in ("$382.5 million", "$382,500 thousand"):
        assert parse_amount(fragment)[0] == Decimal("382500000")
    for pair in ({"claim": "382.5", "source": "382.5", "unit": None},
                 {"claim": "382.5", "source": "382.50", "unit": None},
                 {"claim": "$382.5 million", "source": "$382.5 million", "unit": None},
                 {"claim": "$382.5 million", "source": "$382,500 thousand", "unit": None}):
        ok, checked = check_figures(claim, quote, source, [pair])
        assert ok, pair
        ok, _ = check_figures(claim, quote, source, [pair], value=382.5, unit="USD million")
        assert ok, pair


def test_korean_won_amounts_are_recognised():
    from engine.melchior.quotes import parse_amount
    for fragment in ("7,486,679,200", "7,486,679,200원", "(7,486,679,200)"):
        assert parse_amount(fragment)[0] == Decimal("7486679200"), fragment


def test_a_value_in_another_unit_is_compared_at_the_claims_precision():
    from engine.melchior.quotes import check_figures
    text = node24_text()
    quote = "배당금의 지급 (7,486,679,200)"
    from engine.fetch import normalize
    assert quote in normalize(text) and UNIT in text
    pair = {"claim": "7.486679十亿韩元", "source": "(7,486,679,200)", "unit": UNIT}
    ok, checked = check_figures(DIVIDEND, quote, text, [pair])
    assert ok and checked[0]["claim_value"] == 7486679000 and checked[0]["source_value"] == 7486679200
    wrong = DIVIDEND.replace("7.486679", "7.486779")
    assert not check_figures(wrong, quote, text, [{**pair, "claim": "7.486779十亿韩元"}])[0]
    cash_quote = "기말현금및현금성자산 15,436,600,653"
    assert cash_quote in normalize(text)
    cash = {"claim": "15.436601十亿韩元", "source": "15,436,600,653", "unit": UNIT}
    assert check_figures("合并现金及等价物约15.436601十亿韩元", cash_quote, text, [cash])[0]


def test_a_unit_header_in_thousands_or_millions_is_applied():
    from engine.melchior.quotes import parse_amount
    assert parse_amount("7,486,679", "(단위 : 천원)")[0] == Decimal("7486679000")
    assert parse_amount("7,487", "(단위 : 백만원)")[0] == Decimal("7487000000")


def test_what_cannot_be_decided_is_not_found():
    from engine.melchior.quotes import verdict
    text = node24_text()
    quote = "배당금의 지급 (7,486,679,200)"
    claim = {"text": DIVIDEND}
    base = {"index": 2, "verdict": "supported", "timing": "historical", "quote": quote, "correct": None, "note": None}
    cases = [
        [{"claim": "7.486679十亿韩元", "source": "(7,486,679,200)", "unit": "(단위 : 웬)"}],  # a unit not in the source
        [{"claim": "7.486679十亿美元", "source": "(7,486,679,200)", "unit": UNIT}],  # not part of the claim
        [{"claim": "7.486679十亿韩元", "source": "7,486,679", "unit": None}],  # in thousands, but names no header
    ]
    for figures in cases:
        result = verdict(claim, {**base, "figures": figures}, text)
        assert result["verdict"] == "not_found" and result["note"] == "a figure could not be checked", figures
    good = verdict(claim, {**base, "figures": [{"claim": "7.486679十亿韩元", "source": "(7,486,679,200)",
                                               "unit": UNIT}]}, text)
    assert good["verdict"] == "supported" and good["figures"][0]["source_value"] == 7486679200


def test_every_significant_number_needs_a_figure():
    from engine.melchior.quotes import check_figures, significant_numbers
    claim = "2026H1合并CFO约23.588211十亿韩元，FY2025分红"
    assert significant_numbers(claim) == ["23.588211"]
    assert significant_numbers("截至2026-06-30，H1与FY2025、2026年6月30日") == []
    assert "89.65%" in significant_numbers("约占合并收入89.65%") and "136.000000" in significant_numbers(CASH)
    quote, source = "영업활동현금흐름 23,588,211,000", "(단위 : 원)\n영업활동현금흐름 23,588,211,000"
    pair = {"claim": "23.588211十亿韩元", "source": "23,588,211,000", "unit": UNIT}
    assert check_figures(claim, quote, source, [pair])[0]
    assert not check_figures(claim, quote, source, [])[0]


def test_a_contradicted_claim_needs_the_correct_figure_in_its_quote():
    from engine.melchior.quotes import verdict
    text = node24_text()
    quote = "배당금의 지급 (7,486,679,200)"
    claim = {"text": DIVIDEND.replace("7.486679", "8.000000")}
    item = {"index": 2, "verdict": "contradicted", "timing": "historical", "quote": quote, "figures": [], "note": None,
            "correct": {"text": "H1现金流股息支付约7.486679十亿韩元",
                        "figures": [{"claim": "7.486679十亿韩元", "source": "(7,486,679,200)", "unit": UNIT}]}}
    result = verdict(claim, item, text)
    assert result["verdict"] == "contradicted" and result["correct"]["figures"][0]["source_value"] == 7486679200
    item["correct"]["figures"] = [{"claim": "7.486679十亿韩元", "source": "(7,486,679,201)", "unit": UNIT}]
    result = verdict(claim, item, text)
    assert result["verdict"] == "not_found" and result["correct"] is None


# Production preview run 41718539976 (ev-20261031-jvm-2026-valueup-returns, a KRX page) ---------------------------

def test_a_percent_unit_from_a_table_header_is_read():
    from engine.melchior.quotes import parse_amount
    assert parse_amount("26.4", "(%)") == (Decimal("26.4"), Decimal("0.05"))
    assert parse_amount("26.4", "배당성향(%)") == (Decimal("26.4"), Decimal("0.05"))


def test_korean_multipliers_without_won_directly_after_the_number():
    from engine.melchior.quotes import parse_amount, significant_numbers
    assert parse_amount("0.5조")[0] == Decimal("5E11") and parse_amount("0.5조")[1] == Decimal("5E10")
    assert parse_amount("1,234억")[0] == Decimal("1.234E11")
    assert parse_amount("3천만")[0] == Decimal("3E7") and parse_amount("12백만")[0] == Decimal("1.2E7")
    assert parse_amount("7만")[0] == Decimal("7E4") and parse_amount("8천")[0] == Decimal("8E3")
    assert parse_amount("0.5조원")[0] == Decimal("5E11") and parse_amount("7,487백만원")[0] == Decimal("7.487E9")
    assert significant_numbers("국내 0.16조, 해외 7억") == ["0.16", "7"]


def test_man_or_cheon_not_directly_after_the_number_keeps_its_result():
    from engine.melchior.quotes import parse_amount, significant_numbers
    assert parse_amount("3년 만기") == (Decimal("3"), Decimal("0.5"))
    assert parse_amount("100 천") == (Decimal("100"), Decimal("0.5"))
    assert parse_amount("100만기") == (Decimal("100"), Decimal("0.5"))
    assert parse_amount("5년 천연가스") == (Decimal("5"), Decimal("0.5"))
    assert significant_numbers("3년 만기") == [] and significant_numbers("5만기") == []


def test_the_valueup_figures_agree():
    from engine.melchior.quotes import check_figures
    payout = [{"claim": "26.4%", "source": "26.4", "unit": "(%)"}]
    assert check_figures("净利润派息比26.4%。", "배당성향(%)\n26.4", "배당성향(%)\n26.4", payout)[0] is True
    target = [{"claim": "5,000亿韩元", "source": "0.5조", "unit": None}]
    assert check_figures("2030年收入目标为5,000亿韩元", "30년 0.5조", "30년 0.5조", target)[0] is True
    wrong = [{"claim": "5,000亿韩元", "source": "0.6조", "unit": None}]
    assert check_figures("2030年收入目标为5,000亿韩元", "30년 0.6조", "30년 0.6조", wrong)[0] is False


# Review of #126 at 45422e6: counters and currencies after the multiplier, 십만 to 천억, and article numbers ---------

def test_a_counter_or_currency_after_the_multiplier_does_not_block_it():
    from engine.melchior.quotes import parse_amount
    assert parse_amount("10만주")[0] == Decimal("1E5")
    assert parse_amount("5억달러")[0] == Decimal("5E8")
    assert parse_amount("3천명")[0] == Decimal("3E3")
    assert parse_amount("1만대")[0] == Decimal("1E4")
    for fragment, expected in (("2조엔", "2E12"), ("3억위안", "3E8"), ("4억유로", "4E8"), ("5천개", "5E3"),
                               ("6천건", "6E3"), ("7만톤", "7E4")):
        assert parse_amount(fragment)[0] == Decimal(expected), fragment
    assert parse_amount("100만기") == (Decimal("100"), Decimal("0.5"))  # any other Hangul still blocks it


def test_sip_man_to_cheon_eok_are_read():
    from engine.melchior.quotes import parse_amount
    for fragment in ("5천억원", "5천억", "5 천억원"):
        assert parse_amount(fragment)[0] == Decimal("5E11"), fragment
    assert parse_amount("3백억원")[0] == Decimal("3E10")
    assert parse_amount("2십억")[0] == Decimal("2E9")
    assert parse_amount("5십만")[0] == Decimal("5E5")
    assert parse_amount("1조2천억원") is None  # two digit groups stay unread


def test_an_article_number_is_not_an_amount():
    from engine.melchior.quotes import parse_amount, significant_numbers
    assert parse_amount("제3조") == (Decimal("3"), Decimal("0.5"))
    assert significant_numbers("제3조") == []
    assert parse_amount("제104조의27") is None


def test_significant_numbers_follow_the_same_rules():
    from engine.melchior.quotes import significant_numbers
    assert significant_numbers("자기주식 10만주 취득") == ["10"]
    assert significant_numbers("매출 5억달러, 설치 3천대") == ["5", "3"]
    assert significant_numbers("5천억원") == ["5"] and significant_numbers("7만기") == []


def test_counter_currency_and_large_multiplier_figures_agree():
    from engine.melchior.quotes import check_figures
    shares = [{"claim": "10万股", "source": "10만주", "unit": None}]
    assert check_figures("回购10万股", "자기주식 10만주 취득", "자기주식 10만주 취득", shares)[0] is True
    dollars = [{"claim": "5亿美元", "source": "5억달러", "unit": None}]
    assert check_figures("收入5亿美元", "매출 5억달러", "매출 5억달러", dollars)[0] is True
    won = [{"claim": "5,000亿韩元", "source": "5천억원", "unit": None}]
    assert check_figures("5,000亿韩元", "매출 목표 5천억원", "매출 목표 5천억원", won)[0] is True
    smaller = [{"claim": "500亿韩元", "source": "5천억원", "unit": None}]
    assert check_figures("500亿韩元", "매출 목표 5천억원", "매출 목표 5천억원", smaller)[0] is False


def test_written_numbers_give_each_number_with_its_multiplier():
    # Review of PR #131: one reader for the figure check's significant numbers and the intake rule on `value`.
    from decimal import Decimal
    from engine.melchior.quotes import written_numbers

    def read(text, unit=None):
        return [(n.token, n.written, n.amount) for n in written_numbers(text, unit)]

    assert read("자기주식 10만주 취득") == [("10", Decimal(10), Decimal(100000))]
    assert read("매출 5억달러", "USD million") == [("5", Decimal(5), Decimal(500))]
    assert read("자기주식 0.5조 규모", "억원") == [("0.5", Decimal("0.5"), Decimal(5000))]
    assert read("5천억원", "억원") == [("5", Decimal(5), Decimal(5000))]
    assert read("제3조에 따라") == [("3", Decimal(3), Decimal(3))], "no multiplier after 제"
    assert read("Revenue was $1.2 billion", "USD million") == [("1.2", Decimal("1.2"), Decimal(1200))]
    assert read("175,390,967 shares") == [("175,390,967", Decimal(175390967), Decimal(175390967))]
    assert read("만기 10년") == [("10", Decimal(10), Decimal(10))]


# A number in a range takes the multiplier written after the range's other end ------------------------------------

def _range_read(text, unit=None):
    from engine.melchior.quotes import written_numbers
    return {n.token: n.amount for n in written_numbers(text, unit)}


def test_a_range_end_borrows_the_multiplier_written_after_the_other_end():
    assert _range_read("revenue of $1.595 to $1.605 billion", "USD million") == {"1.595": Decimal(1595),
                                                                                 "1.605": Decimal(1605)}
    assert _range_read("lowered from $265 to $275 million")["265"] == Decimal(265_000_000)
    assert _range_read("in a range between $260 and $270 million")["260"] == Decimal(260_000_000)
    assert _range_read("자사주 1,000~1,200억원 매입", "억원") == {"1,000": Decimal(1000), "1,200": Decimal(1200)}
    from engine.melchior.quotes import written_numbers
    ten = written_numbers("a margin of 10-20%")[0]
    assert ten.amount == Decimal(10) and ten.multiplier is None and ten.borrowed.group(1) == "%"


def test_a_range_borrows_only_where_the_rule_says():
    # These already hold before the change: an own multiplier is kept, and nothing else borrows.
    assert _range_read("$900 million to $1.1 billion")["900"] == Decimal(900_000_000)
    assert _range_read("from 2025 to 2026") == {"2025": Decimal(2025), "2026": Decimal(2026)}
    assert _range_read("5 and 10 million")["5"] == Decimal(5), "and borrows only after between"
    assert _range_read("정관 제3~5조에 따라")["3"] == Decimal(3), "a number directly after 제 borrows nothing"


def test_significant_numbers_of_a_range_are_unchanged():
    from engine.melchior.quotes import significant_numbers
    # What they return today: a borrowed multiplier does not make a number significant.
    assert significant_numbers("$80 to $100 million") == ["100"]
    assert significant_numbers("$1.595 to $1.605 billion") == ["1.595", "1.605"]
    assert significant_numbers("10-20%") == ["20%"]


MIAX_CLAIM = "Full-year adjusted EBITDA guidance was lowered to $260 to $270 million"
MIAX_QUOTE = "adjusted EBITDA is now expected in a range between $260 million and $270 million"
MIAX_PAIRS = [{"claim": "$260", "source": "$260 million", "unit": None},
              {"claim": "$270 million", "source": "$270 million", "unit": None}]
TEM_CLAIM = "Full-year 2026 guidance: revenue of $1.595 to $1.605 billion"
TEM_QUOTE = "The company raised its guidance to $1.595 to $1.605 billion of revenue"
TEM_PAIRS = [{"claim": "$1.595", "source": "$1.595", "unit": None},
             {"claim": "$1.605 billion", "source": "$1.605 billion", "unit": None}]


def test_a_range_whose_unit_is_written_once_is_checked():
    from engine.melchior.quotes import check_figures
    assert check_figures(MIAX_CLAIM, MIAX_QUOTE, MIAX_QUOTE, MIAX_PAIRS)[0]
    assert check_figures(MIAX_CLAIM, MIAX_QUOTE, MIAX_QUOTE, MIAX_PAIRS, value=260, unit="USD million")[0]
    ok, checked = check_figures(TEM_CLAIM, TEM_QUOTE, TEM_QUOTE, TEM_PAIRS, value=1595, unit="USD million")
    assert ok and checked[0]["claim_value"] == 1_595_000_000


def test_a_range_value_that_is_not_an_end_is_still_refused():
    from engine.melchior.quotes import check_figures
    assert not check_figures(TEM_CLAIM, TEM_QUOTE, TEM_QUOTE, TEM_PAIRS, value=1600, unit="USD million")[0]


def test_a_borrowed_multiplier_must_agree_and_be_decidable():
    from engine.melchior.quotes import check_figures
    quote = "a price of $260 per share and $270 million of cash"
    pairs = [{"claim": "$260", "source": "$260 per share", "unit": None},
             {"claim": "$270 million", "source": "$270 million", "unit": None}]
    assert not check_figures("Pay $260 to $270 million", quote, quote, pairs)[0]
    twice = "Costs of $5 to $6 million in one year and $5 to $6 billion in the other"
    source = "costs of $5 million to $6 million"
    pairs = [{"claim": "$5", "source": "$5 million", "unit": None},
             {"claim": "$6 million", "source": "$6 million", "unit": None},
             {"claim": "$6 billion", "source": "$6 million", "unit": None}]
    assert not check_figures(twice, source, source, pairs)[0], "$5 reads as million and as billion"


def test_a_borrowed_reading_takes_its_precision_from_the_number_in_the_fragment():
    # Review of PR #141, item 1: an earlier "1.5" must not lend its precision to "$1.50".
    from engine.melchior.quotes import check_figures
    claim = "Revenue was 1.5 billion in 2025; guidance is $1.50 to $1.60 billion"
    quote = "guidance of $1.54 billion to $1.60 billion"
    pairs = [{"claim": "$1.50", "source": "$1.54 billion", "unit": None},
             {"claim": "$1.60 billion", "source": "$1.60 billion", "unit": None}]
    assert not check_figures(claim, quote, quote, pairs)[0]


def test_a_year_or_a_mark_joined_to_letters_borrows_nothing():
    # Review of PR #141, item 2: neither is a range end.
    from engine.melchior.quotes import written_numbers
    year = next(n for n in written_numbers("guidance for 2026 to $1.2 billion") if n.token == "2026")
    mark = next(n for n in written_numbers("Q3 to $1.2 billion") if n.token == "3")
    assert (year.borrowed, year.amount) == (None, Decimal(2026))
    assert (mark.borrowed, mark.amount) == (None, Decimal(3))
