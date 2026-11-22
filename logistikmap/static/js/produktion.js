// Produktion: Punkte, an denen im Takt Wagen fertig werden, die abgeholt werden müssen (Küche, AEMP, Wäscherei …)
// Hash: #/lieferungen/produktion[/<id> | /neu/<punkt>]

import { api, bestaetigen, darf, fehlerMelden, h, heute, leeren, melden, punktAuswahl, punktName, sekunden, stammdaten, t, uhr, zahl } from "./basis.js";
import { simulationVergessen } from "./ablauf.js";
import { ansichtUmschalter, regelEditor, regelText } from "./lieferungen.js";

export const PRODUKTION_ORTE = ["start", "ziel", "punkt", "produktion"];

/** Wie viele Takte zwischen von und bis liegen (der erste genau um „von“). */
function takte(von, bis, takt) {
  if (!von || !bis || !(takt > 0)) return 0;
  let spanne = sekunden(bis) - sekunden(von);
  if (spanne < 0) spanne += 86400;
  return Math.floor(spanne / (takt * 60) + 1e-9) + 1;
}

/** Wagen je Ziel: die Verteilung der Reihe nach, danach wieder von vorn. */
function jeZiel(verteilung, gesamt) {
  const runde = verteilung.flatMap((v) => Array(v.anzahl).fill(v.ziel_id));
  const summe = new Map();
  if (!runde.length) return summe;
  for (let i = 0; i < gesamt; i++) summe.set(runde[i % runde.length], (summe.get(runde[i % runde.length]) || 0) + 1);
  return summe;
}

export function abholungText(a) {
  if (a.art === "menge") return t("produktion.abholung_kurz.menge", { anzahl: a.menge });
  if (a.art === "zeiten") return t("produktion.abholung_kurz.zeiten", { zeiten: (a.zeiten || []).join(", ") });
  return t("produktion.abholung_kurz.sofort");
}

