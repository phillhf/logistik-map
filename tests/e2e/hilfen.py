"""Hilfsfunktionen für die Oberflächentests."""

import os
from pathlib import Path


def bildschirm(page, x: float, y: float) -> tuple[float, float]:
    """Planpunkt (PDF-Punkte) → Bildschirmposition auf der Karte."""
    return tuple(page.evaluate(
        """([x, y]) => { const k = window.__logistikKarte.karte; const p = k.latLngToContainerPoint([y, x]);
             const r = k.getContainer().getBoundingClientRect(); return [r.left + p.x, r.top + p.y]; }""",
        [x, y],
    ))


def karte_bereit(page) -> None:
    page.wait_for_function("window.__logistikKarte && window.__logistikKarte.karte && window.__logistikKarte.netz.knoten.length > 0")
    page.wait_for_timeout(400)


def screenshot(page, name: str) -> None:
    if os.environ.get("SCREENSHOTS"):
        # Kontrollbilder der Tests – die Bilder der README erzeugt werkzeuge/screenshots.py
        ziel = Path(__file__).resolve().parents[2] / "test-results" / "bilder"
        ziel.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ziel / f"{name}.png"))
