# Änderungen

## [0.3.0] - 2026-11-15

Fit für den Echtbetrieb und für Planungsfragen.

- **Sicherung**: Datenbank und PDF-Pläne als ZIP herunterladen und wieder einspielen. Täglich
  automatisch, die Zahl der aufbewahrten Sicherungen ist einstellbar. Auch per Befehlszeile:
  `sicherung` und `wiederherstellen`.
- **Update-Funktion**: prüft GitHub auf neue Versionen und installiert sie auf Knopfdruck. Das
  Setup wird mit SHA-256 geprüft.
- **HTTPS** mit eigenem Zertifikat (PEM) und Neustart aus der Oberfläche.
- **Anmeldung über Active Directory** (LDAP): Rollen kommen aus AD-Gruppen, lokale Benutzer
  funktionieren weiter. Mit Testanmeldung in den Einstellungen.
- **Rollen und Rechte**: neues Recht „Lieferungen & Szenarien“, mitgelieferte Rolle „Planer“,
  eigene Rollen mit frei wählbaren Rechten.
- **Änderungsprotokoll**: wer hat wann was angelegt, geändert oder gelöscht.
- **Szenarien** („Was wäre wenn“): Lieferzeiten verschieben, Aufzüge außer Betrieb nehmen oder
  größer machen, mehr Personal. Vergleich mit dem Ist-Zustand in Auswertung, Woche und Ablauf.
  Geänderte Lieferungen lassen sich übernehmen.
- **Schichten**: Anzahl der Fahrzeuge bzw. Personen je Uhrzeit und Wochentag, auch über
  Mitternacht.
- **Excel**: Lieferungen exportieren und importieren (auch CSV), mit Prüfung vor der Übernahme.
  Die Auswertung lässt sich als Excel-Datei exportieren.
- **Karte als PDF** mit Plan, Wegen, Warenflüssen im Zeitfenster und Legende. Dazu eine
  Druckansicht der Auswertung.
- **Wochenansicht** als Heatmap: Fahrten und längste Wartezeit je Stunde und Wochentag.
- **Editor**: Rückgängig (Strg+Z), Raumecken verschieben, einfügen und löschen. Das Werkzeug
  „Ausrichten“ schiebt Wege, Punkte und Räume nach einem neuen Planstand an die richtige Stelle,
  der Maßstab wird angepasst.
- **Große Pläne** werden auf mehrere Prozesse verteilt aufbereitet. `plan-test` schätzt die Dauer
  vorab.
- **Englisch** als zweite Sprache. Jede Person kann ihre Sprache im Menü wählen.

## [0.2.0] - 2026-11-15

Alle Bausteine aus dem Konzept sind jetzt drin.

- **Karteneditor** im Modus „Bearbeiten“: Bereiche und Räume (Rechteck oder Vieleck), Start-, Ziel- und
  Übergangspunkte, Aufzüge und Treppen, Wegenetz entlang der Flure. Neue Punkte rasten an Wege an,
  Linien werden waagerecht und senkrecht ausgerichtet. Punkte lassen sich verschieben.
- **Wegsuche** über Stockwerke und Gebäudeteile: schnellster Weg je Transportart, Sperren je
  Wegstück, Aufzüge nur für bestimmte Transportarten, Zwischenstationen.
- **Stammdaten**: Transportarten (Tempo, Lade- und Entladezeit, Wagen je Fahrt, Anzahl, Aufzug
  allein reservieren wie FTS), Wagentypen mit Platzbedarf, Aufzüge mit Plätzen, Fahr-, Tür-,
  Warte- und Räumzeit.
- **Lieferungen** mit Uhrzeit, Ladung, „spätestens am Ziel“, Regeln (Wochentage, Feiertage,
  Zeitraum, Ausnahmen, Zusatztage) und Rückweg (leer, beladen, später, keiner).
- **Simulation** eines Tages: Fahrzeuge, Aufzüge, Engstellen und Rampen mit begrenzter
  Kapazität, Wartezeiten und Verspätungen.
- **Ablauf auf der Karte**: Zeitschieber und Abspielen, Fahrzeuge und Warteschlangen auf dem
  Plan, Warenflüsse nach Menge, Filter nach Startpunkt, Transportart, Richtung und Lieferung.
- **Auswertung**: Kennzahlen, Engpässe mit Tipps, Auslastung im Tagesverlauf, alle Fahrten.

## [0.1.0] - 2026-11-15

Erste Version: das Grundgerüst.

- Gebäudeteile und Stockwerke anlegen.
- PDF-Pläne hochladen, auch sehr große. Jede Seite lässt sich einem Stockwerk zuweisen und wird
  als zoombare Karte aufbereitet.
- Maßstab je Stockwerk über zwei Punkte mit bekanntem Abstand festlegen, mit Maßstabsleiste
  und Messwerkzeug.
- Benutzer und Rollen (Administrator, Betrachter) mit Anmeldung.
- Bundesland wählen. Die Feiertage werden berechnet, eigene Sondertage lassen sich eintragen.
- Windows-Installer mit Port-Auswahl, Firewall-Freigabe und Windows-Dienst.
