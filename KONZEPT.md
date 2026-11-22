# Konzept

Logistik Map macht Warenflüsse in großen Gebäuden sichtbar, vor allem im Krankenhaus. Es zeigt,
wann welche Lieferung wo ankommt, welchen Weg sie durch das Haus nimmt und wo dabei
Engpässe entstehen, zum Beispiel bei Aufzügen.

## Ziel

Beispiel: Um 8:00 Uhr kommt der Wäschedienstleister an der Rampe im Untergeschoss an. Die Wäsche
geht ins Wäschelager im 2. OG. Gleichzeitig kommen 20 weitere Lieferungen. Schaffen die Aufzüge
das? Wer steht um 8:20 Uhr noch und wartet?

## Bausteine

### 1. Gebäude und Pläne ✅
- **Gebäudeteile** (z. B. Haus A, Haus B) → **Stockwerke** (Ebene −1, 0, 1 …).
- Jedes Stockwerk bekommt eine Seite aus einem **PDF-Plan**. Große Pläne (A0 und größer) werden
  einmalig in Kartenkacheln umgewandelt und lassen sich danach flüssig zoomen.
- **Maßstab** je Stockwerk: Du klickst zwei Punkte an und gibst den Abstand in Metern ein.
  Erst damit lassen sich Wegezeiten berechnen.

### 2. Bereiche, Räume und Punkte ✅
- **Bereiche** (z. B. Warenannahme, Station 3B) als Flächen auf dem Plan. Ein Bereich kann
  Räume enthalten, ein Raum kann aber auch allein stehen.
- **Punkte** mit Rolle: Startpunkt (Rampe, Anlieferung), Zielpunkt (Lager, Station),
  Übergang (Aufzug, Treppe, Durchgang zwischen Gebäudeteilen).

### 3. Wegenetz ✅
- Flure werden als Linien eingezeichnet. Aufzüge und Treppen verbinden die Stockwerke.
- Wege berechnet das System selbst (kürzester bzw. schnellster Weg). Bei Bedarf werden sie
  von Hand festgelegt.
- Sperren je Transportart (z. B. „Flur X nicht für FTS“).

### 4. Stammdaten und Rechengrundlagen (jederzeit änderbar) ✅
- **Transportarten**: FTS (fahrerlose Transportsysteme), Materialtransportdienst, weitere.
  Je Art: Geschwindigkeit, Lade- und Entladezeit, Anzahl verfügbarer Fahrzeuge bzw. Personen.
- **Wagentypen** (Wäschewagen, Rollcontainer, Palette …) mit Platzbedarf im Aufzug.
- **Aufzüge**: Plätze, Fahrzeit je Stockwerk, Tür- und Wartezeit, erlaubte Transportarten.
  **FTS reservieren den Aufzug für sich allein.** Das Personal wird per Ansage zum Aussteigen
  aufgefordert, dafür gibt es eine einstellbare Räumzeit. Der Materialtransportdienst teilt sich
  den Aufzug nach Plätzen.
- **Engstellen**: Flure, Türen und Rampen mit Kapazität („max. 1 Wagen gleichzeitig“).

### 5. Lieferungen und Regeln ✅
- Eine Lieferung hat eine Uhrzeit, Start und Ziel, eine Ladung (z. B. „3× Wäschewagen + 1× Rollcontainer“)
  und eine Transportart.
- Jeder Transport hat eine Richtung: **Versorgung** (ins Haus) oder **Entsorgung** (aus dem Haus).
- **Rückwege** (leere Wagen zurück, Schmutzwäsche hinaus) mit eigener Zeit oder „direkt danach“.
- **Wiederholungsregeln**: täglich, bestimmte Wochentage, Wochenende, nicht an Feiertagen, nur in
  bestimmten Zeiträumen.
- **Feiertage** je Bundesland werden ohne Internet berechnet ✅. Eigene Sondertage lassen sich
  zusätzlich eintragen ✅.

### 6. Auswertung ✅
- Datum und Uhrzeit (oder einen Zeitraum) wählen und alle Flüsse auf den Plänen sehen.
- Zeitschieber, um den Tagesablauf abzuspielen.
- **Engpass-Anzeige**: Auslastung von Aufzügen und Engstellen, Wartezeiten, verspätete Ankünfte.
- Filter nach Startpunkt, Lieferant und Transportart.

