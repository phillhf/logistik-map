# Änderungen

## [0.4.0] - 2026-11-16

Korrekturen und Härtung nach der Durchsicht von 0.3.0.

- **Update-Funktion**: Die geplante Aufgabe wird jetzt als XML angelegt. Mit dem bisherigen
  Datumsformat wäre sie auf deutschem Windows gescheitert.
- **Rückgängig**: Ein Klick im Editor (Flur teilen, Punkt, Wegstück) ist ein einziger Schritt.
  Abgelehnte Änderungen hinterlassen keine leeren Schritte mehr. Der Maßstab wird nur noch beim
  Ausrichten mit zurückgenommen. Änderungen anderer Personen lassen sich nicht mehr aus Versehen
  zurücknehmen.
- **Gleichzeitiges Bearbeiten**: Ändert jemand anderes dasselbe Stockwerk, lädt der Editor neu
  und sagt, von wem die Änderung kommt.
- **Anmeldung**: Eine Adresse wird erst nach 30 Fehlversuchen gesperrt (Terminalserver,
  Citrix), ein Benutzername weiter nach 5. Sitzungen enden nach 12 Stunden ohne Nutzung,
  AD-Benutzer müssen sich spätestens nach 12 Stunden neu anmelden. Beides ist einstellbar.
- **Sicherung**: Täglich wird nur die Datenbank gesichert, wöchentlich zusätzlich alle
  PDF-Pläne. Manuelle Sicherungen werden nicht mehr automatisch gelöscht. Beim Einspielen einer
  Sicherung ohne Pläne bleiben die vorhandenen Pläne erhalten.
- **Änderungsprotokoll** mit einstellbarer Aufbewahrungsfrist (Standard 365 Tage).
- **HTTPS**: Die Verknüpfung im Startmenü zeigt nach dem Umstellen auf `https://`.
- **Simulation**: Steht die Aufzugkabine schon auf dem Stockwerk, entfällt die Wartezeit auf
  sie. Späte Lieferungen des Vortags laufen über Mitternacht weiter.
- **Szenarien**: Wegstücke sperren und Kapazitäten von Rampen ändern.
- **Excel-Import** meldet „übernommen“ nur noch, wenn wirklich übernommen wurde.
- **Setup**: Es enthält `THIRD_PARTY_LICENSES.txt` mit den Lizenzen aller mitgelieferten
  Bestandteile. WinSW wird beim Bauen gegen eine feste Prüfsumme geprüft. Unnötige Bibliotheken
  sind herausgenommen, das Setup ist 8 MB kleiner.
- **Oberflächentests im Browser** (Playwright) für Editor, Ausrichten, Import, Sicherung,
  Ablauf und Auswertung, auf GitHub als eigener Testlauf.
- README auf Englisch mit Screenshots, die deutsche Fassung liegt in `README.de.md`.

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
