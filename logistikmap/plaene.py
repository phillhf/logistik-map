"""PDF-Pläne in Kartenkacheln umwandeln.

Koordinaten: Alles wird in PDF-Punkten gespeichert (x nach rechts, y nach unten,
Ursprung oben links auf der gewählten Seite). Die Karte nutzt eine eigene CRS, in der
Zoomstufe z dem Maßstab 2^(z - ZOOM_VERSATZ) Pixel pro PDF-Punkt entspricht.
Zoom 0 zeigt einen A0-Plan also etwa 210 Pixel breit, die höchste Stufe so scharf,
wie es MAX_PIXEL zulässt.

Kacheln werden als 256×256-PNG unter kacheln/<plan_id>/<z>/<x>_<y>.png abgelegt.
Reinweiße Kacheln werden nicht gespeichert, der Server liefert dafür eine leere Kachel.
"""

from __future__ import annotations

import logging
import math
import os
import queue
import re
import shutil
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pymupdf

from .config import Pfade
from .db import Datenbank

log = logging.getLogger(__name__)

KACHEL = 256
ZOOM_VERSATZ = 4
MAX_PIXEL = 16384  # längste Seite in der höchsten Zoomstufe
MAX_MASSSTAB = 8.0  # höchstens 576 dpi, mehr bringt auch bei kleinen Plänen nichts
VORSCHAU_PIXEL = 320


class PdfFehler(Exception):
    pass


def pdf_seiten(pfad: Path) -> list[dict]:
    """Seitengrößen in PDF-Punkten; wirft PdfFehler bei kaputten oder verschlüsselten Dateien."""
    try:
        doc = pymupdf.open(pfad)
    except Exception as e:  # pymupdf wirft verschiedene Fehlerklassen
        raise PdfFehler(str(e)) from e
    try:
        if doc.needs_pass:
            raise PdfFehler("verschluesselt")
        if not doc.is_pdf or doc.page_count == 0:
            raise PdfFehler("keine_seiten")
        return [{"nr": i + 1, "breite": round(p.rect.width, 2), "hoehe": round(p.rect.height, 2)} for i, p in enumerate(doc)]
    finally:
        doc.close()


_MASSSTAB_TEXT = re.compile(r"(?<![\d.,:])1\s*:\s*(\d{1,3}(?:[. ]\d{3})?|\d{2,5})(?![\d,:])")
MASSSTAB_BEREICH = (10, 5000)


def massstab_suchen(pdf: Path, seite: int) -> list[int]:
    """Maßstabsangaben wie „M 1:100“ aus dem Text der Seite, häufigste zuerst.

    Findet nur echten Text. Ist der Schriftzug als Linien gezeichnet oder der Plan
    eingescannt, bleibt die Liste leer.
    """
    try:
        doc = pymupdf.open(pdf)
    except Exception:
        return []
    try:
        if seite < 1 or seite > doc.page_count:
            return []
        text = doc[seite - 1].get_text("text")
    finally:
        doc.close()
    zaehler: dict[int, int] = {}
    for m in _MASSSTAB_TEXT.finditer(text):
        try:
            n = int(re.sub(r"[. ]", "", m.group(1)))
        except ValueError:
            continue
        if MASSSTAB_BEREICH[0] <= n <= MASSSTAB_BEREICH[1]:
            zaehler[n] = zaehler.get(n, 0) + 1
    return sorted(zaehler, key=lambda n: (-zaehler[n], n))


def max_zoom_fuer(breite: float, hoehe: float) -> int:
    laengste = max(breite, hoehe, 1.0)
    massstab = min(MAX_MASSSTAB, MAX_PIXEL / laengste)
    return max(0, ZOOM_VERSATZ + math.floor(math.log2(massstab)))


def vorschau(pdf: Path, seite: int, ziel: Path) -> Path:
    if ziel.exists():
        return ziel
    doc = pymupdf.open(pdf)
    try:
        page = doc[seite - 1]
        f = VORSCHAU_PIXEL / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(f, f), alpha=False)
        tmp = ziel.with_suffix(".tmp")
        tmp.write_bytes(pix.tobytes("png"))
        tmp.replace(ziel)
    finally:
        doc.close()
    return ziel


def kachelanzahl(breite: float, hoehe: float, max_zoom: int) -> int:
    n = 0
    for z in range(max_zoom + 1):
        s = 2.0 ** (z - ZOOM_VERSATZ)
        n += math.ceil(breite * s / KACHEL) * math.ceil(hoehe * s / KACHEL)
    return n


_LEERE_KACHEL: bytes | None = None


def leere_kachel() -> bytes:
    global _LEERE_KACHEL
    if _LEERE_KACHEL is None:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, KACHEL, KACHEL), False)
        pix.clear_with(255)
        _LEERE_KACHEL = pix.tobytes("png")
    return _LEERE_KACHEL


PARALLEL_AB = 600  # ab so vielen Kacheln auf mehrere Prozesse verteilen

