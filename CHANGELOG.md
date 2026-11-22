# Änderungen

## [0.11.0] - 2026-11-22

Neu:

- **Produktion:** Bereiche, in denen laufend etwas entsteht, das abgeholt werden muss – Küche,
  Sterilgut, Wäscherei, Apotheke, Abfall. Unter *Lieferungen → Produktion* trägst du Zeitfenster,
  Takt, Stellplätze, Ziele und die Abholung ein (sofort, ab einer Menge oder zu festen Zeiten). Die
  Fahrten entstehen von selbst.
- **Rückstau:** Sind alle Stellplätze belegt, steht die Produktion. Die Auswertung zeigt, ab wann und
  wie lange, den Verlauf der wartenden Wagen und wann der letzte wirklich fertig wird. Im Ablauf
  steht am Punkt, wie viele Wagen gerade warten.
- **Punkt der Art „Produktion“** auf der Karte, mit der Produktion direkt im Punktformular.
- **Mindestbedarf:** wie viele Fahrzeuge oder Stellplätze nötig sind, damit eine Produktion nicht
  steht. Auch in Streuung, Szenarien, „Erste Schritte“ und im Excel-Export.

Verbessert:

- **Handy:** Die Dialoge für Lieferungen und Produktion ragen nicht mehr über den Bildschirm hinaus.

## [0.10.1] - 2026-11-19

Verbessert:

- **Handy:** Die Karte bekommt im Ablauf und beim Bearbeiten deutlich mehr Platz, die Bedienung
  folgt darunter. Die Zoom-Knöpfe der Karte liegen nicht mehr über dem aufgeklappten Menü.
- **Kopfzeile:** Bei mittleren Bildschirmbreiten (z. B. 1440 Pixel) wurde „Einstellungen“
  abgeschnitten – jetzt passen alle Menüpunkte.
- **Auswertung:** „Auf der Karte zeigen“ ragt in den Engpass-Karten nicht mehr über den Rand.
- **Update-Fenster** zeigt nur noch die Neuerungen einer Version, nicht den ganzen Release-Text.
- **GitHub-Seite:** neues README auf Deutsch mit Bildern aus einem erfundenen Musterklinikum,
  Seite zu Technik und Betrieb (`docs/TECHNIK.md`), `SECURITY.md`. Jedes Release enthält
  jetzt Installation, Prüfsumme und die technischen Eckdaten.

## [0.10.0] - 2026-11-17

Neu:

- **Zugriff je Krankenhaus.** Im Benutzer-Dialog lässt sich anhaken, welche Krankenhäuser jemand
  sehen darf (nichts angehakt = alle, Administratoren sehen immer alle). Andere Häuser fehlen dann
  in der Auswahl und sind auch über direkte Links und Exporte nicht erreichbar.
- **Streuung und Mindestbedarf rechnen im Hintergrund** – mit Fortschrittsbalken und „Abbrechen“.
  Auch große Häuser laufen so nicht mehr in eine Zeitüberschreitung (z. B. hinter Cloudflare).
- **Zeichnen am Tablet und Handy:** Knöpfe „Strecke absetzen“, „Fläche fertig“ und „Letzten Punkt
  zurück“ statt Rechtsklick und Tasten. Auf dem Handy bekommt die Karte deutlich mehr Platz,
  die Werkzeuge lassen sich seitlich wischen.
- **Ablauf: Farbe nach Transportart, Lieferung oder Richtung**, mit Legende. So lässt sich eine
  einzelne Tour gut verfolgen.
- Hilfe um alle neuen Funktionen ergänzt.

## [0.9.3] - 2026-11-17

Behoben:

- **Exporte (Excel, Karten-PDF) wurden nicht gegen Zwischenspeichern geschützt.** Steht Cloudflare
  vor dem Server, konnte es eine heruntergeladene Datei ablegen und an andere weitergeben – auch an
  einen anderen Standort oder an Abgemeldete. Alle Antworten der Schnittstelle sind jetzt
  ausdrücklich „nicht speichern“.