export function zeigeProduktion(wurzel, rest = []) {
  const bearbeiten = darf("lieferungen");
  const box = h("div");
  const neuKnopf = h("button.knopf", { type: "button", disabled: true, onclick: () => dialog() }, "+ " + t("produktion.neu")); // frei, sobald alles geladen ist
  let sprung = rest;
  let liste = [];
  let punkte = [];
  let stamm = null;

  wurzel.append(
    h(
      "section.karte-box",
      h(
        "div.box-kopf",
        h("h2", t("produktion.titel")),
        h("div.knopfreihe", ansichtUmschalter("produktion"), bearbeiten ? neuKnopf : null)
      ),
      h("p.hinweis", t("produktion.hilfe"), " ", h("a", { href: "#/hilfe/produktion" }, t("produktion.mehr"))),
      box
    )
  );

  const punkt = (id) => punkte.find((p) => p.id === id);
  const wagentyp = (id) => stamm.wagentypen.find((w) => w.id === id);

  async function laden() {
    try {
      [liste, punkte, stamm] = await Promise.all([api("produktionen"), api("punkte"), stammdaten(true)]);
    } catch (e) {
      return fehlerMelden(e);
    }
    neuKnopf.disabled = false;
    zeigen();
    const [was, id] = sprung;
    sprung = [];
    if (!was) return;
    history.replaceState(null, "", "#/lieferungen/produktion");
    if (!bearbeiten) return;
    if (was === "neu") dialog({ knoten_id: Number(id) || null });
    else {
      const p = liste.find((x) => x.id === Number(was));
      if (p) dialog(p);
    }
  }

  function zeigen() {
    if (!liste.length) {
      return leeren(
        box,
        h("p.leer", t("produktion.keine")),
        punkte.length ? null : h("p.hinweis", t("lieferung.erst_punkte"), " ", h("a", { href: "#/karte" }, t("nav.karte")))
      );
    }
    leeren(
      box,
      h(
        "div.tabellenrahmen",
        h(
          "table.tabelle",
          h("thead", h("tr", ["zeit", "name", "output", "abholung", "ziele", "wann", ""].map((k) => h("th", k ? t(`produktion.spalte.${k}`) : "")))),
          h(
            "tbody",
            liste.map((p) => {
              const ta = stamm.transportarten.find((x) => x.id === p.transportart_id);
              const summe = jeZiel(p.verteilung, p.gesamt);
              return h(
                "tr",
                { class: p.aktiv ? "" : "inaktiv" },
                h("td.zeit", `${p.von} – ${p.bis}`, p.streuung ? h("small", `± ${p.streuung} min`) : null, p.spaetestens ? h("small", `${t("lieferung.bis")} ${p.spaetestens}`) : null),
                h("td", h("strong", p.name), h("small", punktName(punkt(p.knoten_id)))),
                h(
                  "td",
                  t("produktion.wagen", { anzahl: p.gesamt }),
                  h("small", t("produktion.takt_text", { takt: zahl(p.takt, 2), menge: p.menge, wagentyp: wagentyp(p.wagentyp_id)?.name ?? "?" })),
                  h("small", p.stellplaetze ? t("produktion.stellplaetze_text", { anzahl: p.stellplaetze }) : t("produktion.stellplaetze_unbegrenzt"))
                ),
                h("td", h("div", abholungText(p.abholung)), ta ? h("span.chip", { style: { borderColor: ta.farbe, color: ta.farbe } }, ta.name) : "?"),
                h("td", [...summe].map(([ziel, n]) => h("small", `${n}× ${punktName(punkt(ziel))}`))),
                h("td", regelText(p.regel), p.aktiv ? null : h("span.marke-klein.grau", t("lieferung.inaktiv"))),
                h(
                  "td.aktionen",
                  h("a.knopf-flach", { href: `#/karte/${punkt(p.knoten_id)?.stockwerk_id}/ablauf/${heute()}/${p.von}` }, t("produktion.ablauf")),
                  bearbeiten
                    ? [
                        h("button.knopf-flach", { type: "button", onclick: () => dialog(p) }, t("allgemein.bearbeiten")),
                        h("button.knopf-flach", { type: "button", onclick: () => dialog({ ...p, id: null, name: `${p.name} (${t("lieferung.kopie")})` }) }, t("lieferung.kopieren")),
                        h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(p) }, t("allgemein.loeschen")),
                      ]
                    : null
                )
              );
            })
          )
        )
      )
    );
  }

  async function loeschen(p) {
    if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name: p.name })))) return;
    try {
      await api(`produktionen/${p.id}`, { methode: "DELETE" });
      simulationVergessen();
      laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  // ---------------------------------------------------------------- Dialog
  function dialog(p) {
    if (!punkte.length) return melden(t("lieferung.erst_punkte"), "fehler");
    if (!stamm.wagentypen.length) return melden(t("produktion.erst_wagentyp"), "fehler");
    const neu = !p?.id;
    const v = {
      name: "", knoten_id: null, richtung: "versorgung", transportart_id: null, wagentyp_id: stamm.wagentypen[0].id, von: "06:30", bis: "08:00", takt: 8, menge: 1,
      stellplaetze: null, verteilung: [], spaetestens: "", streuung: 0, regel: { wochentage: [1, 2, 3, 4, 5], feiertage: "ausser" },
      aktiv: true, notiz: "", ...(p || {}),
    };
    v.abholung = { art: "sofort", menge: 4, zeiten: [], ...(v.abholung || {}) };
    v.rueckweg = { modus: "leer", uhrzeit: "", ziel_id: null, ...(v.rueckweg || {}) };
    const orte = (x) => PRODUKTION_ORTE.includes(x.art);
    const ziele = (x) => [...PRODUKTION_ORTE, "tor"].includes(x.art);
    const el = {
      name: h("input", { value: v.name, maxlength: 150, placeholder: t("produktion.name_auto") }),
      ort: punktAuswahl(punkte, v.knoten_id, { filter: orte, leer: t("lieferung.waehlen") }),
      richtung: h("select", ["versorgung", "entsorgung", "intern"].map((r) => h("option", { value: r, selected: r === v.richtung }, t(`richtung.${r}`)))),
      transportart: h("select", h("option", { value: "" }, t("lieferung.transportart_auto")), stamm.transportarten.map((x) => h("option", { value: x.id, selected: x.id === v.transportart_id }, x.name))),
      wagentyp: h("select", stamm.wagentypen.map((w) => h("option", { value: w.id, selected: w.id === v.wagentyp_id }, w.name))),
      von: h("input", { type: "time", value: v.von, required: true }),
      bis: h("input", { type: "time", value: v.bis, required: true }),
      takt: h("input", { type: "number", min: 0.1, max: 1440, step: "any", value: v.takt, required: true }),
      menge: h("input", { type: "number", min: 1, max: 1000, value: v.menge, required: true }),
      stellplaetze: h("input", { type: "number", min: 0, max: 1000, value: v.stellplaetze ?? "", placeholder: "∞" }),
      abholart: h("select", ["sofort", "menge", "zeiten"].map((a) => h("option", { value: a, selected: a === v.abholung.art }, t(`produktion.abholung.${a}`)))),
      abholmenge: h("input", { type: "number", min: 1, max: 1000, value: v.abholung.menge }),
      abholzeiten: h("input", { value: (v.abholung.zeiten || []).join(", "), placeholder: "07:00, 07:30, 08:15" }),
      spaetestens: h("input", { type: "time", value: v.spaetestens || "" }),
      streuung: h("input", { type: "number", min: 0, max: 240, step: 5, value: v.streuung || 0 }),
      rueckModus: h("select", ["leer", "beladen", "spaeter", "keiner"].map((m) => h("option", { value: m, selected: m === v.rueckweg.modus }, t(`rueckweg.${m}`)))),
      rueckUhrzeit: h("input", { type: "time", value: v.rueckweg.uhrzeit || "" }),
      rueckZiel: punktAuswahl(punkte, v.rueckweg.ziel_id, { filter: ziele, leer: t("produktion.zum_ort") }),
      aktiv: h("input", { type: "checkbox", checked: v.aktiv }),
      notiz: h("textarea", { rows: 2, maxlength: 2000 }, v.notiz),
    };
    const regel = regelEditor(v.regel);

    // Verteilung: Zeilen Anzahl + Ziel
    const zielBox = h("div.ladung");
    const zielZeile = (z = { ziel_id: null, anzahl: 1 }) => {
      const zeile = h(
        "div.zeile",
        h("input", { type: "number", min: 1, max: 1000, value: z.anzahl, class: "anzahl", "aria-label": t("produktion.anzahl") }),
        punktAuswahl(punkte, z.ziel_id, { filter: ziele, leer: t("lieferung.waehlen") }),
        h("button.knopf-flach.gefahr", { type: "button", onclick: () => (zeile.remove(), vorschau()), "aria-label": t("allgemein.loeschen") }, "×")
      );
      zielBox.append(zeile);
    };
    (v.verteilung.length ? v.verteilung : [undefined]).forEach((z) => zielZeile(z));
    const verteilungLesen = () =>
      [...zielBox.querySelectorAll(".zeile")]
        .map((z) => ({ ziel_id: Number(z.querySelector("select").value), anzahl: Math.max(1, Number(z.querySelector("input").value) || 1) }))
        .filter((z) => z.ziel_id);

    const ergebnis = h("div.produktion-vorschau");
    function vorschau() {
      const anzahl = takte(el.von.value, el.bis.value, Number(el.takt.value));
      const menge = Number(el.menge.value) || 1;
      const gesamt = anzahl * menge;
      const verteilung = verteilungLesen();
      const soll = verteilung.reduce((s, z) => s + z.anzahl, 0);
      const summe = jeZiel(verteilung, Math.min(gesamt, 5000));
      const letzter = anzahl ? sekunden(el.von.value) + (anzahl - 1) * Number(el.takt.value) * 60 : null;
      leeren(
        ergebnis,
        gesamt ? h("strong", t("produktion.vorschau", { anzahl: gesamt, von: el.von.value, bis: uhr(letzter) })) : null,
        summe.size ? h("span", [...summe].map(([z, n]) => `${punktName(punkt(z))}: ${n}`).join(" · ")) : null,
        soll && soll !== gesamt
          ? h(
              "span",
              t(soll < gesamt ? "produktion.verteilung_wiederholt" : "produktion.verteilung_unvollstaendig", { soll, anzahl: gesamt }),
              " ",
              h("button.knopf-flach", { type: "button", onclick: () => taktAnpassen(soll, menge) }, t("produktion.takt_anpassen", { anzahl: soll }))
            )
          : null
      );
    }
    /** Takt so setzen, dass von–bis genau die Summe der Verteilung fertig wird. */
    function taktAnpassen(soll, menge) {
      const anzahl = Math.ceil(soll / menge);
      let spanne = sekunden(el.bis.value) - sekunden(el.von.value);
      if (spanne < 0) spanne += 86400;
      if (anzahl <= 1) el.bis.value = el.von.value;
      else el.takt.value = Math.max(0.1, Math.floor((spanne / 60 / (anzahl - 1)) * 1000) / 1000);
      if (soll % menge) melden(t("produktion.menge_passt_nicht", { menge, soll }), "fehler");
      vorschau();
    }

    const f = (label, eingabe, hilfe) => h("label.feld", h("span", label), eingabe, hilfe ? h("small", hilfe) : null);
    const mengeFeld = f(t("produktion.abholmenge"), el.abholmenge, t("produktion.abholmenge_hilfe"));
    const zeitenFeld = f(t("produktion.abholzeiten"), el.abholzeiten, t("produktion.abholzeiten_hilfe"));
    const rueckUhrzeitFeld = f(t("produktion.rueck_uhrzeit"), el.rueckUhrzeit);
    const rueckZielFeld = f(t("rueckweg.ziel"), el.rueckZiel);
    const sichtbar = () => {
      mengeFeld.hidden = el.abholart.value !== "menge";
      zeitenFeld.hidden = el.abholart.value !== "zeiten";
      rueckUhrzeitFeld.hidden = el.rueckModus.value !== "spaeter";
      rueckZielFeld.hidden = el.rueckModus.value === "keiner";
    };

    const fehlerZeile = h("p.dialog-fehler", { hidden: true });
    const dlg = h("dialog.dialog.gross");
    const form = h(
      "form.lieferungsformular",
      h("h2", neu ? t("produktion.neu") : `${t("produktion.bearbeiten")}: ${v.name}`),
      h(
        "div.raster",
        f(t("produktion.ort"), el.ort, t("produktion.ort_hilfe")),
        f(t("lieferung.name"), el.name),
        f(t("produktion.wagentyp"), el.wagentyp),
        f(t("lieferung.richtung"), el.richtung)
      ),
      h("h3.dialog-abschnitt", t("produktion.output")),
      h(
        "div.raster",
        f(t("produktion.von"), el.von),
        f(t("produktion.bis"), el.bis, t("produktion.bis_hilfe")),
        f(t("produktion.takt"), el.takt),
        f(t("produktion.menge"), el.menge),
        f(t("produktion.stellplaetze"), el.stellplaetze, t("produktion.stellplaetze_hilfe")),
        f(t("produktion.streuung"), el.streuung, t("produktion.streuung_hilfe"))
      ),
      h("h3.dialog-abschnitt", t("produktion.verteilung")),
      h("p.hinweis", t("produktion.verteilung_hilfe")),
      zielBox,
      h("button.knopf-flach", { type: "button", onclick: () => (zielZeile(), vorschau()) }, "+ " + t("produktion.ziel_hinzu")),
      ergebnis,
      h("h3.dialog-abschnitt", t("produktion.abholung_titel")),
      h(
        "div.raster",
        f(t("produktion.abholart"), el.abholart),
        mengeFeld,
        zeitenFeld,
        f(t("lieferung.transportart"), el.transportart),
        f(t("lieferung.spaetestens"), el.spaetestens, t("lieferung.spaetestens_hilfe"))
      ),
      h("h3.dialog-abschnitt", t("lieferung.rueckweg")),
      h("div.raster", f(t("rueckweg.label"), el.rueckModus), rueckUhrzeitFeld, rueckZielFeld),
      h("h3.dialog-abschnitt", t("lieferung.wann")),
      regel.element,
      h("h3.dialog-abschnitt", t("lieferung.sonstiges")),
      h("label.feld.haken", el.aktiv, h("span", t("lieferung.aktiv"))),
      f(t("lieferung.notiz"), el.notiz),
      fehlerZeile,
      h(
        "div.dialog-knoepfe",
        h("button.knopf-flach", { type: "button", onclick: () => dlg.close() }, t("allgemein.abbrechen")),
        h("button.knopf", { type: "submit" }, t("allgemein.speichern"))
      )
    );
    form.addEventListener("input", () => {
      fehlerZeile.hidden = true;
      vorschau();
    });
    form.addEventListener("change", sichtbar); // Vorschau nur bei „input“: sonst verschwände der Knopf beim Verlassen des Felds unter dem Klick
    sichtbar();
    vorschau();

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const daten = {
        name: el.name.value,
        knoten_id: Number(el.ort.value) || 0,
        richtung: el.richtung.value,
        transportart_id: el.transportart.value ? Number(el.transportart.value) : null,
        wagentyp_id: Number(el.wagentyp.value),
        von: el.von.value,
        bis: el.bis.value,
        takt: Number(el.takt.value),
        menge: Number(el.menge.value),
        stellplaetze: Number(el.stellplaetze.value) || null,
        abholung: { art: el.abholart.value, menge: Math.max(1, Number(el.abholmenge.value) || 1), zeiten: el.abholart.value === "zeiten" ? zeitenLesen(el.abholzeiten.value) : [] },
        verteilung: verteilungLesen(),
        spaetestens: el.spaetestens.value || null,
        streuung: Math.max(0, Math.min(240, Number(el.streuung.value) || 0)),
        regel: regel.lesen(),
        rueckweg: { modus: el.rueckModus.value, uhrzeit: el.rueckUhrzeit.value || null, ziel_id: Number(el.rueckZiel.value) || null },
        aktiv: el.aktiv.checked,
        notiz: el.notiz.value,
      };
      try {
        if (!daten.knoten_id) throw new Error(t("produktion.ort_fehlt"));
        await api(neu ? "produktionen" : `produktionen/${p.id}`, { methode: neu ? "POST" : "PUT", daten });
        dlg.close();
        simulationVergessen();
        melden(t("allgemein.gespeichert"));
        laden();
      } catch (err) {
        fehlerZeile.textContent = err.message;
        fehlerZeile.hidden = false;
        fehlerZeile.scrollIntoView({ block: "nearest" });
      }
    });
    dlg.append(form);
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
    (v.knoten_id ? el.von : el.ort).focus();
  }

  laden();
}

