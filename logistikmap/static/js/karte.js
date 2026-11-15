// Kartenansicht: Stockwerksplan als Kachelkarte, Maßstab festlegen, Strecken messen.
//
// Koordinaten sind PDF-Punkte der Planseite (x nach rechts, y nach unten). In Leaflet
// steht y als "lat" und x als "lng". Zoomstufe z entspricht 2^(z-4) Pixel pro Punkt,
// passend zu logistikmap/plaene.py.

import { api, darf, fehlerMelden, formularDialog, h, leeren, melden, t, zahl } from "./basis.js";

const ZOOM_VERSATZ = 4;
const CRS = L.extend({}, L.CRS.Simple, { transformation: new L.Transformation(2 ** -ZOOM_VERSATZ, 0, 2 ** -ZOOM_VERSATZ, 0) });

const punkt = (latlng) => ({ x: latlng.lng, y: latlng.lat });
const abstand = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

export function zeigeKarte(wurzel, [stockwerkParam]) {
  const seitenleiste = h("aside.seitenleiste");
  const kartenRahmen = h("div.kartenrahmen");
  const kopfzeile = h("div.kartenkopf");
  const hinweis = h("div.kartenhinweis", { hidden: true });
  const kartenEl = h("div.karte");
  kartenRahmen.append(kopfzeile, kartenEl, hinweis);
  wurzel.append(seitenleiste, kartenRahmen);

  let karte = null;
  let stockwerk = null;
  let werkzeug = null; // { beenden() }
  let timer = null;
  const gewaehlt = Number(stockwerkParam) || null;

  // ---------------------------------------------------------------- Seitenleiste
  async function seitenleisteLaden() {
    let teile;
    try {
      teile = await api("gebaeude");
    } catch (e) {
      return fehlerMelden(e);
    }
    if (!teile.length) {
      leeren(
        seitenleiste,
        h("p.leer", t("karte.keine_gebaeude")),
        darf("bearbeiten") ? h("a.knopf", { href: "#/gebaeude" }, t("karte.zur_verwaltung")) : null
      );
      leeren(kopfzeile);
      return;
    }
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
                  { href: `#/karte/${s.id}`, class: s.id === gewaehlt ? "aktiv" : "", title: t("karte.ebene", { ebene: s.ebene }) },
                  h("span", s.name),
                  !s.plan || s.plan.status !== "fertig" ? h("span.punkt", { title: s.plan ? t(`gebaeude.status.${s.plan.status}`, { prozent: "" }) : t("gebaeude.kein_plan") }) : null
                )
              )
            )
          )
        )
      )
    );
    if (!gewaehlt) {
      // erstes Stockwerk mit fertigem Plan öffnen
      const erstes = teile.flatMap((tl) => tl.stockwerke).find((s) => s.plan?.status === "fertig");
      if (erstes) location.replace(`#/karte/${erstes.id}`);
      else leeren(kopfzeile, h("span.gedimmt", t("karte.kein_stockwerk")));
    }
  }

  // ---------------------------------------------------------------- Stockwerk laden
  async function stockwerkLaden() {
    clearTimeout(timer);
    try {
      stockwerk = await api(`stockwerke/${gewaehlt}`);
    } catch (e) {
      return fehlerMelden(e);
    }
    const plan = stockwerk.plan;
    kopfAufbauen();
    if (!plan || plan.status !== "fertig") {
      kartenEl.hidden = true;
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
    kartenEl.hidden = false;
    karteAufbauen(plan);
  }

  function kopfAufbauen() {
    const s = stockwerk;
    const massstab = s.meter_pro_punkt
      ? h("span.massstab-info", `1 : ${zahl(s.meter_pro_punkt / 0.000352778, 0)}`)
      : h("span.massstab-info.fehlt", t("karte.massstab_fehlt"));
    leeren(
      kopfzeile,
      h("h2", s.gebaeudeteil.kuerzel ? h("span.kuerzel", s.gebaeudeteil.kuerzel) : null, s.name),
      s.plan?.status === "fertig" ? massstab : null,
      h("div.abstand"),
      s.plan?.status === "fertig" && s.meter_pro_punkt
        ? h("button.knopf-flach", { type: "button", onclick: () => werkzeugStarten(messen) }, t("karte.messen"))
        : null,
      s.plan?.status === "fertig" && darf("bearbeiten")
        ? h("button.knopf-flach", { type: "button", onclick: () => werkzeugStarten(massstabFestlegen) }, t("karte.massstab_festlegen"))
        : null
    );
  }

  // ---------------------------------------------------------------- Karte
  function karteAufbauen(plan) {
    if (karte) karte.remove();
    const grenzen = L.latLngBounds([0, 0], [plan.hoehe, plan.breite]);
    karte = L.map(kartenEl, {
      crs: CRS,
      minZoom: 0,
      maxZoom: plan.max_zoom + 2,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 90,
      attributionControl: false,
      maxBounds: grenzen.pad(0.5),
      doubleClickZoom: true,
    });
    L.tileLayer(`/api/plaene/${plan.id}/kacheln/{z}/{x}/{y}.png`, {
      tileSize: 256,
      minZoom: 0,
      maxNativeZoom: plan.max_zoom,
      maxZoom: plan.max_zoom + 2,
      bounds: grenzen,
      noWrap: true,
      keepBuffer: 4,
    }).addTo(karte);
    karte.fitBounds(grenzen);
    karte.setMinZoom(Math.max(0, Math.floor(karte.getZoom()) - 1));
    if (stockwerk.meter_pro_punkt) massstabsleiste(stockwerk.meter_pro_punkt).addTo(karte);
    new ResizeObserver(() => karte?.invalidateSize()).observe(kartenEl);
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

  // ---------------------------------------------------------------- Werkzeuge
  function werkzeugStarten(fabrik) {
    if (werkzeug) werkzeug.beenden();
    werkzeug = fabrik();
  }

  function hinweisZeigen(text, beenden) {
    leeren(hinweis, h("span", text), h("button.knopf-flach", { type: "button", onclick: beenden }, t("karte.werkzeug_beenden")));
    hinweis.hidden = false;
  }

  /** Klick-Werkzeug: sammelt Punkte, zeichnet eine Linie, ruft beiKlick(punkte) auf. */
  function linienWerkzeug({ text, beiKlick, beiEnde }) {
    const punkte = [];
    const linie = L.polyline([], { color: "#d9480f", weight: 3, dashArray: "6 4" }).addTo(karte);
    const marker = L.layerGroup().addTo(karte);
    const vorschau = L.polyline([], { color: "#d9480f", weight: 2, opacity: 0.6 }).addTo(karte);
    karte.getContainer().classList.add("fadenkreuz");
    karte.doubleClickZoom.disable();

    const klick = (e) => {
      punkte.push(punkt(e.latlng));
      linie.addLatLng(e.latlng);
      L.circleMarker(e.latlng, { radius: 5, color: "#d9480f", fillOpacity: 1 }).addTo(marker);
      beiKlick?.(punkte, werkzeugObj);
    };
    const bewegen = (e) => {
      if (punkte.length) vorschau.setLatLngs([linie.getLatLngs().at(-1), e.latlng]);
    };
    const taste = (e) => e.key === "Escape" && werkzeugObj.beenden();
    const doppel = () => beiEnde?.(punkte, werkzeugObj);

    karte.on("click", klick);
    karte.on("mousemove", bewegen);
    karte.on("dblclick", doppel);
    document.addEventListener("keydown", taste);

    const werkzeugObj = {
      punkte,
      hinweis: (neuerText) => hinweisZeigen(neuerText, werkzeugObj.beenden),
      beenden() {
        karte.off("click", klick).off("mousemove", bewegen).off("dblclick", doppel);
        document.removeEventListener("keydown", taste);
        [linie, marker, vorschau].forEach((l) => l.remove());
        karte.getContainer().classList.remove("fadenkreuz");
        karte.doubleClickZoom.enable();
        hinweis.hidden = true;
        if (werkzeug === werkzeugObj) werkzeug = null;
      },
    };
    werkzeugObj.hinweis(text);
    return werkzeugObj;
  }

  function messen() {
    const mpp = stockwerk.meter_pro_punkt;
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

  function massstabFestlegen() {
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
            await api(`stockwerke/${stockwerk.id}/massstab`, { methode: "PUT", daten: { meter_pro_punkt: werte.meter / strecke } });
          },
        });
        if (ok) {
          melden(t("karte.massstab_gespeichert"));
          stockwerkLaden();
        }
      },
    });
  }

  seitenleisteLaden();
  if (gewaehlt) stockwerkLaden();

  return () => {
    clearTimeout(timer);
    werkzeug?.beenden();
    karte?.remove();
  };
}
