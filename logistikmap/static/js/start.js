// Erste Schritte: führt durch die Einrichtung. Was erledigt ist, prüft der Server aus den Daten.

import { api, darf, fehlerMelden, h, leeren, melden, t } from "./basis.js";

/** Zahl der offenen Schritte für die Marke im Menü (null, wenn die Seite nicht erlaubt ist) */
export async function offeneSchritte() {
  if (!darf("bearbeiten")) return null;
  const e = await api("einrichtung");
  return { offen: e.gesamt - e.erledigt, fertig: e.fertig };
}

export function zeigeStart(wurzel, _rest, beiAenderung = () => {}) {
  const box = h("div.erste-schritte");
  wurzel.append(box);
  let bundeslaender = null;
  let timer = null;

  async function laden() {
    try {
      const e = await api("einrichtung");
      if (!bundeslaender && darf("verwalten")) bundeslaender = await api("einstellungen");
      zeigen(e);
      beiAenderung(e);
      // Pläne werden im Hintergrund aufbereitet: so lange nachsehen, bis sie fertig sind
      clearTimeout(timer);
      if (e.schritte.some((s) => s.probleme.some((p) => p.code === "plan_laeuft"))) timer = setTimeout(laden, 5000);
    } catch (err) {
      fehlerMelden(err);
    }
  }

  function zeigen(e) {
    const naechster = e.schritte.find((s) => s.status === "offen");
    leeren(
      box,
      h(
        "section.karte-box.start-kopf",
        h("h2", t("start.titel")),
        h("p", e.fertig ? t("start.fertig") : t("start.einleitung")),
        h(
          "div.fortschritt",
          h("div.fortschritt-balken", h("span", { style: { width: `${(100 * e.erledigt) / e.gesamt}%` } })),
          h("span", t("start.stand", { erledigt: e.erledigt, gesamt: e.gesamt }))
        )
      ),
      h(
        "ol.schritte",
        e.schritte.map((s, i) => schritt(s, i + 1, s === naechster))
      ),
      h(
        "section.karte-box.optional",
        h("h3", t("start.optional_titel")),
        h("p.hinweis", t("start.optional_hilfe")),
        h(
          "ul",
          e.optional
            .filter((o) => o.id !== "benutzer" || darf("verwalten"))
            .map((o) =>
              h(
                "li",
                { class: o.erledigt ? "erledigt" : "" },
                h("span.symbol", o.erledigt ? "✓" : "○"),
                h("div", h("strong", t(`start.optional.${o.id}.titel`)), h("small", t(`start.optional.${o.id}.text`))),
                darf("verwalten") ? h("a.knopf-flach", { href: o.link }, o.erledigt ? t("start.ansehen") : t("start.einrichten")) : null
              )
            )
        )
      )
    );
  }

  function schritt(s, nr, naechster) {
    const erledigt = s.status === "erledigt" || s.status === "bereit";
    const symbol = s.status === "erledigt" ? "✓" : s.status === "hinweis" ? "!" : nr;
    const offen = !erledigt || s.status === "hinweis" || naechster || s.id === "ergebnis";
    return h(
      `li.schritt.status-${s.status}`,
      { class: naechster ? "naechster" : "", id: `schritt-${s.id}` },
      h("span.nummer", symbol),
      h(
        "div.schritt-inhalt",
        h(
          "div.schritt-kopf",
          h("h3", t(`start.schritt.${s.id}.titel`)),
          naechster ? h("span.marke-klein", t("start.als_naechstes")) : null,
          s.status === "hinweis" ? h("span.marke-klein.gelb", t("start.pruefen")) : null,
          zahlen(s)
        ),
        offen ? h("p.schritt-text", t(`start.schritt.${s.id}.text`)) : null,
        offen && s.id === "karte" ? h("ol.anleitung", t("start.schritt.karte.liste").map((z) => h("li", z))) : null,
        offen ? probleme(s) : null,
        offen ? aktionen(s, naechster) : null
      )
    );
  }

  function zahlen(s) {
    const z = s.zahlen || {};
    let text = "";
    if (s.id === "bundesland" && z.bundesland) text = (bundeslaender?.bundeslaender || {})[z.bundesland] || z.bundesland;
    if (s.id === "gebaeude") text = t("start.zahlen.gebaeude", z);
    if (s.id === "plaene") text = t("start.zahlen.plaene", z);
    if (s.id === "karte") text = t("start.zahlen.karte", z);
    if (s.id === "stammdaten") text = t("start.zahlen.stammdaten", z);
    if (s.id === "lieferungen") text = t("start.zahlen.lieferungen", z);
    return text ? h("span.schritt-zahlen", text) : null;
  }

  function probleme(s) {
    if (!s.probleme.length) return null;
    return h(
      "ul.probleme",
      s.probleme.map((p) =>
        h(
          "li",
          { class: p.art },
          h("span", t(`start.problem.${p.code}`, p.werte)),
          p.link ? h("a", { href: p.link }, t("start.beheben") + " →") : null
        )
      ),
      s.weitere ? h("li.weitere", t("start.weitere", { anzahl: s.weitere })) : null
    );
  }

  function aktionen(s, naechster) {
    const haupt = naechster ? "a.knopf" : "a.knopf-flach";
    const knoepfe = [];
    if (s.id === "bundesland") {
      if (!darf("verwalten")) return h("p.hinweis", t("start.nur_admin"));
      const auswahl = h(
        "select",
        Object.entries(bundeslaender?.bundeslaender || {}).map(([k, name]) => h("option", { value: k, selected: k === s.zahlen.bundesland }, name))
      );
      knoepfe.push(
        auswahl,
        h(naechster ? "button.knopf" : "button.knopf-flach", { type: "button", onclick: async () => {
          try {
            await api("einstellungen", { methode: "PUT", daten: { bundesland: auswahl.value } });
            melden(t("start.gespeichert"));
            laden();
          } catch (err) {
            fehlerMelden(err);
          }
        } }, s.status === "erledigt" ? t("allgemein.speichern") : t("start.uebernehmen"))
      );
    } else if (s.id === "ergebnis") {
      knoepfe.push(
        h(s.status === "bereit" ? "a.knopf" : "a.knopf-flach", { href: s.link }, t("start.zum_ablauf")),
        h("a.knopf-flach", { href: "#/auswertung" }, t("start.zur_auswertung")),
        h("a.knopf-flach", { href: "#/szenarien" }, t("start.zu_szenarien"))
      );
      if (s.status === "gesperrt") knoepfe.push(h("small.gedimmt", t("start.erst_oben")));
    } else {
      knoepfe.push(h(haupt, { href: s.link }, t(`start.schritt.${s.id}.knopf`)));
      if (s.id === "stammdaten" && !s.zahlen.bestaetigt) {
        knoepfe.push(
          h("button.knopf-flach", { type: "button", onclick: async () => {
            try {
              await api("einrichtung/bestaetigen", { methode: "POST", daten: { schritt: "stammdaten" } });
              laden();
            } catch (err) {
              fehlerMelden(err);
            }
          } }, "✓ " + t("start.werte_passen"))
        );
      }
    }
    return h("div.knopfreihe.schritt-knoepfe", knoepfe);
  }

  laden();
  return () => clearTimeout(timer);
}
