// Benutzer und Rollen verwalten

import { api, bestaetigen, fehlerMelden, formularDialog, h, leeren, t, zustand } from "./basis.js";

export function zeigeBenutzer(wurzel) {
  const box = h("div");
  const rollenBox = h("div");
  let rollen = [];
  let rechte = [];
  let standorte = [];
  wurzel.append(
    h(
      "div.stapel",
      h(
        "section.karte-box",
        h("div.box-kopf", h("h2", t("benutzer.titel")), h("button.knopf", { type: "button", onclick: () => dialog() }, "+ " + t("benutzer.neu"))),
        box
      ),
      h(
        "section.karte-box",
        h("div.box-kopf", h("h2", t("rolle.titel")), h("button.knopf", { type: "button", onclick: () => rollenDialog() }, "+ " + t("rolle.neu"))),
        h("p.hinweis", t("rolle.hilfe")),
        rollenBox
      )
    )
  );

  const rollenName = (schluessel) => {
    const text = t(`rollen.${schluessel}`);
    return text.startsWith("⟨") ? rollen.find((r) => r.schluessel === schluessel)?.name ?? schluessel : text;
  };

  async function laden() {
    try {
      const [liste, r, st] = await Promise.all([api("benutzer"), api("rollen"), api("standorte")]);
      rollen = r.rollen;
      standorte = st.standorte;
      rechte = r.rechte;
      zeigeBenutzerListe(liste);
      zeigeRollen();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  function zeigeBenutzerListe(liste) {
    leeren(
      box,
      h(
        "div.tabellenrahmen",
        h(
          "table.tabelle",
          h("thead", h("tr", h("th", t("benutzer.benutzername")), h("th", t("benutzer.anzeigename")), h("th", t("benutzer.rolle")), h("th"))),
          h(
            "tbody",
            liste.map((b) =>
              h(
                "tr",
                { class: b.aktiv ? "" : "inaktiv" },
                h(
                  "td",
                  b.benutzername,
                  b.id === zustand.benutzer.id ? h("span.marke-klein", t("benutzer.du")) : null,
                  b.quelle === "ldap" ? h("span.marke-klein.grau", { title: t("benutzer.aus_verzeichnis_hilfe") }, t("benutzer.aus_verzeichnis")) : null
                ),
                h("td", b.anzeigename),
                h(
                  "td",
                  rollenName(b.rolle),
                  b.aktiv ? null : h("span.marke-klein.grau", t("benutzer.deaktiviert")),
                  b.standorte?.length && standorte.length > 1
                    ? h("div.gedimmt.klein", t("benutzer.nur_standorte", { namen: b.standorte.map((id) => standorte.find((s) => s.id === id)?.name ?? id).join(", ") }))
                    : null
                ),
                h(
                  "td.aktionen",
                  h("button.knopf-flach", { type: "button", onclick: () => dialog(b) }, t("allgemein.bearbeiten")),
                  b.id === zustand.benutzer.id ? null : h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(b) }, t("allgemein.loeschen"))
                )
              )
            )
          )
        )
      )
    );
  }

  function zeigeRollen() {
    leeren(
      rollenBox,
      h(
        "div.tabellenrahmen",
        h(
          "table.tabelle",
          h("thead", h("tr", h("th", t("rolle.name")), h("th", t("rolle.rechte")), h("th", t("rolle.benutzer")), h("th"))),
          h(
            "tbody",
            rollen.map((r) =>
              h(
                "tr",
                h("td", rollenName(r.schluessel), r.system ? h("span.marke-klein.grau", t("rolle.system")) : null),
                h("td", r.rechte.map((x) => h("span.chip.recht", t(`recht.${x}`)))),
                h("td", r.benutzer),
                h(
                  "td.aktionen",
                  r.system
                    ? null
                    : [
                        h("button.knopf-flach", { type: "button", onclick: () => rollenDialog(r) }, t("allgemein.bearbeiten")),
                        h("button.knopf-flach.gefahr", { type: "button", onclick: () => rolleLoeschen(r) }, t("allgemein.loeschen")),
                      ]
                )
              )
            )
          )
        )
      ),
      h("dl.werte.rechte-erklaerung", rechte.map((x) => [h("dt", t(`recht.${x}`)), h("dd", t(`recht_hilfe.${x}`))]))
    );
  }

  async function rollenDialog(r) {
    const ok = await formularDialog({
      titel: r ? `${t("rolle.bearbeiten")}: ${r.name}` : t("rolle.neu"),
      felder: [
        { name: "name", label: t("rolle.name"), pflicht: true, wert: r?.name },
        { name: "rechte", label: t("rolle.rechte"), typ: "mehrfach", wert: r?.rechte || ["ansehen"], optionen: rechte.map((x) => [x, t(`recht.${x}`)]) },
      ],
      speichern: (w) => api(r ? `rollen/${r.id}` : "rollen", { methode: r ? "PUT" : "POST", daten: w }),
    });
    if (ok) laden();
  }

  async function rolleLoeschen(r) {
    if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name: r.name })))) return;
    try {
      await api(`rollen/${r.id}`, { methode: "DELETE" });
      laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  async function dialog(b) {
    const neu = !b;
    const rollenOptionen = rollen.map((r) => [r.schluessel, rollenName(r.schluessel)]);
    // Zugriff je Krankenhaus – nur sinnvoll, wenn es mehrere gibt
    const standortFeld = standorte.length > 1
      ? [{ name: "standorte", label: t("benutzer.standorte"), typ: "mehrfach", wert: (b?.standorte || []).map(String),
           optionen: standorte.map((s) => [String(s.id), s.name]), hilfe: t("benutzer.standorte_hilfe") }]
      : [];
    const felder = neu
      ? [
          { name: "benutzername", label: t("benutzer.benutzername"), pflicht: true, attr: { autocomplete: "off" } },
          { name: "anzeigename", label: t("benutzer.anzeigename") },
          { name: "rolle", label: t("benutzer.rolle"), typ: "auswahl", optionen: rollenOptionen, wert: "betrachter" },
          { name: "passwort", label: t("benutzer.passwort"), typ: "password", pflicht: true, attr: { autocomplete: "new-password", minlength: 8 } },
          ...standortFeld,
        ]
      : [
          { name: "anzeigename", label: t("benutzer.anzeigename"), wert: b.anzeigename },
          { name: "rolle", label: t("benutzer.rolle"), typ: "auswahl", optionen: rollenOptionen, wert: b.rolle, hilfe: b.quelle === "ldap" ? t("benutzer.rolle_aus_verzeichnis") : null },
          { name: "aktiv", label: t("benutzer.aktiv"), typ: "haken", wert: !!b.aktiv },
          ...standortFeld,
          ...(b.quelle === "ldap" ? [] : [{ name: "passwort", label: t("benutzer.passwort_neu_optional"), typ: "password", attr: { autocomplete: "new-password" } }]),
        ];
    const ok = await formularDialog({
      titel: neu ? t("benutzer.neu") : `${t("benutzer.bearbeiten")}: ${b.benutzername}`,
      felder,
      speichern: (w) => {
        const auswahl = standortFeld.length ? (w.standorte || []).map(Number) : undefined;
        if (neu) return api("benutzer", { methode: "POST", daten: { ...w, standorte: auswahl ?? [] } });
        const daten = { anzeigename: w.anzeigename, rolle: w.rolle, aktiv: w.aktiv };
        if (auswahl) daten.standorte = auswahl;
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