- **Karte zeigte manchmal den falschen Plan.** Nach dem Entfernen eines Plans bekam der nächste
  dieselbe Nummer, der Browser zeigte dann bis zu 7 Tage die alten Kacheln. Jeder neu erzeugte
  Plan hat jetzt eine eigene Adresse.
- Dateinamen von Exporten mit Umlauten (z. B. Stockwerk „Süd“) kommen korrekt an.
- Die Sperre nach Fehlanmeldungen räumt alte Einträge auf, auch wenn Bots laufend neue
  Benutzernamen probieren.

## [0.9.2] - 2026-11-17

Behoben: **Nach einem Update erschien teils noch die alte Oberfläche.** Steht ein Zwischenspeicher
wie Cloudflare vor dem Server, hielt er Skripte und Stile stundenlang fest – so kam z. B. das neue
Handy-Menü aus 0.9.1 gar nicht an. Skripte und Stile kommen jetzt unter einer Adresse mit
Versionsnummer, jedes Update ist damit sofort sichtbar.

## [0.9.1] - 2026-11-17

Neu: **Handytauglich.**

- Auf dem Handy stecken die Menüpunkte hinter **☰** oben links (vorher war das Menü auf schmalen
  Bildschirmen gar nicht zu sehen). Krankenhaus-Auswahl, **?** und Benutzermenü passen in die
  Kopfzeile.
- **Update-Hinweis:** Steht eine neue Version bereit, sehen Administratoren im Menü
  „⬆ Update … verfügbar“ (auf dem Handy mit Marke am ☰). Ein Tipp führt direkt zu
  Einstellungen → Updates – kein langes Scrollen mehr.
- Keine Seite schiebt sich mehr seitlich aus dem Bildschirm: Breite Tabellen wischt man in sich,
  „Gebäude & Pläne“ passt in die Breite.
- Fingergerechte Knöpfe und Eingabefelder (keine automatische Vergrößerung beim Antippen auf dem
  iPhone), Dialoge in voller Breite, Meldungen über die ganze Breite unten.

## [0.9.0] - 2026-11-17

Neu: **Hilfe – eine ausführliche Anleitung im Programm.**

- Menüpunkt **Hilfe** mit Inhaltsverzeichnis und Suche (Fundstellen werden markiert, Enter
  springt zur ersten). Der Knopf **?** oben rechts öffnet die Hilfe genau zu der Seite, auf der
  man gerade ist.
- Inhalt: Überblick und Begriffe, die Einrichtung Schritt für Schritt, jede Seite mit jedem Feld
  und seiner Bedeutung (typische Werte für Geschwindigkeit, Aufzugzeiten usw.), wie die
  Simulation rechnet (Fahrten, Wegsuche, Aufzug, LKW am Tor, Kennzahlen), Anleitungen für
  häufige Aufgaben (LKW über drei Tore, Bettentausch, Personalbedarf, Aufzugsausfall, FTS-Sperre)
  und eine Tabelle zur Fehlersuche. Auf Deutsch und Englisch.
- Einheitliche Begriffe: Gezeichnetes heißt überall **Strecke** bzw. **Streckenstück** (vorher
  teils „Weg“ oder „Wegstück“); „Weg“ ist der Weg, den das System für eine Lieferung findet.
- „Anzahl“ bei Transportarten und im Mindestbedarf ist jetzt klar erklärt: so viele gleichzeitig
  im Einsatz, keine Stellen.
- Szenarien: Tore ohne eingetragene Anzahl fehlten in der Liste „Rampen und Lade-/Entladepunkte“.
- Ablauf: Richtungsfilter heißt „Alle Richtungen“ (umfasst auch „Intern“), Excel-Hinweis nennt
  „Intern“.

## [0.8.0] - 2026-11-16

