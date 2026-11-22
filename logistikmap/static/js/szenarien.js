// Szenarien: „Was wäre wenn …“ – Abweichungen vom Ist-Zustand, ohne die echten Daten zu ändern.
// Gespeichert werden nur die Unterschiede (Lieferungen, Transportarten, Aufzüge).

import { api, bestaetigen, darf, fehlerMelden, formularDialog, h, heute, leeren, melden, stammdaten, t } from "./basis.js";
import { simulationVergessen } from "./ablauf.js";

export function zeigeSzenarien(wurzel, [idParam]) {
  const darfAendern = darf("lieferungen");
  const id = Number(idParam) || null;
  if (id) return editor(wurzel, id, darfAendern);

  const box = h("div");
  wurzel.append(
    h(
      "section.karte-box",
      h("div.box-kopf", h("h2", t("szenario.titel")), darfAendern ? h("button.knopf", { type: "button", onclick: neu }, "+ " + t("szenario.neu")) : null),
      h("p.hinweis", t("szenario.hilfe")),
      box
    )
  );

  async function laden() {
    let liste;
    try {
      liste = await api("szenarien");
    } catch (e) {
      return fehlerMelden(e);
    }
    if (!liste.length) return leeren(box, h("p.leer", t("szenario.keine")));
    leeren(
      box,
      h(
        "div.szenarioliste",
        liste.map((s) => {
          const a = s.aenderungen;
          const anzahl = ["lieferungen", "produktionen", "transportarten", "aufzuege", "kanten", "knoten"].reduce((n, k) => n + Object.keys(a[k] || {}).length, 0);
          return h(
            "div.szenario",
            h("div", h("strong", s.name), s.beschreibung ? h("p.gedimmt", s.beschreibung) : null, h("small", t("szenario.aenderungen", { anzahl }))),
            h(
              "div.knopfreihe",
              h("a.knopf", { href: `#/auswertung/${heute()}/${s.id}` }, t("szenario.vergleichen")),
              h("a.knopf-flach", { href: `#/szenarien/${s.id}` }, darfAendern ? t("allgemein.bearbeiten") : t("szenario.ansehen")),
              darfAendern ? h("button.knopf-flach", { type: "button", onclick: () => uebernehmen(s) }, t("szenario.uebernehmen")) : null,
              darfAendern ? h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(s) }, t("allgemein.loeschen")) : null
            )
          );
        })
      )
    );
  }

  async function neu() {
    const r = await formularDialog({
      titel: t("szenario.neu"),
      felder: [
        { name: "name", label: t("szenario.name"), pflicht: true, attr: { placeholder: t("szenario.name_beispiel") } },
        { name: "beschreibung", label: t("szenario.beschreibung"), typ: "textfeld" },
      ],
      speichern: (w) => api("szenarien", { methode: "POST", daten: { ...w, aenderungen: {} } }),
    });
    if (r?.id) location.hash = `#/szenarien/${r.id}`;
  }

  async function uebernehmen(s) {
    if (!(await bestaetigen(t("szenario.uebernehmen_frage", { name: s.name }), t("szenario.uebernehmen")))) return;
    try {
      const r = await api(`szenarien/${s.id}/uebernehmen`, { methode: "POST" });
      simulationVergessen();
      melden(t("szenario.uebernommen", { anzahl: r.lieferungen }));
    } catch (e) {
      fehlerMelden(e);
    }
  }

  async function loeschen(s) {
    if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name: s.name })))) return;
    try {
      await api(`szenarien/${s.id}`, { methode: "DELETE" });
      laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  laden();
}