### 7. Betrieb und Planung ✅
- Szenarien („Was wäre wenn“) mit Vergleich, Schichten, Wochenansicht.
- Excel-Import und -Export, Karte als PDF, Druckansicht.
- Sicherung, Update-Funktion, HTTPS, Active Directory, eigene Rollen, Änderungsprotokoll.
- Editor mit Rückgängig, Raumecken bearbeiten und Ausrichten bei neuem Planstand.

## So wird gerechnet

Die Simulation spielt einen Tag ereignisgenau durch (Sekunden seit Mitternacht):

- Eine Lieferung mit N Wagen ergibt ceil(N / „Wagen je Fahrt“) Fahrten, alle zur selben Uhrzeit.
- Jede Fahrt braucht ein Fahrzeug bzw. eine Person der Transportart. Bei begrenzter Anzahl
  wartet sie, bis eines frei ist. Belegt ist es bis zur Rückkehr. Mit Schichten ändert sich die
  Anzahl über den Tag. Wer gerade unterwegs ist, fährt zu Ende, auch wenn die Schicht endet.
- Ablauf: Laden am Start → schnellster Weg → Entladen am Ziel → Rückweg (leer, beladen oder keiner).
  „Später zurück“ ist eine eigene Fahrt zur angegebenen Uhrzeit.
- Gehzeit = Länge (aus Plan und Maßstab) / Geschwindigkeit.
- Aufzug = eine Kabine. Fahrzeit = Wartezeit auf die Kabine + 2 × Türzeit + Stockwerke × Fahrzeit
  je Stockwerk, bei FTS zusätzlich die Räumzeit. Steht die Kabine seit höchstens einer Minute
  auf dem Stockwerk, entfällt die Wartezeit auf sie. Wer gleichzeitig mit gleichem Start- und
  Zielstockwerk wartet, fährt mit, solange die Plätze reichen. FTS fahren immer allein.
- Treppen kosten nur Zeit und haben keine Kapazität. Sie dürfen nur Transportarten nutzen, die
  Treppen können.
- Wegstücke und Punkte mit „gleichzeitig höchstens“ sind Engstellen. Wegstücke sind belegt,
  solange sie durchfahren werden, Punkte während des Ladens bzw. Entladens.
- Als Engpass gilt alles, wo jemand mindestens eine Minute wartet oder die Auslastung in einem
  5-Minuten-Abschnitt 90 % erreicht.

- Produktion (Küche, Sterilgut …): Im Takt wird ein Wagen fertig und belegt einen Stellplatz bis nach dem
  Laden. Ist keiner frei, steht die Produktion; die geplante Menge wird trotzdem fertig, nur später. Fahrten
  werden sofort, ab einer Menge (auch bei vollen Stellplätzen) oder zu festen Zeiten gerufen, je Fahrt ein
  Ziel und höchstens „Wagen je Fahrt“. Noch offen: Beginn erst, wenn Ware oder Leerwagen da sind.
- Lieferungen des Vortags ab 16 Uhr werden mitgerechnet, soweit sie nach Mitternacht noch
  unterwegs sind. In den Kennzahlen des Tages zählen sie nicht mit.

Das ist bewusst grob. Personenverkehr im Aufzug steckt nur in der mittleren Wartezeit, und
Begegnungsverkehr im Flur gibt es nur, wenn eine Kapazität gesetzt ist.

## Technik

- Python-Server (FastAPI) mit SQLite, Oberfläche im Browser (Leaflet für die Pläne).
- Läuft lokal auf einem Windows-Server als Dienst. Der Installer fragt den Port ab.
- Kein Internet nötig, alle Daten bleiben auf dem Server.
- Benutzer und Rollen: Administrator (alles), Planer (Lieferungen und Szenarien), Betrachter (nur ansehen) sowie eigene Rollen. Anmeldung lokal oder über Active Directory.
- Oberfläche auf Deutsch und Englisch. Alle Texte stehen in `logistikmap/static/i18n/`.
- Lizenz: AGPL-3.0.