Neu: **Streuung, Mindestbedarf und Grundlast der Aufzüge.**

- **Streuung:** Bei jeder Lieferung lässt sich „Schwankung ± Min.“ eintragen (auch in der
  Excel-Liste), am Tor die Entladezeit je Palette „von – bis“. Auswertung → **Streuung** rechnet
  den Tag 100-mal (einstellbar) mit zufälligen Abweichungen und zeigt je Stelle, an wie viel
  Prozent der Tage dort länger als die Schwelle (z. B. 30 Min.) gewartet wird, dazu üblichen Wert,
  9-von-10-Tage-Wert und schlimmsten Tag, je Lieferung den Anteil verspäteter Tage. Feste
  Startwerte: gleiche Eingabe, gleiches Ergebnis. Die normale Tagesansicht rechnet weiter genau
  nach Plan.
- **Mindestbedarf:** Auswertung → **Mindestbedarf**: Transportart (Fahrzeuge bzw. Mitarbeiter),
  Tor/Rampe oder Engstelle wählen, Höchstwartezeit eingeben – das System probiert 1, 2, 3 …
  durch und nennt die kleinste Anzahl, die reicht. Auf Wunsch mit Streuung (30 Tage, 9 von 10
  müssen passen).
- **Grundlast der Aufzüge:** In den Stammdaten beim Aufzug Zeitfenster eintragen, z. B.
  „Mo–Fr 08:00–10:00: 40 %“. Die Simulation lässt entsprechend Personenfahrten mitfahren; sie
  blockieren die Kabine, zählen aber nicht als Wartezeit der Waren und werden in der Auswertung
  getrennt gezählt.
- Engstellen-Liste filtert jetzt nach Krankenhaus (Fehler aus 0.7.0).

## [0.7.1] - 2026-11-16

- **Strecke für eine Transportart sperren, auf einen Klick für die ganze Strecke:** Beim
  Wegstück (Auswählen → Strecke anklicken) gibt es unter „Gesperrt für“ den Haken „Für die ganze
  Strecke bis zur nächsten Kreuzung“. Die Sperre gilt dann für alle Stücke bis zur nächsten
  Abzweigung oder zum nächsten Punkt. Die Wegsuche nimmt für gesperrte Transportarten (z. B. FTS)
  einen anderen Weg; gesperrte Strecken sind rot gestrichelt.

## [0.7.0] - 2026-11-16

Neu: **mehrere Krankenhäuser (Standorte)** in einer Installation.

- Oben neben „Logistik Map“ steht das aktuelle Krankenhaus als Auswahl. Wechseln lädt die
  Oberfläche neu; jedes Haus hat eigene Gebäude, Stockwerke, Pläne, Strecken, Aufzüge,
  Transportarten, Wagentypen, Lieferungen, Szenarien, Sondertage, Bundesland und
  „Erste Schritte“. Benutzer, Rollen, Anmeldung, Sicherung und Update sind gemeinsam.
- „＋ Neues Krankenhaus …“ (für Administratoren): Name eingeben, Transportarten und Wagentypen
  aus einem vorhandenen Haus übernehmen oder mit Standardwerten beginnen. Danach führt
  „Erste Schritte“ durch die Einrichtung.
- Einstellungen → „Krankenhäuser“: umbenennen, öffnen, löschen (mit allem, was dazugehört;
  das letzte Haus bleibt).
- Bestehende Daten werden beim Update zum ersten Krankenhaus; es heißt wie der erste
  Gebäudeteil und lässt sich umbenennen.

## [0.6.8] - 2026-11-16

- **Große PDF-Pläne (über ~25 MB) lassen sich hochladen.** Der Browser schickt die Datei jetzt
  in Stücken zu 8 MB, der Server setzt sie wieder zusammen. Proxys, Virenscanner oder Webfilter
  im Klinik-Netz begrenzen oft die Größe einer einzelnen Anfrage. Daran scheiterte der Upload bei
  99 %, ohne dass die Anfrage beim Server ankam. Grenze bleibt 1 GB je Datei.
