// Lieferungen: Liste, Regeln, Ladung, Rückweg

import { api, bestaetigen, darf, fehlerMelden, h, heute, leeren, melden, punktAuswahl, punktName, stammdaten, t } from "./basis.js";
import { simulationVergessen } from "./ablauf.js";

const TAGE = [1, 2, 3, 4, 5, 6, 7];

export function regelText(r) {
  const tage = r.wochentage || [];
  let text;
  if (r.feiertage === "nur") text = t("regel.nur_feiertage");
  else if (tage.length === 7) text = t("regel.taeglich");
  else if (tage.join() === "1,2,3,4,5") text = t("regel.mo_fr");
  else if (tage.join() === "1,2,3,4,5,6") text = t("regel.mo_sa");
  else if (tage.join() === "6,7") text = t("regel.wochenende");
  else if (!tage.length) text = t("regel.keine_tage");
  else text = tage.map((d) => t("wochentag")[d % 7]).join(", ");
  if (r.feiertage === "ausser" && tage.length) text += `, ${t("regel.ohne_feiertage")}`;
  if (r.feiertage === "auch" && tage.length) text += `, ${t("regel.auch_feiertage")}`;
  if (r.von || r.bis) text += ` (${r.von ? new Date(r.von).toLocaleDateString() : "…"} – ${r.bis ? new Date(r.bis).toLocaleDateString() : "…"})`;
  return text;
}

