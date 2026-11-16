"""SQLite-Datenbank mit fortlaufenden Migrationen.

Neue Tabellen oder Spalten immer als neuen Eintrag in MIGRATIONEN anhängen,
bestehende Einträge nie ändern – installierte Datenbanken haben sie schon.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

# Rechte, die eine Rolle haben kann. Neue Rechte hier ergänzen.
RECHTE = ("ansehen", "lieferungen", "bearbeiten", "verwalten")

MIGRATIONEN: list[str] = [
    # 1 – Grundgerüst: Einstellungen, Benutzer, Rollen, Gebäude, Stockwerke, Pläne
    """
    CREATE TABLE einstellungen (
        schluessel TEXT PRIMARY KEY,
        wert       TEXT NOT NULL
    );
    CREATE TABLE rollen (
        id         INTEGER PRIMARY KEY,
        schluessel TEXT NOT NULL UNIQUE,
        name       TEXT NOT NULL,
        rechte     TEXT NOT NULL,
        system     INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE benutzer (
        id             INTEGER PRIMARY KEY,
        benutzername   TEXT NOT NULL UNIQUE COLLATE NOCASE,
        anzeigename    TEXT NOT NULL,
        passwort_hash  TEXT NOT NULL,
        rolle_id       INTEGER NOT NULL REFERENCES rollen(id),
        aktiv          INTEGER NOT NULL DEFAULT 1,
        sprache        TEXT,
        erstellt       TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE sitzungen (
        token_hash  TEXT PRIMARY KEY,
        benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
        erstellt    TEXT NOT NULL DEFAULT (datetime('now')),
        zuletzt     TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE sondertage (
        id     INTEGER PRIMARY KEY,
        datum  TEXT NOT NULL,
        name   TEXT NOT NULL
    );
    CREATE TABLE dokumente (
        id              INTEGER PRIMARY KEY,
        dateiname       TEXT NOT NULL,
        groesse         INTEGER NOT NULL,
        seiten          TEXT NOT NULL,
        hochgeladen     TEXT NOT NULL DEFAULT (datetime('now')),
        hochgeladen_von INTEGER REFERENCES benutzer(id) ON DELETE SET NULL
    );
    CREATE TABLE plaene (
        id          INTEGER PRIMARY KEY,
        dokument_id INTEGER NOT NULL REFERENCES dokumente(id),
        seite       INTEGER NOT NULL,
        breite      REAL NOT NULL,
        hoehe       REAL NOT NULL,
        max_zoom    INTEGER NOT NULL,
        status      TEXT NOT NULL DEFAULT 'wartet',
        fortschritt REAL NOT NULL DEFAULT 0,
        fehler      TEXT,
        erstellt    TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE gebaeudeteile (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        kuerzel     TEXT NOT NULL DEFAULT '',
        reihenfolge INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE stockwerke (
        id              INTEGER PRIMARY KEY,
        gebaeudeteil_id INTEGER NOT NULL REFERENCES gebaeudeteile(id) ON DELETE CASCADE,
        name            TEXT NOT NULL,
        ebene           INTEGER NOT NULL DEFAULT 0,
        plan_id         INTEGER REFERENCES plaene(id) ON DELETE SET NULL,
        meter_pro_punkt REAL
    );
    """,
    # 2 – Flächen, Wegenetz, Stammdaten, Lieferungen
    """
    CREATE TABLE transportarten (
        id              INTEGER PRIMARY KEY,
        name            TEXT NOT NULL,
        farbe           TEXT NOT NULL DEFAULT '#1f5f8b',
        geschwindigkeit REAL NOT NULL DEFAULT 1.0,
        ladezeit        REAL NOT NULL DEFAULT 60,
        entladezeit     REAL NOT NULL DEFAULT 60,
        wagen_pro_fahrt INTEGER NOT NULL DEFAULT 1,
        anzahl          INTEGER NOT NULL DEFAULT 0,
        aufzug_exklusiv INTEGER NOT NULL DEFAULT 0,
        treppe          INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE wagentypen (
        id     INTEGER PRIMARY KEY,
        name   TEXT NOT NULL,
        plaetze REAL NOT NULL DEFAULT 1
    );
    CREATE TABLE aufzuege (
        id             INTEGER PRIMARY KEY,
        name           TEXT NOT NULL,
        art            TEXT NOT NULL DEFAULT 'aufzug',
        plaetze        REAL NOT NULL DEFAULT 2,
        fahrzeit_etage REAL NOT NULL DEFAULT 8,
        tuerzeit       REAL NOT NULL DEFAULT 10,
        raeumzeit      REAL NOT NULL DEFAULT 20,
        anfahrt        REAL NOT NULL DEFAULT 15,
        transportarten TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE flaechen (
        id           INTEGER PRIMARY KEY,
        stockwerk_id INTEGER NOT NULL REFERENCES stockwerke(id) ON DELETE CASCADE,
        parent_id    INTEGER REFERENCES flaechen(id) ON DELETE SET NULL,
        art          TEXT NOT NULL DEFAULT 'raum',
        name         TEXT NOT NULL,
        nummer       TEXT NOT NULL DEFAULT '',
        farbe        TEXT NOT NULL DEFAULT '',
        punkte       TEXT NOT NULL
    );
    CREATE TABLE knoten (
        id           INTEGER PRIMARY KEY,
        stockwerk_id INTEGER NOT NULL REFERENCES stockwerke(id) ON DELETE CASCADE,
        x            REAL NOT NULL,
        y            REAL NOT NULL,
        art          TEXT NOT NULL DEFAULT 'weg',
        name         TEXT NOT NULL DEFAULT '',
        flaeche_id   INTEGER REFERENCES flaechen(id) ON DELETE SET NULL,
        aufzug_id    INTEGER REFERENCES aufzuege(id) ON DELETE SET NULL,
        kapazitaet   INTEGER
    );
    CREATE TABLE kanten (
        id         INTEGER PRIMARY KEY,
        von        INTEGER NOT NULL REFERENCES knoten(id) ON DELETE CASCADE,
        nach       INTEGER NOT NULL REFERENCES knoten(id) ON DELETE CASCADE,
        laenge_m   REAL,
        kapazitaet INTEGER,
        gesperrt   TEXT NOT NULL DEFAULT '[]',
        name       TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE lieferungen (
        id              INTEGER PRIMARY KEY,
        name            TEXT NOT NULL,
        lieferant       TEXT NOT NULL DEFAULT '',
        richtung        TEXT NOT NULL DEFAULT 'versorgung',
        transportart_id INTEGER NOT NULL REFERENCES transportarten(id) ON DELETE RESTRICT,
        start_id        INTEGER NOT NULL REFERENCES knoten(id) ON DELETE RESTRICT,
        ziel_id         INTEGER NOT NULL REFERENCES knoten(id) ON DELETE RESTRICT,
        uhrzeit         TEXT NOT NULL,
        spaetestens     TEXT,
        ladung          TEXT NOT NULL DEFAULT '[]',
        via             TEXT NOT NULL DEFAULT '[]',
        regel           TEXT NOT NULL,
        rueckweg        TEXT NOT NULL DEFAULT '{"modus": "keiner"}',
        aktiv           INTEGER NOT NULL DEFAULT 1,
        notiz           TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX knoten_stockwerk ON knoten(stockwerk_id);
    CREATE INDEX flaechen_stockwerk ON flaechen(stockwerk_id);
    CREATE INDEX kanten_von ON kanten(von);
    CREATE INDEX kanten_nach ON kanten(nach);
    INSERT INTO transportarten (name, farbe, geschwindigkeit, ladezeit, entladezeit, wagen_pro_fahrt, anzahl, aufzug_exklusiv, treppe)
        VALUES ('FTS', '#7048e8', 0.8, 60, 60, 1, 4, 1, 0);
    INSERT INTO transportarten (name, farbe, geschwindigkeit, ladezeit, entladezeit, wagen_pro_fahrt, anzahl, aufzug_exklusiv, treppe)
        VALUES ('Materialtransportdienst', '#e8590c', 1.0, 90, 90, 1, 0, 0, 0);
    INSERT INTO wagentypen (name, plaetze) VALUES ('Wäschewagen', 1);
    INSERT INTO wagentypen (name, plaetze) VALUES ('Rollcontainer', 1);
    INSERT INTO wagentypen (name, plaetze) VALUES ('Speisenwagen', 1);
    INSERT INTO wagentypen (name, plaetze) VALUES ('Palette', 2)
    """,
    # 3 – Rechte „lieferungen“, Rolle Planer, Protokoll, Rückgängig, Szenarien, Schichten, AD-Benutzer
    """
    UPDATE rollen SET rechte = '["ansehen", "lieferungen", "bearbeiten", "verwalten"]' WHERE schluessel = 'admin';
    INSERT OR IGNORE INTO rollen (schluessel, name, rechte, system) VALUES ('planer', 'Planer', '["ansehen", "lieferungen"]', 1);
    ALTER TABLE benutzer ADD COLUMN quelle TEXT NOT NULL DEFAULT 'lokal';
    ALTER TABLE transportarten ADD COLUMN schichten TEXT NOT NULL DEFAULT '[]';
    CREATE TABLE protokoll (
        id          INTEGER PRIMARY KEY,
        zeit        TEXT NOT NULL DEFAULT (datetime('now')),
        benutzer    TEXT NOT NULL,
        aktion      TEXT NOT NULL,
        objekt      TEXT NOT NULL,
        objekt_id   INTEGER,
        bezeichnung TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX protokoll_zeit ON protokoll(zeit);
    CREATE TABLE netz_verlauf (
        id           INTEGER PRIMARY KEY,
        stockwerk_id INTEGER NOT NULL REFERENCES stockwerke(id) ON DELETE CASCADE,
        zeit         TEXT NOT NULL DEFAULT (datetime('now')),
        benutzer     TEXT NOT NULL DEFAULT '',
        beschreibung TEXT NOT NULL DEFAULT '',
        daten        TEXT NOT NULL
    );
    CREATE INDEX netz_verlauf_stockwerk ON netz_verlauf(stockwerk_id, id);
    CREATE TABLE szenarien (
        id           INTEGER PRIMARY KEY,
        name         TEXT NOT NULL,
        beschreibung TEXT NOT NULL DEFAULT '',
        aenderungen  TEXT NOT NULL DEFAULT '{}',
        erstellt     TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # 4 – Rückgängig-Schritte zusammenfassen
    """
    ALTER TABLE netz_verlauf ADD COLUMN gruppe TEXT
    """,
    # 5 – Tore (Entladezeit je Ladeeinheit), Wagentyp Bett für interne Transporte
    """
    ALTER TABLE knoten ADD COLUMN minuten_je_einheit REAL;
    INSERT INTO wagentypen (name, plaetze) SELECT 'Bett', 2 WHERE NOT EXISTS (SELECT 1 FROM wagentypen WHERE name = 'Bett')
    """,
    # 6 – „Nein“ bei „Lücken prüfen“: diese Stelle nicht mehr melden
    """
    ALTER TABLE knoten ADD COLUMN ohne_hinweis INTEGER NOT NULL DEFAULT 0
    """,
]

STANDARD_ROLLEN = [
    ("admin", "Administrator", ["ansehen", "lieferungen", "bearbeiten", "verwalten"]),
    ("planer", "Planer", ["ansehen", "lieferungen"]),
    ("betrachter", "Betrachter", ["ansehen"]),
]

STANDARD_EINSTELLUNGEN = {
    "bundesland": "NW",
    "sprache": "de",
}


class Datenbank:
    """Eine Verbindung für den ganzen Prozess, Zugriffe über eine Sperre serialisiert.

    Für ein Werkzeug mit einer Handvoll gleichzeitiger Nutzer ist das schnell genug
    und vermeidet "database is locked" zwischen Webanfragen und Kachel-Erzeugung.
    """

    def __init__(self, pfad: Path):
        self.pfad = Path(pfad)
        self._sperre = threading.RLock()
        self._verbinden()

    def _verbinden(self) -> None:
        self._con = sqlite3.connect(self.pfad, check_same_thread=False, isolation_level=None)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA foreign_keys = ON")
        self._con.execute("PRAGMA journal_mode = WAL")
        self._migrieren()

    def sichern_nach(self, ziel: Path) -> None:
        """Konsistente Kopie der laufenden Datenbank (SQLite-Backup-API)."""
        with self._sperre:
            ziel_con = sqlite3.connect(ziel)
            try:
                self._con.backup(ziel_con)
            finally:
                ziel_con.close()

    def ersetzen_durch(self, quelle: Path) -> None:
        """Ersetzt die Datenbankdatei (Wiederherstellung) und öffnet sie neu, inklusive Migration."""
        import shutil

        with self._sperre:
            self._con.close()
            for endung in ("-wal", "-shm"):
                Path(str(self.pfad) + endung).unlink(missing_ok=True)
            shutil.copyfile(quelle, self.pfad)
            self._verbinden()

    def _migrieren(self) -> None:
        with self._sperre:
            self._con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self._con.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._con.execute("INSERT INTO schema_version VALUES (0)")
                version = 0
            else:
                version = row[0]
            for nr, sql in enumerate(MIGRATIONEN, start=1):
                if nr <= version:
                    continue
                self._con.execute("BEGIN")
                try:
                    # einzeln ausführen: executescript() würde die Transaktion vorzeitig committen
                    for befehl in _sql_befehle(sql):
                        self._con.execute(befehl)
                    self._con.execute("UPDATE schema_version SET version = ?", (nr,))
                    self._con.execute("COMMIT")
                except Exception:
                    self._con.execute("ROLLBACK")
                    raise
            self._standarddaten()

    def _standarddaten(self) -> None:
        for schluessel, name, rechte in STANDARD_ROLLEN:
            self._con.execute(
                "INSERT OR IGNORE INTO rollen (schluessel, name, rechte, system) VALUES (?, ?, ?, 1)",
                (schluessel, name, json.dumps(rechte)),
            )
        for k, v in STANDARD_EINSTELLUNGEN.items():
            self._con.execute(
                "INSERT OR IGNORE INTO einstellungen (schluessel, wert) VALUES (?, ?)", (k, json.dumps(v))
            )

    # -- Zugriff -------------------------------------------------------------
    def eins(self, sql: str, params: tuple = ()) -> dict | None:
        with self._sperre:
            row = self._con.execute(sql, params).fetchone()
        return dict(row) if row else None

    def alle(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._sperre:
            return [dict(r) for r in self._con.execute(sql, params).fetchall()]

    def ausfuehren(self, sql: str, params: tuple = ()) -> int:
        """Führt einen Schreibbefehl aus und gibt lastrowid zurück."""
        with self._sperre:
            cur = self._con.execute(sql, params)
            return cur.lastrowid or 0

    def transaktion(self):
        return _Transaktion(self)

    # -- Einstellungen ---------------------------------------------------------
    def einstellung(self, schluessel: str, standard=None):
        row = self.eins("SELECT wert FROM einstellungen WHERE schluessel = ?", (schluessel,))
        return json.loads(row["wert"]) if row else standard

    def setze_einstellung(self, schluessel: str, wert) -> None:
        self.ausfuehren(
            "INSERT INTO einstellungen (schluessel, wert) VALUES (?, ?) "
            "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
            (schluessel, json.dumps(wert)),
        )

    def schliessen(self) -> None:
        with self._sperre:
            self._con.close()


class _Transaktion:
    def __init__(self, db: Datenbank):
        self.db = db

    def __enter__(self) -> sqlite3.Connection:
        self.db._sperre.acquire()
        self.db._con.execute("BEGIN")
        return self.db._con

    def __exit__(self, typ, wert, tb) -> None:
        try:
            self.db._con.execute("ROLLBACK" if typ else "COMMIT")
        finally:
            self.db._sperre.release()


def _sql_befehle(sql: str) -> list[str]:
    return [b.strip() for b in sql.split(";") if b.strip()]
