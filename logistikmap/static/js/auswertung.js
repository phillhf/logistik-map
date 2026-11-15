// Auswertung eines Tages: Engpässe, Auslastung, Fahrten, Verspätungen

import { api, dauer, fehlerMelden, fehlerText, h, heute, leeren, punktName, sekunden, stammdaten, t, uhr, zahl } from "./basis.js";
import { simulationLaden } from "./ablauf.js";

export function zeigeAuswertung(wurzel, [datumParam]) {
  let datum = /^\d{4}-\d{2}-\d{2}$/.test(datumParam || "") ? datumParam : heute();
  const datumFeld = h("input", { type: "date", value: datum });
  const vonFeld = h("input", { type: "time", value: "00:00" });
  const bisFeld = h("input", { type: "time", value: "23:59" });
  const startWahl = h("select");
  const taWahl = h("select");
  const neuKnopf = h("button.knopf-flach", { type: "button", title: t("auswertung.neu_rechnen") }, "↻");
  const inhalt = h("div.auswertung");
  let sim = null;
  let punkte = [];
  let stamm = null;

  wurzel.append(
    h(
      "section.karte-box",
      h(
        "div.box-kopf",
        h("h2", t("auswertung.titel")),
        h(
          "div.knopfreihe.filter",
          datumFeld,
          h("label.inline", t("auswertung.von"), vonFeld),
          h("label.inline", t("auswertung.bis"), bisFeld),
          startWahl,
          taWahl,
          neuKnopf
        )
      ),
      h("p.hinweis", t("auswertung.hilfe")),
      inhalt
    )
  );

  datumFeld.addEventListener("change", () => {
    datum = datumFeld.value || heute();
    history.replaceState(null, "", `#/auswertung/${datum}`);
    laden();
  });
  [vonFeld, bisFeld, startWahl, taWahl].forEach((e) => e.addEventListener("change", zeigen));
  neuKnopf.addEventListener("click", () => laden(true));

  async function laden(neu = false) {
    leeren(inhalt, h("p.gedimmt", t("allgemein.laedt")));
    try {
      [sim, punkte, stamm] = await Promise.all([simulationLaden(datum, neu), api("punkte"), stammdaten()]);
    } catch (e) {
      return fehlerMelden(e);
    }
    const starts = [...new Set(sim.fahrten.map((f) => f.start_id))];
    const alterStart = startWahl.value;
    leeren(startWahl, h("option", { value: "" }, t("ablauf.filter.alle_starts")), starts.map((id) => h("option", { value: id, selected: String(id) === alterStart }, punktName(punkt(id)))));
    const alteTa = taWahl.value;
    leeren(taWahl, h("option", { value: "" }, t("ablauf.filter.alle_transportarten")), stamm.transportarten.map((x) => h("option", { value: x.id, selected: String(x.id) === alteTa }, x.name)));
    zeigen();
  }

  const punkt = (id) => punkte.find((p) => p.id === id);

  function zeigen() {
    if (!sim) return;
    const von = sekunden(vonFeld.value || "00:00");
    const bis = sekunden(bisFeld.value || "23:59") + 59;
    const fahrten = sim.fahrten.filter(
      (f) => f.geplant >= von && f.geplant <= bis && (!startWahl.value || String(f.start_id) === startWahl.value) && (!taWahl.value || String(f.transportart_id) === taWahl.value)
    );
    const gefiltert = fahrten.length !== sim.fahrten.length;
    const warte = (f) => f.warte.fahrzeug + f.warte.aufzug + f.warte.engstelle;
    const verspaetet = fahrten.filter((f) => f.verspaetet);
    const maxWarte = Math.max(0, ...fahrten.map(warte));

    const kachel = (wert, text, art = "") => h(`div.kennzahl${art ? "." + art : ""}`, h("strong", wert), h("span", text));
    const engpaesse = sim.engpaesse.map((e) => sim.ressourcen.find((r) => r.typ === e.typ && r.id === e.id));

    leeren(
      inhalt,
      sim.feiertag ? h("p.feiertag-hinweis", t("auswertung.feiertag", { name: feiertagName(sim.feiertag) })) : null,
      h(
        "div.kennzahlen",
        kachel(new Set(fahrten.map((f) => f.lieferung_id)).size, t("auswertung.k.lieferungen")),
        kachel(fahrten.length, t("auswertung.k.fahrten")),
        kachel(verspaetet.length, t("auswertung.k.verspaetet"), verspaetet.length ? "schlecht" : "gut"),
        kachel(dauer(maxWarte), t("auswertung.k.max_warte"), maxWarte >= 300 ? "schlecht" : maxWarte >= 60 ? "mittel" : "gut"),
        kachel(engpaesse.length, t("auswertung.k.engpaesse"), engpaesse.length ? "schlecht" : "gut")
      ),
      gefiltert ? h("p.hinweis", t("auswertung.gefiltert")) : null,

      sim.fehler.length
        ? h(
            "div.fehlerbox",
            h("h3", t("auswertung.fehler_titel")),
            h("ul", sim.fehler.map((f) => h("li", h("strong", f.name), ": ", fehlerText(f))))
          )
        : null,

      h("h3", t("auswertung.engpaesse")),
      engpaesse.length
        ? h("div.engpaesse", engpaesse.map((r) => engpassKarte(r)))
        : h("p.gut", sim.fahrten.length ? t("auswertung.keine_engpaesse") : t("auswertung.keine_fahrten")),

      sim.ressourcen.length ? [h("h3", t("auswertung.auslastung")), zeitleiste(sim.ressourcen)] : null,

      h("h3", t("auswertung.fahrten", { anzahl: fahrten.length })),
      fahrten.length ? fahrtenTabelle(fahrten) : h("p.leer", t("auswertung.keine_fahrten"))
    );
  }

  function feiertagName(k) {
    const x = t(`feiertag.${k}`);
    return x.startsWith("⟨") ? k : x;
  }

  function ressourceName(r) {
    return `${t(`ressource.${r.typ}`)}: ${r.name}`;
  }

  function kartenLink(r, zeit) {
    let sid = r.stockwerk_id;
    if (r.typ === "aufzug") sid = punkte.find((p) => p.aufzug_id === r.id)?.stockwerk_id;
    if (!sid) return null;
    return `#/karte/${sid}/ablauf/${datum}/${uhr(zeit)}`;
  }

  function engpassKarte(r) {
    const spitze = r.raster.reduce((a, b) => (b[1] > a[1] ? b : a), [0, 0]);
    const ersteWarte = r.verlauf.find((v) => v[2] > 0)?.[0] ?? spitze[0];
    const link = kartenLink(r, ersteWarte);
    const zeilen = [
      t("engpass.wartezeit", { max: dauer(r.max_wartezeit), summe: dauer(r.summe_wartezeit) }),
      t("engpass.schlange", { anzahl: r.max_schlange }),
      t("engpass.spitze", { prozent: zahl(r.spitze * 100, 0), von: uhr(spitze[0]), bis: uhr(spitze[0] + 300) }),
    ];
    if (r.typ === "aufzug") {
      zeilen.push(t("engpass.aufzugfahrten", { anzahl: r.fahrten, exklusiv: r.exklusiv }));
      if (r.zu_gross) zeilen.push(t("engpass.zu_gross", { anzahl: r.zu_gross }));
    }
    return h(
      "div.engpass",
      h("div.engpass-kopf", h("strong", ressourceName(r)), link ? h("a.knopf-flach", { href: link }, t("auswertung.auf_karte")) : null),
      h("ul", zeilen.map((z) => h("li", z))),
      h("p.tipp", t(`engpass.tipp.${r.typ}`))
    );
  }

  /** Auslastung je 5 Minuten als Farbstreifen, Zeitraum an die Daten angepasst. */
  function zeitleiste(ressourcen) {
    const alle = ressourcen.flatMap((r) => r.raster.map((x) => x[0]));
    if (!alle.length) return null;
    const start = Math.floor(Math.min(...alle) / 3600) * 3600;
    const ende = Math.min(Math.ceil((Math.max(...alle) + 300) / 3600) * 3600, 2 * 86400);
    const spalten = (ende - start) / 300;
    const stunden = [];
    for (let s = start; s < ende; s += 3600) stunden.push(s);
    const sortiert = [...ressourcen].sort((a, b) => b.spitze - a.spitze || b.max_wartezeit - a.max_wartezeit);
    return h(
      "div.zeitleiste",
      { style: { "--spalten": spalten } },
      h("div.zl-name"),
      h("div.zl-achse", stunden.map((s) => h("span", { style: { width: `${(12 / spalten) * 100}%` } }, uhr(s)))),
      sortiert.map((r) => {
        const werte = new Map(r.raster.map(([s, v]) => [s, v]));
        return [
          h("div.zl-name", { title: ressourceName(r) }, ressourceName(r)),
          h(
            "div.zl-streifen",
            Array.from({ length: spalten }, (_, i) => {
              const s = start + i * 300;
              const v = werte.get(s) || 0;
              const link = kartenLink(r, s);
              return h(link ? "a" : "span", {
                href: link || undefined,
                title: `${uhr(s)}–${uhr(s + 300)}: ${zahl(v * 100, 0)} %`,
                style: { background: v ? farbe(v) : "transparent" },
              });
            })
          ),
        ];
      }),
      h("div.zl-legende", h("span", t("auswertung.legende")), [0.25, 0.5, 0.75, 1].map((v) => h("span.zl-feld", { style: { background: farbe(v) } }, `${v * 100} %`)))
    );
  }

  function farbe(v) {
    // grün → gelb → rot
    const x = Math.min(1, v);
    const hue = 120 - 120 * x;
    return `hsl(${hue}, 70%, ${55 - 10 * x}%)`;
  }

  function fahrtenTabelle(fahrten) {
    const ta = (id) => stamm.transportarten.find((x) => x.id === id);
    return h(
      "div.tabellenrahmen",
      h(
        "table.tabelle.kompakt",
        h(
          "thead",
          h("tr", ["geplant", "lieferung", "von_nach", "los", "ankunft", "warten", "zurueck"].map((k) => h("th", t(`auswertung.spalte.${k}`))))
        ),
        h(
          "tbody",
          fahrten
            .slice()
            .sort((a, b) => a.geplant - b.geplant || a.id - b.id)
            .map((f) => {
              const w = f.warte.fahrzeug + f.warte.aufzug + f.warte.engstelle;
              const details = Object.entries(f.warte).filter(([, v]) => v > 0).map(([k, v]) => `${t(`ablauf.warte.${k}`)} ${dauer(v)}`).join(", ");
              const sid = punkt(f.start_id)?.stockwerk_id;
              return h(
                "tr",
                { class: f.verspaetet ? "verspaetet" : "" },
                h("td.zeit", uhr(f.geplant)),
                h(
                  "td",
                  h("strong", f.name),
                  f.von_n > 1 ? h("small", t("ablauf.fahrt_nr", { nr: f.nr, von: f.von_n })) : null,
                  h("small", { style: { color: ta(f.transportart_id)?.farbe } }, ta(f.transportart_id)?.name, f.art === "spaeter" ? ` · ${t("rueckweg.spaeter")}` : "")
                ),
                h("td", h("span", punktName(punkt(f.start_id))), h("small", "→ " + punktName(punkt(f.ziel_id)))),
                h("td.zeit", uhr(f.start)),
                h("td.zeit", uhr(f.ankunft), f.spaetestens ? h("small", `${t("ablauf.spaetestens")} ${uhr(f.spaetestens)}`) : null),
                h("td", { title: details }, w ? dauer(w) : "–", details ? h("small", details) : null),
                h("td.zeit", uhr(f.ende), sid ? h("a.knopf-flach", { href: `#/karte/${sid}/ablauf/${datum}/${uhr(f.geplant)}` }, "→") : null)
              );
            })
        )
      )
    );
  }

  laden();
}
