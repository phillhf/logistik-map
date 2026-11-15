from datetime import date

import pytest

from logistikmap.feiertage import BUNDESLAENDER, feiertage, ist_feiertag, ostersonntag


@pytest.mark.parametrize(
    "jahr, erwartet",
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28)), (2038, date(2038, 4, 25))],
)
def test_ostern(jahr, erwartet):
    assert ostersonntag(jahr) == erwartet


def test_nrw_2026():
    tage = {k: d for d, k in feiertage(2026, "NW")}
    assert tage == {
        "neujahr": date(2026, 1, 1),
        "karfreitag": date(2026, 4, 3),
        "ostermontag": date(2026, 4, 6),
        "tag_der_arbeit": date(2026, 5, 1),
        "christi_himmelfahrt": date(2026, 5, 14),
        "pfingstmontag": date(2026, 5, 25),
        "fronleichnam": date(2026, 6, 4),
        "tag_der_deutschen_einheit": date(2026, 10, 3),
        "allerheiligen": date(2026, 11, 1),
        "weihnachtstag_1": date(2026, 12, 25),
        "weihnachtstag_2": date(2026, 12, 26),
    }


def test_anzahl_je_land_2026():
    anzahl = {bl: len(feiertage(2026, bl)) for bl in BUNDESLAENDER}
    assert anzahl["NW"] == 11
    assert anzahl["BY"] == 12  # mit Heilige Drei Könige, Fronleichnam, Allerheiligen; Mariä Himmelfahrt nur örtlich
    assert anzahl["BE"] == 10  # mit Frauentag
    assert anzahl["SN"] == 11  # Reformationstag und Buß- und Bettag
    assert anzahl["HH"] == 10


def test_buss_und_bettag():
    assert ist_feiertag(date(2026, 11, 18), "SN")
    assert not ist_feiertag(date(2026, 11, 18), "NW")


def test_reformationstag_2017_ueberall():
    assert all(ist_feiertag(date(2017, 10, 31), bl) for bl in BUNDESLAENDER)
    assert not ist_feiertag(date(2016, 10, 31), "NW")


def test_unbekanntes_land():
    with pytest.raises(ValueError):
        feiertage(2026, "XX")
