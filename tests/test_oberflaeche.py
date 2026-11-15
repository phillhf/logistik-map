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
