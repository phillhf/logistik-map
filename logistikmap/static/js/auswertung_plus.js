// Auswertung: „Streuung“ (viele Tage mit Zufall) und „Mindestbedarf“ (wie viele reichen?)

import { api, dauer, fehlerMelden, h, leeren, punktName, t, zahl } from "./basis.js";

const prozent = (x) => `${zahl(x * 100, 0)} %`;

function balken(anteil) {
  const klasse = anteil >= 0.25 ? "schlecht" : anteil >= 0.05 ? "mittel" : "gut";
  return h("div.anteil", h("div.balken", h("div", { class: klasse, style: { width: `${Math.round(anteil * 100)}%` } })), h("span", prozent(anteil)));
}

/** Streuung: Tag N-mal mit Zufall rechnen, je Engpass „an X % der Tage über der Schwelle“. */
export async function streuungZeigen(inhalt, { datum, szenario, stamm }) {
  const laeufe = h("input", { type: "number", min: 5, max: 500, step: 10, value: 100 });
  const schwelle = h("input", { type: "number", min: 1, max: 240, value: 30 });
  const knopf = h("button.knopf", { type: "button" }, t("streuung.berechnen"));
  const ergebnis = h("div");
  let lieferungen = [];
  try {
    lieferungen = await api("lieferungen");
  } catch {}
  const mitStreuung = lieferungen.filter((l) => l.streuung).length;
  const mitGrundlast = stamm.aufzuege.filter((a) => a.grundlast?.length).length;
  leeren(
    inhalt,
    h("p.hinweis", t("streuung.hilfe")),
    h(
      "p.hinweis",
      t("streuung.eingetragen", { lieferungen: mitStreuung, von: lieferungen.length, aufzuege: mitGrundlast }),
      mitStreuung ? null : h("strong", " " + t("streuung.noch_keine"))
    ),
    h("div.knopfreihe.filter", h("label.inline", t("streuung.laeufe"), laeufe), h("label.inline", t("streuung.schwelle"), schwelle), knopf),
    ergebnis
  );

  knopf.addEventListener("click", async () => {
    knopf.disabled = true;
    leeren(ergebnis, h("p.gedimmt", t("streuung.rechnet", { anzahl: laeufe.value })));
    try {
      const r = await api(`simulation/streuung?datum=${datum}&laeufe=${laeufe.value}&schwelle=${schwelle.value}${szenario ? `&szenario=${szenario}` : ""}`);
      zeigen(r);
    } catch (e) {
      fehlerMelden(e);
      leeren(ergebnis);
    } finally {
      knopf.disabled = false;
    }
  });

  function zeigen(r) {
    const minuten = r.schwelle / 60;
    leeren(
      ergebnis,
      h(
        "div.kennzahlen",
        h(`div.kennzahl.${r.anteil_tage_ueber >= 0.25 ? "schlecht" : r.anteil_tage_ueber >= 0.05 ? "mittel" : "gut"}`, h("strong", prozent(r.anteil_tage_ueber)), h("span", t("streuung.tage_ueber", { minuten }))),
        h("div.kennzahl", h("strong", dauer(r.max_wartezeit_p90)), h("span", t("streuung.p90_tag"))),
        h("div.kennzahl", h("strong", r.laeufe), h("span", t("streuung.durchlaeufe")))
      ),
      h("h3", t("streuung.engpaesse")),
      r.ressourcen.length
        ? h(
            "div.tabellenrahmen",
            h(
              "table.tabelle",
              h("thead", h("tr", h("th", t("streuung.wo")), h("th", t("streuung.anteil", { minuten })), h("th", t("streuung.median")), h("th", t("streuung.p90")), h("th", t("streuung.max")), h("th", t("streuung.auslastung")))),
              h(
                "tbody",
                r.ressourcen.map((x) =>
                  h("tr", h("td", x.name, h("small", t(`streuung.typ.${x.typ}`))), h("td", balken(x.anteil_ueber)), h("td", dauer(x.median)), h("td", dauer(x.p90)), h("td", dauer(x.max)), h("td", prozent(x.spitze_p90)))
                )
              )
            )
          )
        : h("p.gut", t("streuung.keine")),
      h("h3", t("streuung.lieferungen")),
      r.lieferungen.length
        ? h(
            "div.tabellenrahmen",
            h(
              "table.tabelle",
              h("thead", h("tr", h("th", t("streuung.lieferung")), h("th", t("streuung.verspaetet")), h("th", t("streuung.anteil", { minuten }) ), h("th", t("streuung.p90")))),
              h("tbody", r.lieferungen.map((x) => h("tr", h("td", x.name), h("td", balken(x.anteil_verspaetet)), h("td", balken(x.anteil_ueber)), h("td", dauer(x.p90)))))
            )
          )
        : h("p.leer", t("auswertung.keine_fahrten")),
      h("p.hinweis", t("streuung.lesen"))
    );
  }
}

