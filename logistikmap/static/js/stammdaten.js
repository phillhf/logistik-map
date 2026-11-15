// Stammdaten und Rechengrundlagen: Transportarten, Wagentypen, Aufzüge und Treppen

import { api, bestaetigen, darf, fehlerMelden, formularDialog, h, leeren, stammdaten, t, zahl } from "./basis.js";
import { simulationVergessen } from "./ablauf.js";

export function zeigeStammdaten(wurzel) {
  const bearbeiten = darf("bearbeiten");
  const taBox = h("div");
  const wtBox = h("div");
  const aufBox = h("div");
  let stamm = null;

  const abschnitt = (titel, hilfe, neu, box) =>
    h(
      "section.karte-box",
      h("div.box-kopf", h("h2", titel), bearbeiten ? h("button.knopf", { type: "button", onclick: () => neu() }, "+ " + t("allgemein.anlegen")) : null),
      h("p.hinweis", hilfe),
      box
    );

  wurzel.append(
    h(
      "div.stapel",
      abschnitt(t("stamm.transportarten"), t("stamm.transportarten_hilfe"), () => transportartDialog(), taBox),
      h(
        "div.spalten.gleich",
        abschnitt(t("stamm.aufzuege"), t("stamm.aufzuege_hilfe"), () => aufzugDialog(), aufBox),
        abschnitt(t("stamm.wagentypen"), t("stamm.wagentypen_hilfe"), () => wagentypDialog(), wtBox)
      )
    )
  );

  async function laden() {
    try {
      stamm = await stammdaten(true);
    } catch (e) {
      return fehlerMelden(e);
    }
    zeigen();
  }

  const aktionen = (bearb, loesch) =>
    bearbeiten
      ? h(
          "td.aktionen",
          h("button.knopf-flach", { type: "button", onclick: bearb }, t("allgemein.bearbeiten")),
          h("button.knopf-flach.gefahr", { type: "button", onclick: loesch }, t("allgemein.loeschen"))
        )
      : h("td");

  function tabelle(spalten, zeilen) {
    if (!zeilen.length) return h("p.leer", t("allgemein.keine_eintraege"));
    return h("div.tabellenrahmen", h("table.tabelle", h("thead", h("tr", spalten.map((s) => h("th", s)), h("th"))), h("tbody", zeilen)));
  }

  function zeigen() {
    leeren(
      taBox,
      tabelle(
        [t("stamm.name"), t("stamm.geschwindigkeit"), t("stamm.laden_entladen"), t("stamm.wagen_pro_fahrt"), t("stamm.anzahl"), t("stamm.aufzug")],
        stamm.transportarten.map((x) =>
          h(
            "tr",
            h("td", h("span.farbpunkt", { style: { background: x.farbe } }), x.name),
            h("td", `${zahl(x.geschwindigkeit, 2)} m/s (${zahl(x.geschwindigkeit * 3.6, 1)} km/h)`),
            h("td", `${zahl(x.ladezeit, 0)} s / ${zahl(x.entladezeit, 0)} s`),
            h("td", x.wagen_pro_fahrt),
            h("td", x.anzahl || t("stamm.unbegrenzt")),
            h("td", x.aufzug_exklusiv ? t("stamm.exklusiv") : t("stamm.geteilt"), x.treppe ? ` · ${t("stamm.treppe_ja")}` : ""),
            aktionen(() => transportartDialog(x), () => loeschen(`transportarten/${x.id}`, x.name))
          )
        )
      )
    );
    leeren(
      aufBox,
      tabelle(
        [t("stamm.name"), t("stamm.plaetze"), t("stamm.zeiten")],
        stamm.aufzuege.map((a) =>
          h(
            "tr",
            h("td", a.name, h("small", t(`aufzug.art.${a.art}`))),
            h("td", a.art === "treppe" ? "–" : a.plaetze || t("stamm.unbegrenzt")),
            h(
              "td",
              a.art === "treppe"
                ? t("stamm.treppe_zeit", { s: zahl(a.fahrzeit_etage, 0) })
                : t("stamm.aufzug_zeit", { etage: zahl(a.fahrzeit_etage, 0), tuer: zahl(a.tuerzeit, 0), anfahrt: zahl(a.anfahrt, 0), raeum: zahl(a.raeumzeit, 0) }),
              a.transportarten.length ? h("small", `${t("stamm.nur_fuer")}: ${a.transportarten.map((id) => stamm.transportarten.find((x) => x.id === id)?.name).join(", ")}`) : null
            ),
            aktionen(() => aufzugDialog(a), () => loeschen(`aufzuege/${a.id}`, a.name))
          )
        )
      )
    );
    leeren(
      wtBox,
      tabelle(
        [t("stamm.name"), t("stamm.platzbedarf")],
        stamm.wagentypen.map((w) => h("tr", h("td", w.name), h("td", zahl(w.plaetze, 1)), aktionen(() => wagentypDialog(w), () => loeschen(`wagentypen/${w.id}`, w.name))))
      )
    );
  }

  async function speichern(pfad, id, daten) {
    await api(id ? `${pfad}/${id}` : pfad, { methode: id ? "PUT" : "POST", daten });
    simulationVergessen();
  }

  async function transportartDialog(x = {}) {
    const ok = await formularDialog({
      titel: x.id ? `${t("stamm.transportart")}: ${x.name}` : t("stamm.transportart_neu"),
      felder: [
        { name: "name", label: t("stamm.name"), pflicht: true, wert: x.name },
        { name: "farbe", label: t("stamm.farbe"), typ: "color", wert: x.farbe || "#1f5f8b" },
        { name: "geschwindigkeit", label: t("stamm.geschwindigkeit_ms"), typ: "number", pflicht: true, wert: x.geschwindigkeit ?? 1, attr: { min: 0.05, step: 0.05 }, hilfe: t("stamm.geschwindigkeit_hilfe") },
        { name: "ladezeit", label: t("stamm.ladezeit"), typ: "number", pflicht: true, wert: x.ladezeit ?? 60, attr: { min: 0 } },
        { name: "entladezeit", label: t("stamm.entladezeit"), typ: "number", pflicht: true, wert: x.entladezeit ?? 60, attr: { min: 0 } },
        { name: "wagen_pro_fahrt", label: t("stamm.wagen_pro_fahrt"), typ: "number", pflicht: true, wert: x.wagen_pro_fahrt ?? 1, attr: { min: 1 }, hilfe: t("stamm.wagen_pro_fahrt_hilfe") },
        { name: "anzahl", label: t("stamm.anzahl"), typ: "number", pflicht: true, wert: x.anzahl ?? 0, attr: { min: 0 }, hilfe: t("stamm.anzahl_hilfe") },
        { name: "aufzug_exklusiv", label: t("stamm.aufzug_exklusiv"), typ: "haken", wert: x.aufzug_exklusiv },
        { name: "treppe", label: t("stamm.kann_treppe"), typ: "haken", wert: x.treppe },
      ],
      speichern: (w) => speichern("transportarten", x.id, w),
    });
    if (ok) laden();
  }

  async function aufzugDialog(a = {}) {
    const ok = await formularDialog({
      titel: a.id ? `${t(`aufzug.art.${a.art}`)}: ${a.name}` : t("stamm.aufzug_neu"),
      felder: [
        { name: "name", label: t("stamm.name"), pflicht: true, wert: a.name },
        { name: "art", label: t("stamm.art"), typ: "auswahl", wert: a.art || "aufzug", optionen: [["aufzug", t("aufzug.art.aufzug")], ["treppe", t("aufzug.art.treppe")]] },
        { name: "plaetze", label: t("stamm.plaetze"), typ: "number", pflicht: true, wert: a.plaetze ?? 2, attr: { min: 0, step: 0.5 }, hilfe: t("stamm.plaetze_hilfe") },
        { name: "fahrzeit_etage", label: t("stamm.fahrzeit_etage"), typ: "number", pflicht: true, wert: a.fahrzeit_etage ?? 8, attr: { min: 0 } },
        { name: "tuerzeit", label: t("stamm.tuerzeit"), typ: "number", pflicht: true, wert: a.tuerzeit ?? 10, attr: { min: 0 }, hilfe: t("stamm.tuerzeit_hilfe") },
        { name: "anfahrt", label: t("stamm.anfahrt"), typ: "number", pflicht: true, wert: a.anfahrt ?? 30, attr: { min: 0 }, hilfe: t("stamm.anfahrt_hilfe") },
        { name: "raeumzeit", label: t("stamm.raeumzeit"), typ: "number", pflicht: true, wert: a.raeumzeit ?? 20, attr: { min: 0 }, hilfe: t("stamm.raeumzeit_hilfe") },
        { name: "transportarten", label: t("stamm.erlaubt_fuer"), typ: "mehrfach", wert: a.transportarten || [], optionen: stamm.transportarten.map((x) => [x.id, x.name]), hilfe: t("stamm.erlaubt_fuer_hilfe") },
      ],
      speichern: (w) => speichern("aufzuege", a.id, w),
    });
    if (ok) laden();
  }

  async function wagentypDialog(w = {}) {
    const ok = await formularDialog({
      titel: w.id ? `${t("stamm.wagentyp")}: ${w.name}` : t("stamm.wagentyp_neu"),
      felder: [
        { name: "name", label: t("stamm.name"), pflicht: true, wert: w.name },
        { name: "plaetze", label: t("stamm.platzbedarf"), typ: "number", pflicht: true, wert: w.plaetze ?? 1, attr: { min: 0.1, step: 0.1 }, hilfe: t("stamm.platzbedarf_hilfe") },
      ],
      speichern: (x) => speichern("wagentypen", w.id, x),
    });
    if (ok) laden();
  }

  async function loeschen(pfad, name) {
    if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name })))) return;
    try {
      await api(pfad, { methode: "DELETE" });
      simulationVergessen();
      laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  laden();
}