/** „7:00, 7.30 8:15“ → ["07:00", "07:30", "08:15"]; Unlesbares bleibt stehen und wird vom Server gemeldet. */
function zeitenLesen(text) {
  return text
    .split(/[,;\s]+/)
    .filter(Boolean)
    .map((x) => {
      const m = /^(\d{1,2})[:.](\d{2})$/.exec(x);
      return m ? `${m[1].padStart(2, "0")}:${m[2]}` : x;
    });
}

/** Auswertung: Tabelle und Verlauf der wartenden Wagen je Produktion. */
export function produktionAuswertung(sim, ist, punkte, kartenLink) {
  return h(
    "div.produktionen",
    sim.produktionen.map((p) => {
      const vorher = ist?.produktionen.find((x) => x.id === p.id);
      const ort = punkte.find((x) => x.id === p.knoten_id);
      const steht = p.stillstand >= 1;
      const ersterStillstand = p.stillstaende.find(([a, b]) => b === null || b - a >= 1);
      const link = kartenLink(p, ersterStillstand?.[0] ?? p.erster ?? 0);
      const dauerText = (s) => (s < 60 ? `${Math.round(s)} s` : `${zahl(s / 60, s < 600 ? 1 : 0)} min`);
      const offen = p.gesamt - p.fertig;
      const liegen = p.fertig - p.abgeholt;
      return h(
        `div.produktion-karte${steht || offen || liegen ? ".steht" : ""}`,
        h("div.engpass-kopf", h("div", h("strong", p.name), ort ? h("div.gedimmt", punktName(ort)) : null), link ? h("a.knopf-flach", { href: link }, t("auswertung.auf_karte")) : null),
        h(
          "p.produktion-satz",
          { class: steht ? "warnung" : "gut" },
          p.stillstaende.at(-1)?.[1] === null
            ? t("produktion.steht_ab", { zeit: uhr(p.stillstaende.at(-1)[0]) })
            : steht
            ? t("produktion.steht", { zeit: uhr(ersterStillstand[0]), dauer: dauerText(p.stillstand), anzahl: p.stillstaende.length })
            : t("produktion.laeuft_durch")
        ),
        h(
          "ul",
          h("li", t("produktion.zeile_wagen", { fertig: p.fertig, gesamt: p.gesamt, abgeholt: p.abgeholt })),
          h("li", p.letzter === null ? t("produktion.zeile_ende_offen", { plan: uhr(p.letzter_plan) }) : t("produktion.zeile_ende", { plan: uhr(p.letzter_plan), ist: uhr(p.letzter) })),
          h("li", p.stellplaetze ? t("produktion.zeile_plaetze", { anzahl: p.max_wartend, plaetze: p.stellplaetze }) : t("produktion.zeile_plaetze_frei", { anzahl: p.max_wartend })),
          h("li", t("produktion.zeile_standzeit", { max: dauerText(p.max_standzeit), mittel: dauerText(p.mittlere_standzeit) })),
          offen ? h("li.warnung", t("produktion.zeile_offen", { anzahl: offen })) : null,
          liegen ? h("li.warnung", t("produktion.zeile_liegen", { anzahl: liegen })) : null,
          vorher ? h("li.gedimmt", t("produktion.zeile_ist", { dauer: dauerText(vorher.stillstand) })) : null
        ),
        verlaufBild(p)
      );
    })
  );
}