/** Mindestbedarf: 1, 2, 3 … durchprobieren, bis dort niemand länger als X Minuten wartet. */
export async function bedarfZeigen(inhalt, { datum, szenario, stamm }) {
  let punkte = [];
  let engstellen = [];
  try {
    [punkte, engstellen] = await Promise.all([api("punkte"), api("engstellen")]);
  } catch (e) {
    return fehlerMelden(e);
  }
  const tore = punkte.filter((p) => p.art === "tor" || p.kapazitaet);
  const wahl = h(
    "select",
    h("optgroup", { label: t("bedarf.gruppe.transportart") }, stamm.transportarten.map((x) => h("option", { value: `transportart:${x.id}` }, x.name))),
    tore.length ? h("optgroup", { label: t("bedarf.gruppe.knoten") }, tore.map((p) => h("option", { value: `knoten:${p.id}` }, punktName(p)))) : null,
    engstellen.filter((e) => e.kapazitaet).length
      ? h("optgroup", { label: t("bedarf.gruppe.kante") }, engstellen.filter((e) => e.kapazitaet).map((e) => h("option", { value: `kante:${e.id}` }, e.name || `${e.von_name || "·"} – ${e.nach_name || "·"} (${e.stockwerk})`)))
      : null
  );
  const ziel = h("input", { type: "number", min: 0, max: 240, value: 15 });
  const mitStreuung = h("input", { type: "checkbox" });
  const knopf = h("button.knopf", { type: "button" }, t("bedarf.berechnen"));
  const ergebnis = h("div");
  leeren(
    inhalt,
    h("p.hinweis", t("bedarf.hilfe")),
    h(
      "div.knopfreihe.filter",
      h("label.inline", t("bedarf.was"), wahl),
      h("label.inline", t("bedarf.ziel"), ziel),
      h("label.inline.haken", mitStreuung, h("span", t("bedarf.mit_streuung"))),
      knopf
    ),
    ergebnis
  );

  knopf.addEventListener("click", async () => {
    const [art, id] = wahl.value.split(":");
    knopf.disabled = true;
    leeren(ergebnis, h("p.gedimmt", t("bedarf.rechnet")));
    try {
      const r = await api(`simulation/bedarf?art=${art}&id=${id}&ziel=${ziel.value}&datum=${datum}&laeufe=${mitStreuung.checked ? 30 : 0}${szenario ? `&szenario=${szenario}` : ""}`);
      zeigen(r, wahl.selectedOptions[0].textContent, art);
    } catch (e) {
      fehlerMelden(e);
      leeren(ergebnis);
    } finally {
      knopf.disabled = false;
    }
  });

  function zeigen(r, name, art) {
    const einheit = t(`bedarf.einheit.${art}`);
    const ta = art === "transportart" ? stamm.transportarten.find((x) => x.id === r.id) : null;
    leeren(
      ergebnis,
      r.empfehlung
        ? h("p.bedarf-ergebnis.gut", t("bedarf.ergebnis", { anzahl: r.empfehlung, einheit, name, minuten: r.ziel }))
        : h("p.bedarf-ergebnis.schlecht", t("bedarf.reicht_nicht", { anzahl: r.punkte.at(-1)?.anzahl, einheit, name, minuten: r.ziel })),
      art === "transportart" ? h("p.hinweis", t("bedarf.anzahl_hinweis")) : null,
      ta?.schichten?.length ? h("p.hinweis", t("bedarf.schichten_hinweis")) : null,
      r.laeufe ? h("p.hinweis", t("bedarf.streuung_hinweis", { laeufe: r.laeufe })) : null,
      h(
        "div.tabellenrahmen",
        h(
          "table.tabelle",
          h("thead", h("tr", h("th", t("bedarf.anzahl", { einheit })), h("th", t("bedarf.wartezeit")), h("th", t("bedarf.auslastung")), h("th", t("bedarf.verspaetet")))),
          h(
            "tbody",
            r.punkte.map((p) =>
              h(
                "tr",
                { class: p.anzahl === r.empfehlung ? "empfohlen" : "" },
                h("td", h("strong", p.anzahl), p.anzahl === r.empfehlung ? h("span.marke-klein", t("bedarf.reicht")) : null),
                h("td", { class: p.wartezeit <= r.ziel * 60 ? "gut" : "schlecht" }, dauer(p.wartezeit)),
                h("td", prozent(p.auslastung)),
                h("td", zahl(p.verspaetet, 1))
              )
            )
          )
        )
      )
    );
  }
}
