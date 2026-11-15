// Einstellungen: Bundesland, Sprache, Feiertage und eigene Sondertage

import { api, bestaetigen, darf, datumText, fehlerMelden, h, leeren, melden, t } from "./basis.js";

export function zeigeEinstellungen(wurzel) {
  const allgemein = h("div");
  const feiertagBox = h("div");
  const titel = h("h2");
  let jahr = new Date().getFullYear();
  const verwalten = darf("verwalten");

  wurzel.append(
    h(
      "div.spalten.gleich",
      h("section.karte-box", h("div.box-kopf", h("h2", t("einstellungen.allgemein"))), allgemein),
      h(
        "section.karte-box",
        h(
          "div.box-kopf",
          titel,
          h(
            "div.knopfreihe",
            h("button.knopf-flach", { type: "button", "aria-label": "-1", onclick: () => ((jahr -= 1), feiertageLaden()) }, "‹"),
            h("button.knopf-flach", { type: "button", "aria-label": "+1", onclick: () => ((jahr += 1), feiertageLaden()) }, "›")
          )
        ),
        feiertagBox,
        h("h3", t("einstellungen.sondertage")),
        h("p.hinweis", t("einstellungen.sondertage_hilfe")),
        verwalten ? sondertagFormular() : null
      )
    )
  );

  async function laden() {
    try {
      const e = await api("einstellungen");
      const auswahl = (name, optionen, wert) =>
        h(
          "select",
          {
            name,
            disabled: !verwalten,
            onchange: async (ev) => {
              try {
                await api("einstellungen", { methode: "PUT", daten: { [name]: ev.target.value } });
                melden(t("allgemein.gespeichert"));
                if (name === "sprache") location.reload();
                feiertageLaden();
              } catch (err) {
                fehlerMelden(err);
              }
            },
          },
          Object.entries(optionen).map(([k, v]) => h("option", { value: k, selected: k === wert }, v))
        );
      leeren(
        allgemein,
        h("label.feld", h("span", t("einstellungen.bundesland")), auswahl("bundesland", e.bundeslaender, e.bundesland)),
        h("label.feld", h("span", t("einstellungen.sprache")), auswahl("sprache", e.sprachen, e.sprache))
      );
    } catch (err) {
      fehlerMelden(err);
    }
  }

  async function feiertageLaden() {
    titel.textContent = t("einstellungen.feiertage", { jahr });
    try {
      const daten = await api(`feiertage?jahr=${jahr}`);
      leeren(
        feiertagBox,
        h(
          "table.tabelle.kompakt",
          h(
            "tbody",
            daten.tage.map((tag) =>
              h(
                "tr",
                { class: tag.art },
                h("td", datumText(tag.datum)),
                h("td", tag.art === "gesetzlich" ? t(`feiertag.${tag.schluessel}`) : tag.name),
                h(
                  "td.aktionen",
                  tag.art === "sondertag"
                    ? [
                        h("span.marke-klein", t("einstellungen.sondertag")),
                        verwalten
                          ? h("button.knopf-flach.gefahr", { type: "button", onclick: () => sondertagLoeschen(tag) }, t("allgemein.loeschen"))
                          : null,
                      ]
                    : null
                )
              )
            )
          )
        )
      );
    } catch (err) {
      fehlerMelden(err);
    }
  }

  function sondertagFormular() {
    const datum = h("input", { type: "date", required: true, "aria-label": t("einstellungen.datum") });
    const name = h("input", { type: "text", required: true, maxlength: 100, placeholder: t("einstellungen.bezeichnung") });
    const form = h("form.zeile", datum, name, h("button.knopf", { type: "submit" }, t("allgemein.anlegen")));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("sondertage", { methode: "POST", daten: { datum: datum.value, name: name.value } });
        jahr = Number(datum.value.slice(0, 4));
        form.reset();
        feiertageLaden();
      } catch (err) {
        fehlerMelden(err);
      }
    });
    return form;
  }

  async function sondertagLoeschen(tag) {
    if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name: tag.name })))) return;
    try {
      await api(`sondertage/${tag.id}`, { methode: "DELETE" });
      feiertageLaden();
    } catch (err) {
      fehlerMelden(err);
    }
  }

  laden();
  feiertageLaden();
}
