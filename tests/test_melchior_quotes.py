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
