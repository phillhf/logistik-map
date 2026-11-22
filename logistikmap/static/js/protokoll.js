// Änderungsprotokoll: wer hat wann was geändert

import { api, fehlerMelden, h, leeren, sprache, t } from "./basis.js";

export function zeigeProtokoll(wurzel) {
  const benutzerWahl = h("select");
  const objektWahl = h("select");
  const box = h("div");
  const mehr = h("button.knopf-flach", { type: "button", hidden: true }, t("protokoll.mehr"));
  let seite = 0;
  let geladen = [];

  wurzel.append(
    h(
      "section.karte-box",
      h("div.box-kopf", h("h2", t("protokoll.titel")), h("div.knopfreihe", benutzerWahl, objektWahl, h("a.knopf-flach", { href: "#/einstellungen" }, t("protokoll.zurueck")))),
      h("p.hinweis", t("protokoll.hilfe")),
      box,
      mehr
    )
  );

  const objekte = ["lieferungen", "produktionen", "knoten", "kanten", "flaechen", "stockwerke", "gebaeudeteile", "dokumente", "benutzer", "rollen", "transportarten", "wagentypen", "aufzuege", "szenarien", "sondertage", "einstellungen", "sicherung", "update"];
  leeren(objektWahl, h("option", { value: "" }, t("protokoll.alle_objekte")), objekte.map((o) => h("option", { value: o }, objektText(o))));
  [benutzerWahl, objektWahl].forEach((s) => s.addEventListener("change", () => laden(true)));
  mehr.addEventListener("click", () => {
    seite += 1;
    laden(false);
  });

  function objektText(o) {
    const x = t(`protokoll.objekt.${o}`);
    return x.startsWith("⟨") ? o : x;
  }

  function aktionText(a) {
    const x = t(`protokoll.aktion.${a}`);
    return x.startsWith("⟨") ? a : x;
  }

  async function laden(neu) {
    if (neu) {
      seite = 0;
      geladen = [];
    }
    try {
      const q = new URLSearchParams({ seite, benutzer: benutzerWahl.value, objekt: objektWahl.value });
      const d = await api(`protokoll?${q}`);
      geladen = geladen.concat(d.eintraege);
      if (neu) {
        const alt = benutzerWahl.value;
        leeren(benutzerWahl, h("option", { value: "" }, t("protokoll.alle_benutzer")), d.benutzer.map((b) => h("option", { value: b, selected: b === alt }, b)));
      }
      mehr.hidden = geladen.length >= d.gesamt;
      zeigen();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  function zeigen() {
    if (!geladen.length) return leeren(box, h("p.leer", t("allgemein.keine_eintraege")));
    leeren(
      box,
      h(
        "div.tabellenrahmen",
        h(
          "table.tabelle.kompakt",
          h("thead", h("tr", h("th", t("protokoll.zeit")), h("th", t("protokoll.benutzer")), h("th", t("protokoll.was")), h("th", t("protokoll.objekt_titel")))),
          h(
            "tbody",
            geladen.map((e) =>
              h(
                "tr",
                h("td.zeit", new Date(e.zeit.replace(" ", "T") + "Z").toLocaleString(sprache)),
                h("td", e.benutzer),
                h("td", aktionText(e.aktion)),
                h("td", objektText(e.objekt), e.bezeichnung ? h("small", e.bezeichnung) : e.objekt_id ? h("small", `#${e.objekt_id}`) : null)
              )
            )
          )
        )
      )
    );
  }

  laden(true);
}
