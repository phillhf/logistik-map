"""Gesetzliche Feiertage in Deutschland je Bundesland – ohne Internet berechnet.

Berücksichtigt nur landesweite Feiertage. Feiertage, die nur in einzelnen Gemeinden
gelten (z. B. Fronleichnam in Teilen Sachsens und Thüringens, Mariä Himmelfahrt in
Teilen Bayerns, Augsburger Friedensfest), lassen sich als Sondertage ergänzen.
"""

from __future__ import annotations

from datetime import date, timedelta

BUNDESLAENDER = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}


def ostersonntag(jahr: int) -> date:
    """Gaußsche Osterformel (anonymer gregorianischer Algorithmus)."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def _buss_und_bettag(jahr: int) -> date:
    # Mittwoch vor dem 23. November
    d = date(jahr, 11, 22)
    while d.weekday() != 2:
        d -= timedelta(days=1)
    return d


def feiertage(jahr: int, bundesland: str) -> list[tuple[date, str]]:
    """Liste (Datum, Schlüssel) sortiert nach Datum. Der Schlüssel wird in der Oberfläche übersetzt."""
    bl = bundesland.upper()
    if bl not in BUNDESLAENDER:
        raise ValueError(f"Unbekanntes Bundesland: {bundesland}")
    ostern = ostersonntag(jahr)
    tage: list[tuple[date, str]] = [
        (date(jahr, 1, 1), "neujahr"),
        (ostern - timedelta(days=2), "karfreitag"),
        (ostern + timedelta(days=1), "ostermontag"),
        (date(jahr, 5, 1), "tag_der_arbeit"),
        (ostern + timedelta(days=39), "christi_himmelfahrt"),
        (ostern + timedelta(days=50), "pfingstmontag"),
        (date(jahr, 10, 3), "tag_der_deutschen_einheit"),
        (date(jahr, 12, 25), "weihnachtstag_1"),
        (date(jahr, 12, 26), "weihnachtstag_2"),
    ]
    if bl in ("BW", "BY", "ST"):
        tage.append((date(jahr, 1, 6), "heilige_drei_koenige"))
    if (bl == "BE" and jahr >= 2019) or (bl == "MV" and jahr >= 2023):
        tage.append((date(jahr, 3, 8), "frauentag"))
    if bl == "BB":
        tage.append((ostern, "ostersonntag"))
        tage.append((ostern + timedelta(days=49), "pfingstsonntag"))
    if bl in ("BW", "BY", "HE", "NW", "RP", "SL"):
        tage.append((ostern + timedelta(days=60), "fronleichnam"))
    if bl == "SL":
        tage.append((date(jahr, 8, 15), "mariae_himmelfahrt"))
    if bl == "TH" and jahr >= 2019:
        tage.append((date(jahr, 9, 20), "weltkindertag"))
    reformation = {"BB", "MV", "SN", "ST", "TH"}
    if jahr >= 2018:
        reformation |= {"HB", "HH", "NI", "SH"}
    if bl in reformation or jahr == 2017:
        tage.append((date(jahr, 10, 31), "reformationstag"))
    if bl in ("BW", "BY", "NW", "RP", "SL"):
        tage.append((date(jahr, 11, 1), "allerheiligen"))
    if bl == "SN":
        tage.append((_buss_und_bettag(jahr), "buss_und_bettag"))
    return sorted(tage)


def ist_feiertag(tag: date, bundesland: str) -> bool:
    return any(d == tag for d, _ in feiertage(tag.year, bundesland))
