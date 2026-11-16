"""Sammelt die Lizenzen aller mitgelieferten Bestandteile in eine Datei (THIRD_PARTY_LICENSES.txt).

Aufruf: python installer/lizenzen.py ZIEL.txt [--toc PYZ-00.toc --paket _internal] [Lizenzdatei=Name ...]

Mit --toc/--paket werden genau die Python-Pakete erfasst, die PyInstaller ins Paket gepackt hat
(Modulliste der Analyse und Ordner im Paket). Ohne diese Angaben: requirements.txt samt Abhängigkeiten.
Dazu kommen Python selbst, Leaflet und zusätzlich übergebene Dateien (z. B. WinSW).
"""

from __future__ import annotations

import importlib.metadata as md
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent


def anforderungen(datei: Path) -> list[str]:
    namen = []
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        zeile = zeile.split("#")[0].strip()
        if zeile and not zeile.startswith("-"):
            namen.append(re.split(r"[<>=!~\[; ]", zeile)[0])
    return namen


def abhaengigkeiten(start: list[str]) -> list[md.Distribution]:
    gesehen: dict[str, md.Distribution] = {}
    offen = list(start)
    while offen:
        name = offen.pop()
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        schluessel = dist.metadata["Name"].lower()
        if schluessel in gesehen:
            continue
        gesehen[schluessel] = dist
        for req in dist.requires or []:
            if "extra ==" in req:
                continue  # optionale Extras werden nicht mitgeliefert
            offen.append(re.split(r"[<>=!~\[; (]", req)[0])
    return sorted(gesehen.values(), key=lambda d: d.metadata["Name"].lower())


def aus_paket(toc: Path, paket: Path) -> list[md.Distribution]:
    """Distributionen, deren Module tatsächlich im PyInstaller-Paket stecken."""
    oben: set[str] = set()
    for name, pfad in re.findall(r"\('([\w.]+)',\s*((?:'[^']*'\s*)+),\s*'(?:PYMODULE|EXTENSION)'", toc.read_text(encoding="utf-8")):
        if "site-packages" in pfad:
            oben.add(name.split(".")[0])
    oben |= {d.name for d in paket.iterdir() if d.is_dir()}
    zuordnung = md.packages_distributions()
    namen = {dist for modul in oben for dist in zuordnung.get(modul, [])}
    ergebnis = []
    for n in sorted(namen, key=str.lower):
        try:
            ergebnis.append(md.distribution(n))
        except md.PackageNotFoundError:
            pass
    return ergebnis


def lizenztexte(dist: md.Distribution) -> list[str]:
    texte = []
    for datei in dist.files or []:
        name = datei.name.upper()
        if any(name.startswith(p) for p in ("LICENSE", "LICENCE", "COPYING", "NOTICE")) or "/licenses/" in str(datei).replace("\\", "/"):
            try:
                texte.append(Path(datei.locate()).read_text(encoding="utf-8", errors="replace").replace(chr(0), "").strip())
            except (OSError, FileNotFoundError):
                pass
    return texte


def main(argv: list[str]) -> int:
    ziel = Path(argv[1])
    rest = argv[2:]
    toc = paket = None
    if "--toc" in rest:
        i = rest.index("--toc")
        toc = Path(rest[i + 1])
        del rest[i : i + 2]
    if "--paket" in rest:
        i = rest.index("--paket")
        paket = Path(rest[i + 1])
        del rest[i : i + 2]
    teile = [
        "Logistik Map – Lizenzen der mitgelieferten Bestandteile / third-party licenses",
        "Logistik Map selbst steht unter der GNU Affero General Public License v3.0 (siehe LICENSE).",
        "",
    ]

    def abschnitt(titel: str, text: str) -> None:
        teile.extend(["=" * 78, titel, "=" * 78, text.strip(), ""])

    dists = aus_paket(toc, paket) if toc and paket else abhaengigkeiten(anforderungen(WURZEL / "requirements.txt"))
    for dist in dists:
        m = dist.metadata
        kopf = f"{m['Name']} {dist.version}"
        lizenz = m.get("License-Expression") or m.get("License") or ", ".join(
            k.split("::")[-1].strip() for k in m.get_all("Classifier") or [] if k.startswith("License ::")
        )
        texte = lizenztexte(dist)
        abschnitt(kopf, f"Lizenz: {lizenz or 'siehe Text'}\nQuelle: {m.get('Home-page') or m.get('Project-URL', '')}\n\n" + ("\n\n".join(texte) or "(kein Lizenztext im Paket enthalten)"))

    python_lizenz = Path(sys.base_prefix) / "LICENSE.txt"
    if python_lizenz.exists():
        abschnitt(f"Python {sys.version.split()[0]}", python_lizenz.read_text(encoding="utf-8", errors="replace"))
    abschnitt("Leaflet 1.9.4", (WURZEL / "logistikmap" / "static" / "vendor" / "leaflet" / "LICENSE").read_text(encoding="utf-8"))
    for zusatz in rest:
        datei, _, name = zusatz.partition("=")
        abschnitt(name or Path(datei).name, Path(datei).read_text(encoding="utf-8-sig", errors="replace"))

    ziel.write_text("\n".join(teile), encoding="utf-8")
    print(f"{ziel}: {len(teile)} Zeilen")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
