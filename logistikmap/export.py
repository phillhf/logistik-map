"""Import und Export: Lieferungen als Excel/CSV, Auswertung als Excel, Karte als PDF."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, time

import pymupdf

TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
SPALTEN = [
    "ID", "Bezeichnung", "Lieferant", "Richtung", "Transportart", "Start", "Ziel", "Uhrzeit", "Spätestens",
    "Ladung", "Tage", "Feiertage", "Gültig ab", "Gültig bis", "Rückweg", "Rückweg Uhrzeit", "Rückweg nach", "Aktiv", "Notiz",
]
HINWEISE = [
    ("ID", "Leer lassen für neue Lieferungen. Mit ID wird die vorhandene Lieferung aktualisiert."),
    ("Richtung", "Versorgung oder Entsorgung"),
    ("Transportart", "Name wie unter Stammdaten, z. B. FTS"),
    ("Start / Ziel / Rückweg nach", "Name des Punkts. Gibt es den Namen mehrfach: „Name (Stockwerk)“ oder „Name (Stockwerk, Kürzel)“"),
    ("Uhrzeit / Spätestens", "HH:MM, z. B. 08:00"),
    ("Ladung", "z. B. „12 Wäschewagen, 2 Rollcontainer“"),
    ("Tage", "täglich, Mo-Fr, Mo-Sa, Wochenende oder einzeln: Mo, Mi, Fr"),
    ("Feiertage", "nicht (Standard), auch oder nur"),
    ("Gültig ab / bis", "Datum, optional"),
    ("Rückweg", "leer (Standard), beladen, später, keiner – bei „später“ die Rückweg-Uhrzeit angeben"),
    ("Aktiv", "ja oder nein"),
]


class ImportFehler(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- Hilfen
def tage_text(regel: dict) -> str:
    t = regel.get("wochentage", [])
    if t == [1, 2, 3, 4, 5, 6, 7]:
        return "täglich"
    if t == [1, 2, 3, 4, 5]:
        return "Mo-Fr"
    if t == [1, 2, 3, 4, 5, 6]:
        return "Mo-Sa"
    if t == [6, 7]:
        return "Wochenende"
    return ", ".join(TAGE[d - 1] for d in t)


def tage_lesen(text: str) -> list[int]:
    t = (text or "").strip().lower().replace("–", "-")
    if not t or t in ("täglich", "taeglich", "alle", "mo-so"):
        return [1, 2, 3, 4, 5, 6, 7]
    if t in ("wochenende", "sa-so", "sa, so", "sa,so"):
        return [6, 7]
    namen = [x.lower() for x in TAGE]
    tage = set()
    for teil in re.split(r"[,;/ ]+", t):
        if not teil:
            continue
        if "-" in teil:
            a, b = teil.split("-", 1)
            if a[:2] not in namen or b[:2] not in namen:
                raise ValueError(teil)
            i, j = namen.index(a[:2]), namen.index(b[:2])
            tage |= set(range(i + 1, j + 2)) if i <= j else set(range(i + 1, 8)) | set(range(1, j + 2))
        elif teil[:2] in namen:
            tage.add(namen.index(teil[:2]) + 1)
        else:
            raise ValueError(teil)
    return sorted(tage)


def punkt_bezeichnung(p: dict, alle: list[dict]) -> str:
    if not p:
        return ""
    name = p["name"] or f"#{p['id']}"
    gleich = [x for x in alle if x["name"] == p["name"]]
    if len(gleich) <= 1:
        return name
    gleiches_stockwerk = [x for x in gleich if x["stockwerk"] == p["stockwerk"]]
    if len(gleiches_stockwerk) <= 1:
        return f"{name} ({p['stockwerk']})"
    return f"{name} ({p['stockwerk']}, {p['kuerzel'] or p['gebaeudeteil']})"


def punkt_finden(text: str, alle: list[dict]) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    for p in alle:
        if punkt_bezeichnung(p, alle).lower() == text.lower():
            return p
    treffer = [p for p in alle if (p["name"] or "").lower() == text.lower()]
    return treffer[0] if len(treffer) == 1 else None


def ladung_text(ladung: list[dict], wagentypen: list[dict]) -> str:
    namen = {w["id"]: w["name"] for w in wagentypen}
    return ", ".join(f"{p['anzahl']} {namen.get(p['wagentyp_id'], '?')}" for p in ladung)


def ladung_lesen(text: str, wagentypen: list[dict]) -> list[dict]:
    ergebnis = []
    for teil in re.split(r"[,;+\n]+", text or ""):
        teil = teil.strip()
        if not teil:
            continue
        m = re.match(r"^(\d+)\s*[x×]?\s*(.+)$", teil, re.IGNORECASE)
        if not m:
            raise ValueError(teil)
        name = m.group(2).strip().lower()
        wt = next((w for w in wagentypen if w["name"].lower() == name), None)
        if wt is None:
            raise ValueError(m.group(2))
        ergebnis.append({"wagentyp_id": wt["id"], "anzahl": int(m.group(1))})
    return ergebnis


def _zeit(wert) -> str:
    if wert in (None, ""):
        return ""
    if isinstance(wert, (datetime, time)):
        return f"{wert.hour:02d}:{wert.minute:02d}"
    if isinstance(wert, float) and 0 <= wert < 1:  # Excel-Uhrzeit als Tagesbruchteil
        m = round(wert * 1440)
        return f"{m // 60:02d}:{m % 60:02d}"
    t = str(wert).strip()
    m = re.match(r"^(\d{1,2})[:.](\d{2})", t)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else t


def _datum(wert) -> str | None:
    if wert in (None, ""):
        return None
    if isinstance(wert, datetime):
        return wert.date().isoformat()
    t = str(wert).strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", t)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return t[:10]


# --------------------------------------------------------------------------- Lieferungen
def lieferungen_xlsx(punkte: list[dict], stamm: dict, lieferungen: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    nach_id = {p["id"]: p for p in punkte}
    ta = {t["id"]: t["name"] for t in stamm["transportarten"]}
    wb = Workbook()
    ws = wb.active
    ws.title = "Lieferungen"
    ws.append(SPALTEN)
    for l in lieferungen:
        r = l["rueckweg"] or {}
        ws.append([
            l["id"], l["name"], l["lieferant"], "Entsorgung" if l["richtung"] == "entsorgung" else "Versorgung",
            ta.get(l["transportart_id"], ""), punkt_bezeichnung(nach_id.get(l["start_id"]), punkte), punkt_bezeichnung(nach_id.get(l["ziel_id"]), punkte),
            l["uhrzeit"], l["spaetestens"] or "", ladung_text(l["ladung"], stamm["wagentypen"]), tage_text(l["regel"]),
            {"ausser": "nicht", "auch": "auch", "nur": "nur"}[l["regel"].get("feiertage", "ausser")],
            l["regel"].get("von") or "", l["regel"].get("bis") or "",
            {"leer": "leer", "beladen": "beladen", "spaeter": "später", "keiner": "keiner"}.get(r.get("modus", "leer"), "leer"),
            r.get("uhrzeit") or "", punkt_bezeichnung(nach_id.get(r.get("ziel_id")), punkte) if r.get("ziel_id") else "",
            "ja" if l["aktiv"] else "nein", l["notiz"],
        ])
    for i, breite in enumerate([6, 28, 22, 12, 22, 30, 30, 9, 11, 32, 14, 10, 12, 12, 10, 14, 26, 7, 30], start=1):
        ws.column_dimensions[get_column_letter(i)].width = breite
    for zelle in ws[1]:
        zelle.font = Font(bold=True, color="FFFFFF")
        zelle.fill = PatternFill("solid", fgColor="1F5F8B")
    ws.freeze_panes = "B2"
    h = wb.create_sheet("Hinweise")
    h.append(["Spalte", "Erklärung"])
    for zeile in HINWEISE:
        h.append(list(zeile))
    h.append([])
    h.append(["Punkte", "Diese Namen können bei Start, Ziel und Rückweg verwendet werden:"])
    for p in punkte:
        if p["art"] != "weg":
            h.append(["", punkt_bezeichnung(p, punkte)])
    h.append([])
    h.append(["Wagentypen", ", ".join(w["name"] for w in stamm["wagentypen"])])
    h.append(["Transportarten", ", ".join(t["name"] for t in stamm["transportarten"])])
    h.column_dimensions["A"].width = 28
    h.column_dimensions["B"].width = 90
    for zelle in h[1]:
        zelle.font = Font(bold=True)
    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


def lieferungen_lesen(inhalt: bytes, dateiname: str) -> list[dict]:
    """Liest Zeilen aus XLSX oder CSV als Liste von {Spaltenname: Wert}."""
    if dateiname.lower().endswith((".xlsx", ".xlsm")) or inhalt[:2] == b"PK":
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(inhalt), read_only=True, data_only=True)
        except Exception as e:
            raise ImportFehler("datei_unlesbar") from e
        ws = wb["Lieferungen"] if "Lieferungen" in wb.sheetnames else wb.worksheets[0]
        reihen = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        text = None
        for kodierung in ("utf-8-sig", "cp1252"):
            try:
                text = inhalt.decode(kodierung)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ImportFehler("datei_unlesbar")
        trenner = ";" if text.count(";") >= text.count(",") else ","
        reihen = list(csv.reader(io.StringIO(text), delimiter=trenner))
    reihen = [r for r in reihen if any(v not in (None, "") for v in r)]
    if not reihen:
        raise ImportFehler("datei_leer")
    kopf = [str(k or "").strip() for k in reihen[0]]
    if "Bezeichnung" not in kopf or "Start" not in kopf or "Ziel" not in kopf or "Uhrzeit" not in kopf:
        raise ImportFehler("spalten_fehlen")
    return [dict(zip(kopf, r)) for r in reihen[1:]]


def lieferungen_zuordnen(zeilen: list[dict], kontext: dict) -> list[dict]:
    punkte, stamm = kontext["punkte"], kontext["stamm"]
    benannt = [p for p in punkte if p["art"] != "weg"]
    ergebnis = []
    for nr, z in enumerate(zeilen, start=2):
        fehler = []
        g = lambda k: ("" if z.get(k) is None else str(z.get(k))).strip()  # noqa: E731
        name = g("Bezeichnung")
        if not name:
            fehler.append("bezeichnung_fehlt")
        ta = next((t for t in stamm["transportarten"] if t["name"].lower() == g("Transportart").lower()), None)
        if ta is None:
            fehler.append("transportart_unbekannt")
        start, ziel = punkt_finden(g("Start"), benannt), punkt_finden(g("Ziel"), benannt)
        if start is None:
            fehler.append("start_unbekannt")
        if ziel is None:
            fehler.append("ziel_unbekannt")
        uhrzeit = _zeit(z.get("Uhrzeit"))
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", uhrzeit):
            fehler.append("uhrzeit_ungueltig")
        try:
            ladung = ladung_lesen(g("Ladung"), stamm["wagentypen"])
        except ValueError:
            ladung = []
            fehler.append("ladung_ungueltig")
        try:
            tage = tage_lesen(g("Tage"))
        except ValueError:
            tage = []
            fehler.append("tage_ungueltig")
        feiertage = {"": "ausser", "nicht": "ausser", "nein": "ausser", "auch": "auch", "ja": "auch", "nur": "nur"}.get(g("Feiertage").lower())
        if feiertage is None:
            fehler.append("feiertage_ungueltig")
        rueck = {"": "leer", "leer": "leer", "beladen": "beladen", "später": "spaeter", "spaeter": "spaeter", "keiner": "keiner", "kein": "keiner"}.get(g("Rückweg").lower())
        if rueck is None:
            fehler.append("rueckweg_ungueltig")
        rueck_ziel = punkt_finden(g("Rückweg nach"), benannt) if g("Rückweg nach") else None
        if g("Rückweg nach") and rueck_ziel is None:
            fehler.append("rueckweg_ziel_unbekannt")
        richtung = "entsorgung" if g("Richtung").lower().startswith("ent") else "versorgung"
        aktiv = g("Aktiv").lower() not in ("nein", "0", "false", "aus")
        lid = None
        if g("ID"):
            try:
                lid = int(float(g("ID")))
            except ValueError:
                fehler.append("id_ungueltig")
        daten = {
            "name": name, "lieferant": g("Lieferant"), "richtung": richtung, "transportart_id": ta["id"] if ta else 0,
            "start_id": start["id"] if start else 0, "ziel_id": ziel["id"] if ziel else 0, "uhrzeit": uhrzeit,
            "spaetestens": _zeit(z.get("Spätestens")) or None, "ladung": ladung,
            "regel": {"wochentage": tage, "feiertage": feiertage or "ausser", "von": _datum(z.get("Gültig ab")), "bis": _datum(z.get("Gültig bis"))},
            "rueckweg": {"modus": rueck or "leer", "uhrzeit": _zeit(z.get("Rückweg Uhrzeit")) or None, "ziel_id": rueck_ziel["id"] if rueck_ziel else None},
            "aktiv": aktiv, "notiz": g("Notiz"),
        }
        ergebnis.append({"zeile": nr, "id": lid, "name": name, "uhrzeit": uhrzeit, "fehler": fehler, "daten": daten})
    return ergebnis


# --------------------------------------------------------------------------- Auswertung
def _uhr(s) -> str:
    if s is None:
        return ""
    tag, rest = divmod(int(round(s)), 86400)
    return f"{'+' + str(tag) + ' ' if tag else ''}{rest // 3600:02d}:{rest % 3600 // 60:02d}"


def auswertung_xlsx(e: dict, kontext: dict, szenario: str | None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    punkte = {p["id"]: p for p in kontext["punkte"]}
    ta = {t["id"]: t["name"] for t in kontext["stamm"]["transportarten"]}
    wb = Workbook()
    ws = wb.active
    ws.title = "Übersicht"
    zs = e["zusammenfassung"]
    for zeile in [
        ["Logistik Map – Auswertung"], ["Datum", e["datum"]], ["Szenario", szenario or "Ist-Zustand"], ["Feiertag", e.get("feiertag") or ""], [],
        ["Lieferungen", zs["lieferungen"]], ["Fahrten", zs["fahrten"]], ["Verspätet", zs["verspaetet"]],
        ["Längste Wartezeit (min)", round(zs["max_wartezeit"] / 60, 1)], ["Wartezeit gesamt (min)", round(zs["summe_wartezeit"] / 60, 1)],
        ["Engpässe", zs["engpaesse"]],
    ]:
        ws.append(zeile)
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 24

    def kopf(blatt, spalten, breiten):
        blatt.append(spalten)
        for zelle in blatt[1]:
            zelle.font = Font(bold=True, color="FFFFFF")
            zelle.fill = PatternFill("solid", fgColor="1F5F8B")
        for i, b in enumerate(breiten, start=1):
            blatt.column_dimensions[get_column_letter(i)].width = b
        blatt.freeze_panes = "A2"

    typ_name = {"aufzug": "Aufzug", "kante": "Engstelle", "knoten": "Lade-/Entladepunkt", "fahrzeuge": "Fahrzeuge"}
    eng = wb.create_sheet("Engpässe")
    kopf(eng, ["Art", "Name", "Max. Wartezeit (min)", "Wartezeit gesamt (min)", "Max. wartend", "Spitze Auslastung", "Vorgänge"], [20, 30, 20, 22, 14, 18, 12])
    engpaesse = {(x["typ"], x["id"]) for x in e["engpaesse"]}
    for r in sorted(e["ressourcen"], key=lambda r: (-r["max_wartezeit"], -r["spitze"])):
        eng.append([typ_name.get(r["typ"], r["typ"]), r["name"], round(r["max_wartezeit"] / 60, 1), round(r["summe_wartezeit"] / 60, 1),
                    r["max_schlange"], f"{round(r['spitze'] * 100)} %", r["anzahl"]])
        if (r["typ"], r["id"]) in engpaesse:
            for zelle in eng[eng.max_row]:
                zelle.fill = PatternFill("solid", fgColor="FFE3E3")

    fa = wb.create_sheet("Fahrten")
    kopf(fa, ["Geplant", "Lieferung", "Fahrt", "Transportart", "Von", "Nach", "Los", "Ankunft", "Spätestens", "Verspätet",
              "Warten Fahrzeug (min)", "Warten Aufzug (min)", "Warten Engstelle (min)", "Zurück"],
         [9, 26, 8, 20, 30, 30, 8, 9, 10, 10, 12, 12, 12, 9])
    for f in sorted(e["fahrten"], key=lambda f: (f["geplant"], f["id"])):
        fa.append([_uhr(f["geplant"]), f["name"], f"{f['nr']}/{f['von_n']}", ta.get(f["transportart_id"], ""),
                   (punkte.get(f["start_id"]) or {}).get("name", ""), (punkte.get(f["ziel_id"]) or {}).get("name", ""),
                   _uhr(f["start"]), _uhr(f["ankunft"]), _uhr(f["spaetestens"]), "ja" if f["verspaetet"] else "",
                   round(f["warte"]["fahrzeug"] / 60, 1), round(f["warte"]["aufzug"] / 60, 1), round(f["warte"]["engstelle"] / 60, 1), _uhr(f["ende"])])

    au = wb.create_sheet("Auslastung")
    zeiten = sorted({s for r in e["ressourcen"] for s, _ in r["raster"]})
    kopf(au, ["Uhrzeit"] + [f"{typ_name.get(r['typ'], r['typ'])}: {r['name']}" for r in e["ressourcen"]], [9] + [22] * len(e["ressourcen"]))
    werte = [{s: v for s, v in r["raster"]} for r in e["ressourcen"]]
    for s in zeiten:
        au.append([_uhr(s)] + [round(w.get(s, 0) * 100) for w in werte])

    if e["fehler"]:
        fe = wb.create_sheet("Ohne Weg")
        kopf(fe, ["Lieferung", "Problem"], [30, 60])
        for x in e["fehler"]:
            fe.append([x["name"], x["code"]])

    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


# --------------------------------------------------------------------------- Karte als PDF
def _farbe(hexwert: str, standard=(0.12, 0.37, 0.55)) -> tuple:
    m = re.match(r"^#([0-9a-fA-F]{6})$", hexwert or "")
    if not m:
        return standard
    v = int(m.group(1), 16)
    return ((v >> 16) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255)


def karte_pdf(db, pfade, sid: int, e: dict, von: str, bis: str, start_filter: int | None, szenario: str | None, kontext: dict) -> bytes:
    """Plan des Stockwerks mit Flächen, Wegen, Punkten und den Warenflüssen im Zeitfenster."""
    sw = db.eins(
        """SELECT s.*, g.name AS teil, g.kuerzel, p.dokument_id, p.seite FROM stockwerke s
           JOIN gebaeudeteile g ON g.id = s.gebaeudeteil_id JOIN plaene p ON p.id = s.plan_id WHERE s.id = ?""",
        (sid,),
    )
    quelle = pymupdf.open(pfade.dokumente / f"{sw['dokument_id']}.pdf")
    qseite = quelle[sw["seite"] - 1]
    breite, hoehe = qseite.rect.width, qseite.rect.height
    rand = max(breite, hoehe) * 0.24
    doc = pymupdf.open()
    seite = doc.new_page(width=breite + rand, height=hoehe)
    seite.show_pdf_page(pymupdf.Rect(0, 0, breite, hoehe), quelle, sw["seite"] - 1)
    quelle.close()
    e_ = max(breite, hoehe) / 900  # Grundmaß für Linien und Schrift

    flaechen = db.alle("SELECT * FROM flaechen WHERE stockwerk_id = ?", (sid,))
    knoten = {k["id"]: k for k in db.alle("SELECT * FROM knoten WHERE stockwerk_id = ?", (sid,))}
    for f in sorted(flaechen, key=lambda f: f["art"] != "bereich"):
        pp = [pymupdf.Point(x, y) for x, y in json.loads(f["punkte"])]
        farbe = _farbe(f["farbe"], (0.12, 0.37, 0.55) if f["art"] == "bereich" else (0.29, 0.31, 0.34))
        seite.draw_polyline(pp + [pp[0]], color=farbe, fill=farbe, fill_opacity=0.07, width=e_ * (1.2 if f["art"] == "bereich" else 0.6),
                            dashes=f"[{e_ * 4} {e_ * 3}] 0" if f["art"] == "bereich" else None)

    # Warenflüsse im Zeitfenster
    t0 = int(von[:2]) * 3600 + int(von[3:]) * 60
    t1 = int(bis[:2]) * 3600 + int(bis[3:]) * 60 + 59
    farben = {t["id"]: t["farbe"] for t in kontext["stamm"]["transportarten"]}
    fluesse: dict = {}
    fahrten = [f for f in e["fahrten"] if t0 <= f["geplant"] <= t1 and (not start_filter or f["start_id"] == start_filter)]
    for f in fahrten:
        gesehen = set()
        for a in f["abschnitte"]:
            if a["typ"] != "weg" or a["stockwerk_id"] != sid:
                continue
            key = tuple(sorted((a["von"], a["nach"])))
            if key in gesehen:
                continue
            gesehen.add(key)
            eintrag = fluesse.setdefault(key, {"a": a, "anzahl": 0, "farben": {}})
            eintrag["anzahl"] += 1
            eintrag["farben"][farben.get(f["transportart_id"])] = eintrag["farben"].get(farben.get(f["transportart_id"]), 0) + 1
    maximal = max([x["anzahl"] for x in fluesse.values()] or [1])
    for x in sorted(fluesse.values(), key=lambda x: x["anzahl"]):
        a = x["a"]
        farbe = _farbe(max(x["farben"].items(), key=lambda kv: kv[1])[0] or "")
        seite.draw_line((a["x0"], a["y0"]), (a["x1"], a["y1"]), color=farbe, width=e_ * (2 + 10 * x["anzahl"] / maximal), stroke_opacity=0.6, lineCap=1)

    # Punkte mit Namen
    punkt_farben = {"start": (0.17, 0.54, 0.24), "ziel": (0.79, 0.16, 0.16), "punkt": (0.11, 0.49, 0.84), "aufzug": (0.44, 0.28, 0.91), "uebergang": (0.9, 0.47, 0.0)}
    aufzuege = {a["id"]: a["name"] for a in kontext["stamm"]["aufzuege"]}
    for k in knoten.values():
        if k["art"] == "weg":
            continue
        seite.draw_circle((k["x"], k["y"]), e_ * 5, color=(1, 1, 1), fill=punkt_farben.get(k["art"], (0.3, 0.3, 0.3)), width=e_ * 1.2)
        name = k["name"] or aufzuege.get(k["aufzug_id"], "")
        if name:
            seite.insert_text((k["x"] + e_ * 7, k["y"] + e_ * 3), name, fontsize=e_ * 9, color=(0.1, 0.1, 0.1),
                              render_mode=0, fontname="Helvetica")

    # Legende rechts
    x = breite + rand * 0.08
    y = e_ * 30
    def zeile(text, groesse=10, fett=False, farbe=(0.1, 0.1, 0.1)):
        nonlocal y
        seite.insert_text((x, y), text, fontsize=e_ * groesse, fontname="Helvetica-Bold" if fett else "Helvetica", color=farbe)
        y += e_ * groesse * 1.6

    seite.draw_rect(pymupdf.Rect(breite, 0, breite + rand, hoehe), color=None, fill=(0.97, 0.98, 0.99))
    zeile("Logistik Map", 14, True, (0.12, 0.37, 0.55))
    zeile(f"{sw['kuerzel'] + ' · ' if sw['kuerzel'] else ''}{sw['teil']} - {sw['name']}", 11, True)
    zeile(f"{datetime.fromisoformat(e['datum']).strftime('%d.%m.%Y')}, {von} - {bis} Uhr")
    if szenario:
        zeile(f"Szenario: {szenario}")
    if start_filter:
        p = next((p for p in kontext["punkte"] if p["id"] == start_filter), None)
        zeile(f"Nur ab: {p['name'] if p else start_filter}")
    y += e_ * 6
    zeile(f"{len(fahrten)} Fahrten im Zeitfenster", 10, True)
    zeile("Linienbreite = Anzahl Fahrten", 8)
    for t in kontext["stamm"]["transportarten"]:
        seite.draw_line((x, y - e_ * 3), (x + e_ * 18, y - e_ * 3), color=_farbe(t["farbe"]), width=e_ * 4)
        seite.insert_text((x + e_ * 24, y), t["name"], fontsize=e_ * 9, fontname="Helvetica")
        y += e_ * 14
    y += e_ * 8
    eng = [r for r in e["ressourcen"] if (r["typ"], r["id"]) in {(z["typ"], z["id"]) for z in e["engpaesse"]}]
    if eng:
        zeile("Engpässe des Tages", 10, True, (0.79, 0.16, 0.16))
        for r in eng[:12]:
            zeile(f"{r['name']}: bis {round(r['max_wartezeit'] / 60, 1)} min Wartezeit", 8)
    y = hoehe - e_ * 20
    seite.insert_text((x, y), f"Erstellt {datetime.now():%d.%m.%Y %H:%M}", fontsize=e_ * 7, fontname="Helvetica", color=(0.4, 0.4, 0.4))
    daten = doc.tobytes(deflate=True, garbage=3)
    doc.close()
    return daten
