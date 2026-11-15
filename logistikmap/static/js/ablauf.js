// Zeitablauf auf der Karte: Simulation eines Tages abspielen.
// Zeigt Fahrzeuge (Punkte), Warenflüsse (Linien, dicker = mehr Fahrten) und Aufzüge mit Warteschlange.

import { api, dauer, fehlerMelden, h, heute, leeren, punktName, sekunden, szenarioAuswahl, t, uhr } from "./basis.js";
import { ll } from "./karte.js";

const cache = new Map(); // "datum|szenario" → Simulationsergebnis
export async function simulationLaden(datum, neu = false, szenario = null) {
  const schluessel = `${datum}|${szenario || ""}`;
  if (neu || !cache.has(schluessel)) cache.set(schluessel, await api(`simulation?datum=${datum}${szenario ? `&szenario=${szenario}` : ""}`));
  return cache.get(schluessel);
}
export function simulationVergessen() {
  cache.clear();
}

const FENSTER = [
  ["jetzt", "ablauf.fenster.jetzt"],
  ["15", "ablauf.fenster.15"],
  ["30", "ablauf.fenster.30"],
  ["60", "ablauf.fenster.60"],
  ["tag", "ablauf.fenster.tag"],
];
const TEMPI = [30, 60, 120, 300, 600];

/** Position einer Fahrt zur Zeit t auf Stockwerk sid, oder null. */
export function position(fahrt, zeit, sid) {
  for (const a of fahrt.abschnitte) {
    if (zeit < a.t0 || zeit > a.t1) continue;
    if (a.typ === "weg") {
      if (a.stockwerk_id !== sid) return null;
      const f = a.t1 > a.t0 ? (zeit - a.t0) / (a.t1 - a.t0) : 1;
      return { x: a.x0 + (a.x1 - a.x0) * f, y: a.y0 + (a.y1 - a.y0) * f, zustand: "faehrt" };
    }
    if (a.typ === "aufzug") {
      if (zeit < a.t_einstieg) return a.von_stockwerk === sid ? { x: a.x0, y: a.y0, zustand: "wartet", aufzug: a.aufzug_id } : null;
      return a.nach_stockwerk === sid ? { x: a.x1, y: a.y1, zustand: "im_aufzug", aufzug: a.aufzug_id } : null;
    }
    if (a.typ === "uebergang") {
      const f = a.t1 > a.t0 ? (zeit - a.t0) / (a.t1 - a.t0) : 1;
      if (f < 0.5 && a.von_stockwerk === sid) return { x: a.x0, y: a.y0, zustand: "faehrt" };
      if (f >= 0.5 && a.nach_stockwerk === sid) return { x: a.x1, y: a.y1, zustand: "faehrt" };
      return null;
    }
    // laden, entladen, warten
    if (a.stockwerk_id !== sid) return null;
    return { x: a.x, y: a.y, zustand: a.typ === "warten" ? "wartet" : a.typ };
  }
  return null;
}

/** Auf welchem Stockwerk ist die Fahrt zur Zeit t? */
function stockwerkZur(fahrt, zeit) {
  for (const a of fahrt.abschnitte) {
    if (zeit < a.t0 || zeit > a.t1) continue;
    if (a.typ === "aufzug" || a.typ === "uebergang") return zeit < (a.t_einstieg ?? (a.t0 + a.t1) / 2) ? a.von_stockwerk : a.nach_stockwerk;
    return a.stockwerk_id;
  }
  return null;
}

