// Standorte: mehrere Krankenhäuser in einer Installation (Auswahl im Kopf, Verwaltung in den Einstellungen)

import { api, bestaetigen, darf, fehlerMelden, formularDialog, h, leeren, melden, t, zustand } from "./basis.js";

/** Zum Standort wechseln: neu laden, damit alle Seiten frisch aus dem anderen Haus kommen. */
export async function standortWechseln(id) {
  await api(`standorte/${id}/waehlen`, { methode: "POST" });
  location.hash = "#/";
  location.reload();
}

/** Dialog „Neues Krankenhaus“; legt an und wechselt dorthin. */
export async function standortAnlegen() {
  const { aktuell, standorte } = await api("standorte");
  const ok = await formularDialog({
    titel: t("standort.neu_titel"),
    felder: [
      { name: "name", label: t("standort.name"), pflicht: true, attr: { maxlength: 120, placeholder: t("standort.name_beispiel") } },
      {
        name: "stammdaten_von",
        label: t("standort.stammdaten_von"),
        typ: "auswahl",
        wert: aktuell,
        optionen: [...standorte.map((s) => [s.id, s.name]), ["", t("standort.standardwerte")]],
        hilfe: t("standort.stammdaten_hilfe"),
      },
    ],
    speichernText: t("standort.anlegen"),
    speichern: (w) => api("standorte", { methode: "POST", daten: { name: w.name, stammdaten_von: w.stammdaten_von ? Number(w.stammdaten_von) : null, wechseln: true } }),
  });
  if (ok) {
    location.hash = "#/";
    location.reload();
  }
}

/** Auswahl im Kopf: „Klinikum A ▾“, für Verwalter mit „+ Neues Krankenhaus …“. */
export async function standortKopf(kopf) {
  let daten;
  try {
    daten = await api("standorte");
  } catch {
    return;
  }
  zustand.standort = daten.standorte.find((s) => s.id === daten.aktuell) || null;
  const auswahl = h(
    "select",
    { id: "standort-wahl", "aria-label": t("standort.titel"), title: t("standort.titel") },
    daten.standorte.map((s) => h("option", { value: s.id, selected: s.id === daten.aktuell }, s.name)),
    darf("verwalten") ? h("option", { value: "neu" }, t("standort.neu_menue")) : null
  );
  auswahl.addEventListener("change", async () => {
    const wert = auswahl.value;
    auswahl.value = String(daten.aktuell);
    try {
      if (wert === "neu") await standortAnlegen();
      else if (Number(wert) !== daten.aktuell) await standortWechseln(Number(wert));
    } catch (e) {
      fehlerMelden(e);
    }
  });
  document.getElementById("standort-wahl")?.remove();
  kopf.querySelector(".marke").after(auswahl);
}

/** Verwaltung in den Einstellungen: umbenennen, löschen, neu. */
export function standortBox() {
  const liste = h("div");
  const box = h(
    "section.karte-box",
    h("div.box-kopf", h("h2", t("standort.verwalten")), h("button.knopf", { type: "button", onclick: () => standortAnlegen().catch(fehlerMelden) }, "+ " + t("standort.neu_titel"))),
    h("p.hinweis", t("standort.hilfe")),
    liste
  );
  async function laden() {
    try {
      const { aktuell, standorte } = await api("standorte");
      leeren(
        liste,
        h(
          "table.tabelle",
          h("thead", h("tr", h("th", t("standort.name")), h("th", t("standort.inhalt")), h("th", ""))),
          h(
            "tbody",
            standorte.map((s) => {
              const name = h("input", { value: s.name, maxlength: 120 });
              return h(
                "tr",
                h("td", name, s.id === aktuell ? h("span.marke-klein", t("standort.aktuell")) : null),
                h("td", t("standort.zahlen", { gebaeude: s.gebaeudeteile, lieferungen: s.lieferungen })),
                h(
                  "td.knopfreihe",
                  h("button.knopf-flach", { type: "button", onclick: () => umbenennen(s, name.value) }, t("allgemein.speichern")),
                  s.id !== aktuell ? h("button.knopf-flach", { type: "button", onclick: () => standortWechseln(s.id).catch(fehlerMelden) }, t("standort.wechseln")) : null,
                  standorte.length > 1 ? h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(s, aktuell) }, t("allgemein.loeschen")) : null
                )
              );
            })
          )
        )
      );
    } catch (e) {
      fehlerMelden(e);
    }
  }
  async function umbenennen(s, name) {
    try {
      await api(`standorte/${s.id}`, { methode: "PUT", daten: { name } });
      melden(t("allgemein.gespeichert"));
      const kopf = document.getElementById("kopf");
      if (kopf) await standortKopf(kopf);
      laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }
  async function loeschen(s, aktuell) {
    if (!(await bestaetigen(t("standort.loeschen_frage", { name: s.name, gebaeude: s.gebaeudeteile, lieferungen: s.lieferungen })))) return;
    try {
      await api(`standorte/${s.id}`, { methode: "DELETE" });
      melden(t("standort.geloescht", { name: s.name }));
      if (s.id === aktuell) {
        location.hash = "#/";
        location.reload();
      } else laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }
  laden();
  return box;
}
