"""Hilfe: beide Sprachen haben dieselben Kapitel, alle Verweise führen auf ein vorhandenes Ziel."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "logistikmap" / "static"
SPRACHEN = ("de", "en")


class _Leser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.kapitel: list[str] = []
        self.links: list[str] = []
        self.offen: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
            if tag == "section":
                self.kapitel.append(a["id"])
        if tag == "a" and a.get("href", "").startswith("#/hilfe/"):
            self.links.append(a["href"][len("#/hilfe/"):])
        if tag in ("section", "table", "ol", "ul", "div"):
            self.offen.append(tag)

    def handle_endtag(self, tag):
        if tag in ("section", "table", "ol", "ul", "div"):
            assert self.offen and self.offen[-1] == tag, f"</{tag}> passt nicht zu {self.offen[-1:]}"
            self.offen.pop()


def _lesen(sprache: str) -> _Leser:
    leser = _Leser()
    leser.feed((STATIC / "hilfe" / f"{sprache}.html").read_text(encoding="utf-8"))
    assert not leser.offen, f"nicht geschlossen: {leser.offen}"
    return leser


@pytest.mark.parametrize("sprache", SPRACHEN)
def test_verweise_haben_ziel(sprache):
    h = _lesen(sprache)
    assert len(h.ids) == len(set(h.ids)), "doppelte id"
    assert h.kapitel, "keine Kapitel"
    assert not [z for z in h.links if z not in h.ids]


def test_sprachen_haben_dieselben_kapitel():
    de, en = _lesen("de"), _lesen("en")
    assert de.ids == en.ids


def test_fragezeichen_findet_kapitel():
    quelltext = (STATIC / "js" / "hilfe.js").read_text(encoding="utf-8")
    block = re.search(r"KAPITEL_JE_SEITE = \{(.*?)\};", quelltext, re.S).group(1)
    ziele = re.findall(r':\s*"([a-z0-9-]+)"', block)
    ids = set(_lesen("de").ids)
    assert ziele and not [z for z in ziele if z not in ids]


def test_hilfe_wird_ausgeliefert(client):
    for sprache in SPRACHEN:
        r = client.get(f"/hilfe/{sprache}.html")
        assert r.status_code == 200
        assert 'id="lieferungen"' in r.text