export async function starteAblauf(ctx) {
  const { karte, unten, stockwerk } = ctx;
  const sid = stockwerk.id;
  const [datumParam, zeitParam, szenarioParam] = ctx.rest;
  let szenario = Number(szenarioParam) || null;
  let datum = /^\d{4}-\d{2}-\d{2}$/.test(datumParam || "") ? datumParam : heute();
  let zeit = /^\d{2}:\d{2}$/.test(zeitParam || "") ? sekunden(zeitParam) : 8 * 3600;
  let sim = null;
  let laeuft = false;
  let tempo = 60;
  let fenster = "30";
  let filter = { start: "", transportart: "", richtung: "", lieferung: "" };
  let animation = null;
  let letzterFrame = 0;
  const marker = new Map(); // fahrt.id → circleMarker
  const aufzugMarker = new Map();

  const datumFeld = h("input", { type: "date", value: datum });
  const zeitText = h("strong.zeitanzeige");
  const regler = h("input.zeitregler", { type: "range", min: 0, max: 86400 - 60, step: 60, value: zeit });
  const knopfStart = h("button.knopf", { type: "button" });
  const tempoWahl = h("select", { title: t("ablauf.tempo") }, TEMPI.map((x) => h("option", { value: x, selected: x === tempo }, `${x}×`)));
  const fensterWahl = h("select", { title: t("ablauf.anzeige") }, FENSTER.map(([w, k]) => h("option", { value: w, selected: w === fenster }, t(k))));
  const filterLeiste = h("div.filterleiste");
  const info = h("div.ablaufinfo");

  const szenarioWahl = await szenarioAuswahl(szenario, async (wert) => {
    szenario = wert;
    await laden();
  });
  leeren(
    unten,
    h(
      "div.ablaufsteuerung",
      datumFeld,
      szenarioWahl,
      knopfStart,
      zeitText,
      regler,
      tempoWahl,
      fensterWahl
    ),
    filterLeiste,
    info
  );
  unten.hidden = false;
  unten.classList.add("ablauf");

  datumFeld.addEventListener("change", async () => {
    datum = datumFeld.value || heute();
    await laden();
  });
  regler.addEventListener("input", () => {
    zeit = Number(regler.value);
    zeichnen();
  });
  regler.addEventListener("change", hashAktualisieren);
  tempoWahl.addEventListener("change", () => (tempo = Number(tempoWahl.value)));
  fensterWahl.addEventListener("change", () => {
    fenster = fensterWahl.value;
    zeichnen();
  });
  knopfStart.addEventListener("click", () => (laeuft ? anhalten() : abspielen()));

  function hashAktualisieren() {
    const teil = ["ablauf", datum, uhr(zeit), ...(szenario ? [szenario] : [])];
    history.replaceState(null, "", ctx.stockwerkLink(sid, ...teil));
    ctx.seitenleiste.querySelectorAll("a[data-stockwerk]").forEach((a) => (a.href = ctx.stockwerkLink(a.dataset.stockwerk, ...teil)));
  }

  function knopfText() {
    knopfStart.textContent = laeuft ? `⏸ ${t("ablauf.anhalten")}` : `▶ ${t("ablauf.abspielen")}`;
  }

  function abspielen() {
    laeuft = true;
    knopfText();
    letzterFrame = performance.now();
    const schritt = (jetzt) => {
      if (!laeuft) return;
      const dt = (jetzt - letzterFrame) / 1000;
      letzterFrame = jetzt;
      zeit = Math.min(86400 - 60, zeit + dt * tempo);
      regler.value = zeit;
      zeichnen();
      if (zeit >= 86400 - 60) return anhalten();
      animation = requestAnimationFrame(schritt);
    };
    animation = requestAnimationFrame(schritt);
  }

  function anhalten(adresseMerken = true) {
    const lief = laeuft;
    laeuft = false;
    cancelAnimationFrame(animation);
    knopfText();
    if (adresseMerken && lief) hashAktualisieren();
  }

  async function laden() {
    anhalten();
    leeren(info, h("span.gedimmt", t("allgemein.laedt")));
    try {
      sim = await simulationLaden(datum, false, szenario);
    } catch (e) {
      fehlerMelden(e);
      return;
    }
    filterAufbauen();
    hashAktualisieren();
    zeichnen();
  }

  function filterAufbauen() {
    const startIds = [...new Set(sim.fahrten.map((f) => f.start_id))];
    const auswahl = (name, optionen, alle) =>
      h(
        "select",
        {
          onchange: (e) => {
            filter[name] = e.target.value;
            zeichnen();
          },
        },
        h("option", { value: "" }, alle),
        optionen.map(([w, text]) => h("option", { value: w, selected: String(w) === filter[name] }, text))
      );
    const lieferungen = [...new Map(sim.fahrten.map((f) => [f.lieferung_id, f])).values()];
    leeren(
      filterLeiste,
      auswahl("start", startIds.map((id) => [id, punktName(ctx.punkte.find((p) => p.id === id))]), t("ablauf.filter.alle_starts")),
      auswahl("transportart", ctx.stamm.transportarten.map((x) => [x.id, x.name]), t("ablauf.filter.alle_transportarten")),
      auswahl("richtung", [["versorgung", t("richtung.versorgung")], ["entsorgung", t("richtung.entsorgung")]], t("ablauf.filter.alle_richtungen")),
      auswahl("lieferung", lieferungen.map((f) => [f.lieferung_id, `${uhr(f.geplant)} ${f.name}`]), t("ablauf.filter.alle_lieferungen"))
    );
  }

  function passt(f) {
    return (
      (!filter.start || String(f.start_id) === filter.start) &&
      (!filter.transportart || String(f.transportart_id) === filter.transportart) &&
      (!filter.richtung || f.richtung === filter.richtung) &&
      (!filter.lieferung || String(f.lieferung_id) === filter.lieferung)
    );
  }

  function imFenster(f) {
    if (fenster === "tag") return true;
    const ende = f.ende ?? f.fertig ?? f.ankunft ?? Infinity;
    if (fenster === "jetzt") return f.geplant <= zeit && ende >= zeit;
    const m = Number(fenster) * 60;
    // Fahrten, die im Zeitraum [zeit, zeit + m] starten sollen oder dann noch unterwegs sind
    return f.geplant <= zeit + m && ende >= zeit;
  }

  function farbe(f) {
    return ctx.stamm.transportarten.find((x) => x.id === f.transportart_id)?.farbe || "#d9480f";
  }

  function zeichnen() {
    zeitText.textContent = uhr(zeit);
    knopfText();
    if (!sim) return;
    const fahrten = sim.fahrten.filter(passt);
    const sichtbar = fahrten.filter(imFenster);

    // ---- Warenflüsse: Kanten nach Anzahl Fahrten im Fenster
    ctx.ebenen.overlay.clearLayers();
    const fluesse = new Map();
    for (const f of sichtbar) {
      const gesehen = new Set();
      for (const a of f.abschnitte) {
        if (a.typ !== "weg" || a.stockwerk_id !== sid) continue;
        const key = a.von < a.nach ? `${a.von}-${a.nach}` : `${a.nach}-${a.von}`;
        if (gesehen.has(key)) continue;
        gesehen.add(key);
        const e = fluesse.get(key) || { a, anzahl: 0, farben: new Map(), rueck: 0 };
        e.anzahl += 1;
        if (a.rueck) e.rueck += 1;
        e.farben.set(farbe(f), (e.farben.get(farbe(f)) || 0) + 1);
        fluesse.set(key, e);
      }
    }
    const max = Math.max(1, ...[...fluesse.values()].map((e) => e.anzahl));
    for (const e of fluesse.values()) {
      const hauptfarbe = [...e.farben].sort((x, y) => y[1] - x[1])[0][0];
      const breite = 3 + 11 * (e.anzahl / max);
      L.polyline([ll(e.a.x0, e.a.y0), ll(e.a.x1, e.a.y1)], { pane: "fluss", color: hauptfarbe, weight: breite, opacity: 0.55, lineCap: "round" })
        .bindTooltip(t("ablauf.fahrten_hier", { anzahl: e.anzahl }), { sticky: true })
        .addTo(ctx.ebenen.overlay);
    }

    // ---- Fahrzeuge: an derselben Stelle stehende werden zu einem Punkt mit Anzahl zusammengefasst
    const wartendAm = new Map(); // aufzug_id → Anzahl wartend auf diesem Stockwerk
    const gruppen = new Map();
    for (const f of fahrten) {
      const p = position(f, zeit, sid);
      if (!p) continue;
      if (p.zustand === "wartet" && p.aufzug) wartendAm.set(p.aufzug, (wartendAm.get(p.aufzug) || 0) + 1);
      const steht = p.zustand !== "faehrt";
      const key = steht ? `${Math.round(p.x)}:${Math.round(p.y)}:${p.zustand}` : `f${f.id}`;
      const g = gruppen.get(key) || { p, fahrten: [] };
      g.fahrten.push(f);
      gruppen.set(key, g);
    }
    for (const [key, g] of gruppen) {
      const f = g.fahrten[0];
      const n = g.fahrten.length;
      const wartet = g.p.zustand === "wartet";
      const html = `<span class="fz${wartet ? " wartet" : ""}" style="background:${farbe(f)}">${n > 1 ? n : ""}</span>`;
      const groesse = n > 1 ? 22 : 14;
      let m = marker.get(key);
      if (!m) {
        m = L.marker(ll(g.p.x, g.p.y), { pane: "fahrzeuge", keyboard: false });
        m.bindTooltip("", { direction: "top", offset: [0, -8] });
        m.addTo(ctx.ebenen.fahrzeuge);
        marker.set(key, m);
      }
      if (m._html !== html) {
        m.setIcon(L.divIcon({ className: "fahrzeug", html, iconSize: [groesse, groesse] }));
        m._html = html;
      }
      m.setLatLng(ll(g.p.x, g.p.y));
      m.off("click").on("click", () => fahrtInfo(f, g.fahrten));
      const namen = [...new Set(g.fahrten.map((x) => x.name))].join(", ");
      m.setTooltipContent(`${n > 1 ? `${n}× ` : ""}${namen}${n === 1 && f.von_n > 1 ? ` (${f.nr}/${f.von_n})` : ""} · ${t(`ablauf.zustand.${g.p.zustand}`)}`);
    }
    for (const [key, m] of marker) {
      if (!gruppen.has(key)) {
        m.remove();
        marker.delete(key);
      }
    }

    // ---- Aufzüge: Status je Haltepunkt auf diesem Stockwerk
    for (const k of ctx.netz.knoten.filter((x) => x.aufzug_id)) {
      const res = sim.ressourcen.find((r) => r.typ === "aufzug" && r.id === k.aufzug_id);
      let m = aufzugMarker.get(k.id);
      if (!res) {
        m?.remove();
        aufzugMarker.delete(k.id);
        continue;
      }
      const beleg = res.belegungen.find(([s, e]) => zeit >= s && zeit < e);
      const hier = wartendAm.get(k.aufzug_id) || 0;
      const zustand = hier >= 3 ? "stau" : hier ? "wartend" : beleg ? "faehrt" : "frei";
      const html = `<span class="aufzug-status ${zustand}">${hier ? `⏳ ${hier}` : beleg ? "▲▼" : "✓"}</span>`;
      if (!m) {
        m = L.marker(ll(k.x, k.y), { pane: "fahrzeuge", interactive: false, icon: L.divIcon({ className: "aufzug-marke", html, iconSize: [44, 20], iconAnchor: [-12, 26] }) });
        m.addTo(ctx.ebenen.overlay);
        aufzugMarker.set(k.id, m);
      }
      m.setIcon(L.divIcon({ className: "aufzug-marke", html, iconSize: [44, 20], iconAnchor: [-12, 26] }));
      if (!ctx.ebenen.overlay.hasLayer(m)) m.addTo(ctx.ebenen.overlay);
    }

    // ---- Zahlen je Stockwerk in der Seitenleiste
    const jeStockwerk = {};
    for (const f of fahrten) {
      const s = stockwerkZur(f, zeit);
      if (s) jeStockwerk[s] = (jeStockwerk[s] || 0) + 1;
    }
    ctx.seitenleisteMarken(jeStockwerk);

    // ---- Infozeile
    const unterwegs = fahrten.filter((f) => f.start !== null && f.start <= zeit && (f.ende ?? Infinity) >= zeit).length;
    const wartend = fahrten.filter((f) => position(f, zeit, sid)?.zustand === "wartet").length;
    const engpaesse = sim.engpaesse.length;
    leeren(
      info,
      sim.feiertag ? h("span.marke-klein", feiertagText(sim.feiertag)) : null,
      h("span", t("ablauf.info", { lieferungen: sim.lieferungen.length, fahrten: sim.fahrten.length, unterwegs })),
      wartend ? h("span.warnung", t("ablauf.wartend_hier", { anzahl: wartend })) : null,
      engpaesse ? h("a", { href: `#/auswertung/${datum}${szenario ? `/${szenario}` : ""}` }, t("ablauf.engpaesse", { anzahl: engpaesse })) : h("span.gut", t("ablauf.keine_engpaesse")),
      sim.fehler.length ? h("a.warnung", { href: `#/auswertung/${datum}${szenario ? `/${szenario}` : ""}` }, t("ablauf.fehler", { anzahl: sim.fehler.length })) : null,
      h("a", { href: `/api/export/karte/${sid}.pdf?datum=${datum}&von=${uhr(Math.max(0, zeit))}&bis=${uhr(Math.min(86340, zeit + (fenster === "tag" ? 86400 : (Number(fenster) || 30) * 60)))}${filter.start ? `&start=${filter.start}` : ""}${szenario ? `&szenario=${szenario}` : ""}`, target: "_blank" }, "⤓ " + t("ablauf.pdf"))
    );
  }

  function feiertagText(f) {
    const text = t(`feiertag.${f}`);
    return text.startsWith("⟨") ? f : text;
  }

  function fahrtInfo(f, alle = [f]) {
    const start = ctx.punkte.find((p) => p.id === f.start_id);
    const weitere = alle.length > 1 ? h("p.hinweis", t("ablauf.weitere_hier", { anzahl: alle.length - 1 }), " ", alle.slice(1, 8).map((x) => h("button.knopf-flach", { type: "button", onclick: () => fahrtInfo(x, alle) }, `${x.name} ${x.nr}/${x.von_n}`))) : null;
    const ziel = ctx.punkte.find((p) => p.id === f.ziel_id);
    const warte = Object.entries(f.warte).filter(([, v]) => v > 0);
    leeren(
      ctx.panel,
      h("div.panel-kopf", h("h3", f.name), h("button.knopf-flach", { type: "button", onclick: () => (ctx.panel.hidden = true), "aria-label": t("allgemein.schliessen") }, "×")),
      h("p.gedimmt", [f.lieferant, f.von_n > 1 ? t("ablauf.fahrt_nr", { nr: f.nr, von: f.von_n }) : null, f.wagen.join(", ")].filter(Boolean).join(" · ")),
      h(
        "dl.werte",
        h("dt", t("ablauf.von")), h("dd", punktName(start)),
        h("dt", t("ablauf.nach")), h("dd", punktName(ziel)),
        h("dt", t("ablauf.geplant")), h("dd", uhr(f.geplant)),
        h("dt", t("ablauf.los")), h("dd", uhr(f.start)),
        h("dt", t("ablauf.ankunft")), h("dd", { class: f.verspaetet ? "warnung" : "" }, uhr(f.ankunft), f.spaetestens ? ` (${t("ablauf.spaetestens")} ${uhr(f.spaetestens)})` : ""),
        h("dt", t("ablauf.zurueck")), h("dd", uhr(f.ende)),
        warte.length ? [h("dt", t("ablauf.gewartet")), h("dd", warte.map(([k, v]) => `${t(`ablauf.warte.${k}`)} ${dauer(v)}`).join(", "))] : null
      ),
      weitere
    );
    ctx.panel.hidden = false;
  }

  ctx.zeichnen();
  knopfText();
  await laden();

  return () => {
    anhalten(false);
    unten.classList.remove("ablauf");
    unten.hidden = true;
    ctx.panel.hidden = true;
    ctx.seitenleisteMarken(null);
  };
}
