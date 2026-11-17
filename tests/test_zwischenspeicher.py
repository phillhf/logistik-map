"""Skripte und Stile kommen unter einer Adresse mit Versionsnummer – sonst hält ein
vorgeschalteter Zwischenspeicher nach einem Update die alte Oberfläche fest."""

import re

from logistikmap import __version__


def test_startseite_verweist_auf_versionierte_dateien(client):
    for pfad in ("/", "/index.html", "/irgendwas-unbekanntes"):
        r = client.get(pfad)
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache"
        assert f'src="v/{__version__}/js/app.js"' in r.text
        assert f'href="v/{__version__}/style.css"' in r.text
        assert 'href="favicon.svg"' in r.text


def test_versionierte_dateien_werden_ausgeliefert(client):
    seite = client.get("/").text
    for adresse in re.findall(r'(?:href|src)="(v/[^"]+)"', seite):
        assert client.get("/" + adresse).status_code == 200, adresse
    # Module laden einander relativ – das landet ebenfalls unter der Versionsadresse
    assert client.get(f"/v/{__version__}/js/hilfe.js").status_code == 200


def test_api_antworten_werden_nicht_zwischengespeichert(admin):
    """Ohne Kopf legt Cloudflare .xlsx/.pdf ab und gibt sie an andere (auch Abgemeldete) weiter."""
    for pfad in ("/api/status", "/api/export/lieferungen.xlsx"):
        r = admin.get(pfad)
        assert r.status_code == 200
        assert "no-store" in r.headers["cache-control"]
        assert "private" in r.headers["cache-control"]


def test_dateiname_mit_umlauten(admin):
    r = admin.get("/api/export/lieferungen.xlsx")
    kopf = r.headers["content-disposition"]
    assert kopf.startswith("attachment; filename=\"lieferungen-") and "filename*=UTF-8''" in kopf
