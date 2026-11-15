// Editor auf der Karte: Bereiche, Räume, Punkte und Wegenetz einzeichnen und bearbeiten.

import { api, bestaetigen, fehlerMelden, formularDialog, h, leeren, melden, punktAuswahl, stammdaten, t, zahl } from "./basis.js";
import { abstand, ll, xy } from "./karte.js";

const FARBEN = [
  ["", "editor.farbe.standard"],
  ["#1f5f8b", "editor.farbe.blau"],
  ["#2b8a3e", "editor.farbe.gruen"],
  ["#e67700", "editor.farbe.orange"],
  ["#c92a2a", "editor.farbe.rot"],
  ["#7048e8", "editor.farbe.lila"],
  ["#495057", "editor.farbe.grau"],
];
const PUNKT_ARTEN = ["start", "ziel", "punkt", "aufzug", "uebergang"];
const FANG_KNOTEN = 14; // Pixel
const FANG_KANTE = 10;
const WINKEL_FANG = 8; // Grad: fast waagerecht/senkrecht wird gerade gezogen

export function starteEditor(ctx) {
  const { karte, werkzeugleiste, panel } = ctx;
  let werkzeug = null;
  let werkzeugName = "auswahl";
  const sid = ctx.stockwerk.id;

  const WERKZEUGE = [
    ["auswahl", "editor.werkzeug.auswahl", null],
    ["weg", "editor.werkzeug.weg", wegWerkzeug],
    ["punkt", "editor.werkzeug.punkt", punktWerkzeug],
    ["raum_rechteck", "editor.werkzeug.raum_rechteck", () => flaechenWerkzeug("raum", true)],
    ["raum", "editor.werkzeug.raum", () => flaechenWerkzeug("raum", false)],
    ["bereich", "editor.werkzeug.bereich", () => flaechenWerkzeug("bereich", false)],
    ["ausrichten", "editor.werkzeug.ausrichten", ausrichtenWerkzeug],
  ];
  const eckenEbene = L.layerGroup().addTo(karte);

  function leisteZeichnen() {
    leeren(
      werkzeugleiste,
      WERKZEUGE.map(([name, text]) =>
        h("button", { type: "button", class: name === werkzeugName ? "aktiv" : "", onclick: () => wechseln(name) }, t(text))
      ),
      h("span.trenner"),
      h("button", { type: "button", title: t("editor.rueckgaengig_hilfe"), onclick: rueckgaengig }, "↶ " + t("editor.rueckgaengig")),
      ctx.stockwerk.meter_pro_punkt ? null : h("span.warnung", t("editor.massstab_zuerst"))
    );
    werkzeugleiste.hidden = false;
  }

  function wechseln(name) {
    eckenEbene?.clearLayers();
    werkzeug?.beenden();
    werkzeug = null;
    werkzeugName = name;
    const fabrik = WERKZEUGE.find((w) => w[0] === name)[2];
    if (fabrik) werkzeug = fabrik();
    else ctx.hinweis(t("editor.hilfe.auswahl"));
    leisteZeichnen();
  }
  ctx.editorWerkzeugBeenden = () => wechseln("auswahl");

  // ---------------------------------------------------------------- Fangen
  function naechsterKnoten(p, px = FANG_KNOTEN, ohne = null) {
    let beste = null;
    for (const k of ctx.netz.knoten) {
      if (k.id === ohne) continue;
      const d = ctx.pixel(p, k);
      if (d <= px && (!beste || d < beste.d)) beste = { k, d };
    }
    return beste?.k ?? null;
  }

  function naechsteKante(p, px = FANG_KANTE) {
    let beste = null;
    for (const e of ctx.netz.kanten) {
      const a = ctx.knotenNachId(e.von);
      const b = ctx.knotenNachId(e.nach);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const l2 = dx * dx + dy * dy || 1;
      const tt = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2));
      const q = { x: a.x + tt * dx, y: a.y + tt * dy };
      const d = ctx.pixel(p, q);
      if (d <= px && (!beste || d < beste.d)) beste = { kante: e, punkt: q, d };
    }
    return beste;
  }

  function geradeZiehen(von, p) {
    if (!von) return p;
    const winkel = (Math.atan2(p.y - von.y, p.x - von.x) * 180) / Math.PI;
    const w = ((winkel % 180) + 180) % 180;
    if (Math.min(w, 180 - w) < WINKEL_FANG) return { x: p.x, y: von.y };
    if (Math.abs(w - 90) < WINKEL_FANG) return { x: von.x, y: p.y };
    return p;
  }

  /** Knoten an Position p: vorhandenen fangen, Kante teilen oder neuen Wegknoten setzen. */
  async function knotenAn(p) {
    const k = naechsterKnoten(p);
    if (k) return k.id;
    const e = naechsteKante(p);
    if (e) return (await api(`kanten/${e.kante.id}/teilen`, { methode: "POST", daten: e.punkt })).id;
    return (await api("knoten", { methode: "POST", daten: { stockwerk_id: sid, x: p.x, y: p.y, art: "weg" } })).id;
  }

  // ---------------------------------------------------------------- Klicks auf Elemente
  ctx.beiKlick = ({ typ, objekt, ereignis }) => {
    if (werkzeug?.objektKlick) return werkzeug.objektKlick(typ, objekt, ereignis);
    if (werkzeugName !== "auswahl") return;
    L.DomEvent.stopPropagation(ereignis);
    auswaehlen({ typ, id: objekt.id });
  };

  ctx.beiVerschieben = async (k, p) => {
    try {
      await api(`knoten/${k.id}`, { methode: "PUT", daten: { x: p.x, y: p.y } });
      await ctx.netzLaden();
      if (ctx.auswahl) auswaehlen(ctx.auswahl);
    } catch (e) {
      fehlerMelden(e);
      ctx.zeichnen();
    }
  };

  function auswaehlen(a) {
    ctx.auswahl = a;
    ctx.zeichnen();
    panelZeigen();
    eckenZeigen();
  }

  function abwaehlen() {
    ctx.auswahl = null;
    panel.hidden = true;
    eckenEbene.clearLayers();
    ctx.zeichnen();
  }

  // ---------------------------------------------------------------- Rückgängig
  async function rueckgaengig() {
    try {
      const r = await api(`stockwerke/${sid}/rueckgaengig`, { methode: "POST" });
      const was = t(`editor.verlauf.${r.beschreibung}`);
      melden(t("editor.rueckgaengig_ok", { was: was.startsWith("⟨") ? r.beschreibung : was }));
      ctx.auswahl = null;
      panel.hidden = true;
      eckenEbene.clearLayers();
      await ctx.netzLaden();
      ctx.punkte = await api("punkte");
    } catch (e) {
      fehlerMelden(e);
    }
  }

  // ---------------------------------------------------------------- Ecken einer Fläche bearbeiten
  function eckenZeigen() {
    eckenEbene.clearLayers();
    const a = ctx.auswahl;
    if (!a || a.typ !== "flaeche" || werkzeugName !== "auswahl") return;
    const f = ctx.netz.flaechen.find((x) => x.id === a.id);
    if (!f) return;
    const punkte = f.punkte.map(([x, y]) => ({ x, y }));
    const speichern = async (neu) => {
      try {
        await api(`flaechen/${f.id}`, { methode: "PUT", daten: { punkte: neu.map((q) => [q.x, q.y]) } });
        await ctx.netzLaden();
        auswaehlen(a);
      } catch (e) {
        fehlerMelden(e);
        auswaehlen(a);
      }
    };
    punkte.forEach((q, i) => {
      const m = L.marker(ll(q.x, q.y), { draggable: true, icon: L.divIcon({ className: "ecke", iconSize: [12, 12] }), title: t("editor.ecke_hilfe"), zIndexOffset: 1000 });
      m.on("dragend", (e) => {
        const neu = punkte.slice();
        neu[i] = xy(e.target.getLatLng());
        speichern(neu);
      });
      m.on("contextmenu dblclick", (e) => {
        L.DomEvent.stop(e);
        if (punkte.length <= 3) return melden(t("fehler.zu_wenige_punkte"), "fehler");
        speichern(punkte.filter((_, j) => j !== i));
      });
      m.addTo(eckenEbene);
      // Mittelpunkt zur nächsten Ecke: ziehen fügt eine neue Ecke ein
      const n = punkte[(i + 1) % punkte.length];
      const mitte = L.marker(ll((q.x + n.x) / 2, (q.y + n.y) / 2), { draggable: true, icon: L.divIcon({ className: "ecke mitte", iconSize: [10, 10] }), title: t("editor.ecke_einfuegen"), zIndexOffset: 900 });
      mitte.on("dragend", (e) => {
        const neu = punkte.slice();
        neu.splice(i + 1, 0, xy(e.target.getLatLng()));
        speichern(neu);
      });
      mitte.addTo(eckenEbene);
    });
  }

  // ---------------------------------------------------------------- Werkzeug: Ausrichten (neuer Planstand)
  function ausrichtenWerkzeug() {
    const paare = [];
    let alt = null;
    const ebene = L.layerGroup().addTo(karte);
    karte.getContainer().classList.add("fadenkreuz");
    const hinweisNeu = () =>
      ctx.hinweis(
        alt ? t("editor.hilfe.ausrichten_neu") : t("editor.hilfe.ausrichten_alt", { anzahl: paare.length }),
        [
          ...(paare.length >= 2 ? [[t("editor.ausrichten_anwenden", { anzahl: paare.length }), anwenden]] : []),
          [t("karte.werkzeug_beenden"), () => wechseln("auswahl")],
        ]
      );
    const zeichnen = () => {
      ebene.clearLayers();
      for (const [a, b] of paare) {
        L.polyline([ll(a.x, a.y), ll(b.x, b.y)], { color: "#c2255c", weight: 2, dashArray: "4 4", interactive: false }).addTo(ebene);
        L.circleMarker(ll(a.x, a.y), { radius: 5, color: "#c2255c", fillOpacity: 0, interactive: false }).addTo(ebene);
        L.circleMarker(ll(b.x, b.y), { radius: 5, color: "#c2255c", fillColor: "#c2255c", fillOpacity: 1, interactive: false }).addTo(ebene);
      }
      if (alt) L.circleMarker(ll(alt.x, alt.y), { radius: 6, color: "#c2255c", fillOpacity: 0, weight: 3, interactive: false }).addTo(ebene);
    };
    const klick = (p) => {
      if (!alt) {
        // alte Lage: auf vorhandene Punkte oder Flächenecken fangen
        const k = naechsterKnoten(p);
        let fang = k ? { x: k.x, y: k.y } : null;
        if (!fang) {
          for (const f of ctx.netz.flaechen) for (const [x, y] of f.punkte) if (ctx.pixel(p, { x, y }) < FANG_KNOTEN) fang = { x, y };
        }
        alt = fang || p;
      } else {
        paare.push([alt, p]);
        alt = null;
      }
      zeichnen();
      hinweisNeu();
    };
    const mapKlick = (e) => klick(xy(e.latlng));
    const tasteA = (e) => {
      if (e.key === "Escape") alt ? ((alt = null), zeichnen(), hinweisNeu()) : wechseln("auswahl");
    };
    async function anwenden() {
      try {
        const r = await api(`stockwerke/${sid}/ausrichten`, {
          methode: "POST",
          daten: { paare: paare.map(([a, b]) => ({ alt_x: a.x, alt_y: a.y, neu_x: b.x, neu_y: b.y })) },
        });
        melden(t("editor.ausrichten_ok", { faktor: zahl(r.massstab, 3) }));
        wechseln("auswahl");
        ctx.stockwerk = await api(`stockwerke/${sid}`);
        await ctx.netzLaden();
      } catch (e) {
        fehlerMelden(e);
      }
    }
    karte.on("click", mapKlick);
    document.addEventListener("keydown", tasteA);
    hinweisNeu();
    return {
      objektKlick(typ, objekt, ereignis) {
        if (typ === "knoten") {
          L.DomEvent.stopPropagation(ereignis);
          klick({ x: objekt.x, y: objekt.y });
        }
      },
      beenden() {
        karte.off("click", mapKlick);
        document.removeEventListener("keydown", tasteA);
        ebene.remove();
        karte.getContainer().classList.remove("fadenkreuz");
        ctx.hinweisWeg();
      },
    };
  }

  const kartenKlick = () => {
    if (werkzeugName === "auswahl" && ctx.auswahl) abwaehlen();
  };
  karte.on("click", kartenKlick);

  const taste = async (e) => {
    if (e.target.closest?.("input, textarea, select, dialog")) return;
    if (e.key === "Delete" && ctx.auswahl && werkzeugName === "auswahl") loeschen(ctx.auswahl);
    if (e.key === "Escape" && werkzeugName === "auswahl" && ctx.auswahl) abwaehlen();
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      rueckgaengig();
    }
  };
  document.addEventListener("keydown", taste);

  // ---------------------------------------------------------------- Werkzeug: Weg
  function wegWerkzeug() {
    let letzter = null;
    let arbeitet = false;
    const vorschau = L.polyline([], { color: "#f08c00", weight: 3, dashArray: "6 6", interactive: false }).addTo(karte);
    karte.getContainer().classList.add("fadenkreuz");
    ctx.hinweis(t("editor.hilfe.weg"), [[t("karte.werkzeug_beenden"), () => wechseln("auswahl")]]);

    async function klick(latlng) {
      if (arbeitet) return;
      arbeitet = true;
      try {
        const von = letzter ? ctx.knotenNachId(letzter) : null;
        const p = geradeZiehen(von, xy(latlng));
        const id = await knotenAn(p);
        if (letzter && letzter !== id) await api("kanten", { methode: "POST", daten: { von: letzter, nach: id } });
        letzter = id;
        await ctx.netzLaden();
      } catch (e) {
        fehlerMelden(e);
      } finally {
        arbeitet = false;
      }
    }
    const mapKlick = (e) => klick(e.latlng);
    const bewegen = (e) => {
      const von = letzter ? ctx.knotenNachId(letzter) : null;
      if (!von) return vorschau.setLatLngs([]);
      const p = geradeZiehen(von, xy(e.latlng));
      const fang = naechsterKnoten(p);
      vorschau.setLatLngs([ll(von.x, von.y), fang ? ll(fang.x, fang.y) : ll(p.x, p.y)]);
    };
    const ende = () => {
      if (letzter === null) wechseln("auswahl");
      letzter = null;
      vorschau.setLatLngs([]);
    };
    const tasteWeg = (e) => e.key === "Escape" && ende();
    karte.on("click", mapKlick).on("mousemove", bewegen).on("dblclick", ende);
    document.addEventListener("keydown", tasteWeg);
    return {
      objektKlick(typ, objekt, ereignis) {
        if (typ === "knoten") {
          L.DomEvent.stopPropagation(ereignis);
          klick(ll(objekt.x, objekt.y));
        }
      },
      beenden() {
        karte.off("click", mapKlick).off("mousemove", bewegen).off("dblclick", ende);
        document.removeEventListener("keydown", tasteWeg);
        vorschau.remove();
        karte.getContainer().classList.remove("fadenkreuz");
        ctx.hinweisWeg();
      },
    };
  }

  // ---------------------------------------------------------------- Werkzeug: Punkt
  function punktWerkzeug() {
    karte.getContainer().classList.add("fadenkreuz");
    ctx.hinweis(t("editor.hilfe.punkt"), [[t("karte.werkzeug_beenden"), () => wechseln("auswahl")]]);
    const mapKlick = async (e) => {
      const p = xy(e.latlng);
      await punktAnlegen(p);
    };
    karte.on("click", mapKlick);
    return {
      objektKlick(typ, objekt, ereignis) {
        if (typ === "knoten") {
          L.DomEvent.stopPropagation(ereignis);
          auswaehlen({ typ: "knoten", id: objekt.id });
          wechseln("auswahl");
        }
      },
      beenden() {
        karte.off("click", mapKlick);
        karte.getContainer().classList.remove("fadenkreuz");
        ctx.hinweisWeg();
      },
    };
  }

  function aufzugOptionen() {
    return [["", t("editor.kein_aufzug")], ...ctx.stamm.aufzuege.map((a) => [a.id, `${a.name} (${t(`aufzug.art.${a.art}`)})`]), ["neu", t("editor.aufzug_neu")], ["neu_treppe", t("editor.treppe_neu")]];
  }

  async function aufzugWert(wert, name) {
    if (wert === "neu" || wert === "neu_treppe") {
      const art = wert === "neu" ? "aufzug" : "treppe";
      const anzahl = ctx.stamm.aufzuege.filter((a) => a.art === art).length + 1;
      const r = await api("aufzuege", {
        methode: "POST",
        daten: {
          name: name || `${t(`aufzug.art.${art}`)} ${anzahl}`,
          art,
          plaetze: art === "aufzug" ? 2 : 0,
          fahrzeit_etage: art === "aufzug" ? 8 : 20,
          tuerzeit: art === "aufzug" ? 10 : 0,
          raeumzeit: art === "aufzug" ? 20 : 0,
          anfahrt: art === "aufzug" ? 30 : 0,
          transportarten: [],
        },
      });
      ctx.stamm = await stammdaten(true);
      melden(t("editor.aufzug_angelegt"));
      return r.id;
    }
    return wert === "" || wert === null ? null : Number(wert);
  }

  async function punktAnlegen(p) {
    const ergebnis = await formularDialog({
      titel: t("editor.punkt_neu"),
      felder: [
        { name: "art", label: t("knoten.art_label"), typ: "auswahl", wert: "punkt", optionen: PUNKT_ARTEN.map((a) => [a, t(`knoten.art.${a}`)]) },
        { name: "name", label: t("knoten.name"), pflicht: true, attr: { maxlength: 100 } },
        { name: "aufzug", label: t("knoten.aufzug"), typ: "auswahl", wert: "", optionen: aufzugOptionen(), hilfe: t("editor.aufzug_hilfe") },
        { name: "kapazitaet", label: t("knoten.kapazitaet"), typ: "number", attr: { min: 1 }, hilfe: t("knoten.kapazitaet_hilfe") },
        { name: "verbinden", label: t("editor.mit_weg_verbinden"), typ: "haken", wert: true },
      ],
      speichern: async (w) => {
        if (w.art === "aufzug" && !w.aufzug) throw new Error(t("editor.aufzug_waehlen"));
        const aufzug_id = await aufzugWert(w.aufzug, w.art === "aufzug" ? null : null);
        const neu = await api("knoten", {
          methode: "POST",
          daten: { stockwerk_id: sid, x: p.x, y: p.y, art: w.art, name: w.name, aufzug_id, kapazitaet: w.kapazitaet || null },
        });
        if (w.verbinden) await anschliessen(neu.id, p);
        return neu;
      },
    });
    if (ergebnis) {
      await ctx.netzLaden();
      ctx.punkte = await api("punkte");
    }
  }

  /** Neuen Punkt mit dem nächsten Weg verbinden (Knoten fangen oder Kante teilen). */
  async function anschliessen(id, p) {
    const k = naechsterKnoten(p, 60, id);
    const e = naechsteKante(p, 120);
    let ziel = null;
    if (k && (!e || ctx.pixel(p, k) <= e.d + 4)) ziel = k.id;
    else if (e) ziel = (await api(`kanten/${e.kante.id}/teilen`, { methode: "POST", daten: e.punkt })).id;
    if (ziel && ziel !== id) await api("kanten", { methode: "POST", daten: { von: id, nach: ziel } });
    else melden(t("editor.kein_weg_in_der_naehe"), "fehler");
  }

  // ---------------------------------------------------------------- Werkzeug: Flächen
  function flaechenWerkzeug(art, rechteck) {
    const punkte = [];
    const form = L.polygon([], { color: "#f08c00", weight: 2, dashArray: "6 4", fillOpacity: 0.1, interactive: false }).addTo(karte);
    const ecken = L.layerGroup().addTo(karte);
    karte.getContainer().classList.add("fadenkreuz");
    ctx.hinweis(t(rechteck ? "editor.hilfe.rechteck" : "editor.hilfe.vieleck"), [[t("karte.werkzeug_beenden"), () => wechseln("auswahl")]]);

    const zeichne = (maus) => {
      let pp = [...punkte];
      if (rechteck && punkte.length === 1 && maus) pp = rechteckAus(punkte[0], maus);
      else if (maus) pp.push(maus);
      form.setLatLngs(pp.map((q) => ll(q.x, q.y)));
    };
    const rechteckAus = (a, b) => [a, { x: b.x, y: a.y }, b, { x: a.x, y: b.y }];

    const fertig = async () => {
      const pp = rechteck ? rechteckAus(punkte[0], punkte[1]) : [...punkte];
      zuruecksetzen();
      if (pp.length < 3) return;
      const ok = await formularDialog({
        titel: t(`editor.${art}_neu`),
        felder: [
          { name: "name", label: t("flaeche.name"), pflicht: true },
          { name: "nummer", label: t("flaeche.nummer") },
          { name: "art", label: t("flaeche.art"), typ: "auswahl", wert: art, optionen: [["raum", t("flaeche.raum")], ["bereich", t("flaeche.bereich")]] },
          { name: "farbe", label: t("flaeche.farbe"), typ: "auswahl", wert: "", optionen: FARBEN.map(([w, k]) => [w, t(k)]) },
        ],
        speichern: (w) => api("flaechen", { methode: "POST", daten: { stockwerk_id: sid, ...w, punkte: pp.map((q) => [q.x, q.y]) } }),
      });
      if (ok) {
        await ctx.netzLaden();
        ctx.punkte = await api("punkte");
      }
    };

    const zuruecksetzen = () => {
      punkte.length = 0;
      ecken.clearLayers();
      form.setLatLngs([]);
    };

    const klick = (e) => {
      const p = xy(e.latlng);
      if (!rechteck && punkte.length >= 3 && ctx.pixel(p, punkte[0]) < 12) return fertig();
      punkte.push(punkte.length && !rechteck ? geradeZiehen(punkte.at(-1), p) : p);
      L.circleMarker(e.latlng, { radius: 4, color: "#f08c00", fillOpacity: 1, interactive: false }).addTo(ecken);
      zeichne();
      if (rechteck && punkte.length === 2) fertig();
    };
    const bewegen = (e) => {
      if (!punkte.length) return;
      const p = xy(e.latlng);
      zeichne(rechteck ? p : geradeZiehen(punkte.at(-1), p));
    };
    const doppel = () => {
      if (!rechteck && punkte.length >= 3) fertig();
    };
    const tasteF = (e) => {
      if (e.key === "Escape") punkte.length ? zuruecksetzen() : wechseln("auswahl");
      if (e.key === "Backspace" && punkte.length) {
        punkte.pop();
        ecken.getLayers().at(-1)?.remove();
        zeichne();
      }
    };
    karte.on("click", klick).on("mousemove", bewegen).on("dblclick", doppel);
    document.addEventListener("keydown", tasteF);
    return {
      objektKlick(typ, objekt, ereignis) {
        // Klicks auf Knoten setzen einen Eckpunkt an deren Position
        if (typ === "knoten") {
          L.DomEvent.stopPropagation(ereignis);
          klick({ latlng: ll(objekt.x, objekt.y) });
        }
      },
      beenden() {
        karte.off("click", klick).off("mousemove", bewegen).off("dblclick", doppel);
        document.removeEventListener("keydown", tasteF);
        form.remove();
        ecken.remove();
        karte.getContainer().classList.remove("fadenkreuz");
        ctx.hinweisWeg();
      },
    };
  }

  // ---------------------------------------------------------------- Eigenschaften
  function panelZeigen() {
    const a = ctx.auswahl;
    if (!a) return (panel.hidden = true);
    const objekt =
      a.typ === "knoten" ? ctx.netz.knoten.find((k) => k.id === a.id) : a.typ === "kante" ? ctx.netz.kanten.find((k) => k.id === a.id) : ctx.netz.flaechen.find((f) => f.id === a.id);
    if (!objekt) return abwaehlen();
    const kopf = (titel) =>
      h("div.panel-kopf", h("h3", titel), h("button.knopf-flach", { type: "button", onclick: abwaehlen, "aria-label": t("allgemein.schliessen") }, "×"));
    const fuss = (speichern) =>
      h(
        "div.panel-knoepfe",
        h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(a) }, t("allgemein.loeschen")),
        speichern ? h("button.knopf", { type: "submit" }, t("allgemein.speichern")) : null
      );
    let form;
    if (a.typ === "knoten") form = knotenFormular(objekt, kopf, fuss);
    else if (a.typ === "kante") form = kantenFormular(objekt, kopf, fuss);
    else form = flaechenFormular(objekt, kopf, fuss);
    leeren(panel, form);
    panel.hidden = false;
  }

  function feld(label, eingabe, hilfe) {
    return h("label.feld", h("span", label), eingabe, hilfe ? h("small", hilfe) : null);
  }

  async function speichernUndNeu(pfad, daten) {
    try {
      await api(pfad, { methode: "PUT", daten });
      melden(t("allgemein.gespeichert"));
      await ctx.netzLaden();
      ctx.punkte = await api("punkte");
      panelZeigen();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  function knotenFormular(k, kopf, fuss) {
    const name = h("input", { value: k.name, maxlength: 100 });
    const art = h("select", ["weg", ...PUNKT_ARTEN].map((x) => h("option", { value: x, selected: x === k.art }, t(`knoten.art.${x}`))));
    const aufzug = h("select", aufzugOptionen().map(([w, text]) => h("option", { value: w, selected: String(w) === String(k.aufzug_id ?? "") }, text)));
    const kap = h("input", { type: "number", min: 0, value: k.kapazitaet ?? "" });
    const p = ctx.punkte.find((x) => x.id === k.id);
    const uebergaenge = ctx.netz.kanten.filter((e) => (e.von === k.id || e.nach === k.id) && e.von_stockwerk !== e.nach_stockwerk);
    const form = h(
      "form",
      kopf(ctx.knotenTitel(k)),
      p?.flaeche ? h("p.gedimmt", `${t("knoten.liegt_in")}: ${p.nummer ? p.nummer + " " : ""}${p.flaeche}`) : null,
      feld(t("knoten.name"), name),
      feld(t("knoten.art_label"), art),
      feld(t("knoten.aufzug"), aufzug, t("editor.aufzug_hilfe")),
      feld(t("knoten.kapazitaet"), kap, t("knoten.kapazitaet_hilfe")),
      h("h4", t("editor.uebergaenge")),
      h("p.hinweis", t("editor.uebergaenge_hilfe")),
      uebergaenge.length
        ? h(
            "ul.linkliste",
            uebergaenge.map((e) => {
              const f = ctx.netz.fremde_knoten.find((x) => x.id === (e.von === k.id ? e.nach : e.von));
              return h(
                "li",
                h("a", { href: ctx.stockwerkLink(f?.stockwerk_id) }, `${f?.name || "?"} – ${f?.gebaeudeteil} ${f?.stockwerk}`),
                ` · ${zahl(e.laenge_m)} m `,
                h("button.knopf-flach.gefahr", { type: "button", onclick: () => kanteLoeschen(e) }, "×")
              );
            })
          )
        : null,
      h("button.knopf-flach", { type: "button", onclick: () => uebergangAnlegen(k) }, "+ " + t("editor.uebergang_neu")),
      fuss(true)
    );
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const aufzug_id = await aufzugWert(aufzug.value, null);
        await speichernUndNeu(`knoten/${k.id}`, { name: name.value, art: art.value, aufzug_id, kapazitaet: kap.value === "" ? 0 : Number(kap.value) });
      } catch (err) {
        fehlerMelden(err);
      }
    });
    return form;
  }

  async function uebergangAnlegen(k) {
    const andere = ctx.punkte.filter((p) => p.stockwerk_id !== sid);
    if (!andere.length) return melden(t("editor.keine_punkte_anderswo"), "fehler");
    const auswahl = punktAuswahl(andere, null);
    const laenge = h("input", { type: "number", min: 0.1, step: 0.1, required: true });
    const dialog = h("dialog.dialog");
    const form = h(
      "form",
      h("h2", t("editor.uebergang_neu")),
      h("p.hinweis", t("editor.uebergang_dialog_hilfe")),
      h("label.feld", h("span", t("editor.uebergang_ziel")), auswahl),
      h("label.feld", h("span", t("editor.uebergang_laenge")), laenge),
      h(
        "div.dialog-knoepfe",
        h("button.knopf-flach", { type: "button", onclick: () => dialog.close() }, t("allgemein.abbrechen")),
        h("button.knopf", { type: "submit" }, t("allgemein.anlegen"))
      )
    );
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("kanten", { methode: "POST", daten: { von: k.id, nach: Number(auswahl.value), laenge_m: Number(laenge.value) } });
        dialog.close();
        await ctx.netzLaden();
        panelZeigen();
      } catch (err) {
        fehlerMelden(err);
      }
    });
    dialog.append(form);
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }

  async function kanteLoeschen(e) {
    try {
      await api(`kanten/${e.id}`, { methode: "DELETE" });
      await ctx.netzLaden();
      panelZeigen();
    } catch (err) {
      fehlerMelden(err);
    }
  }

  function kantenFormular(k, kopf, fuss) {
    const a = ctx.knotenNachId(k.von);
    const b = ctx.knotenNachId(k.nach);
    const berechnet = a && b && ctx.stockwerk.meter_pro_punkt ? abstand(a, b) * ctx.stockwerk.meter_pro_punkt : null;
    const name = h("input", { value: k.name, maxlength: 100, placeholder: t("kante.name_hilfe") });
    const laenge = h("input", { type: "number", min: 0, step: 0.1, value: k.laenge_m ?? "", placeholder: berechnet ? zahl(berechnet) : "" });
    const kap = h("input", { type: "number", min: 0, value: k.kapazitaet ?? "" });
    const sperren = ctx.stamm.transportarten.map((ta) => h("label.haken", h("input", { type: "checkbox", value: ta.id, checked: k.gesperrt.includes(ta.id) }), h("span", ta.name)));
    const form = h(
      "form",
      kopf(t("kante.titel")),
      h("p.gedimmt", ctx.kantenText(k)),
      feld(t("kante.name"), name),
      feld(t("kante.laenge"), laenge, t("kante.laenge_hilfe")),
      feld(t("kante.kapazitaet"), kap, t("kante.kapazitaet_hilfe")),
      h("div.feld", h("span", t("kante.gesperrt")), h("div.mehrfach", sperren)),
      fuss(true)
    );
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      speichernUndNeu(`kanten/${k.id}`, {
        name: name.value,
        laenge_m: laenge.value === "" ? 0 : Number(laenge.value),
        kapazitaet: kap.value === "" ? 0 : Number(kap.value),
        gesperrt: sperren.map((l) => l.querySelector("input")).filter((i) => i.checked).map((i) => Number(i.value)),
      });
    });
    return form;
  }

  function flaechenFormular(f, kopf, fuss) {
    const name = h("input", { value: f.name, maxlength: 100, required: true });
    const nummer = h("input", { value: f.nummer, maxlength: 30 });
    const art = h("select", ["raum", "bereich"].map((x) => h("option", { value: x, selected: x === f.art }, t(`flaeche.${x}`))));
    const farbe = h("select", FARBEN.map(([w, k]) => h("option", { value: w, selected: w === f.farbe }, t(k))));
    const bereiche = ctx.netz.flaechen.filter((x) => x.art === "bereich" && x.id !== f.id);
    const parent = h("select", h("option", { value: "" }, "–"), bereiche.map((b) => h("option", { value: b.id, selected: b.id === f.parent_id }, b.name)));
    const enthalten = ctx.netz.flaechen.filter((x) => x.parent_id === f.id);
    const form = h(
      "form",
      kopf(f.name),
      feld(t("flaeche.name"), name),
      feld(t("flaeche.nummer"), nummer),
      feld(t("flaeche.art"), art),
      feld(t("flaeche.farbe"), farbe),
      f.art === "raum" ? feld(t("flaeche.gehoert_zu"), parent) : null,
      enthalten.length ? [h("h4", t("flaeche.enthaelt")), h("ul.linkliste", enthalten.map((r) => h("li", `${r.nummer ? r.nummer + " " : ""}${r.name}`)))] : null,
      fuss(true)
    );
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      speichernUndNeu(`flaechen/${f.id}`, { name: name.value, nummer: nummer.value, art: art.value, farbe: farbe.value, parent_id: parent.value ? Number(parent.value) : null });
    });
    return form;
  }

  async function loeschen(a) {
    const pfad = { knoten: "knoten", kante: "kanten", flaeche: "flaechen" }[a.typ];
    const objekt = a.typ === "knoten" ? ctx.netz.knoten.find((k) => k.id === a.id) : a.typ === "flaeche" ? ctx.netz.flaechen.find((f) => f.id === a.id) : null;
    const name = objekt ? objekt.name || t(`knoten.art.${objekt.art}`) : t("kante.titel");
    if (a.typ !== "kante" || objekt?.name) {
      if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name })))) return;
    }
    try {
      await api(`${pfad}/${a.id}`, { methode: "DELETE" });
      abwaehlen();
      await ctx.netzLaden();
      ctx.punkte = await api("punkte");
    } catch (e) {
      fehlerMelden(e);
    }
  }

  ctx.zeichnen({ netz: true });
  wechseln("auswahl");

  return () => {
    werkzeug?.beenden();
    karte.off("click", kartenKlick);
    document.removeEventListener("keydown", taste);
    werkzeugleiste.hidden = true;
    panel.hidden = true;
    eckenEbene.remove();
    ctx.beiKlick = null;
    ctx.beiVerschieben = null;
    ctx.auswahl = null;
  };
}
