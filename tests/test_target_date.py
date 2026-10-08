from datetime import date

import engine.timeutil as timeutil


def test_target_date_adds_calendar_months():
    assert timeutil.target_date("2026-10-02T03:00:00Z", 18) == "2028-04-02"
    assert timeutil.target_date("2026-10-02T03:00:00Z", 120) == "2036-10-02"
    assert timeutil.add_months(date(2026, 11, 15), 2) == date(2027, 1, 15)


def test_a_missing_day_becomes_the_last_day_of_the_month():
    assert timeutil.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert timeutil.add_months(date(2027, 11, 30), 3) == date(2028, 2, 29)
    assert timeutil.add_months(date(2026, 3, 31), 1) == date(2026, 4, 30)


def test_the_publication_date_is_the_utc_date():
    assert timeutil.target_date("2026-10-01T23:30:00Z", 1) == "2026-11-01"
