"""Verbatim quotes and figures, checked by program (design 22.9.1; plan 9, items 5 and 7).

This module is the one implementation of both checks. A quote counts only when it appears in the fetched source
after both are normalised (NFKC, every kind of space made one space), so Korean and full-width text compare
correctly. A figure counts only when the model's pair of fragments, one from the claim and one from the quote, both
appear where they should and convert to amounts that agree at the precision of the claim's own wording. Whatever
the program cannot decide makes the claim not_found, never supported.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ..fetch import normalize

MIN_QUOTE = 8
UNIT_WINDOW = 3000  # characters before the quote in which a unit such as a table header may stand
NOT_IN_SOURCE = "quote not in the source"
UNCHECKED = "a figure could not be checked"

# Multipliers, longest first so that 十亿 is not read as 亿 and 백만원 not as 원.
_WORDS = [("trillion", 10**12), ("billion", 10**9), ("million", 10**6), ("thousand", 10**3),
          ("조원", 10**12), ("억원", 10**8), ("백만원", 10**6), ("천만원", 10**7), ("만원", 10**4), ("천원", 10**3),
          ("원", 1), ("十亿", 10**9), ("千万", 10**7), ("百万", 10**6), ("亿", 10**8), ("万", 10**4)]
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_DATES = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{4}年\d{1,2}月(?:\d{1,2}日)?|\d{4}[./]\d{1,2}[./]\d{1,2}")
_UNIT_AFTER = re.compile(r"\s*(%|trillion|billion|million|thousand|조원|억원|백만원|천만원|만원|천원|원|十亿|千万|百万|亿|万)",
                         re.IGNORECASE)


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
    """(amount, precision) of a fragment such as `$382.5 million`, `(7,486,679,200)` or `7.486679十亿韩元`; None when
    it holds no single number or cannot be read. The precision is half a unit of the fragment's last digit. `unit`,
    for example a table header `(단위 : 천원)` or a claim's `USD million`, applies when the fragment names no unit."""
    if not isinstance(fragment, str):
        return None
    text = normalize(fragment).replace("−", "-")
    numbers = _NUMBER.findall(text)
    if len(numbers) != 1:
        return None
    digits = numbers[0].replace(",", "")
    try:
        amount = Decimal(digits)
    except InvalidOperation:
        return None
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    rest = text.replace(numbers[0], " ", 1)
    factor = _multiplier(rest)
    if factor is None and "%" not in rest and unit:
        factor = _multiplier(normalize(unit))
        if factor is None:
            return None  # a unit that cannot be read
    factor = factor or 1
    precision = Decimal(5) * Decimal(10) ** (-(decimals + 1)) * factor
    return amount * factor, precision


def significant_numbers(claim_text: str) -> list[str]:
    """Numbers in a claim that a figure must cover: with a decimal point, with a unit, a percentage, or an integer of
    three digits or more. Years from 1900 to 2100, dates and marks joined to letters (H1, FY2025, Q3) do not count."""
    text = _DATES.sub(lambda m: " " * len(m.group(0)), normalize(claim_text))
    found = []
    for match in _NUMBER.finditer(text):
        token, start, end = match.group(0), match.start(), match.end()
        before = text[start - 1] if start else ""
        after = text[end] if end < len(text) else ""
        if (before.isascii() and before.isalpha()) or (after.isascii() and after.isalpha()):
            continue
        plain = token.replace(",", "")
        unit = _UNIT_AFTER.match(text, end)
        if "." in plain or unit or len(plain) >= 3:
            if "." not in plain and "," not in token and len(plain) == 4 and 1900 <= int(plain) <= 2100 and not unit:
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
        claimed, source_amount = parse_amount(claim_part), parse_amount(source_part, unit_part)
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
