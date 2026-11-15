"""Befehlszeile.

  LogistikMap.exe                         Server starten (Port aus config.json)
  LogistikMap.exe serve [--port N]        dasselbe
  LogistikMap.exe config --port N         Port in config.json speichern
  LogistikMap.exe passwort BENUTZER       Passwort neu setzen (Notfall, z. B. Admin-Passwort vergessen)
  LogistikMap.exe --selftest              Prüft, ob das Paket vollständig ist
  LogistikMap.exe --version

Überall gilt: --data ORDNER wählt einen anderen Datenordner.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import logging.handlers
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .config import Pfade, lade_konfiguration, speichere_konfiguration, standard_datenordner, static_ordner


def _logging(pfade: Pfade) -> None:
    pfade.logs.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    datei = logging.handlers.RotatingFileHandler(pfade.logs / "logistikmap.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    datei.setFormatter(fmt)
    konsole = logging.StreamHandler()
    konsole.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(datei)
    root.addHandler(konsole)


def befehl_serve(pfade: Pfade, port: int | None) -> int:
    import uvicorn

    from .server import erstelle_app

    _logging(pfade)
    k = lade_konfiguration(pfade)
    if port:
        k.port = port
    logging.getLogger(__name__).info("%s %s startet auf %s:%s, Daten in %s", APP_NAME, __version__, k.host, k.port, pfade.daten)
    app = erstelle_app(pfade)
    uvicorn.run(app, host=k.host, port=k.port, log_config=None, access_log=False)
    return 0


def befehl_config(pfade: Pfade, port: int | None) -> int:
    k = lade_konfiguration(pfade)
    if port is not None:
        if not 1 <= port <= 65535:
            print("Port muss zwischen 1 und 65535 liegen.", file=sys.stderr)
            return 2
        k.port = port
    pfade.anlegen()
    speichere_konfiguration(pfade, k)
    # Datenbank anlegen bzw. migrieren, damit Fehler schon bei der Installation auffallen
    from .db import Datenbank

    Datenbank(pfade.datenbank).schliessen()
    print(f"Konfiguration gespeichert: {pfade.config} (Port {k.port})")
    return 0


def befehl_passwort(pfade: Pfade, benutzer: str, passwort: str | None) -> int:
    from . import auth
    from .db import Datenbank

    db = Datenbank(pfade.datenbank)
    try:
        row = db.eins("SELECT id FROM benutzer WHERE benutzername = ?", (benutzer,))
        if row is None:
            print(f"Benutzer {benutzer!r} gibt es nicht.", file=sys.stderr)
            return 1
        if passwort is None:
            passwort = getpass.getpass("Neues Passwort: ")
            if getpass.getpass("Wiederholen: ") != passwort:
                print("Die Passwörter stimmen nicht überein.", file=sys.stderr)
                return 1
        if len(passwort) < auth.MIN_PASSWORT:
            print(f"Mindestens {auth.MIN_PASSWORT} Zeichen.", file=sys.stderr)
            return 1
        db.ausfuehren("UPDATE benutzer SET passwort_hash = ?, aktiv = 1 WHERE id = ?", (auth.passwort_hash(passwort), row["id"]))
        db.ausfuehren("DELETE FROM sitzungen WHERE benutzer_id = ?", (row["id"],))
        print(f"Passwort für {benutzer} gesetzt.")
        return 0
    finally:
        db.schliessen()


def selbsttest() -> int:
    import tempfile

    import pymupdf

    from .plaene import kacheln_erzeugen

    assert (static_ordner() / "index.html").is_file(), "static/index.html fehlt"
    assert (static_ordner() / "vendor" / "leaflet" / "leaflet.js").is_file(), "Leaflet fehlt"
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "t.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=400)
        page.draw_rect(pymupdf.Rect(50, 50, 550, 350))
        doc.save(pdf)
        doc.close()
        kacheln_erzeugen(pdf, 1, Path(tmp) / "k", 4)
        assert any((Path(tmp) / "k" / "4").iterdir()), "keine Kacheln erzeugt"
        from .server import erstelle_app

        erstelle_app(Pfade(Path(tmp) / "daten"), kacheln_starten=False).state.db.schliessen()
    print(f"{APP_NAME} {__version__}: Selbsttest bestanden")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="LogistikMap", description=f"{APP_NAME} {__version__}")
    p.add_argument("--data", type=Path, help="Datenordner")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="befehl")
    s = sub.add_parser("serve", help="Server starten")
    s.add_argument("--port", type=int)
    c = sub.add_parser("config", help="Konfiguration schreiben")
    c.add_argument("--port", type=int)
    pw = sub.add_parser("passwort", help="Passwort eines Benutzers neu setzen")
    pw.add_argument("benutzer")
    pw.add_argument("--passwort", help="ohne Angabe wird nachgefragt")
    args = p.parse_args(argv)

    if args.selftest:
        return selbsttest()
    pfade = Pfade(args.data or standard_datenordner())
    if args.befehl == "config":
        return befehl_config(pfade, args.port)
    if args.befehl == "passwort":
        return befehl_passwort(pfade, args.benutzer, args.passwort)
    return befehl_serve(pfade, getattr(args, "port", None))


if __name__ == "__main__":
    sys.exit(main())
