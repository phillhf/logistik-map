// Auswertung: Tag (Engpässe, Auslastung, Fahrten) oder Woche (Heatmap) – Ist-Zustand oder Szenario im Vergleich.
// Hash: #/auswertung/<datum>[/<szenario>][?woche]

import { api, dauer, fehlerMelden, fehlerText, h, herunterladen, heute, leeren, punktName, sekunden, stammdaten, szenarioAuswahl, t, uhr, zahl } from "./basis.js";
import { simulationLaden } from "./ablauf.js";

function merkerLesen() {
  try {
    return sessionStorage.getItem("auswertung-ansicht");
  } catch {
    return null;
  }
}
function merkerSetzen(wert) {
  try {
    sessionStorage.setItem("auswertung-ansicht", wert);
  } catch {}
}

export async function zeigeAuswertung(wurzel, [datumParam, szenarioParam]) {
  let datum = /^\d{4}-\d{2}-\d{2}$/.test(datumParam || "") ? datumParam : heute();
  let szenario = Number(szenarioParam) || null;
  let ansicht = merkerLesen() || "tag";
  const datumFeld = h("input", { type: "date", value: datum });
  const vonFeld = h("input", { type: "time", value: "00:00" });
  const bisFeld = h("input", { type: "time", value: "23:59" });
  const startWahl = h("select");
  const taWahl = h("select");
  const neuKnopf = h("button.knopf-flach", { type: "button", title: t("auswertung.neu_rechnen") }, "↻");
  const ansichtWahl = h("div.umschalter");
  const exportLeiste = h("div.knopfreihe.export");
  const inhalt = h("div.auswertung");
  let sim = null;
  let ist = null;
  let punkte = [];
  let stamm = null;
  let stockwerke = [];

  const szenarioWahl = await szenarioAuswahl(szenario, (wert) => {
    szenario = wert;
    adresse();
    laden();
  });

  wurzel.append(
    h(
      "section.karte-box",
      h(
        "div.box-kopf",
        h("h2", t("auswertung.titel")),
        h("div.knopfreihe.filter", ansichtWahl, datumFeld, szenarioWahl, h("span.nur-tag", h("label.inline", t("auswertung.von"), vonFeld), h("label.inline", t("auswertung.bis"), bisFeld), startWahl, taWahl), neuKnopf)
      ),
      h("p.hinweis", t("auswertung.hilfe")),
      exportLeiste,
      inhalt
    )
  );

  function ansichtKnoepfe() {
    leeren(
      ansichtWahl,
      ["tag", "woche"].map((a) =>
        h("a", { href: "javascript:void 0", class: a === ansicht ? "aktiv" : "", onclick: () => ((ansicht = a), merkerSetzen(a), ansichtKnoepfe(), laden()) }, t(`auswertung.ansicht.${a}`))
      )
    );
    wurzel.querySelector(".nur-tag")?.toggleAttribute("hidden", ansicht !== "tag");
  }

  function adresse() {
    history.replaceState(null, "", `#/auswertung/${datum}${szenario ? `/${szenario}` : ""}`);
  }

  datumFeld.addEventListener("change", () => {
    datum = datumFeld.value || heute();
    adresse();
    laden();
  });
  [vonFeld, bisFeld, startWahl, taWahl].forEach((e) => e.addEventListener("change", zeigen));
  neuKnopf.addEventListener("click", () => laden(true));

  async function laden(neu = false) {
    leeren(inhalt, h("p.gedimmt", t("allgemein.laedt")));
    exportLeisteAufbauen();
    try {
      [punkte, stamm, stockwerke] = await Promise.all([api("punkte"), stammdaten(), api("gebaeude").then((g) => g.flatMap((teil) => teil.stockwerke.filter((s) => s.plan?.status === "fertig").map((s) => ({ ...s, teil }))))]);
      exportLeisteAufbauen();
      if (ansicht === "woche") return wocheZeigen();
      [sim, ist] = await Promise.all([simulationLaden(datum, neu, szenario), szenario ? simulationLaden(datum, neu, null) : Promise.resolve(null)]);
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

  function exportLeisteAufbauen() {
    const q = `datum=${datum}${szenario ? `&szenario=${szenario}` : ""}`;
    const swWahl = h("select", stockwerke.map((s) => h("option", { value: s.id }, `${s.teil.kuerzel || s.teil.name} · ${s.name}`)));
    leeren(
      exportLeiste,
      h("button.knopf-flach", { type: "button", onclick: () => herunterladen(`export/auswertung.xlsx?${q}`).catch(fehlerMelden) }, "⤓ " + t("auswertung.export_excel")),
      stockwerke.length
        ? h(
            "span.inline-gruppe",
            swWahl,
            h(
              "button.knopf-flach",
              {
                type: "button",
                onclick: () =>
                  herunterladen(`export/karte/${swWahl.value}.pdf?${q}&von=${vonFeld.value || "00:00"}&bis=${bisFeld.value || "23:59"}${startWahl.value ? `&start=${startWahl.value}` : ""}`).catch(fehlerMelden),
              },
              "⤓ " + t("auswertung.export_karte")
            )
          )
        : null,
      h("button.knopf-flach", { type: "button", onclick: () => window.print() }, "⎙ " + t("auswertung.drucken"))
    );
  }

  const punkt = (id) => punkte.find((p) => p.id === id);
  const warte = (f) => f.warte.fahrzeug + f.warte.aufzug + f.warte.engstelle;

  function kennzahlen(e, fahrten) {
    const verspaetet = fahrten.filter((f) => f.verspaetet).length;
    const maxWarte = Math.max(0, ...fahrten.map(warte));
    return {
      lieferungen: new Set(fahrten.map((f) => f.lieferung_id)).size,
      fahrten: fahrten.length,
      verspaetet,
      max_warte: maxWarte,
      summe_warte: fahrten.reduce((s, f) => s + warte(f), 0),
      engpaesse: e.engpaesse.length,
    };
  }

  function filtern(e) {
    const von = sekunden(vonFeld.value || "00:00");
    const bis = sekunden(bisFeld.value || "23:59") + 59;
    return e.fahrten.filter(
      (f) => f.geplant >= von && f.geplant <= bis && (!startWahl.value || String(f.start_id) === startWahl.value) && (!taWahl.value || String(f.transportart_id) === taWahl.value)
    );
  }

  function zeigen() {
    if (!sim || ansicht !== "tag") return;
    const fahrten = filtern(sim);
    const k = kennzahlen(sim, fahrten);
    const gefiltert = fahrten.length !== sim.fahrten.length;
    const kachel = (wert, text, art = "", vorher = null) =>
      h(`div.kennzahl${art ? "." + art : ""}`, h("strong", wert), h("span", text), vorher !== null ? h("small.vergleich", `${t("auswertung.ist")}: ${vorher}`) : null);
    const kIst = ist ? kennzahlen(ist, filtern(ist)) : null;
    const engpaesse = sim.engpaesse.map((e) => sim.ressourcen.find((r) => r.typ === e.typ && r.id === e.id));

    leeren(
      inhalt,
      szenario ? h("p.szenario-hinweis", t("auswertung.szenario_aktiv")) : null,
      sim.feiertag ? h("p.feiertag-hinweis", t("auswertung.feiertag", { name: feiertagName(sim.feiertag) })) : null,
      h(
        "div.kennzahlen",
        kachel(k.lieferungen, t("auswertung.k.lieferungen"), "", kIst?.lieferungen ?? null),
        kachel(k.fahrten, t("auswertung.k.fahrten"), "", kIst?.fahrten ?? null),
        kachel(k.verspaetet, t("auswertung.k.verspaetet"), k.verspaetet ? "schlecht" : "gut", kIst?.verspaetet ?? null),
        kachel(dauer(k.max_warte), t("auswertung.k.max_warte"), k.max_warte >= 300 ? "schlecht" : k.max_warte >= 60 ? "mittel" : "gut", kIst ? dauer(kIst.max_warte) : null),
        kachel(dauer(k.summe_warte), t("auswertung.k.summe_warte"), "", kIst ? dauer(kIst.summe_warte) : null),
        kachel(k.engpaesse, t("auswertung.k.engpaesse"), k.engpaesse ? "schlecht" : "gut", kIst?.engpaesse ?? null)
      ),
      kIst ? vergleichsSatz(k, kIst) : null,
      gefiltert ? h("p.hinweis", t("auswertung.gefiltert")) : null,
      sim.fehler.length ? h("div.fehlerbox", h("h3", t("auswertung.fehler_titel")), h("ul", sim.fehler.map((f) => h("li", h("strong", f.name), ": ", fehlerText(f))))) : null,
      h("h3", t("auswertung.engpaesse")),
      engpaesse.length ? h("div.engpaesse", engpaesse.map((r) => engpassKarte(r))) : h("p.gut", sim.fahrten.length ? t("auswertung.keine_engpaesse") : t("auswertung.keine_fahrten")),
      sim.ressourcen.length ? [h("h3", t("auswertung.auslastung")), zeitleiste(sim.ressourcen)] : null,
      h("h3", t("auswertung.fahrten", { anzahl: fahrten.length })),
      fahrten.length ? fahrtenTabelle(fahrten) : h("p.leer", t("auswertung.keine_fahrten"))
    );
  }

  function vergleichsSatz(k, kIst) {
    const diff = k.summe_warte - kIst.summe_warte;
    if (Math.abs(diff) < 1 && k.verspaetet === kIst.verspaetet) return h("p.vergleich-satz", t("auswertung.vergleich_gleich"));
    return h(
      "p.vergleich-satz",
      { class: diff < 0 ? "gut" : "warnung" },
      diff < 0 ? t("auswertung.vergleich_besser", { zeit: dauer(-diff) }) : t("auswertung.vergleich_schlechter", { zeit: dauer(diff) }),
      k.verspaetet !== kIst.verspaetet ? ` ${t("auswertung.vergleich_verspaetet", { vorher: kIst.verspaetet, nachher: k.verspaetet })}` : ""
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
    return `#/karte/${sid}/ablauf/${datum}/${uhr(zeit)}${szenario ? `/${szenario}` : ""}`;
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
    const vorher = ist?.ressourcen.find((x) => x.typ === r.typ && x.id === r.id);
    if (vorher) zeilen.push(t("engpass.ist_vergleich", { max: dauer(vorher.max_wartezeit) }));
    return h(
      "div.engpass",
      h("div.engpass-kopf", h("strong", ressourceName(r)), link ? h("a.knopf-flach", { href: link }, t("auswertung.auf_karte")) : null),
      h("ul", zeilen.map((z) => h("li", z))),
      h("p.tipp", t(`engpass.tipp.${r.typ}`))
    );
  }

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
              return h(link ? "a" : "span", { href: link || undefined, title: `${uhr(s)}–${uhr(s + 300)}: ${zahl(v * 100, 0)} %`, style: { background: v ? farbe(v) : "transparent" } });
            })
          ),
        ];
      }),
      h("div.zl-legende", h("span", t("auswertung.legende")), [0.25, 0.5, 0.75, 1].map((v) => h("span.zl-feld", { style: { background: farbe(v) } }, `${v * 100} %`)))
    );
  }

  function farbe(v) {
    const x = Math.min(1, v);
    return `hsl(${120 - 120 * x}, 70%, ${55 - 10 * x}%)`;
  }

  function fahrtenTabelle(fahrten) {
    const ta = (id) => stamm.transportarten.find((x) => x.id === id);
    return h(
      "div.tabellenrahmen",
      h(
        "table.tabelle.kompakt",
        h("thead", h("tr", ["geplant", "lieferung", "von_nach", "los", "ankunft", "warten", "zurueck"].map((k) => h("th", t(`auswertung.spalte.${k}`))))),
        h(
          "tbody",
          fahrten
            .slice()
            .sort((a, b) => a.geplant - b.geplant || a.id - b.id)
            .map((f) => {
              const w = warte(f);
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
                h("td.zeit", uhr(f.ende), sid ? h("a.knopf-flach.kein-druck", { href: `#/karte/${sid}/ablauf/${datum}/${uhr(f.geplant)}${szenario ? `/${szenario}` : ""}` }, "→") : null)
              );
            })
        )
      )
    );
  }

  // ---------------------------------------------------------------- Woche
  async function wocheZeigen() {
    // Woche ab Montag der gewählten Woche
    const d = new Date(datum + "T00:00:00");
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const montag = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    let w, wIst;
    try {
      [w, wIst] = await Promise.all([
        api(`simulation/woche?von=${montag}${szenario ? `&szenario=${szenario}` : ""}`),
        szenario ? api(`simulation/woche?von=${montag}`) : Promise.resolve(null),
      ]);
    } catch (e) {
      return fehlerMelden(e);
    }
    const stunden = new Set();
    w.tage.forEach((tag) => Object.keys(tag.stunden).forEach((s) => stunden.add(Number(s))));
    const liste = stunden.size ? [...stunden].sort((a, b) => a - b) : [];
    const von = liste.length ? liste[0] : 6;
    const bis = liste.length ? liste.at(-1) : 18;
    const spalten = [];
    for (let s = von; s <= bis; s++) spalten.push(s);
    const zelle = (tag, s) => {
      const x = tag.stunden[String(s)];
      if (!x) return h("td.leer-zelle");
      const v = Math.min(1, x.max_warte / 600); // 10 min Wartezeit = rot
      return h(
        "td.wzelle",
        { style: { background: x.max_warte > 0 ? farbe(v) : "#e6f4ea" }, title: t("auswertung.woche_zelle", { fahrten: x.fahrten, warte: dauer(x.max_warte), verspaetet: x.verspaetet }) },
        h("a", { href: `#/auswertung/${tag.datum}${szenario ? `/${szenario}` : ""}`, onclick: () => merkerSetzen("tag") }, x.fahrten)
      );
    };
    leeren(
      inhalt,
      szenario ? h("p.szenario-hinweis", t("auswertung.szenario_aktiv")) : null,
      h("p.hinweis", t("auswertung.woche_hilfe")),
      h(
        "div.tabellenrahmen",
        h(
          "table.wochentabelle",
          h("thead", h("tr", h("th"), spalten.map((s) => h("th", `${String(s).padStart(2, "0")}`)), h("th", t("auswertung.k.max_warte")), szenario ? h("th", t("auswertung.ist")) : null)),
          h(
            "tbody",
            w.tage.map((tag, i) => {
              const dd = new Date(tag.datum + "T00:00:00");
              return h(
                "tr",
                { class: tag.feiertag ? "feiertag" : "" },
                h("th", `${t("wochentag")[dd.getDay()]} ${dd.getDate()}.${dd.getMonth() + 1}.`, tag.feiertag ? h("small", feiertagName(tag.feiertag)) : null),
                spalten.map((s) => zelle(tag, s)),
                h("td.zahl", dauer(tag.zusammenfassung.max_wartezeit), tag.fehler ? h("small.warnung", t("ablauf.fehler", { anzahl: tag.fehler })) : null),
                wIst ? h("td.zahl.gedimmt", dauer(wIst.tage[i].zusammenfassung.max_wartezeit)) : null
              );
            })
          )
        )
      ),
      h("div.zl-legende.woche", h("span", t("auswertung.woche_legende")), [0, 0.25, 0.5, 1].map((v) => h("span.zl-feld", { style: { background: v ? farbe(v) : "#e6f4ea", color: v ? "#fff" : "#2b8a3e" } }, dauer(v * 600))))
    );
  }

  ansichtKnoepfe();
  laden();
}
