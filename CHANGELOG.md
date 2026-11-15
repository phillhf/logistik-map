# Änderungen

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