const SVG = "http://www.w3.org/2000/svg";
function svg(tag, attribute, ...kinder) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, w] of Object.entries(attribute)) el.setAttribute(k, w);
  for (const kind of kinder.flat()) if (kind) el.append(kind);
  return el;
}

/** Treppenlinie: wie viele fertige Wagen stehen wann. Rot hinterlegt: Produktion steht. */
function verlaufBild(p) {
  if (!p.verlauf.length) return null;
  const B = 560, H = 130, L = 30, R = 8, O = 12, U = 26;
  const start = p.verlauf[0][0];
  const letzte = p.verlauf.at(-1)[0];
  const ende = Math.max(letzte, start + 600);
  const hoch = Math.max(p.max_wartend, p.stellplaetze || 0, 1);
  const x = (zeit) => L + ((Math.min(Math.max(zeit, start), ende) - start) / (ende - start)) * (B - L - R);
  const y = (n) => O + (1 - n / hoch) * (H - O - U);
  let pfad = `M${x(start)},${y(0)}`;
  for (const [zeit, n] of p.verlauf) pfad += `H${x(zeit).toFixed(1)}V${y(n).toFixed(1)}`;
  const flaeche = `${pfad}V${y(0)}H${x(start)}Z`;
  const schritt = [300, 600, 900, 1800, 3600, 7200, 14400].find((s) => (ende - start) / s <= 8) || 28800;
  const marken = [];
  for (let zeit = Math.ceil(start / schritt) * schritt; zeit <= ende; zeit += schritt) marken.push(zeit);
  return svg(
    "svg",
    { viewBox: `0 0 ${B} ${H}`, class: "produktion-verlauf", role: "img", "aria-label": t("produktion.verlauf") },
    p.stillstaende.map(([a, b]) => svg("rect", { x: x(a), y: O, width: Math.max(1.5, x(b ?? ende) - x(a)), height: H - O - U, class: "steht" })),
    marken.map((zeit) => svg("line", { x1: x(zeit), x2: x(zeit), y1: O, y2: H - U, class: "gitter" })),
    svg("path", { d: flaeche, class: "flaeche" }),
    svg("path", { d: pfad, class: "linie" }),
    p.stellplaetze ? svg("line", { x1: L, x2: B - R, y1: y(p.stellplaetze), y2: y(p.stellplaetze), class: "grenze" }) : null,
    svg("line", { x1: L, x2: B - R, y1: y(0), y2: y(0), class: "achse" }),
    [0, hoch].map((n) => svg("text", { x: L - 5, y: y(n) + 4, "text-anchor": "end" }, n)),
    marken.filter((zeit) => x(zeit) < B - 14).map((zeit) => svg("text", { x: x(zeit), y: H - 6, "text-anchor": "middle" }, uhr(zeit)))
  );
}
