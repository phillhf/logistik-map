// Verwaltung: Gebäudeteile, Stockwerke, PDF-Pläne

import { api, bestaetigen, datumText, fehlerMelden, formularDialog, groesse, h, hochladen, leeren, melden, t, zahl } from "./basis.js";

export function zeigeGebaeude(wurzel) {
  const teileBox = h("div.teile");
  const dokBox = h("div");
  let timer = null;

  wurzel.append(
    h(
      "div.spalten",
      h(
        "section.karte-box.breit",
        h("div.box-kopf", h("h2", t("gebaeude.teile")), h("button.knopf", { type: "button", onclick: teilDialog }, "+ " + t("gebaeude.teil_neu"))),
        teileBox
      ),
      h(
        "section.karte-box",
        h("div.box-kopf", h("h2", t("dokumente.titel")), uploadKnopf()),
        h("p.hinweis", t("dokumente.hinweis")),
        dokBox
      )
    )
  );

  let dokumente = [];

  async function laden() {
    try {
      const [teile, doks] = await Promise.all([api("gebaeude"), api("dokumente")]);
      dokumente = doks;
      zeigeTeile(teile);
      zeigeDokumente();
      // laufende Aufbereitung: regelmäßig nachladen
      const laeuft = teile.some((tl) => tl.stockwerke.some((s) => s.plan && ["wartet", "laeuft"].includes(s.plan.status)));
      clearTimeout(timer);
      if (laeuft) timer = setTimeout(laden, 2000);
    } catch (e) {
      fehlerMelden(e);
    }
  }

  function zeigeTeile(teile) {
    if (!teile.length) return leeren(teileBox, h("p.leer", t("gebaeude.keine_teile")));
    leeren(
      teileBox,
      teile.map((teil) =>
        h(
          "div.teil",
          h(
            "div.teil-kopf",
            h("h3", teil.kuerzel ? h("span.kuerzel", teil.kuerzel) : null, teil.name),
            h(
              "div.knopfreihe",
              h("button.knopf-flach", { type: "button", onclick: () => stockwerkDialog(teil) }, "+ " + t("gebaeude.stockwerk_neu")),
              h("button.knopf-flach", { type: "button", onclick: () => teilDialog(teil) }, t("allgemein.bearbeiten")),
              h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(`gebaeudeteile/${teil.id}`, teil.name) }, t("allgemein.loeschen"))
            )
          ),
          teil.stockwerke.length
            ? h(
                "table.tabelle",
                h("thead", h("tr", h("th", t("gebaeude.ebene")), h("th", t("gebaeude.stockwerk")), h("th", t("gebaeude.plan")), h("th"))),
                h("tbody", teil.stockwerke.map((s) => stockwerkZeile(teil, s)))
              )
            : h("p.leer", t("gebaeude.keine_stockwerke"))
        )
      )
    );
  }

  function planStatus(plan) {
    if (!plan) return h("span.gedimmt", t("gebaeude.kein_plan"));
    const text = t(`gebaeude.status.${plan.status}`, { prozent: zahl(plan.fortschritt * 100, 0) });
    return h(
      "div.planinfo",
      h("span", `${plan.dateiname} · ${t("gebaeude.seite", { nr: plan.seite })}`),
      h(`span.status.${plan.status}`, { title: plan.fehler || "" }, text),
      plan.status === "laeuft" ? h("progress", { max: 1, value: plan.fortschritt }) : null
    );
  }

  function stockwerkZeile(teil, s) {
    return h(
      "tr",
      h("td.zahl", s.ebene),
      h("td", s.plan?.status === "fertig" ? h("a", { href: `#/karte/${s.id}` }, s.name) : s.name),
      h("td", planStatus(s.plan)),
      h(
        "td.aktionen",
        h("button.knopf-flach", { type: "button", onclick: () => planDialog(s) }, s.plan ? t("gebaeude.plan_aendern") : t("gebaeude.plan_zuweisen")),
        s.plan?.status === "fehler"
          ? h("button.knopf-flach", { type: "button", onclick: () => aktion(`plaene/${s.plan.id}/neu`, "POST") }, t("gebaeude.plan_neu_erzeugen"))
          : null,
        s.plan ? h("button.knopf-flach", { type: "button", onclick: () => aktion(`stockwerke/${s.id}/plan`, "DELETE") }, t("gebaeude.plan_entfernen")) : null,
        h("button.knopf-flach", { type: "button", onclick: () => stockwerkDialog(teil, s) }, t("allgemein.bearbeiten")),
        h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(`stockwerke/${s.id}`, s.name) }, t("allgemein.loeschen"))
      )
    );
  }

  async function aktion(pfad, methode) {
    try {
      await api(pfad, { methode });
      laden();
    } catch (e) {
      fehlerMelden(e);
    }
  }

  async function loeschen(pfad, name) {
    if (!(await bestaetigen(t("allgemein.sicher_loeschen", { name })))) return;
    await aktion(pfad, "DELETE");
  }

  async function teilDialog(teil) {
    const neu = !teil?.id;
    const ok = await formularDialog({
      titel: neu ? t("gebaeude.teil_neu") : t("gebaeude.teil_bearbeiten"),
      felder: [
        { name: "name", label: t("gebaeude.name"), pflicht: true, wert: teil?.name },
        { name: "kuerzel", label: t("gebaeude.kuerzel"), wert: teil?.kuerzel, attr: { maxlength: 10 } },
        { name: "reihenfolge", label: t("gebaeude.reihenfolge"), typ: "number", wert: teil?.reihenfolge ?? 0 },
      ],
      speichern: (w) =>
        api(neu ? "gebaeudeteile" : `gebaeudeteile/${teil.id}`, { methode: neu ? "POST" : "PUT", daten: { ...w, reihenfolge: w.reihenfolge ?? 0 } }),
    });
    if (ok) laden();
  }

  async function stockwerkDialog(teil, s) {
    const neu = !s;
    const ok = await formularDialog({
      titel: neu ? t("gebaeude.stockwerk_neu") : t("gebaeude.stockwerk_bearbeiten"),
      felder: [
        { name: "name", label: t("gebaeude.name"), pflicht: true, wert: s?.name },
        { name: "ebene", label: t("gebaeude.ebene"), typ: "number", pflicht: true, wert: s?.ebene ?? 0, hilfe: t("gebaeude.ebene_hilfe") },
      ],
      speichern: (w) =>
        neu
          ? api("stockwerke", { methode: "POST", daten: { gebaeudeteil_id: teil.id, name: w.name, ebene: w.ebene ?? 0 } })
          : api(`stockwerke/${s.id}`, { methode: "PUT", daten: { name: w.name, ebene: w.ebene ?? 0 } }),
    });
    if (ok) laden();
  }

  // Plan zuweisen: PDF und Seite über Vorschaubilder wählen
  function planDialog(s) {
    const dialog = h("dialog.dialog.gross");
    const auswahl = h("div.seitenauswahl");
    const dokWahl = h(
      "select",
      { onchange: () => seitenZeigen(Number(dokWahl.value)) },
      dokumente.map((d) => h("option", { value: d.id, selected: d.id === s.plan?.dokument_id }, `${d.dateiname} (${t("dokumente.seiten", { anzahl: d.seiten.length })})`))
    );
    const upload = uploadKnopf(async (dok) => {
      await laden();
      dokWahl.append(h("option", { value: dok.id }, `${dok.dateiname} (${t("dokumente.seiten", { anzahl: dok.seiten.length })})`));
      dokWahl.value = dok.id;
      seitenZeigen(dok.id);
    });

    function seitenZeigen(did) {
      const dok = dokumente.find((d) => d.id === did);
      if (!dok) return leeren(auswahl, h("p.leer", t("dokumente.keine")));
      leeren(
        auswahl,
        dok.seiten.map((seite) =>
          h(
            "button.seite",
            {
              type: "button",
              class: s.plan?.dokument_id === did && s.plan?.seite === seite.nr ? "gewaehlt" : "",
              onclick: async () => {
                try {
                  const r = await api(`stockwerke/${s.id}/plan`, { methode: "PUT", daten: { dokument_id: did, seite: seite.nr } });
                  dialog.close();
                  if (r.inhalt_vorhanden) planGewechseltHinweis(s);
                  laden();
                } catch (e) {
                  fehlerMelden(e);
                }
              },
            },
            h("img", { src: `/api/dokumente/${did}/vorschau/${seite.nr}`, alt: "", loading: "lazy" }),
            h("span", t("gebaeude.seite", { nr: seite.nr }))
          )
        )
      );
    }

    dialog.append(
      h("h2", `${t("gebaeude.plan_zuweisen")}: ${s.name}`),
      h("div.knopfreihe", dokWahl, upload),
      h("p.hinweis", t("gebaeude.seite_waehlen")),
      auswahl,
      h("div.dialog-knoepfe", h("button.knopf-flach", { type: "button", onclick: () => dialog.close() }, t("allgemein.schliessen")))
    );
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
    if (dokumente.length) seitenZeigen(Number(dokWahl.value));
    else leeren(auswahl, h("p.leer", t("dokumente.keine")));
  }

  function planGewechseltHinweis(s) {
    const dlg = h("dialog.dialog");
    dlg.append(
      h(
        "form",
        { method: "dialog" },
        h("h2", t("gebaeude.plan_gewechselt_titel")),
        h("p", t("gebaeude.plan_gewechselt", { name: s.name })),
        h("div.dialog-knoepfe", h("button.knopf-flach", { value: "nein" }, t("allgemein.schliessen")), h("button.knopf", { value: "ja" }, t("gebaeude.jetzt_ausrichten")))
      )
    );
    dlg.addEventListener("close", () => {
      dlg.remove();
      if (dlg.returnValue === "ja") location.hash = `#/karte/${s.id}/bearbeiten/werkzeug/ausrichten`;
    });
    document.body.append(dlg);
    dlg.showModal();
  }

  function zeigeDokumente() {
    if (!dokumente.length) return leeren(dokBox, h("p.leer", t("dokumente.keine")));
    leeren(
      dokBox,
      h(
        "ul.dokliste",
        dokumente.map((d) =>
          h(
            "li",
            h("img", { src: `/api/dokumente/${d.id}/vorschau/1`, alt: "", loading: "lazy" }),
            h(
              "div",
              h("strong", d.dateiname),
              h("small", `${t("dokumente.seiten", { anzahl: d.seiten.length })} · ${groesse(d.groesse)} · ${datumText(d.hochgeladen.slice(0, 10))}`),
              d.verwendet ? h("small", t("dokumente.verwendet", { anzahl: d.verwendet })) : null
            ),
            d.verwendet ? null : h("button.knopf-flach.gefahr", { type: "button", onclick: () => loeschen(`dokumente/${d.id}`, d.dateiname) }, t("allgemein.loeschen"))
          )
        )
      )
    );
  }

  function uploadKnopf(nachUpload) {
    const eingabe = h("input", { type: "file", accept: "application/pdf,.pdf", hidden: true });
    const knopf = h("button.knopf", { type: "button", onclick: () => eingabe.click() }, t("dokumente.hochladen"));
    eingabe.addEventListener("change", async () => {
      const datei = eingabe.files[0];
      eingabe.value = "";
      if (!datei) return;
      knopf.disabled = true;
      try {
        const dok = await hochladen("dokumente", "datei", datei, (anteil) => {
          knopf.textContent = t("dokumente.hochladen_laeuft", { prozent: zahl(anteil * 100, 0) });
        });
        melden(t("dokumente.hochgeladen", { name: dok.dateiname, seiten: dok.seiten.length }));
        if (nachUpload) await nachUpload(dok);
        else laden();
      } catch (e) {
        fehlerMelden(e);
      } finally {
        knopf.disabled = false;
        knopf.textContent = t("dokumente.hochladen");
      }
    });
    return h("span", knopf, eingabe);
  }

  laden();
  return () => clearTimeout(timer);
}
