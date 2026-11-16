// Kartenansicht: Stockwerksplan mit Flächen, Punkten und Wegenetz.
// Modi: ansehen | bearbeiten (Editor, editor.js) | weg (Weg einer Lieferung) | ablauf (Zeitablauf, ablauf.js)
//
// Hash: #/karte/<stockwerk>[/bearbeiten | /weg/<lieferung> | /ablauf/<datum>/<HH:MM>]
//
// Koordinaten sind PDF-Punkte der Planseite (x nach rechts, y nach unten). In Leaflet
// steht y als "lat" und x als "lng". Zoomstufe z entspricht 2^(z-4) Pixel pro Punkt,
// passend zu logistikmap/plaene.py.

import { api, darf, dauer, fehlerMelden, formularDialog, h, leeren, melden, stammdaten, t, zahl } from "./basis.js";
import { starteAblauf } from "./ablauf.js";
import { starteEditor } from "./editor.js";

const METER_PRO_PDF_PUNKT = 0.0254 / 72; // 1 PDF-Punkt auf dem Papier

/** DIN-Format der Seite (A0 … A4), wenn sie eines hat. */
function papierformat(b, hh) {
  const [kurz, lang] = [Math.min(b, hh), Math.max(b, hh)];
  for (let n = 0; n <= 4; n++) {
    const fk = Math.round(841 / 2 ** (n / 2)), fl = Math.round(1189 / 2 ** (n / 2));
    if (Math.abs(kurz - fk) <= fk * 0.02 && Math.abs(lang - fl) <= fl * 0.02) return `A${n}`;
  }
  return "";
}

const ZOOM_VERSATZ = 4;
const CRS = L.extend({}, L.CRS.Simple, { transformation: new L.Transformation(2 ** -ZOOM_VERSATZ, 0, 2 ** -ZOOM_VERSATZ, 0) });

export const ll = (x, y) => L.latLng(y, x);
export const xy = (latlng) => ({ x: latlng.lng, y: latlng.lat });
export const abstand = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

export const KNOTEN_FARBEN = { weg: "#868e96", start: "#2b8a3e", ziel: "#c92a2a", punkt: "#1c7ed6", aufzug: "#7048e8", uebergang: "#e67700" };
const KNOTEN_ZEICHEN = { start: "S", ziel: "Z", punkt: "•", aufzug: "⇅", uebergang: "↔" };

