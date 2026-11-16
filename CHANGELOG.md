# Änderungen

## [0.6.2] - 2026-11-16

- **„Flure zeichnen“** statt „Weg zeichnen“, mit dem Hinweis, dass die Linien nur sagen, wo
  man fahren kann. Den besten Weg sucht das System selbst.
- **Kreuzungen entstehen von selbst:** Zieht eine neue Linie quer über einen vorhandenen Flur,
  werden beide an der Kreuzung verbunden. Vorher war das nur so, wenn man genau auf den Flur
  klickte.
- **Neues Werkzeug „Flur löschen“:** Ein Klick löscht das Flurstück bis zur nächsten Kreuzung
  bzw. zum nächsten Punkt. Übrig gebliebene Zwischenpunkte werden mit weggeräumt, benannte Punkte
  bleiben. „Rückgängig“ holt alles zurück.
- Der Hinweis zum aktiven Werkzeug steht jetzt unten auf der Karte und fängt keine Klicks mehr ab.

## [0.6.1] - 2026-11-16

- **Karte mit gedrückter rechter (oder mittlerer) Maustaste verschieben**, auch mitten beim
  Zeichnen einer Flurlinie.
- **Punkte automatisch an Flure hängen:** Führt eine neue Flurlinie dicht an einem Punkt vorbei,
  der noch an keinem Weg hängt, wird er gleich angeschlossen. Dazu der Knopf „Punkte anschließen“
  im Editor: Er hängt alle losen Punkte des Stockwerks an den nächsten Flur (bis 25 m) und nennt
  die, die zu weit weg sind. So können Punkte zuerst gesetzt und die Flure danach gezogen werden.

## [0.6.0] - 2026-11-16

- **Lieferung in einer Zeile:** Oben auf der Seite Lieferungen: „Um [08:00] kommen [5] [Paletten]
  von [Lager] nach [B25], danach [leer zurück] [Mo–Fr] → Anlegen“. Den Namen bildet das System
  selbst („Lager → B25“). Die Transportart wählt es nach dem, was durchkommt, zum Beispiel den
  Transportdienst, wenn das FTS den Aufzug nicht nutzen darf. Nach dem Anlegen sagt eine Meldung,
  ob es einen Weg gibt. Auch im großen Dialog sind Name und Transportart jetzt optional
  („Automatisch“).
- **Tor / Rampe (LKW)** als neue Punktart. „Gleichzeitig höchstens“ ist dort die Anzahl der Tore.
  Ein LKW belegt ein Tor, bis alle Paletten bzw. Wagen entladen sind (Standard 2 Minuten je
  Einheit, am Tor einstellbar), erst dann geht die Ware weiter. Sind alle Tore belegt, wartet
  der nächste LKW, und die Auswertung zeigt das Tor als Engpass.
- **Interne Transporte:** Neue Richtung „Intern“ und Wagentyp „Bett“. Bettentausch: Station →
  Aufbereitung mit 1 Bett, „beladen zurück“ bringt das saubere Bett zurück.

## [0.5.4] - 2026-11-16

- „Maßstab festlegen“ fragt, wie: **Eintippen** (springt ins Feld „Maßstab“ oben) oder
  **Auf dem Plan abmessen** (zwei Punkte anklicken).
- Nach einem Update lädt sich eine offene Seite selbst neu, statt mit dem alten Stand
  weiterzulaufen. Geprüft wird beim Seitenwechsel, beim Zurückkehren in den Tab und jede Minute.
- Die Kopfzeile der Karte bricht um, statt Knöpfe abzuschneiden.

## [0.5.3] - 2026-11-16

- **Maßstab-Feld fest oben auf der Karte:** „Maßstab 1 : [___] Speichern“ steht in jedem Modus
  in der Kopfzeile, solange man Bearbeitungsrechte hat. Steht der Maßstab als Text im Plan, ist er
  schon eingetragen. Der Dialog von 0.5.1 entfällt. „Maßstab abmessen“ (zwei Punkte anklicken)
  gibt es weiter im Modus „Bearbeiten“.

## [0.5.2] - 2026-11-16

- Maßstabsfeld nimmt auch „1:200“, „1 : 200“ oder „M 1:200“ an, nicht nur die Zahl.
- Nach einem Update lädt der Browser die neue Oberfläche sofort. Bisher konnte er noch eine
  Weile die alten Skripte aus dem Zwischenspeicher nehmen.

## [0.5.1] - 2026-11-16

- **Maßstab eintragen:** „Maßstab festlegen“ fragt jetzt nach dem Maßstab laut Plan („1 : 100“).
  Steht er als Text in der PDF, wird er vorgeschlagen. Das Anklicken zweier Punkte mit bekanntem
  Abstand bleibt als zweiter Weg. Der Dialog zeigt das Seitenformat der PDF, denn die Angabe
  stimmt nur bei Originalgröße.

## [0.5.0] - 2026-11-16

Neue Seite **Erste Schritte**: führt nach der Installation durch die Einrichtung.

- Solange nicht alles eingerichtet ist, ist sie die Startseite. Im Menü zeigt eine Zahl, wie
  viele Schritte noch offen sind.
- Sieben Schritte in Arbeitsreihenfolge: Bundesland, Gebäudeteile und Stockwerke, PDF-Pläne,
  Maßstab, Karte zeichnen, Stammdaten, Lieferungen. Danach Wegweiser zu Ablauf, Auswertung
  und Szenarien.
- Erledigt wird aus den Daten geprüft, nicht abgehakt. Nur Bundesland und Stammdaten werden
  bestätigt, weil dort schon Vorgaben eingetragen sind.
- Die Seite findet typische Fehler: Stockwerke ohne Plan oder Maßstab, Punkte, die an keinem
  Weg hängen, Aufzüge, die nur auf einem Stockwerk eingezeichnet sind, vom übrigen Netz
  getrennte Stockwerke, Übergänge ohne Gegenstück und Transportarten ohne Begrenzung.
- **Wegeprüfung für jede Lieferung** (hin und zurück): Fehlt ein Weg, steht dort, wo das Netz
  reißt, zum Beispiel „Von Rampe aus erreichbar: UG. Station 1 liegt auf EG, dorthin fehlt eine
  Verbindung“ oder „FTS darf Aufzug Ost nicht benutzen“.
- „Beheben“ springt an die richtige Stelle: Stockwerk mit gestartetem Maßstab-Werkzeug, den
  betroffenen Punkt ausgewählt auf der Karte, die Lieferung oder die Stammdaten.
- Menü in Arbeitsreihenfolge: Erste Schritte, Gebäude & Pläne, Karte, Stammdaten, Lieferungen,
  Auswertung, Szenarien.
- Leere Seiten verweisen auf die ersten Schritte. „Jetzt ausrichten“ nach einem Planwechsel
  startet direkt das Werkzeug.

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
