// Benutzer und Rollen verwalten

import { api, bestaetigen, fehlerMelden, formularDialog, h, leeren, t, zustand } from "./basis.js";

export function zeigeBenutzer(wurzel) {
  const box = h("div");
  let rollen = [];
  wurzel.append(
    h(
      "section.karte-box.schmal",
      h("div.box-kopf", h("h2", t("benutzer.titel")), h("button.knopf", { type: "button", onclick: () => dialog() }, "+ " + t("benutzer.neu"))),
      box
    )
  );

  const rollenName = (schluessel) => {
    const text = t(`rollen.${schluessel}`);
    return text.startsWith("⟨") ? rollen.find((r) => r.schluessel === schluessel)?.name ?? schluessel : text;
  };

  async function laden() {
    try {
      const [liste, r] = await Promise.all([api("benutzer"), api("rollen")]);
      rollen = r;
      leeren(
        box,
        h(
          "table.tabelle",
          h("thead", h("tr", h("th", t("benutzer.benutzername")), h("th", t("benutzer.anzeigename")), h("th", t("benutzer.rolle")), h("th"))),
          h(
            "tbody",
            liste.map((b) =>
              h(
                "tr",
                { class: b.aktiv ? "" : "inaktiv" },
                h("td", b.benutzername, b.id === zustand.benutzer.id ? h("span.marke-klein", t("benutzer.du")) : null),
                h("td", b.anzeigename),
                h("td", rollenName(b.rolle), b.aktiv ? null : h("span.marke-klein.grau", t("benutzer.deaktiviert"))),
                h(
                  "td.aktionen",
                  h("button.knopf-flach", { type: "button", onclick: () => dialog(b) }, t("allgemein.bearbeiten")),
                  b.id === zustand.benutzer.id
                    ? null
                    : h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(b) }, t("allgemein.loeschen"))
                )
              )
            )
          )
        )
      );
    } catch (e) {
      fehlerMelden(e);
    }
  }

  async function dialog(b) {
    const neu = !b;
    const rollenOptionen = rollen.map((r) => [r.schluessel, rollenName(r.schluessel)]);
    const felder = neu
      ? [
          { name: "benutzername", label: t("benutzer.benutzername"), pflicht: true, attr: { autocomplete: "off" } },
          { name: "anzeigename", label: t("benutzer.anzeigename") },
          { name: "rolle", label: t("benutzer.rolle"), typ: "auswahl", optionen: rollenOptionen, wert: "betrachter" },
          { name: "passwort", label: t("benutzer.passwort"), typ: "password", pflicht: true, attr: { autocomplete: "new-password", minlength: 8 } },
        ]
      : [
          { name: "anzeigename", label: t("benutzer.anzeigename"), wert: b.anzeigename },
          { name: "rolle", label: t("benutzer.rolle"), typ: "auswahl", optionen: rollenOptionen, wert: b.rolle },
          { name: "aktiv", label: t("benutzer.aktiv"), typ: "haken", wert: !!b.aktiv },
          { name: "passwort", label: t("benutzer.passwort_neu_optional"), typ: "password", attr: { autocomplete: "new-password" } },
        ];
    const ok = await formularDialog({
      titel: neu ? t("benutzer.neu") : `${t("benutzer.bearbeiten")}: ${b.benutzername}`,
      felder,
      speichern: (w) => {
        if (neu) return api("benutzer", { methode: "POST", daten: w });
        const daten = { anzeigename: w.anzeigename, rolle: w.rolle, aktiv: w.aktiv };
        if (w.passwort) daten.passwort = w.passwort;
        return api(`benutzer/${b.id}`, { methode: "PUT", daten });
      },
    });
    if (ok) laden();
  }

  async function loeschen(b) {
    if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name: b.benutzername })))) return;
    try {
      await api(`benutzer/${b.id}`, { methode: "DELETE" });
      laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  laden();
}