export function zeigeKarte(wurzel, [stockwerkParam, modusParam, ...rest]) {
  const seitenleiste = h("aside.seitenleiste");
  const kartenRahmen = h("div.kartenrahmen");
  const kopfzeile = h("div.kartenkopf");
  const werkzeugleiste = h("div.werkzeugleiste", { hidden: true });
  const hinweis = h("div.kartenhinweis", { hidden: true });
  const panel = h("div.eigenschaften", { hidden: true });
  const unten = h("div.kartenfuss", { hidden: true });
  const kartenEl = h("div.karte");
  const kartenBereich = h("div.kartenbereich", kartenEl, hinweis, panel);
  kartenRahmen.append(kopfzeile, werkzeugleiste, kartenBereich, unten);
  wurzel.append(seitenleiste, kartenRahmen);

  const gewaehlt = Number(stockwerkParam) || null;
  const modus = ["bearbeiten", "weg", "ablauf"].includes(modusParam) && (modusParam !== "bearbeiten" || darf("bearbeiten")) ? modusParam : "ansehen";
  let timer = null;
  let modusAufraeumen = null;
  let teile = [];

  const ctx = {
    karte: null,
    stockwerk: null,
    netz: { flaechen: [], knoten: [], kanten: [], fremde_knoten: [] },
    stamm: null,
    punkte: [],
    modus,
    rest,
    ebenen: {},
    seitenleiste,
    werkzeugleiste,
    panel,
    unten,
    kopfzeile,
    zeichnen,
    netzLaden,
    hinweis: hinweisZeigen,
    hinweisWeg: () => (hinweis.hidden = true),
    knotenNachId: (id) => ctx.netz.knoten.find((k) => k.id === id),
    pixel: (a, b) => ctx.karte.latLngToContainerPoint(ll(a.x, a.y)).distanceTo(ctx.karte.latLngToContainerPoint(ll(b.x, b.y))),
    stockwerkLink: (sid, ...teil) => `#/karte/${[sid, ...teil].join("/")}`,
    seitenleisteMarken: () => {},
    teile: () => teile,
  };

  // ---------------------------------------------------------------- Seitenleiste
  async function seitenleisteLaden() {
    try {
      teile = await api("gebaeude");
    } catch (e) {
      return fehlerMelden(e);
    }
    if (!teile.length) {
      leeren(
        seitenleiste,
        h("p.leer", t("karte.keine_gebaeude")),
        darf("bearbeiten") ? h("a.knopf", { href: "#/start" }, t("karte.zur_verwaltung")) : null
      );
      leeren(kopfzeile);
      return;
    }
    const zusatz = modus === "ablauf" ? `/ablauf/${rest.join("/")}` : modus === "bearbeiten" ? "/bearbeiten" : modus === "weg" ? `/weg/${rest[0]}` : "";
    leeren(
      seitenleiste,
      teile.map((teil) =>
        h(
          "div.baum",
          h("h3", teil.kuerzel ? h("span.kuerzel", teil.kuerzel) : null, teil.name),
          h(
            "ul",
            teil.stockwerke.map((s) =>
              h(
                "li",
                h(
                  "a",
                  { href: `#/karte/${s.id}${zusatz}`, class: s.id === gewaehlt ? "aktiv" : "", title: t("karte.ebene", { ebene: s.ebene }), "data-stockwerk": s.id },
                  h("span", s.name),
                  h("span.marke-zahl", { hidden: true }),
                  !s.plan || s.plan.status !== "fertig" ? h("span.punkt", { title: s.plan ? t(`gebaeude.status.${s.plan.status}`, { prozent: "" }) : t("gebaeude.kein_plan") }) : null
                )
              )
            )
          )
        )
      )
    );
    if (!gewaehlt) {
      const erstes = teile.flatMap((tl) => tl.stockwerke).find((s) => s.plan?.status === "fertig");
      if (erstes) location.replace(`#/karte/${erstes.id}${zusatz}`);
      else leeren(kopfzeile, h("span.gedimmt", t("karte.kein_stockwerk")));
    }
  }

  /** Zahlen neben den Stockwerken (z. B. Fahrzeuge unterwegs im Ablauf) */
  ctx.seitenleisteMarken = (zahlen) => {
    seitenleiste.querySelectorAll("a[data-stockwerk]").forEach((a) => {
      const n = zahlen?.[a.dataset.stockwerk];
      const el = a.querySelector(".marke-zahl");
      el.hidden = !n;
      el.textContent = n || "";
    });
  };

  // ---------------------------------------------------------------- Stockwerk
  async function stockwerkLaden() {
    clearTimeout(timer);
    try {
      [ctx.stockwerk, ctx.stamm, ctx.punkte] = await Promise.all([api(`stockwerke/${gewaehlt}`), stammdaten(true), api("punkte")]);
    } catch (e) {
      return fehlerMelden(e);
    }
    const plan = ctx.stockwerk.plan;
    kopfAufbauen();
    if (!plan || plan.status !== "fertig") {
      kartenBereich.hidden = true;
      let text = t("karte.kein_plan");
      if (plan?.status === "laeuft") text = t("karte.plan_wird_erstellt", { prozent: zahl(plan.fortschritt * 100, 0) });
      if (plan?.status === "wartet") text = t("karte.plan_wartet");
      if (plan?.status === "fehler") text = t("karte.plan_fehler", { fehler: plan.fehler || "" });
      kartenRahmen.querySelector(".kartenleer")?.remove();
      kartenRahmen.append(
        h(
          "div.kartenleer",
          h("p", text),
          plan?.status === "laeuft" ? h("progress", { max: 1, value: plan.fortschritt }) : null,
          !plan && darf("bearbeiten") ? h("a.knopf", { href: "#/gebaeude" }, t("gebaeude.plan_zuweisen")) : null
        )
      );
      if (plan && ["wartet", "laeuft"].includes(plan.status)) timer = setTimeout(stockwerkLaden, 2000);
      return;
    }
    kartenRahmen.querySelector(".kartenleer")?.remove();
    kartenBereich.hidden = false;
    karteAufbauen(plan);
    await netzLaden();
    if (modus === "bearbeiten" && ctx.rest[0] === "massstab") {
      // Link aus „Erste Schritte“: Maßstab-Werkzeug gleich starten
      ctx.rest = [];
      history.replaceState(null, "", ctx.stockwerkLink(ctx.stockwerk.id, "bearbeiten"));
      modusAufraeumen = starteEditor(ctx);
      massstabDialog();
    } else if (modus === "bearbeiten") modusAufraeumen = starteEditor(ctx);
    else if (modus === "ablauf") modusAufraeumen = await starteAblauf(ctx);
    else if (modus === "weg") await wegZeigen(Number(rest[0]));
  }

  function kopfAufbauen() {
    const s = ctx.stockwerk;
    const fertig = s.plan?.status === "fertig";
    const massstab = s.meter_pro_punkt
      ? h("span.massstab-info", `1 : ${zahl(s.meter_pro_punkt / METER_PRO_PDF_PUNKT, 0)}`)
      : h("span.massstab-info.fehlt", t("karte.massstab_fehlt"));
    const modi = [
      ["ansehen", t("karte.modus.ansehen"), ctx.stockwerkLink(s.id)],
      darf("bearbeiten") ? ["bearbeiten", t("karte.modus.bearbeiten"), ctx.stockwerkLink(s.id, "bearbeiten")] : null,
      ["ablauf", t("karte.modus.ablauf"), ctx.stockwerkLink(s.id, "ablauf", ...(modus === "ablauf" ? rest : []))],
    ].filter(Boolean);
    leeren(
      kopfzeile,
      h("h2", s.gebaeudeteil.kuerzel ? h("span.kuerzel", s.gebaeudeteil.kuerzel) : null, s.name),
      fertig ? massstab : null,
      h("div.abstand"),
      fertig ? h("div.umschalter", modi.map(([m, text, link]) => h("a", { href: link, class: m === modus || (modus === "weg" && m === "ansehen") ? "aktiv" : "" }, text))) : null,
      fertig && s.meter_pro_punkt && modus !== "ablauf" ? h("button.knopf-flach", { type: "button", onclick: () => werkzeugStarten(messen) }, t("karte.messen")) : null,
      fertig && darf("bearbeiten") && modus === "bearbeiten"
        ? h("button.knopf-flach", { type: "button", onclick: massstabDialog }, t("karte.massstab_festlegen"))
        : null
    );
  }

  // ---------------------------------------------------------------- Karte & Ebenen
  function karteAufbauen(plan) {
    if (ctx.karte) ctx.karte.remove();
    const grenzen = L.latLngBounds([0, 0], [plan.hoehe, plan.breite]);
    const karte = L.map(kartenEl, {
      crs: CRS,
      minZoom: 0,
      maxZoom: plan.max_zoom + 3,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 90,
      attributionControl: false,
      maxBounds: grenzen.pad(0.5),
      doubleClickZoom: modus !== "bearbeiten",
    });
    ctx.karte = karte;
    window.__logistikKarte = ctx; // für die Oberflächentests (Planpunkte → Bildschirm)
    L.tileLayer(`/api/plaene/${plan.id}/kacheln/{z}/{x}/{y}.png`, {
      tileSize: 256,
      minZoom: 0,
      maxNativeZoom: plan.max_zoom,
      maxZoom: plan.max_zoom + 3,
      bounds: grenzen,
      noWrap: true,
      keepBuffer: 4,
    }).addTo(karte);
    karte.createPane("flaechen").style.zIndex = 350;
    karte.createPane("kanten").style.zIndex = 420;
    karte.createPane("fluss").style.zIndex = 430;
    karte.createPane("knoten").style.zIndex = 620;
    karte.createPane("fahrzeuge").style.zIndex = 640;
    ctx.ebenen = {
      flaechen: L.layerGroup().addTo(karte),
      kanten: L.layerGroup().addTo(karte),
      knoten: L.layerGroup().addTo(karte),
      overlay: L.layerGroup().addTo(karte),
      fahrzeuge: L.layerGroup().addTo(karte),
    };
    karte.fitBounds(grenzen);
    karte.setMinZoom(Math.max(0, Math.floor(karte.getZoom()) - 1));
    if (ctx.stockwerk.meter_pro_punkt) massstabsleiste(ctx.stockwerk.meter_pro_punkt).addTo(karte);
    const zoomKlasse = () => {
      const z = karte.getZoom() - plan.max_zoom;
      kartenEl.classList.toggle("zoom-fern", z < -4.5);
      kartenEl.classList.toggle("zoom-nah", z >= -2.5);
    };
    karte.on("zoomend", zoomKlasse);
    zoomKlasse();
    beobachter?.disconnect();
    beobachter = new ResizeObserver(() => {
      if (ctx.karte === karte && karte._mapPane) karte.invalidateSize();
    });
    beobachter.observe(kartenEl);
  }
  let beobachter = null;

  async function netzLaden() {
    try {
      ctx.netz = await api(`stockwerke/${gewaehlt}/netz`);
    } catch (e) {
      return fehlerMelden(e);
    }
    zeichnen();
  }

  /** Zeichnet Flächen, Kanten und Knoten neu. optionen.auswahl hebt ein Element hervor. */
  function zeichnen(optionen = {}) {
    const { flaechen, kanten, knoten } = ctx.ebenen;
    [flaechen, kanten, knoten].forEach((e) => e.clearLayers());
    const bearbeiten = modus === "bearbeiten";
    const auswahl = optionen.auswahl || ctx.auswahl;

    for (const f of [...ctx.netz.flaechen].sort((a, b) => (a.art === "bereich" ? -1 : 1) - (b.art === "bereich" ? -1 : 1))) {
      const farbe = f.farbe || (f.art === "bereich" ? "#1f5f8b" : "#495057");
      const gewaehlt = auswahl?.typ === "flaeche" && auswahl.id === f.id;
      const poly = L.polygon(
        f.punkte.map(([x, y]) => ll(x, y)),
        {
          pane: "flaechen",
          color: gewaehlt ? "#f08c00" : farbe,
          weight: gewaehlt ? 3 : f.art === "bereich" ? 2 : 1,
          dashArray: f.art === "bereich" ? "8 6" : null,
          fillColor: farbe,
          fillOpacity: f.art === "bereich" ? 0.06 : 0.1,
          interactive: bearbeiten,
          className: `flaeche ${f.art}`,
        }
      );
      poly.bindTooltip(`${f.nummer ? f.nummer + " " : ""}${f.name}`, { permanent: true, direction: "center", className: `flaechen-label ${f.art}` });
      poly.flaeche = f;
      if (bearbeiten) poly.on("click", (e) => ctx.beiKlick?.({ typ: "flaeche", objekt: f, ereignis: e }));
      poly.addTo(flaechen);
    }

    if (bearbeiten || optionen.netz) {
      const knotenMap = new Map(ctx.netz.knoten.map((k) => [k.id, k]));
      for (const k of ctx.netz.kanten) {
        const a = knotenMap.get(k.von);
        const b = knotenMap.get(k.nach);
        const gewaehlt = auswahl?.typ === "kante" && auswahl.id === k.id;
        if (a && b) {
          const linie = L.polyline([ll(a.x, a.y), ll(b.x, b.y)], {
            pane: "kanten",
            color: gewaehlt ? "#f08c00" : k.gesperrt.length ? "#c92a2a" : k.kapazitaet ? "#e67700" : "#495057",
            weight: gewaehlt ? 6 : 4,
            opacity: 0.75,
            dashArray: k.gesperrt.length ? "6 6" : null,
            interactive: bearbeiten,
          });
          if (bearbeiten) {
            linie.on("click", (e) => ctx.beiKlick?.({ typ: "kante", objekt: k, ereignis: e }));
            linie.bindTooltip(kantenText(k), { sticky: true });
          }
          linie.addTo(kanten);
        }
      }
    }

    for (const k of ctx.netz.knoten) {
      if (k.art === "weg" && !bearbeiten) continue;
      const gewaehlt = auswahl?.typ === "knoten" && auswahl.id === k.id;
      const marker = L.marker(ll(k.x, k.y), {
        pane: "knoten",
        icon: knotenIcon(k, gewaehlt),
        draggable: bearbeiten,
        keyboard: false,
        riseOnHover: true,
      });
      if (k.art !== "weg") {
        marker.bindTooltip(knotenTitel(k), { permanent: true, direction: "right", offset: [10, 0], className: "knoten-label" });
      }
      marker.knoten = k;
      if (bearbeiten) {
        marker.on("click", (e) => ctx.beiKlick?.({ typ: "knoten", objekt: k, ereignis: e }));
        marker.on("dragend", (e) => ctx.beiVerschieben?.(k, xy(e.target.getLatLng())));
      } else {
        marker.on("click", () => knotenInfo(k));
      }
      marker.addTo(knoten);
    }
  }

  function knotenTitel(k) {
    if (k.art === "aufzug") {
      const a = ctx.stamm.aufzuege.find((x) => x.id === k.aufzug_id);
      return k.name || a?.name || t("knoten.art.aufzug");
    }
    return k.name || t(`knoten.art.${k.art}`);
  }

  function knotenIcon(k, gewaehlt) {
    const farbe = KNOTEN_FARBEN[k.art] || "#495057";
    if (k.art === "weg") {
      return L.divIcon({ className: `knoten-icon weg${gewaehlt ? " gewaehlt" : ""}`, iconSize: [12, 12], html: "" });
    }
    const el = document.createElement("span");
    el.textContent = KNOTEN_ZEICHEN[k.art] || "";
    el.style.background = farbe;
    if (k.kapazitaet) el.dataset.kapazitaet = k.kapazitaet;
    return L.divIcon({ className: `knoten-icon ${k.art}${gewaehlt ? " gewaehlt" : ""}`, iconSize: [22, 22], html: el.outerHTML });
  }

  function kantenText(k) {
    const teile = [];
    if (k.name) teile.push(k.name);
    const a = ctx.knotenNachId(k.von);
    const b = ctx.knotenNachId(k.nach);
    if (k.laenge_m) teile.push(`${zahl(k.laenge_m)} m`);
    else if (a && b && ctx.stockwerk.meter_pro_punkt) teile.push(`${zahl(abstand(a, b) * ctx.stockwerk.meter_pro_punkt)} m`);
    if (k.kapazitaet) teile.push(t("kante.max_gleichzeitig", { anzahl: k.kapazitaet }));
    if (k.gesperrt.length) teile.push(t("kante.gesperrt_fuer", { arten: k.gesperrt.map((id) => ctx.stamm.transportarten.find((x) => x.id === id)?.name).join(", ") }));
    return teile.join(" · ") || t("kante.weg");
  }
  ctx.kantenText = kantenText;
  ctx.knotenTitel = knotenTitel;

  function knotenInfo(k) {
    const p = ctx.punkte.find((x) => x.id === k.id);
    const fremd = ctx.netz.kanten
      .filter((e) => (e.von === k.id || e.nach === k.id) && e.von_stockwerk !== e.nach_stockwerk)
      .map((e) => ctx.netz.fremde_knoten.find((f) => f.id === (e.von === k.id ? e.nach : e.von)))
      .filter(Boolean);
    const aufzug = k.aufzug_id ? ctx.stamm.aufzuege.find((a) => a.id === k.aufzug_id) : null;
    const halte = aufzug ? ctx.punkte.filter((x) => x.aufzug_id === aufzug.id && x.id !== k.id) : [];
    const ziele = [...fremd.map((f) => [f.stockwerk_id, `${f.gebaeudeteil} – ${f.stockwerk}`]), ...halte.map((x) => [x.stockwerk_id, `${x.kuerzel || x.gebaeudeteil} – ${x.stockwerk}`])];
    leeren(
      panel,
      h("div.panel-kopf", h("h3", knotenTitel(k)), h("button.knopf-flach", { type: "button", onclick: () => (panel.hidden = true), "aria-label": t("allgemein.schliessen") }, "×")),
      h("p.gedimmt", t(`knoten.art.${k.art}`), p?.flaeche ? ` · ${p.flaeche}` : ""),
      k.kapazitaet ? h("p", t("knoten.kapazitaet_text", { anzahl: k.kapazitaet })) : null,
      ziele.length ? [h("p.gedimmt", t("knoten.weiter_nach")), h("ul.linkliste", ziele.map(([sid, text]) => h("li", h("a", { href: ctx.stockwerkLink(sid) }, text))))] : null
    );
    panel.hidden = false;
  }

  // Maßstabsleiste unten links: wählt eine runde Meterzahl, die höchstens 140 px breit ist
  function massstabsleiste(meterProPunkt) {
    const Leiste = L.Control.extend({
      options: { position: "bottomleft" },
      onAdd(map) {
        const el = h("div.massstabsleiste", h("div.balken"), h("span"));
        const aktualisieren = () => {
          const pxProMeter = 2 ** (map.getZoom() - ZOOM_VERSATZ) / meterProPunkt;
          const schritte = [0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000];
          const meter = schritte.filter((m) => m * pxProMeter <= 140).pop() ?? schritte[0];
          el.querySelector(".balken").style.width = `${meter * pxProMeter}px`;
          el.querySelector("span").textContent = `${zahl(meter)} m`;
        };
        map.on("zoomend", aktualisieren);
        aktualisieren();
        return el;
      },
    });
    return new Leiste();
  }

  // ---------------------------------------------------------------- Weg einer Lieferung
  async function wegZeigen(lid) {
    let weg, lieferung;
    try {
      [weg, lieferung] = await Promise.all([api(`lieferungen/${lid}/weg`), api("lieferungen").then((l) => l.find((x) => x.id === lid))]);
    } catch (e) {
      hinweisZeigen(e.message);
      return;
    }
    const sid = ctx.stockwerk.id;
    const ta = ctx.stamm.transportarten.find((x) => x.id === lieferung?.transportart_id);
    const farbe = ta?.farbe || "#d9480f";
    // Teilstrecken auf diesem Stockwerk
    let linie = [];
    const linien = [];
    for (const k of weg.knoten) {
      if (k.stockwerk_id === sid) linie.push(ll(k.x, k.y));
      else if (linie.length) {
        linien.push(linie);
        linie = [];
      }
    }
    if (linie.length) linien.push(linie);
    for (const l of linien) {
      L.polyline(l, { pane: "fluss", color: "#fff", weight: 10, opacity: 0.9 }).addTo(ctx.ebenen.overlay);
      L.polyline(l, { pane: "fluss", color: farbe, weight: 6 }).addTo(ctx.ebenen.overlay);
    }
    const start = weg.knoten[0];
    const ziel = weg.knoten.at(-1);
    if (start.stockwerk_id === sid) L.circleMarker(ll(start.x, start.y), { pane: "fahrzeuge", radius: 9, color: "#fff", weight: 3, fillColor: KNOTEN_FARBEN.start, fillOpacity: 1 }).addTo(ctx.ebenen.overlay);
    if (ziel.stockwerk_id === sid) L.circleMarker(ll(ziel.x, ziel.y), { pane: "fahrzeuge", radius: 9, color: "#fff", weight: 3, fillColor: KNOTEN_FARBEN.ziel, fillOpacity: 1 }).addTo(ctx.ebenen.overlay);
    if (linien.length) ctx.karte.fitBounds(L.latLngBounds(linien.flat()).pad(0.3));

    // Stockwerke entlang des Wegs
    const folge = [];
    for (const k of weg.knoten) if (folge.at(-1) !== k.stockwerk_id) folge.push(k.stockwerk_id);
    const alle = teile.flatMap((tl) => tl.stockwerke.map((s) => ({ ...s, teil: tl })));
    leeren(
      unten,
      h("strong", lieferung?.name || ""),
      h("span", `${t("weg.dauer")}: ${dauer(weg.dauer)} · ${t("weg.laenge")}: ${zahl(weg.laenge_m, 0)} m`),
      h(
        "span.wegfolge",
        folge.map((s, i) => {
          const sw = alle.find((x) => x.id === s);
          const text = `${sw?.teil.kuerzel || ""} ${sw?.name || "?"}`.trim();
          return [i ? " → " : "", s === sid ? h("strong", text) : h("a", { href: ctx.stockwerkLink(s, "weg", lid) }, text)];
        })
      ),
      h("a.knopf-flach", { href: "#/lieferungen" }, t("weg.zurueck"))
    );
    unten.hidden = false;
  }

  // ---------------------------------------------------------------- Hinweis & Werkzeuge
  function hinweisZeigen(text, aktionen = []) {
    leeren(hinweis, h("span", text), aktionen.map(([label, fn]) => h("button.knopf-flach", { type: "button", onclick: fn }, label)));
    hinweis.hidden = false;
  }

  let werkzeug = null;
  function werkzeugStarten(fabrik) {
    if (werkzeug) werkzeug.beenden();
    ctx.editorWerkzeugBeenden?.();
    werkzeug = fabrik();
  }

  /** Klick-Werkzeug: sammelt Punkte, zeichnet eine Linie, ruft beiKlick(punkte) auf. */
  function linienWerkzeug({ text, beiKlick, beiEnde }) {
    const karte = ctx.karte;
    const punkte = [];
    const linie = L.polyline([], { color: "#d9480f", weight: 3, dashArray: "6 4" }).addTo(karte);
    const marker = L.layerGroup().addTo(karte);
    const vorschau = L.polyline([], { color: "#d9480f", weight: 2, opacity: 0.6 }).addTo(karte);
    karte.getContainer().classList.add("fadenkreuz");
    const dz = karte.doubleClickZoom.enabled();
    karte.doubleClickZoom.disable();

    const klick = (e) => {
      punkte.push(xy(e.latlng));
      linie.addLatLng(e.latlng);
      L.circleMarker(e.latlng, { radius: 5, color: "#d9480f", fillOpacity: 1 }).addTo(marker);
      beiKlick?.(punkte, werkzeugObj);
    };
    const bewegen = (e) => {
      if (punkte.length) vorschau.setLatLngs([linie.getLatLngs().at(-1), e.latlng]);
    };
    const taste = (e) => e.key === "Escape" && werkzeugObj.beenden();
    const doppel = () => beiEnde?.(punkte, werkzeugObj);

    karte.on("click", klick).on("mousemove", bewegen).on("dblclick", doppel);
    document.addEventListener("keydown", taste);

    const werkzeugObj = {
      punkte,
      hinweis: (neuerText) => hinweisZeigen(neuerText, [[t("karte.werkzeug_beenden"), werkzeugObj.beenden]]),
      beenden() {
        karte.off("click", klick).off("mousemove", bewegen).off("dblclick", doppel);
        document.removeEventListener("keydown", taste);
        [linie, marker, vorschau].forEach((l) => l.remove());
        karte.getContainer().classList.remove("fadenkreuz");
        if (dz) karte.doubleClickZoom.enable();
        hinweis.hidden = true;
        if (werkzeug === werkzeugObj) werkzeug = null;
      },
    };
    werkzeugObj.hinweis(text);
    return werkzeugObj;
  }

  function messen() {
    const mpp = ctx.stockwerk.meter_pro_punkt;
    return linienWerkzeug({
      text: t("karte.messen_hilfe"),
      beiKlick(punkte, w) {
        let summe = 0;
        for (let i = 1; i < punkte.length; i++) summe += abstand(punkte[i - 1], punkte[i]);
        if (punkte.length > 1) w.hinweis(t("karte.messen_ergebnis", { meter: zahl(summe * mpp, 1) }));
      },
      beiEnde: (_, w) => setTimeout(() => w.beenden(), 0),
    });
  }

  /** Maßstab eintragen („1 : 100“ wie auf dem Plan) oder auf dem Plan messen. */
  async function massstabDialog() {
    const s = ctx.stockwerk;
    let gefunden = [];
    try {
      gefunden = (await api(`stockwerke/${s.id}/massstab-vorschlag`)).gefunden;
    } catch {
      /* Vorschlag ist nur eine Hilfe */
    }
    const jetzt = s.meter_pro_punkt ? Math.round(s.meter_pro_punkt / METER_PRO_PDF_PUNKT) : null;
    const plan = s.plan || {};
    const mm = (pt) => Math.round((pt / 72) * 25.4);
    const format = papierformat(mm(plan.breite || 0), mm(plan.hoehe || 0));
    let messen = false;
    const messKnopf = h(
      "button.knopf-flach",
      { type: "button", onclick: (e) => { messen = true; e.target.closest("dialog").close(); } },
      t("karte.massstab_messen")
    );
    const ok = await formularDialog({
      titel: t("karte.massstab_festlegen"),
      felder: [
        {
          name: "verhaeltnis", label: t("karte.massstab_eingeben"), typ: "number", pflicht: true,
          wert: gefunden[0] ?? jetzt ?? "", attr: { min: 1, step: 1, placeholder: "100" },
          hilfe: gefunden.length
            ? t("karte.massstab_gefunden", { werte: gefunden.slice(0, 3).map((n) => `1:${n}`).join(", ") })
            : t("karte.massstab_nicht_gefunden"),
        },
        { name: "_hinweis", typ: "element", element: h("p.hinweis", t("karte.massstab_original", {
          format: format ? `${format}, ` : "", breite: mm(plan.breite || 0), hoehe: mm(plan.hoehe || 0) })), lesen: () => null },
        { name: "_messen", typ: "element", label: t("karte.massstab_oder"), element: messKnopf, lesen: () => null },
      ],
      speichern: async (werte) => {
        if (!(werte.verhaeltnis >= 1)) throw new Error(t("karte.massstab_ungueltig"));
        await api(`stockwerke/${s.id}/massstab`, { methode: "PUT", daten: { verhaeltnis: werte.verhaeltnis } });
      },
    });
    if (messen) return werkzeugStarten(massstabMessen);
    if (ok) {
      melden(t("karte.massstab_gespeichert_pruefen", { wert: ok.verhaeltnis }));
      aufraeumen();
      stockwerkLaden();
    }
  }

  function massstabMessen() {
    return linienWerkzeug({
      text: t("karte.massstab_hilfe"),
      async beiKlick(punkte, w) {
        if (punkte.length < 2) return;
        const [a, b] = punkte;
        w.beenden();
        const strecke = abstand(a, b);
        if (strecke < 1) return;
        const ok = await formularDialog({
          titel: t("karte.massstab_festlegen"),
          felder: [{ name: "meter", label: t("karte.massstab_frage"), typ: "number", pflicht: true, attr: { min: 0.01, step: 0.01 } }],
          speichern: async (werte) => {
            if (!(werte.meter > 0)) throw new Error(t("karte.massstab_meter"));
            await api(`stockwerke/${ctx.stockwerk.id}/massstab`, { methode: "PUT", daten: { meter_pro_punkt: werte.meter / strecke } });
          },
        });
        if (ok) {
          melden(t("karte.massstab_gespeichert"));
          aufraeumen();
          stockwerkLaden();
        }
      },
    });
  }

  function aufraeumen() {
    clearTimeout(timer);
    werkzeug?.beenden();
    modusAufraeumen?.();
    modusAufraeumen = null;
  }

  seitenleisteLaden();
  if (gewaehlt) stockwerkLaden();

  return () => {
    aufraeumen();
    beobachter?.disconnect();
    ctx.karte?.remove();
    ctx.karte = null;
  };
}
