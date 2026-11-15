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
import queue
import shutil
import threading
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


def kacheln_erzeugen(pdf: Path, seite: int, ziel: Path, max_zoom: int, fortschritt=None, abbruch=None) -> None:
    """Erzeugt alle Kacheln einer Seite. fortschritt(anteil 0..1) wird regelmäßig aufgerufen."""
    doc = pymupdf.open(pdf)
    try:
        page = doc[seite - 1]
        breite, hoehe = page.rect.width, page.rect.height
        liste = page.get_displaylist(annots=False)
        gesamt = kachelanzahl(breite, hoehe, max_zoom)
        fertig = 0
        for z in range(max_zoom + 1):
            s = 2.0 ** (z - ZOOM_VERSATZ)
            ordner = ziel / str(z)
            ordner.mkdir(parents=True, exist_ok=True)
            nx, ny = math.ceil(breite * s / KACHEL), math.ceil(hoehe * s / KACHEL)
            m = pymupdf.Matrix(s, s)
            for ty in range(ny):
                for tx in range(nx):
                    if abbruch is not None and abbruch():
                        return
                    clip = pymupdf.Rect(tx * KACHEL / s, ty * KACHEL / s, (tx + 1) * KACHEL / s, (ty + 1) * KACHEL / s)
                    clip &= page.rect
                    pix = liste.get_pixmap(matrix=m, clip=clip, alpha=False)
                    # reinweiß? (pix.is_unicolor ist in PyMuPDF 2 reines Python und sehr langsam)
                    if pix.samples.strip(b"\xff"):
                        if pix.width != KACHEL or pix.height != KACHEL:
                            voll = pymupdf.Pixmap(
                                pymupdf.csRGB,
                                pymupdf.IRect(tx * KACHEL, ty * KACHEL, (tx + 1) * KACHEL, (ty + 1) * KACHEL),
                                False,
                            )
                            voll.clear_with(255)
                            voll.copy(pix, pix.irect)
                            pix = voll
                        (ordner / f"{tx}_{ty}.png").write_bytes(pix.tobytes("png"))
                    fertig += 1
                    if fortschritt is not None and fertig % 25 == 0:
                        fortschritt(fertig / gesamt)
        if fortschritt is not None:
            fortschritt(1.0)
    finally:
        doc.close()


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
