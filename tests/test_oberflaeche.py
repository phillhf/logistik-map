"""Statische Prüfungen der Oberfläche: Jeder Text-Schlüssel im JavaScript steht in de.json."""

import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "logistikmap" / "static"


def _hat(daten: dict, schluessel: str) -> bool:
    o = daten
    for teil in schluessel.split("."):
        if not isinstance(o, dict) or teil not in o:
            return False
        o = o[teil]
    return True


def test_alle_texte_vorhanden():
    de = json.loads((STATIC / "i18n" / "de.json").read_text(encoding="utf-8"))
    fehlt = []
    for datei in (STATIC / "js").glob("*.js"):
        quelltext = datei.read_text(encoding="utf-8")
        for k in re.findall(r'\bt\(\s*"([a-z0-9_.]+)"', quelltext):
            if not _hat(de, k):
                fehlt.append(f"{datei.name}: {k}")
        # dynamische Schlüssel wie t(`knoten.art.${x}`): zumindest der Abschnitt muss existieren
        for k in re.findall(r"\bt\(\s*`([a-z0-9_.]+)\.\$\{", quelltext):
            if not _hat(de, k):
                fehlt.append(f"{datei.name}: {k}.*")
    assert not fehlt, "Fehlende Texte:\n" + "\n".join(sorted(set(fehlt)))


def test_feiertage_haben_namen():
    from logistikmap.feiertage import BUNDESLAENDER, feiertage

    de = json.loads((STATIC / "i18n" / "de.json").read_text(encoding="utf-8"))
    for bl in BUNDESLAENDER:
        for _, k in feiertage(2026, bl):
            assert k in de["feiertag"], k


def _schluessel(daten: dict, praefix: str = "") -> set[str]:
    ergebnis = set()
    for k, v in daten.items():
        if isinstance(v, dict):
            ergebnis |= _schluessel(v, f"{praefix}{k}.")
        else:
            ergebnis.add(f"{praefix}{k}")
    return ergebnis


def test_alle_sprachen_vollstaendig():
    de = json.loads((STATIC / "i18n" / "de.json").read_text(encoding="utf-8"))
    for datei in (STATIC / "i18n").glob("*.json"):
        andere = json.loads(datei.read_text(encoding="utf-8"))
        fehlt = _schluessel(de) - _schluessel(andere)
        zuviel = _schluessel(andere) - _schluessel(de)
        assert not fehlt and not zuviel, f"{datei.name}: fehlt {sorted(fehlt)}, zu viel {sorted(zuviel)}"
        # Platzhalter müssen übereinstimmen
        def wert(d, k):
            for teil in k.split("."):
                d = d[teil]
            return d
        for k in _schluessel(de):
            a, b = wert(de, k), wert(andere, k)
            if isinstance(a, str):
                assert set(re.findall(r"\{(\w+)\}", a)) == set(re.findall(r"\{(\w+)\}", b)), f"{datei.name}: Platzhalter in {k}"