_offen: dict = {}  # je Prozess: (pdf, seite) → (doc, page, displaylist)


def _seite_oeffnen(pdf: str, seite: int):
    schluessel = (pdf, seite)
    if schluessel not in _offen:
        for doc, *_ in _offen.values():
            doc.close()
        _offen.clear()
        doc = pymupdf.open(pdf)
        page = doc[seite - 1]
        _offen[schluessel] = (doc, page, page.get_displaylist(annots=False))
    return _offen[schluessel]


def _zeile_rendern(pdf: str, seite: int, ziel: str, z: int, ty: int) -> int:
    """Rendert eine Kachelzeile. Läuft im Hauptprozess oder in einem Arbeitsprozess."""
    _, page, liste = _seite_oeffnen(pdf, seite)
    s = 2.0 ** (z - ZOOM_VERSATZ)
    nx = math.ceil(page.rect.width * s / KACHEL)
    m = pymupdf.Matrix(s, s)
    ordner = Path(ziel) / str(z)
    for tx in range(nx):
        clip = pymupdf.Rect(tx * KACHEL / s, ty * KACHEL / s, (tx + 1) * KACHEL / s, (ty + 1) * KACHEL / s)
        clip &= page.rect
        pix = liste.get_pixmap(matrix=m, clip=clip, alpha=False)
        # reinweiß? (pix.is_unicolor ist in PyMuPDF 2 reines Python und sehr langsam)
        if pix.samples.strip(b"\xff"):
            if pix.width != KACHEL or pix.height != KACHEL:
                voll = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(tx * KACHEL, ty * KACHEL, (tx + 1) * KACHEL, (ty + 1) * KACHEL), False)
                voll.clear_with(255)
                voll.copy(pix, pix.irect)
                pix = voll
            (ordner / f"{tx}_{ty}.png").write_bytes(pix.tobytes("png"))
    return nx


def arbeitsprozesse() -> int:
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def kacheln_erzeugen(pdf: Path, seite: int, ziel: Path, max_zoom: int, fortschritt=None, abbruch=None, prozesse: int | None = None) -> None:
    """Erzeugt alle Kacheln einer Seite. fortschritt(anteil 0..1) wird regelmäßig aufgerufen.

    Große Pläne werden zeilenweise auf mehrere Prozesse verteilt (prozesse=None: automatisch).
    """
    doc = pymupdf.open(pdf)
    breite, hoehe = doc[seite - 1].rect.width, doc[seite - 1].rect.height
    doc.close()
    gesamt = kachelanzahl(breite, hoehe, max_zoom)
    auftraege = []
    for z in range(max_zoom + 1):
        s = 2.0 ** (z - ZOOM_VERSATZ)
        (ziel / str(z)).mkdir(parents=True, exist_ok=True)
        auftraege += [(z, ty) for ty in range(math.ceil(hoehe * s / KACHEL))]
    if prozesse is None:
        prozesse = arbeitsprozesse() if gesamt >= PARALLEL_AB else 1
    fertig = 0
    letzte_meldung = 0.0
    if prozesse <= 1:
        for z, ty in auftraege:
            if abbruch is not None and abbruch():
                return
            fertig += _zeile_rendern(str(pdf), seite, str(ziel), z, ty)
            if fortschritt is not None and time.monotonic() - letzte_meldung > 0.5:
                letzte_meldung = time.monotonic()
                fortschritt(fertig / gesamt)
        _offen.clear()
    else:
        with ProcessPoolExecutor(max_workers=prozesse) as pool:
            laufend = [pool.submit(_zeile_rendern, str(pdf), seite, str(ziel), z, ty) for z, ty in auftraege]
            for f in as_completed(laufend):
                if abbruch is not None and abbruch():
                    pool.shutdown(wait=True, cancel_futures=True)
                    return
                fertig += f.result()
                if fortschritt is not None and time.monotonic() - letzte_meldung > 0.5:
                    letzte_meldung = time.monotonic()
                    fortschritt(fertig / gesamt)
    if fortschritt is not None:
        fortschritt(1.0)


