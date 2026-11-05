"""Verbatim quotes and figures, checked by program (design 22.9.1; plan 9, items 5 and 7).

This module is the one implementation of both checks. A quote counts only when it appears in the fetched source
after both are normalised (NFKC, every kind of space made one space), so Korean and full-width text compare
correctly. A figure counts only when the model's pair of fragments, one from the claim and one from the quote, both
appear where they should and convert to amounts that agree at the precision of the claim's own wording. Whatever
the program cannot decide makes the claim not_found, never supported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..fetch import normalize

MIN_QUOTE = 8
UNIT_WINDOW = 3000  # characters before the quote in which a unit such as a table header may stand
NOT_IN_SOURCE = "quote not in the source"
UNCHECKED = "a figure could not be checked"

# Multipliers, longest first so that 十亿 is not read as 亿 and 백만원 not as 원.
_WORDS = [("trillion", 10**12), ("billion", 10**9), ("million", 10**6), ("thousand", 10**3),
          ("천억원", 10**11), ("백억원", 10**10), ("십억원", 10**9), ("십만원", 10**5),
          ("조원", 10**12), ("억원", 10**8), ("백만원", 10**6), ("천만원", 10**7), ("만원", 10**4), ("천원", 10**3),
          ("원", 1), ("十亿", 10**9), ("千万", 10**7), ("百万", 10**6), ("亿", 10**8), ("万", 10**4)]
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_DATES = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{4}年\d{1,2}月(?:\d{1,2}日)?|\d{4}[./]\d{1,2}[./]\d{1,2}")
# Korean multipliers directly after the number (0.5조, 1,234억, 10만주, 5억달러, 5천억원), longest first. The next
# Hangul syllable may only be 원 or a currency or counter word from a closed list; any other one blocks the
# multiplier, so that a word such as 만기 or 천연 is never read as 만 or 천. After 제 (제3조, an article) no Korean
# multiplier is read. A number with two digit groups, such as 1조2천억원, holds two numbers and stays unread.
_KOREAN = {"천억": 10**11, "백억": 10**10, "십억": 10**9, "십만": 10**5, "천만": 10**7, "백만": 10**6,
           "조": 10**12, "억": 10**8, "만": 10**4, "천": 10**3}
_KOREAN_NEXT = ("원", "달러", "엔", "위안", "유로", "주", "명", "개", "건", "톤", "대")
_KOREAN_ALTERNATIVES = "|".join(sorted(_KOREAN, key=len, reverse=True))
_KOREAN_GUARD = "(?=" + "|".join(_KOREAN_NEXT) + "|[^가-힣]|$)"
_KOREAN_AFTER = re.compile(f"({_KOREAN_ALTERNATIVES}){_KOREAN_GUARD}")
_UNIT_AFTER = re.compile(r"\s*(%|trillion|billion|million|thousand|천억원|백억원|십억원|십만원|조원|억원|백만원|천만원|만원|천원"
                         r"|원|十亿|千万|百万|亿|万)", re.IGNORECASE)
ARTICLE = "제"  # 제3조: an article of a law or of the articles of incorporation, not an amount
_PERCENT = re.compile(r"%|percent|퍼센트|百分比")


def quote_in(quote: str | None, source_text: str) -> bool:
    if not isinstance(quote, str):
        return False
    wanted = normalize(quote)
    return len(wanted) >= MIN_QUOTE and wanted in normalize(source_text)


def _multiplier(text: str) -> int | None:
    lowered = text.lower()
    for word, factor in _WORDS:
        if word in lowered:
            return factor
    return None


def parse_amount(fragment: str | None, unit: str | None = None) -> tuple[Decimal, Decimal] | None:
    """(amount, precision) of a fragment such as `$382.5 million`, `(7,486,679,200)`, `7.486679十亿韩元` or `0.5조`;
    None when it holds no single number or cannot be read. The precision is half a unit of the fragment's last digit.
    `unit`, for example a table header `(단위 : 천원)`, a row header `배당성향(%)` or a claim's `USD million`, applies
    when the fragment names no unit; a unit that names a percentage reads with the factor 1."""
    if not isinstance(fragment, str):
        return None
    text = normalize(fragment).replace("−", "-")
    matches = list(_NUMBER.finditer(text))
    if len(matches) != 1:
        return None
    numbers = [matches[0].group(0)]
    digits = numbers[0].replace(",", "")
    try:
        amount = Decimal(digits)
    except InvalidOperation:
        return None
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    rest = text.replace(numbers[0], " ", 1)
    article = matches[0].start() > 0 and text[matches[0].start() - 1] == ARTICLE
    korean = None if article else _KOREAN_AFTER.match(text, matches[0].end())
    factor = _KOREAN[korean.group(1)] if korean else _multiplier(rest)
    if factor is None and "%" not in rest and unit:
        unit_text = normalize(unit)
        factor = _multiplier(unit_text)
        if factor is None and _PERCENT.search(unit_text.lower()):
            factor = 1  # a header such as 배당성향(%): the number is a percentage
        if factor is None:
            return None  # a unit that cannot be read
    factor = factor or 1
    precision = Decimal(5) * Decimal(10) ** (-(decimals + 1)) * factor
    return amount * factor, precision


@dataclass(frozen=True)
class WrittenNumber:
    token: str  # the number as the text writes it, for example `1,234.5`
    start: int
    end: int
    written: Decimal  # the number as written, without thousands separators or sign
    multiplier: re.Match | None  # its own multiplier, directly after it, if any
    amount: Decimal  # the number times its own or else its borrowed multiplier, divided by that of the `unit` given
    borrowed: re.Match | None = None  # the multiplier written after the other end of a range, when it has none


# A range: the connector between a number with no multiplier of its own and a number that has one ($1.595 to $1.605
# billion, $260-$270 million, 1,000~1,200억원). NFKC turns ～ into ~ but leaves 〜. `and` counts only after `between`.
_CURRENCY = r"[$€£¥₩]?\s*"
_RANGE = re.compile(r"\s*(?:to\b|-|–|—|~|〜|至|到)\s*" + _CURRENCY, re.IGNORECASE)
_RANGE_AND = re.compile(r"\s*and\s*" + _CURRENCY, re.IGNORECASE)
_BETWEEN = re.compile(r"\bbetween\s*[$€£¥₩]?\s*$", re.IGNORECASE)


def _joined_to_letters(text: str, start: int, end: int) -> bool:
    """A mark such as Q3, H1 or FY2026: the number touches an ASCII letter on either side."""
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    return (before.isascii() and before.isalpha()) or (after.isascii() and after.isalpha())


def _bare_year(token: str, own: re.Match | None) -> bool:
    """A year: a four-digit integer from 1900 to 2100, written without a comma, a decimal point or a multiplier."""
    plain = token.replace(",", "")
    return "." not in plain and "," not in token and len(plain) == 4 and 1900 <= int(plain) <= 2100 and own is None


def _factor(match: re.Match | None) -> int:
    if match is None:
        return 1
    if match.re is _KOREAN_AFTER:
        return _KOREAN[match.group(1)]
    return _multiplier(match.group(1)) or 1


def written_numbers(text: str, unit: str | None = None) -> list[WrittenNumber]:
    """Each number of `text`, read as given (callers normalise it), with the amount that the number and the
    multiplier directly after it give: a word or sign of _UNIT_AFTER (`%`, `million`, `억원`), else a Korean multiplier
    of _KOREAN_AFTER (`10만주`, `0.5조`), and none for a number directly after 제 (제3조, an article). A number with no
    multiplier of its own, not after 제, and neither a year nor a mark joined to letters (Q3, FY2026), that a range
    connector (`to`, `-`, `–`, `—`, `~`, `〜`, `至`, `到`, or `and` after `between`) joins to a number with its own
    multiplier, borrows that multiplier: `$1.595 to $1.605 billion`. The amount is divided by the multiplier of `unit`
    (1 when the unit names none). significant_numbers and the intake rule on a claim's `value` (engine/semantic.py)
    both read numbers here, so the two cannot drift apart."""
    divisor = Decimal(_multiplier(normalize(unit)) or 1) if unit else Decimal(1)
    matches = list(_NUMBER.finditer(text))
    articles = [match.start() > 0 and text[match.start() - 1] == ARTICLE for match in matches]
    own = [None if article else (_UNIT_AFTER.match(text, match.end()) or _KOREAN_AFTER.match(text, match.end()))
           for match, article in zip(matches, articles)]
    found = []
    for index, match in enumerate(matches):
        borrowed = None
        # A year or a mark joined to letters is not a range end, as significant_numbers skips them (PR #141 review).
        if own[index] is None and not articles[index] and index + 1 < len(matches) and own[index + 1] is not None \
                and not _joined_to_letters(text, match.start(), match.end()) and not _bare_year(match.group(0), None):
            # Only the number directly before the connector borrows, and only the other end's own multiplier.
            gap = text[match.end():matches[index + 1].start()]
            between = _BETWEEN.search(text[:match.start()]) is not None
            if _RANGE.fullmatch(gap) or (between and _RANGE_AND.fullmatch(gap)):
                borrowed = own[index + 1]
        written = Decimal(match.group(0).replace(",", ""))
        factor = _factor(own[index] or borrowed)
        found.append(WrittenNumber(match.group(0), match.start(), match.end(), written, own[index],
                                   written * factor / divisor, borrowed))
    return found


def _borrowed_reading(fragment: str, text: str):
    """The (amount, precision) of a fragment's one number read with the multiplier it borrows where the fragment
    stands in `text`; None when it borrows none there; False when the fragment occurs more than once and the
    readings differ, so the program cannot decide."""
    wanted = normalize(fragment)
    if not wanted:
        return None
    numbers = written_numbers(text)
    readings, position = [], text.find(wanted)
    while position >= 0:
        inside = [n for n in numbers if position <= n.start and n.end <= position + len(wanted)]
        number = inside[0] if len(inside) == 1 else None
        readings.append((number.token.replace(",", ""), _factor(number.borrowed))
                        if number is not None and number.multiplier is None and number.borrowed is not None else None)
        position = text.find(wanted, position + 1)
    if not readings or all(reading is None for reading in readings):
        return None
    if len(set(readings)) > 1:
        return False
    # The token of the number inside the fragment gives the precision: $1.50 is read to 0.005, not as an earlier 1.5.
    token, factor = readings[0]
    decimals = len(token.split(".")[1]) if "." in token else 0
    return Decimal(token) * factor, Decimal(5) * Decimal(10) ** (-(decimals + 1)) * factor


def significant_numbers(claim_text: str) -> list[str]:
    """Numbers in a claim that a figure must cover: with a decimal point, with a unit, a percentage, or an integer of
    three digits or more. Years from 1900 to 2100, dates and marks joined to letters (H1, FY2025, Q3) do not count."""
    text = _DATES.sub(lambda m: " " * len(m.group(0)), normalize(claim_text))
    found = []
    for number in written_numbers(text):
        token, start, end, unit = number.token, number.start, number.end, number.multiplier
        if _joined_to_letters(text, start, end):
            continue
        plain = token.replace(",", "")
        if "." in plain or unit or len(plain) >= 3:
            if _bare_year(token, unit):
                continue
            found.append(token + ("%" if unit and unit.group(1) == "%" else ""))
    return found


def _value(amount: Decimal) -> int | float:
    return int(amount) if amount == amount.to_integral_value() else float(amount)


def check_figures(claim_text: str, quote: str, source_text: str, figures, value=None,
                  unit: str | None = None) -> tuple[bool, list[dict]]:
    """True with the checked pairs when every pair agrees, every significant number of the claim is covered and
    `value` (when given) equals one of the pairs; otherwise False."""
    claim_norm, quote_norm, source_norm = normalize(claim_text), normalize(quote or ""), normalize(source_text)
    position = source_norm.find(quote_norm) if quote_norm else -1
    if position < 0 or not isinstance(figures, list):
        return False, []
    window = source_norm[max(0, position - UNIT_WINDOW):position + len(quote_norm)]
    checked, amounts = [], []
    for pair in figures:
        if not isinstance(pair, dict):
            return False, []
        claim_part, source_part, unit_part = pair.get("claim"), pair.get("source"), pair.get("unit")
        if not isinstance(claim_part, str) or not isinstance(source_part, str):
            return False, []
        if normalize(claim_part) not in claim_norm or normalize(source_part) not in quote_norm:
            return False, []
        if unit_part is not None and (not isinstance(unit_part, str) or normalize(unit_part) not in window):
            return False, []
        # A fragment whose number takes the multiplier written after a range's other end reads with it, where the
        # fragment stands (the claim text, the quote); it then names a unit, so a table header does not apply.
        claim_borrowed, source_borrowed = _borrowed_reading(claim_part, claim_norm), \
            _borrowed_reading(source_part, quote_norm)
        if claim_borrowed is False or source_borrowed is False:
            return False, []
        claimed = claim_borrowed or parse_amount(claim_part)
        source_amount = source_borrowed or parse_amount(source_part, unit_part)
        if claimed is None or source_amount is None:
            return False, []
        if abs(abs(claimed[0]) - abs(source_amount[0])) > claimed[1]:
            return False, []
        checked.append({"claim": claim_part, "source": source_part, "unit": unit_part,
                        "claim_value": _value(abs(claimed[0])), "source_value": _value(abs(source_amount[0]))})
        amounts.append((abs(claimed[0]), abs(source_amount[0])))
    covered = " ".join(normalize(pair["claim"]) for pair in checked)
    if any(number.rstrip("%") not in covered for number in significant_numbers(claim_text)):
        return False, []
    if value is not None:
        try:
            raw = Decimal(str(value))
        except InvalidOperation:
            return False, []
        decimals = -raw.as_tuple().exponent if raw.as_tuple().exponent < 0 else 0
        factor = _multiplier(unit or "") or 1
        candidates = [(abs(raw), Decimal(5) * Decimal(10) ** (-(decimals + 1)))]
        candidates.append((abs(raw) * factor, candidates[0][1] * factor))
        if not any(abs(want - got) <= tolerance for want, tolerance in candidates for pair in amounts for got in pair):
            return False, []
    return True, checked


def verdict(claim: dict, item: dict, source_text: str) -> dict:
    """The model's answer for one claim, changed into what may be written to the record.

    `supported` needs the quote in the source and the figures to agree; `contradicted` needs the quote in the source
    and the correct figures to agree with it. Anything else becomes not_found, with the reason in `note`, and no text
    from outside the source is kept."""
    result = {"index": item.get("index"), "verdict": "not_found", "timing": item.get("timing"), "quote": None,
              "figures": [], "correct": None, "note": item.get("note")}
    answer = item.get("verdict")
    if answer not in ("supported", "contradicted"):
        return result
    quote = item.get("quote")
    if not quote_in(quote, source_text):
        result["note"] = NOT_IN_SOURCE
        return result
    if answer == "supported":
        ok, checked = check_figures(claim.get("text", ""), quote, source_text, item.get("figures") or [],
                                    claim.get("value"), claim.get("unit"))
        if not ok:
            return {**result, "quote": quote, "note": UNCHECKED}
        return {**result, "verdict": "supported", "quote": quote, "figures": checked}
    correct = item.get("correct")
    if not isinstance(correct, dict) or not isinstance(correct.get("text"), str) or not correct["text"].strip():
        return {**result, "quote": quote, "note": UNCHECKED}
    ok, checked = check_figures(correct["text"], quote, source_text, correct.get("figures") or [])
    if not ok:
        return {**result, "quote": quote, "note": UNCHECKED}
    return {**result, "verdict": "contradicted", "quote": quote, "correct": {"text": correct["text"], "figures": checked}}
