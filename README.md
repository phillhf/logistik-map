# Logistik Map

Logistik Map zeigt Warenflüsse und Transportwege in großen Gebäuden, zum Beispiel im
Krankenhaus. Grundlage sind die Gebäudepläne als PDF: Stockwerke anlegen, Pläne hochladen,
Wege und Lieferungen einzeichnen und sehen, wo es eng wird.

> **Stand:** Version 0.1. Fertig sind Gebäude, Stockwerke, PDF-Pläne als zoombare Karte,
> der Maßstab, Benutzer und Rollen sowie die Feiertage je Bundesland. Was noch kommt,
> steht in [KONZEPT.md](KONZEPT.md).

## Installation (Windows-Server)

1. `LogistikMap-Setup-x.y.z.exe` aus den Releases herunterladen und als Administrator ausführen.
2. Port wählen (Standard 8470) und bei Bedarf die Firewall-Freigabe anhaken.
3. Nach der Installation öffnet sich der Browser. Dort legst du das Administrator-Konto an.

Logistik Map läuft dann als Windows-Dienst **LogistikMap** und ist im Netzwerk unter
`http://<Servername>:<Port>` erreichbar.

Die Daten liegen in `C:\ProgramData\Logistik Map` (Datenbank, PDF-Pläne, Kacheln, Protokolle,
`config.json`). Update und Deinstallation lassen sie unangetastet.

### Admin-Passwort vergessen

In einer Eingabeaufforderung mit Administratorrechten:

```
"C:\Program Files\Logistik Map\LogistikMap.exe" passwort admin
```

## Entwicklung

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m logistikmap --data data serve --port 8470
```

Das Setup baut `installer\build.ps1`. Dafür werden Inno Setup 6 und `gh` gebraucht.
Ein Tag `vX.Y.Z` baut über GitHub Actions das Setup und veröffentlicht es als Release.

### Aufbau

| Pfad | Inhalt |
|---|---|
| `logistikmap/server.py` | Webserver und JSON-Schnittstelle |
| `logistikmap/db.py` | SQLite-Datenbank mit Migrationen |
| `logistikmap/plaene.py` | PDF → Kartenkacheln (PyMuPDF) |
| `logistikmap/feiertage.py` | Feiertage je Bundesland |
| `logistikmap/static/` | Oberfläche (ohne Build-Schritt, Leaflet liegt bei) |
| `logistikmap/static/i18n/` | Texte der Oberfläche je Sprache |
| `installer/` | Inno-Setup-Skript, Windows-Dienst (WinSW), Build-Skript |

### Weitere Sprache hinzufügen

1. `logistikmap/static/i18n/de.json` kopieren, z. B. nach `en.json`, und übersetzen.
2. In `logistikmap/server.py` die Sprache in `SPRACHEN` eintragen.

## Lizenz

[GNU Affero General Public License v3.0](LICENSE). Leaflet steht unter der BSD-2-Clause-Lizenz
(`logistikmap/static/vendor/leaflet/LICENSE`), PyMuPDF unter der AGPL-3.0.