async function editor(wurzel, id, darfAendern) {
  let szenario, lieferungen, stamm, punkte, engstellen, produktionen;
  try {
    [szenario, lieferungen, stamm, punkte, engstellen, produktionen] = await Promise.all([
      api("szenarien").then((l) => l.find((s) => s.id === id)),
      api("lieferungen"),
      stammdaten(true),
      api("punkte"),
      api("engstellen"),
      api("produktionen"),
    ]);
  } catch (e) {
    return fehlerMelden(e);
  }
  if (!szenario) {
    location.hash = "#/szenarien";
    return;
  }
  const a = szenario.aenderungen;
  // Lade- und Entladepunkte: Start-/Zielpunkte und alles mit Kapazität
  const rampen = punkte.filter((p) => ["start", "ziel", "punkt", "produktion", "tor"].includes(p.art) || p.kapazitaet);
  const name = h("input", { value: szenario.name, maxlength: 150, disabled: !darfAendern });
  const beschreibung = h("textarea", { rows: 2, disabled: !darfAendern }, szenario.beschreibung);
  const eingaben = []; // {art, id, feld, el, ist}

  const feld = (art, obj, feldname, el, ist) => {
    const wert = a[art]?.[obj.id]?.[feldname];
    if (wert !== undefined) {
      if (el.type === "checkbox") el.checked = !!wert;
      else el.value = wert;
    }
    el.disabled = !darfAendern;
    const markieren = () => el.closest("td")?.classList.toggle("geaendert", lesen(el) !== ist && String(lesen(el)) !== String(ist));
    el.addEventListener("input", markieren);
    el.addEventListener("change", markieren);
    eingaben.push({ art, id: obj.id, feld: feldname, el, ist });
    setTimeout(markieren);
    return el;
  };
  const lesen = (el) => (el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.tagName === "SELECT" && /^\d+$/.test(el.value) ? Number(el.value) : el.value || null);

  const taOptionen = (wert) => stamm.transportarten.map((x) => h("option", { value: x.id, selected: x.id === wert }, x.name));

  wurzel.append(
    h(
      "div.stapel",
      h(
        "section.karte-box",
        h(
          "div.box-kopf",
          h("h2", `${t("szenario.kurz")}: ${szenario.name}`),
          h(
            "div.knopfreihe",
            h("a.knopf-flach", { href: "#/szenarien" }, t("szenario.zur_liste")),
            h("a.knopf-flach", { href: `#/auswertung/${heute()}/${id}` }, t("szenario.vergleichen")),
            darfAendern ? h("button.knopf", { type: "button", onclick: speichern }, t("allgemein.speichern")) : null
          )
        ),
        h("div.raster2", h("label.feld", h("span", t("szenario.name")), name), h("label.feld", h("span", t("szenario.beschreibung")), beschreibung)),
        h("p.hinweis", t("szenario.editor_hilfe"))
      ),
      h(
        "section.karte-box",
        h("h2", t("szenario.lieferungen")),
        h(
          "div.tabellenrahmen",
          h(
            "table.tabelle.kompakt.szenariotabelle",
            h("thead", h("tr", h("th", t("lieferung.aktiv_kurz")), h("th", t("lieferung.spalte.name")), h("th", t("lieferung.uhrzeit")), h("th", t("lieferung.spaetestens")), h("th", t("lieferung.transportart")))),
            h(
              "tbody",
              lieferungen.map((l) =>
                h(
                  "tr",
                  h("td", feld("lieferungen", l, "aktiv", h("input", { type: "checkbox", checked: l.aktiv }), l.aktiv)),
                  h("td", l.name, l.lieferant ? h("small", l.lieferant) : null),
                  h("td", feld("lieferungen", l, "uhrzeit", h("input", { type: "time", value: l.uhrzeit }), l.uhrzeit)),
                  h("td", feld("lieferungen", l, "spaetestens", h("input", { type: "time", value: l.spaetestens || "" }), l.spaetestens || null)),
                  h("td", feld("lieferungen", l, "transportart_id", h("select", taOptionen(l.transportart_id)), l.transportart_id))
                )
              )
            )
          )
        )
      ),
      produktionen.length
        ? h(
            "section.karte-box",
            h("h2", t("szenario.produktion")),
            h(
              "div.tabellenrahmen",
              h(
                "table.tabelle.kompakt.szenariotabelle",
                h("thead", h("tr", h("th", t("lieferung.aktiv_kurz")), h("th", t("produktion.spalte.name")), h("th", t("produktion.von_kurz")), h("th", t("produktion.bis_kurz")), h("th", t("produktion.takt")), h("th", t("produktion.menge")), h("th", t("produktion.stellplaetze")), h("th", t("lieferung.transportart")))),
                h(
                  "tbody",
                  produktionen.map((p) =>
                    h(
                      "tr",
                      h("td", feld("produktionen", p, "aktiv", h("input", { type: "checkbox", checked: p.aktiv }), p.aktiv)),
                      h("td", p.name),
                      h("td", feld("produktionen", p, "von", h("input", { type: "time", value: p.von, required: true }), p.von)),
                      h("td", feld("produktionen", p, "bis", h("input", { type: "time", value: p.bis, required: true }), p.bis)),
                      h("td", feld("produktionen", p, "takt", h("input", { type: "number", min: 0.1, step: "any", value: p.takt, style: { width: "80px" } }), p.takt)),
                      h("td", feld("produktionen", p, "menge", h("input", { type: "number", min: 1, value: p.menge, style: { width: "70px" } }), p.menge)),
                      h("td", feld("produktionen", p, "stellplaetze", h("input", { type: "number", min: 0, value: p.stellplaetze ?? "", placeholder: "∞", style: { width: "70px" } }), p.stellplaetze ?? 0)),
                      h("td", feld("produktionen", p, "transportart_id", h("select", taOptionen(p.transportart_id)), p.transportart_id))
                    )
                  )
                )
              )
            )
          )
        : null,
      h(
        "div.spalten.gleich",
        h(
          "section.karte-box",
          h("h2", t("szenario.aufzuege")),
          h(
            "table.tabelle.kompakt.szenariotabelle",
            h("thead", h("tr", h("th", t("stamm.name")), h("th", t("szenario.ausser_betrieb")), h("th", t("stamm.plaetze")), h("th", t("szenario.fahrzeit")))),
            h(
              "tbody",
              stamm.aufzuege.map((x) =>
                h(
                  "tr",
                  h("td", x.name),
                  h("td", feld("aufzuege", x, "ausser_betrieb", h("input", { type: "checkbox" }), false)),
                  h("td", x.art === "treppe" ? "–" : feld("aufzuege", x, "plaetze", h("input", { type: "number", min: 0, step: 0.5, value: x.plaetze, style: { width: "70px" } }), x.plaetze)),
                  h("td", feld("aufzuege", x, "fahrzeit_etage", h("input", { type: "number", min: 0, value: x.fahrzeit_etage, style: { width: "70px" } }), x.fahrzeit_etage))
                )
              )
            )
          )
        ),
        h(
          "section.karte-box",
          h("h2", t("szenario.transportarten")),
          h("p.hinweis", t("szenario.transportarten_hilfe")),
          h(
            "table.tabelle.kompakt.szenariotabelle",
            h("thead", h("tr", h("th", t("stamm.name")), h("th", t("stamm.anzahl")), h("th", t("stamm.geschwindigkeit_ms")))),
            h(
              "tbody",
              stamm.transportarten.map((x) =>
                h(
                  "tr",
                  h("td", x.name, x.schichten?.length ? h("small", t("szenario.hat_schichten")) : null),
                  h("td", feld("transportarten", x, "anzahl", h("input", { type: "number", min: 0, value: x.anzahl, style: { width: "80px" } }), x.anzahl)),
                  h("td", feld("transportarten", x, "geschwindigkeit", h("input", { type: "number", min: 0.05, step: 0.05, value: x.geschwindigkeit, style: { width: "80px" } }), x.geschwindigkeit))
                )
              )
            )
          )
        )
      ),
      h(
        "div.spalten.gleich",
        h(
          "section.karte-box",
          h("h2", t("szenario.rampen")),
          h("p.hinweis", t("szenario.rampen_hilfe")),
          rampen.length
            ? h(
                "table.tabelle.kompakt.szenariotabelle",
                h("thead", h("tr", h("th", t("stamm.name")), h("th", t("knoten.kapazitaet")))),
                h(
                  "tbody",
                  rampen.map((p) =>
                    h(
                      "tr",
                      h("td", p.name, h("small", `${p.kuerzel || p.gebaeudeteil} · ${p.stockwerk}`)),
                      h("td", feld("knoten", p, "kapazitaet", h("input", { type: "number", min: 0, value: p.kapazitaet ?? "", placeholder: p.art === "tor" ? "1" : "∞", style: { width: "80px" } }), p.kapazitaet ?? 0))
                    )
                  )
                )
              )
            : h("p.leer", t("allgemein.keine_eintraege"))
        ),
        h(
          "section.karte-box",
          h("h2", t("szenario.engstellen")),
          h("p.hinweis", t("szenario.engstellen_hilfe")),
          engstellen.length
            ? h(
                "table.tabelle.kompakt.szenariotabelle",
                h("thead", h("tr", h("th", t("kante.name")), h("th", t("szenario.gesperrt")))),
                h(
                  "tbody",
                  engstellen.map((k) =>
                    h(
                      "tr",
                      h("td", k.name || `${k.von_name || "·"} – ${k.nach_name || "·"}`, h("small", `${k.kuerzel || k.gebaeudeteil} · ${k.stockwerk}${k.kapazitaet ? ` · ${t("kante.max_gleichzeitig", { anzahl: k.kapazitaet })}` : ""}`)),
                      h("td", feld("kanten", k, "gesperrt", h("input", { type: "checkbox" }), false))
                    )
                  )
                )
              )
            : h("p.leer", t("szenario.keine_engstellen"))
        )
      )
    )
  );

  async function speichern() {
    const aenderungen = {};
    for (const e of eingaben) {
      const wert = lesen(e.el);
      if (wert === e.ist || String(wert) === String(e.ist ?? "") || ((e.feld === "ausser_betrieb" || e.feld === "gesperrt") && !wert)) continue;
      aenderungen[e.art] ??= {};
      aenderungen[e.art][e.id] ??= {};
      aenderungen[e.art][e.id][e.feld] = wert;
      // feste Anzahl im Szenario ersetzt die Schichten
      if (e.art === "transportarten" && e.feld === "anzahl") aenderungen[e.art][e.id].schichten = [];
    }
    try {
      await api(`szenarien/${id}`, { methode: "PUT", daten: { name: name.value, beschreibung: beschreibung.value, aenderungen } });
      simulationVergessen();
      melden(t("allgemein.gespeichert"));
    } catch (e) {
      fehlerMelden(e);
    }
  }
}
