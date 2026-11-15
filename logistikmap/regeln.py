"""Wiederholungsregeln für Lieferungen.

Eine Regel ist ein JSON-Objekt:
  wochentage  Liste der ISO-Wochentage (1 = Montag … 7 = Sonntag), leer = an keinem Wochentag
  feiertage   "ausser" – nicht an Feiertagen (Standard)
              "auch"   – Feiertage zählen wie normale Tage (nur Wochentag entscheidet)
              "nur"    – ausschließlich an Feiertagen
  von, bis    optional, "JJJJ-MM-TT": nur in diesem Zeitraum
  ausnahmen   Liste von Daten, an denen die Lieferung entfällt
  zusatztage  Liste von Daten, an denen sie zusätzlich stattfindet

Als Feiertage gelten die gesetzlichen Feiertage des eingestellten Bundeslands und die eigenen Sondertage.
"""

from __future__ import annotations

from datetime import date

STANDARD_REGEL = {"wochentage": [1, 2, 3, 4, 5, 6, 7], "feiertage": "ausser", "von": None, "bis": None, "ausnahmen": [], "zusatztage": []}
FEIERTAG_MODI = ("ausser", "auch", "nur")


class RegelFehler(ValueError):
    pass


def normalisieren(regel: dict | None) -> dict:
    """Prüft eine Regel und füllt fehlende Felder mit Standardwerten."""
    r = dict(STANDARD_REGEL)
    r.update({k: v for k, v in (regel or {}).items() if k in STANDARD_REGEL})
    tage = r["wochentage"]
    if not isinstance(tage, list) or any(not isinstance(t, int) or not 1 <= t <= 7 for t in tage):
        raise RegelFehler("wochentage")
    r["wochentage"] = sorted(set(tage))
    if r["feiertage"] not in FEIERTAG_MODI:
        raise RegelFehler("feiertage")
    for k in ("von", "bis"):
        if r[k] in ("", None):
            r[k] = None
        else:
            _datum(r[k], k)
    if r["von"] and r["bis"] and r["von"] > r["bis"]:
        raise RegelFehler("zeitraum")
    for k in ("ausnahmen", "zusatztage"):
        if not isinstance(r[k], list):
            raise RegelFehler(k)
        r[k] = sorted({_datum(d, k).isoformat() for d in r[k]})
    return r


def _datum(text, feld: str) -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError as e:
        raise RegelFehler(feld) from e


def gilt_am(regel: dict, tag: date, ist_feiertag: bool) -> bool:
    iso = tag.isoformat()
    if iso in regel.get("ausnahmen", []):
        return False
    if iso in regel.get("zusatztage", []):
        return True
    if regel.get("von") and iso < regel["von"]:
        return False
    if regel.get("bis") and iso > regel["bis"]:
        return False
    modus = regel.get("feiertage", "ausser")
    if modus == "nur":
        return ist_feiertag
    if modus == "ausser" and ist_feiertag:
        return False
    return tag.isoweekday() in regel.get("wochentage", [])