export function zeigeLieferungen(wurzel) {
  const bearbeiten = darf("bearbeiten");
  const suche = h("input", { type: "search", placeholder: t("lieferung.suchen") });
  const box = h("div");
  const vorschau = h("div.tagesvorschau");
  let liste = [];
  let punkte = [];
  let stamm = null;

  wurzel.append(
    h(
      "section.karte-box",
      h(
        "div.box-kopf",
        h("h2", t("lieferung.titel")),
        h("div.knopfreihe", suche, bearbeiten ? h("button.knopf", { type: "button", onclick: () => dialog() }, "+ " + t("lieferung.neu")) : null)
      ),
      vorschau,
      box
    )
  );
  suche.addEventListener("input", zeigen);

  async function laden() {
    try {
      [liste, punkte, stamm] = await Promise.all([api("lieferungen"), api("punkte"), stammdaten(true)]);
      zeigen();
      vorschauLaden();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  async function vorschauLaden() {
    try {
      const tage = await api(`kalender?von=${heute()}&tage=14`);
      leeren(
        vorschau,
        tage.map((tag) => {
          const d = new Date(tag.datum + "T00:00:00");
          return h(
            "a.tag",
            { href: `#/auswertung/${tag.datum}`, class: tag.feiertag ? "feiertag" : d.getDay() % 6 === 0 ? "wochenende" : "", title: tag.feiertag ? feiertagName(tag.feiertag) : "" },
            h("span", `${t("wochentag")[d.getDay()]} ${d.getDate()}.${d.getMonth() + 1}.`),
            h("strong", tag.lieferungen.length)
          );
        })
      );
    } catch {}
  }

  function feiertagName(k) {
    const x = t(`feiertag.${k}`);
    return x.startsWith("⟨") ? k : x;
  }

  const punkt = (id) => punkte.find((p) => p.id === id);
  const transportart = (id) => stamm.transportarten.find((x) => x.id === id);

  function ladungText(l) {
    return l.ladung.map((p) => `${p.anzahl}× ${stamm.wagentypen.find((w) => w.id === p.wagentyp_id)?.name ?? "?"}`).join(", ") || "–";
  }

  function zeigen() {
    const q = suche.value.trim().toLowerCase();
    const gefiltert = liste.filter((l) => !q || [l.name, l.lieferant, punkt(l.start_id)?.name, punkt(l.ziel_id)?.name].join(" ").toLowerCase().includes(q));
    if (!liste.length) {
      return leeren(
        box,
        h("p.leer", t("lieferung.keine")),
        punkte.length ? null : h("p.hinweis", t("lieferung.erst_punkte"), " ", h("a", { href: "#/karte" }, t("nav.karte")))
      );
    }
    leeren(
      box,
      h(
        "div.tabellenrahmen",
        h(
          "table.tabelle",
          h(
            "thead",
            h("tr", ["uhrzeit", "name", "von_nach", "ladung", "transportart", "regel", ""].map((k) => h("th", k ? t(`lieferung.spalte.${k}`) : "")))
          ),
          h(
            "tbody",
            gefiltert.map((l) => {
              const ta = transportart(l.transportart_id);
              return h(
                "tr",
                { class: l.aktiv ? "" : "inaktiv" },
                h("td.zeit", l.uhrzeit, l.spaetestens ? h("small", `${t("lieferung.bis")} ${l.spaetestens}`) : null),
                h("td", h("strong", l.name), l.lieferant ? h("small", l.lieferant) : null, h("small", { class: `richtung ${l.richtung}` }, t(`richtung.${l.richtung}`))),
                h("td", h("span", punktName(punkt(l.start_id))), h("small", "→ " + punktName(punkt(l.ziel_id))), rueckwegText(l) ? h("small", rueckwegText(l)) : null),
                h("td", ladungText(l)),
                h("td", ta ? h("span.chip", { style: { borderColor: ta.farbe, color: ta.farbe } }, ta.name) : "?"),
                h("td", regelText(l.regel), l.aktiv ? null : h("span.marke-klein.grau", t("lieferung.inaktiv"))),
                h(
                  "td.aktionen",
                  h("a.knopf-flach", { href: `#/karte/${punkt(l.start_id)?.stockwerk_id}/weg/${l.id}` }, t("lieferung.weg_zeigen")),
                  bearbeiten
                    ? [
                        h("button.knopf-flach", { type: "button", onclick: () => dialog(l) }, t("allgemein.bearbeiten")),
                        h("button.knopf-flach", { type: "button", onclick: () => dialog({ ...l, id: null, name: `${l.name} (${t("lieferung.kopie")})` }) }, t("lieferung.kopieren")),
                        h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(l) }, t("allgemein.loeschen")),
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

  function rueckwegText(l) {
    const r = l.rueckweg || {};
    if (r.modus === "beladen") return `↩ ${t("rueckweg.beladen")}`;
    if (r.modus === "spaeter") return `↩ ${t("rueckweg.spaeter_um", { uhrzeit: r.uhrzeit })}`;
    if (r.modus === "keiner") return `↩ ${t("rueckweg.keiner")}`;
    return "";
  }

  async function loeschen(l) {
    if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name: l.name })))) return;
    try {
      await api(`lieferungen/${l.id}`, { methode: "DELETE" });
      simulationVergessen();
      laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  // ---------------------------------------------------------------- Dialog
  function dialog(l) {
    if (!punkte.length) return melden(t("lieferung.erst_punkte"), "fehler");
    const neu = !l?.id;
    const v = {
      name: "", lieferant: "", richtung: "versorgung", transportart_id: stamm.transportarten[0]?.id, start_id: null, ziel_id: null,
      uhrzeit: "08:00", spaetestens: "", ladung: [], via: [], regel: { wochentage: [1, 2, 3, 4, 5], feiertage: "ausser" },
      rueckweg: { modus: "leer", uhrzeit: "", ziel_id: null }, aktiv: true, notiz: "", ...(l || {}),
    };
    const startPunkte = (p) => p.art !== "weg";
    const el = {
      name: h("input", { value: v.name, required: true, maxlength: 150 }),
      lieferant: h("input", { value: v.lieferant, maxlength: 150 }),
      richtung: h("select", ["versorgung", "entsorgung"].map((r) => h("option", { value: r, selected: r === v.richtung }, t(`richtung.${r}`)))),
      transportart: h("select", stamm.transportarten.map((x) => h("option", { value: x.id, selected: x.id === v.transportart_id }, x.name))),
      uhrzeit: h("input", { type: "time", value: v.uhrzeit, required: true }),
      spaetestens: h("input", { type: "time", value: v.spaetestens || "" }),
      start: punktAuswahl(punkte, v.start_id, { filter: startPunkte, leer: t("lieferung.waehlen") }),
      ziel: punktAuswahl(punkte, v.ziel_id, { filter: startPunkte, leer: t("lieferung.waehlen") }),
      feiertage: h("select", ["ausser", "auch", "nur"].map((m) => h("option", { value: m, selected: m === (v.regel.feiertage || "ausser") }, t(`regel.feiertage.${m}`)))),
      von: h("input", { type: "date", value: v.regel.von || "" }),
      bis: h("input", { type: "date", value: v.regel.bis || "" }),
      ausnahmen: h("input", { value: (v.regel.ausnahmen || []).join(", "), placeholder: "2026-12-24, 2026-12-31" }),
      zusatztage: h("input", { value: (v.regel.zusatztage || []).join(", "), placeholder: "2026-12-27" }),
      rueckModus: h("select", ["leer", "beladen", "spaeter", "keiner"].map((m) => h("option", { value: m, selected: m === v.rueckweg.modus }, t(`rueckweg.${m}`)))),
      rueckUhrzeit: h("input", { type: "time", value: v.rueckweg.uhrzeit || "" }),
      rueckZiel: punktAuswahl(punkte, v.rueckweg.ziel_id, { filter: startPunkte, leer: t("rueckweg.zum_start") }),
      aktiv: h("input", { type: "checkbox", checked: v.aktiv }),
      notiz: h("textarea", { rows: 2, maxlength: 2000 }, v.notiz),
    };
    const tage = TAGE.map((d) => h("label.tagwahl", h("input", { type: "checkbox", value: d, checked: (v.regel.wochentage || []).includes(d) }), h("span", t("wochentag")[d % 7])));
    const tageSetzen = (liste) => tage.forEach((l) => (l.querySelector("input").checked = liste.includes(Number(l.querySelector("input").value))));

    // Ladung: Zeilen Wagentyp + Anzahl
    const ladungBox = h("div.ladung");
    const ladungZeile = (p = { wagentyp_id: stamm.wagentypen[0]?.id, anzahl: 1 }) => {
      const zeile = h(
        "div.zeile",
        h("input", { type: "number", min: 0, max: 1000, value: p.anzahl, class: "anzahl" }),
        h("select", stamm.wagentypen.map((w) => h("option", { value: w.id, selected: w.id === p.wagentyp_id }, w.name))),
        h("button.knopf-flach.gefahr", { type: "button", onclick: () => zeile.remove(), "aria-label": t("allgemein.loeschen") }, "×")
      );
      ladungBox.append(zeile);
    };
    (v.ladung.length ? v.ladung : [undefined]).forEach((p) => ladungZeile(p));

    // Zwischenstationen
    const viaBox = h("div.via");
    const viaZeile = (id = null) => {
      const auswahl = punktAuswahl(punkte, id);
      const zeile = h("div.zeile", auswahl, h("button.knopf-flach.gefahr", { type: "button", onclick: () => zeile.remove(), "aria-label": t("allgemein.loeschen") }, "×"));
      viaBox.append(zeile);
    };
    v.via.forEach((id) => viaZeile(id));

    const rueckZeile = h("div.zeile", el.rueckUhrzeit);
    const rueckSichtbar = () => {
      rueckZeile.hidden = el.rueckModus.value !== "spaeter";
      el.rueckZiel.closest("label").hidden = el.rueckModus.value === "keiner";
    };
    el.rueckModus.addEventListener("change", rueckSichtbar);

    const fehlerZeile = h("p.dialog-fehler", { hidden: true });
    const f = (label, eingabe, hilfe) => h("label.feld", h("span", label), eingabe, hilfe ? h("small", hilfe) : null);
    const dlg = h("dialog.dialog.gross");
    const form = h(
      "form.lieferungsformular",
      h("h2", neu ? t("lieferung.neu") : `${t("lieferung.bearbeiten")}: ${v.name}`),
      h(
        "div.raster",
        f(t("lieferung.name"), el.name),
        f(t("lieferung.lieferant"), el.lieferant),
        f(t("lieferung.richtung"), el.richtung),
        f(t("lieferung.transportart"), el.transportart),
        f(t("lieferung.uhrzeit"), el.uhrzeit),
        f(t("lieferung.spaetestens"), el.spaetestens, t("lieferung.spaetestens_hilfe")),
        f(t("lieferung.start"), el.start),
        f(t("lieferung.ziel"), el.ziel)
      ),
      h("h3.dialog-abschnitt", t("lieferung.ladung")),
      ladungBox,
      h("button.knopf-flach", { type: "button", onclick: () => ladungZeile() }, "+ " + t("lieferung.wagen_hinzu")),
      h("h3.dialog-abschnitt", t("lieferung.wann")),
      h(
        "div.tage",
        tage,
        h("span.trenner"),
        h("button.knopf-flach", { type: "button", onclick: () => tageSetzen([1, 2, 3, 4, 5]) }, t("regel.mo_fr")),
        h("button.knopf-flach", { type: "button", onclick: () => tageSetzen(TAGE) }, t("regel.taeglich")),
        h("button.knopf-flach", { type: "button", onclick: () => tageSetzen([6, 7]) }, t("regel.wochenende"))
      ),
      h(
        "div.raster",
        f(t("regel.feiertage_label"), el.feiertage),
        h("div"),
        f(t("regel.von"), el.von),
        f(t("regel.bis"), el.bis),
        f(t("regel.ausnahmen"), el.ausnahmen, t("regel.ausnahmen_hilfe")),
        f(t("regel.zusatztage"), el.zusatztage, t("regel.zusatztage_hilfe"))
      ),
      h("h3.dialog-abschnitt", t("lieferung.rueckweg")),
      h("div.raster", f(t("rueckweg.label"), el.rueckModus), h("div", rueckZeile), f(t("rueckweg.ziel"), el.rueckZiel)),
      h("h3.dialog-abschnitt", t("lieferung.zwischenstationen")),
      h("p.hinweis", t("lieferung.zwischenstationen_hilfe")),
      viaBox,
      h("button.knopf-flach", { type: "button", onclick: () => viaZeile() }, "+ " + t("lieferung.station_hinzu")),
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
    rueckSichtbar();

    const datumsliste = (text) => text.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const daten = {
        name: el.name.value,
        lieferant: el.lieferant.value,
        richtung: el.richtung.value,
        transportart_id: Number(el.transportart.value),
        start_id: Number(el.start.value) || 0,
        ziel_id: Number(el.ziel.value) || 0,
        uhrzeit: el.uhrzeit.value,
        spaetestens: el.spaetestens.value || null,
        ladung: [...ladungBox.querySelectorAll(".zeile")].map((z) => ({ anzahl: Number(z.querySelector("input").value) || 0, wagentyp_id: Number(z.querySelector("select").value) })),
        via: [...viaBox.querySelectorAll("select")].map((s) => Number(s.value)).filter(Boolean),
        regel: {
          wochentage: tage.map((l) => l.querySelector("input")).filter((i) => i.checked).map((i) => Number(i.value)),
          feiertage: el.feiertage.value,
          von: el.von.value || null,
          bis: el.bis.value || null,
          ausnahmen: datumsliste(el.ausnahmen.value),
          zusatztage: datumsliste(el.zusatztage.value),
        },
        rueckweg: { modus: el.rueckModus.value, uhrzeit: el.rueckUhrzeit.value || null, ziel_id: Number(el.rueckZiel.value) || null },
        aktiv: el.aktiv.checked,
        notiz: el.notiz.value,
      };
      try {
        if (!daten.start_id || !daten.ziel_id) throw new Error(t("lieferung.start_ziel_fehlt"));
        await api(neu ? "lieferungen" : `lieferungen/${l.id}`, { methode: neu ? "POST" : "PUT", daten });
        dlg.close();
        simulationVergessen();
        melden(t("allgemein.gespeichert"));
        laden();
      } catch (err) {
        fehlerZeile.textContent = err.message;
        fehlerZeile.hidden = false;
      }
    });
    dlg.append(form);
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
    el.name.focus();
  }

  laden();
}
