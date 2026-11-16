"""Maßstab als „1 : N“ eintragen und aus dem Plantext vorschlagen."""

import pymupdf
import pytest

from logistikmap.plaene import massstab_suchen


def _pdf(tmp_path, *texte):
    doc = pymupdf.open()
    page = doc.new_page(width=1190, height=842)
    for i, text in enumerate(texte):
        page.insert_text((40, 60 + 30 * i), text, fontsize=12)
    pfad = tmp_path / "plan.pdf"
    doc.save(pfad)
    doc.close()
    return pfad


@pytest.mark.parametrize(
    ("texte", "erwartet"),
    [
        (["M 1:100"], [100]),
        (["Maßstab 1 : 200", "Detail M 1:50", "M 1:200"], [200, 50]),
        (["M. 1:1.000"], [1000]),
        (["Plot 12:30 Uhr", "Gefälle 1:2", "Raum 1.12"], []),
        (["1:500"], [500]),
    ],
)
def test_massstab_suchen(tmp_path, texte, erwartet):
    assert massstab_suchen(_pdf(tmp_path, *texte), 1) == erwartet


def test_massstab_suchen_falsche_seite(tmp_path):
    assert massstab_suchen(_pdf(tmp_path, "M 1:100"), 3) == []


def test_verhaeltnis_eintragen(admin, tmp_path):
    gid = admin.post("/api/gebaeudeteile", json={"name": "Haus A"}).json()["id"]
    sid = admin.post("/api/stockwerke", json={"gebaeudeteil_id": gid, "name": "EG", "ebene": 0}).json()["id"]
    assert admin.get(f"/api/stockwerke/{sid}/massstab-vorschlag").json() == {"gefunden": []}
    pdf = _pdf(tmp_path, "Erdgeschoss", "M 1:100").read_bytes()
    did = admin.post("/api/dokumente", files={"datei": ("eg.pdf", pdf, "application/pdf")}).json()["id"]
    admin.put(f"/api/stockwerke/{sid}/plan", json={"dokument_id": did, "seite": 1})
    assert admin.get(f"/api/stockwerke/{sid}/massstab-vorschlag").json() == {"gefunden": [100]}

    r = admin.put(f"/api/stockwerke/{sid}/massstab", json={"verhaeltnis": 100})
    assert r.status_code == 200
    # 1 PDF-Punkt = 0,3528 mm auf Papier, bei 1:100 also 3,528 cm
    assert r.json()["meter_pro_punkt"] == pytest.approx(0.035278, rel=1e-4)
    assert admin.get(f"/api/stockwerke/{sid}").json()["meter_pro_punkt"] == pytest.approx(0.035278, rel=1e-4)
    assert admin.put(f"/api/stockwerke/{sid}/massstab", json={"verhaeltnis": 0}).status_code == 422