- **Unbekannte Fehler zeigen Code und Text** (z. B. „Fehler 413 vom Server: …“) statt nur
  „Es ist ein Fehler aufgetreten“.
- Abgelehnte Änderungen stehen mit Status und Größe im Server-Log.

## [0.6.7] - 2026-11-16

- **Mehrere PDF-Pläne auf einmal:** Im Dateidialog lassen sich mehrere PDFs auswählen, oder du
  ziehst sie auf den Bereich „Hochgeladene PDF-Pläne“. Bisher wurde nur die erste Datei
  hochgeladen.
- **Ergebnis bleibt stehen:** Für jede Datei steht eine Zeile da, ✓ hochgeladen oder ✗ mit Grund.
  Vorher verschwand eine Fehlermeldung nach wenigen Sekunden.
- PDFs mit Zeichen vor der PDF-Kennung (erlaubt laut Norm, kommt bei Plot-Programmen vor) werden
  angenommen. Abgelehnte Uploads stehen im Server-Log.

## [0.6.6] - 2026-11-16

- **„Lücken prüfen“ fragt deutlich:** Rechts neben der Karte steht die Frage („Hier endet eine
  Strecke 2,1 m neben einer anderen. Sollen beide verbunden werden?“) mit den Knöpfen
  **Ja, verbinden** und **Nein**. Der Vorschlag ist auf der Karte nur dünn gepunktet mit einem
  Fragezeichen eingezeichnet, damit er nicht wie eine fertige Strecke aussieht.
- **Nein gilt dauerhaft:** Die Stelle wird gespeichert, nicht mehr vorgeschlagen und nicht mehr
  orange markiert.

## [0.6.5] - 2026-11-16

- **„Lücken prüfen“ statt automatisch verbinden:** Der Knopf geht die Vorschläge einzeln
  durch. Die Karte springt zur Stelle, die vorgeschlagene Verbindung ist gestrichelt
  eingezeichnet, und du entscheidest jedes Mal: „Verbinden“ (Enter) oder „Überspringen“
  (Leertaste).
- Beim Zeichnen werden Punkte neben der Linie nicht mehr still angeschlossen. Kreuzungen mit
  vorhandenen Strecken entstehen weiterhin.

## [0.6.4] - 2026-11-16

- **Lücken im Streckennetz sichtbar:** Ein Streckenende, an dem es nicht weitergeht, ist im
  Editor orange markiert. Zwei Punkte, die nur dicht beieinander liegen, sind nicht verbunden –
  das fällt so sofort auf.
- **Punkt auf Punkt ziehen verbindet beide:** Ein Streckenpunkt, der auf einen anderen Punkt
  gezogen wird, geht in ihm auf; die Strecken hängen danach zusammen.
- **„Lücken schließen“** (bisher „Punkte anschließen“): verbindet zusätzlich offene Enden, die
  weniger als 4 m neben einem Punkt oder einer anderen Strecke aufhören.
- Beim Zeichnen werden vorhandene Punkte aus etwas größerem Abstand gefangen.

## [0.6.3] - 2026-11-16

- **„Strecken zeichnen“** und **„Strecke löschen“** statt „Flure zeichnen“/„Flur löschen“.
- **Aufhören mit Rechtsklick:** Ein Rechtsklick (ohne Ziehen) beendet die aktuelle Linie, ein
  zweiter Rechtsklick das Werkzeug. Beim Raum-Vieleck schließt der Rechtsklick die Fläche. Bei den
  übrigen Werkzeugen geht es mit Rechtsklick zurück zu „Auswählen“.
- Ein zweiter Klick auf den Knopf des aktiven Werkzeugs schaltet ebenfalls zurück zu „Auswählen“.

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