def plan_test(pdf: Path) -> dict:
    """Schnelltest für einen Plan: Seitengrößen, Zoomstufen, geschätzte Aufbereitungszeit."""
    ergebnis = {"seiten": []}
    doc = pymupdf.open(pdf)
    try:
        for i, page in enumerate(doc):
            t0 = time.monotonic()
            liste = page.get_displaylist(annots=False)
            t_liste = time.monotonic() - t0
            mz = max_zoom_fuer(page.rect.width, page.rect.height)
            s = 2.0 ** (mz - ZOOM_VERSATZ)
            # Stichprobe: Kacheln aus der Mitte der höchsten Zoomstufe
            mx, my = page.rect.width / 2, page.rect.height / 2
            t0 = time.monotonic()
            for d in range(9):
                cx, cy = mx + (d % 3 - 1) * KACHEL / s, my + (d // 3 - 1) * KACHEL / s
                liste.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=pymupdf.Rect(cx, cy, cx + KACHEL / s, cy + KACHEL / s) & page.rect, alpha=False).tobytes("png")
            je_kachel = (time.monotonic() - t0) / 9
            n = kachelanzahl(page.rect.width, page.rect.height, mz)
            ergebnis["seiten"].append({
                "nr": i + 1, "breite_mm": round(page.rect.width / 72 * 25.4), "hoehe_mm": round(page.rect.height / 72 * 25.4),
                "max_zoom": mz, "kacheln": n, "einlesen_s": round(t_liste, 2), "ms_je_kachel": round(je_kachel * 1000, 1),
                "geschaetzt_s": round(t_liste + n * je_kachel / max(1, arbeitsprozesse() if n >= PARALLEL_AB else 1), 1),
            })
    finally:
        doc.close()
    return ergebnis


class KachelDienst:
    """Ein Hintergrund-Thread, der Pläne nacheinander in Kacheln umwandelt."""

    def __init__(self, db: Datenbank, pfade: Pfade):
        self.db = db
        self.pfade = pfade
        self._warteschlange: queue.Queue[int | None] = queue.Queue()
        self._abgebrochen: set[int] = set()
        self._stopp = threading.Event()
        self._thread: threading.Thread | None = None

    def starten(self) -> None:
        if self._thread is not None:
            return
        self._stopp.clear()
        self._warteschlange = queue.Queue()
        self._thread = threading.Thread(target=self._schleife, name="kacheln", daemon=True)
        self._thread.start()
        # nach einem Neustart unfertige Pläne wieder aufnehmen
        for row in self.db.alle("SELECT id FROM plaene WHERE status IN ('wartet', 'laeuft') ORDER BY id"):
            self.einreihen(row["id"])

    def stoppen(self) -> None:
        if self._thread is not None:
            self._stopp.set()  # laufende Erzeugung bricht ab und bleibt 'laeuft' → beim nächsten Start weiter
            self._warteschlange.put(None)
            self._thread.join(timeout=30)
            self._thread = None

    def einreihen(self, plan_id: int) -> None:
        self._abgebrochen.discard(plan_id)
        self.db.ausfuehren("UPDATE plaene SET status = 'wartet', fortschritt = 0, fehler = NULL WHERE id = ?", (plan_id,))
        self._warteschlange.put(plan_id)

    def abbrechen(self, plan_id: int) -> None:
        self._abgebrochen.add(plan_id)

    def ordner(self, plan_id: int) -> Path:
        return self.pfade.kacheln / str(plan_id)

    def warte_bis_leer(self, timeout: float = 60) -> None:
        """Nur für Tests."""
        import time

        ende = time.monotonic() + timeout
        while time.monotonic() < ende:
            offen = self.db.eins("SELECT COUNT(*) AS n FROM plaene WHERE status IN ('wartet', 'laeuft')")
            if offen["n"] == 0 and self._warteschlange.empty():
                return
            time.sleep(0.05)
        raise TimeoutError("Kacheln nicht rechtzeitig fertig")

    def _schleife(self) -> None:
        while True:
            plan_id = self._warteschlange.get()
            if plan_id is None:
                return
            if plan_id in self._abgebrochen:
                continue
            try:
                self._erzeugen(plan_id)
            except Exception as e:
                log.exception("Kacheln für Plan %s fehlgeschlagen", plan_id)
                self.db.ausfuehren("UPDATE plaene SET status = 'fehler', fehler = ? WHERE id = ?", (str(e)[:500], plan_id))

    def _erzeugen(self, plan_id: int) -> None:
        plan = self.db.eins("SELECT * FROM plaene WHERE id = ?", (plan_id,))
        if plan is None or plan["status"] == "fertig":
            return
        pdf = self.pfade.dokumente / f"{plan['dokument_id']}.pdf"
        ziel = self.ordner(plan_id)
        if ziel.exists():
            shutil.rmtree(ziel)
        self.db.ausfuehren("UPDATE plaene SET status = 'laeuft', fortschritt = 0 WHERE id = ?", (plan_id,))

        def fortschritt(anteil: float) -> None:
            self.db.ausfuehren("UPDATE plaene SET fortschritt = ? WHERE id = ?", (round(anteil, 4), plan_id))

        kacheln_erzeugen(
            pdf,
            plan["seite"],
            ziel,
            plan["max_zoom"],
            fortschritt,
            abbruch=lambda: plan_id in self._abgebrochen or self._stopp.is_set(),
        )
        if self._stopp.is_set():
            return
        if plan_id in self._abgebrochen:
            shutil.rmtree(ziel, ignore_errors=True)
            return
        self.db.ausfuehren("UPDATE plaene SET status = 'fertig', fortschritt = 1 WHERE id = ?", (plan_id,))
        log.info("Plan %s fertig (%s)", plan_id, ziel)
