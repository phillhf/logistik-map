// Einstellungen: Bundesland, Sprache, Feiertage, Sondertage – für Administratoren zusätzlich
// Sicherung, Update, HTTPS, Anmeldung über Active Directory und Protokoll.

import { api, bestaetigen, darf, dateiWaehlen, datumText, fehlerMelden, groesse, h, herunterladen, hochladen, leeren, melden, t, zahl, zustand } from "./basis.js";
import { standortBox } from "./standorte.js";

export function zeigeEinstellungen(wurzel) {
  const allgemein = h("div");
  const feiertagBox = h("div");
  const titel = h("h2");
  let jahr = new Date().getFullYear();
  const verwalten = darf("verwalten");

  wurzel.append(
    h(
      "div.stapel",
      verwalten ? standortBox() : null,
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
      ),
      verwalten ? h("div.spalten.gleich", sicherungBox(), updateBox()) : null,
      verwalten ? h("div.spalten.gleich", ldapBox(), httpsBox()) : null
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
        h("label.feld", h("span", t("einstellungen.bundesland")), auswahl("bundesland", e.bundeslaender, e.bundesland),
          zustand.standort ? h("small", t("standort.bundesland_gilt", { name: zustand.standort.name })) : null),
        h("label.feld", h("span", t("einstellungen.sprache")), auswahl("sprache", e.sprachen, e.sprache), h("small", t("einstellungen.sprache_hilfe"))),
        verwalten ? zahlFeld("sitzung_inaktiv_stunden", t("einstellungen.sitzung_inaktiv"), e.sitzung_inaktiv_stunden, { min: 0.25, step: 0.25 }) : null,
        verwalten ? zahlFeld("sitzung_ad_stunden", t("einstellungen.sitzung_ad"), e.sitzung_ad_stunden, { min: 1, step: 1 }) : null,
        verwalten ? zahlFeld("protokoll_tage", t("einstellungen.protokoll_tage"), e.protokoll_tage, { min: 0, step: 1 }, t("einstellungen.protokoll_tage_hilfe")) : null,
        verwalten ? h("p", h("a", { href: "#/protokoll" }, t("einstellungen.protokoll_link"))) : null
      );
    } catch (err) {
      fehlerMelden(err);
    }
  }

  function zahlFeld(name, label, wert, attr, hilfe) {
    const eingabe = h("input", { type: "number", value: wert, style: { width: "110px" }, ...attr });
    eingabe.addEventListener("change", async () => {
      try {
        await api("einstellungen", { methode: "PUT", daten: { [name]: Number(eingabe.value) } });
        melden(t("allgemein.gespeichert"));
      } catch (err) {
        fehlerMelden(err);
      }
    });
    return h("label.feld", h("span", label), eingabe, hilfe ? h("small", hilfe) : null);
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
                        verwalten ? h("button.knopf-flach.gefahr", { type: "button", onclick: () => sondertagLoeschen(tag) }, t("allgemein.loeschen")) : null,
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

  // ---------------------------------------------------------------- Sicherung
  function sicherungBox() {
    const liste = h("div");
    const anzahl = h("input", { type: "number", min: 1, max: 365, style: { width: "80px" } });
    const box = h(
      "section.karte-box",
      h("div.box-kopf", h("h2", t("sicherung.titel"))),
      h("p.hinweis", t("sicherung.hilfe")),
      h(
        "div.knopfreihe",
        h("button.knopf", { type: "button", onclick: () => herunterladen("sicherung").catch(fehlerMelden) }, t("sicherung.herunterladen")),
        h("button.knopf-flach", { type: "button", onclick: jetzt }, t("sicherung.jetzt")),
        h("button.knopf-flach.gefahr", { type: "button", onclick: einspielen }, t("sicherung.einspielen"))
      ),
      h("label.inline.abstand-oben", t("sicherung.behalten"), anzahl),
      h("h3", t("sicherung.vorhanden")),
      liste
    );
    anzahl.addEventListener("change", async () => {
      try {
        await api("einstellungen", { methode: "PUT", daten: { sicherung_anzahl: Number(anzahl.value) } });
        melden(t("allgemein.gespeichert"));
      } catch (e) {
        fehlerMelden(e);
      }
    });

    async function listeLaden() {
      try {
        const [s, e] = await Promise.all([api("sicherungen"), api("einstellungen")]);
        anzahl.value = e.sicherung_anzahl;
        leeren(
          liste,
          s.length
            ? h(
                "ul.dokliste",
                s.slice(0, 20).map((x) =>
                  h(
                    "li",
                    h(
                      "div",
                      h("strong", new Date(x.zeit).toLocaleString(), " ", h(`span.marke-klein${x.dokumente ? "" : ".grau"}`, x.dokumente ? t("sicherung.voll") : t("sicherung.nur_db"))),
                      h("small", `${x.name} · ${groesse(x.groesse)}`)
                    ),
                    h("button.knopf-flach", { type: "button", onclick: () => herunterladen(`sicherungen/${encodeURIComponent(x.name)}`, x.name).catch(fehlerMelden) }, "⤓")
                  )
                )
              )
            : h("p.leer", t("sicherung.keine"))
        );
      } catch (e) {
        fehlerMelden(e);
      }
    }

    async function jetzt() {
      try {
        await api("sicherungen", { methode: "POST" });
        melden(t("sicherung.angelegt"));
        listeLaden();
      } catch (e) {
        fehlerMelden(e);
      }
    }

    async function einspielen() {
      const datei = await dateiWaehlen(".zip,application/zip");
      if (!datei) return;
      if (!(await bestaetigen(t("sicherung.wirklich", { name: datei.name }), t("sicherung.einspielen")))) return;
      try {
        const r = await hochladen("sicherung/wiederherstellen", "datei", datei, () => {});
        melden(t("sicherung.eingespielt", { zeit: new Date(r.zeit).toLocaleString() }));
        if (r.fehlende_dokumente?.length) melden(t("sicherung.fehlende_plaene", { liste: r.fehlende_dokumente.join(", ") }), "fehler");
        setTimeout(() => location.reload(), 1500);
      } catch (e) {
        fehlerMelden(e);
      }
    }

    listeLaden();
    return box;
  }

  // ---------------------------------------------------------------- Update
  function updateBox() {
    const inhalt = h("div");
    const box = h("section.karte-box", h("div.box-kopf", h("h2", t("update.titel")), h("button.knopf-flach", { type: "button", onclick: () => pruefen(true) }, t("update.pruefen"))), inhalt);

    async function pruefen(neu = false) {
      leeren(inhalt, h("p.gedimmt", t("allgemein.laedt")));
      let u;
      try {
        u = await api(`update${neu ? "?neu=true" : ""}`);
      } catch (e) {
        return fehlerMelden(e);
      }
      if (u.fehler) return leeren(inhalt, h("p", t("update.version", { version: zustand.version })), h("p.warnung", t("update.keine_verbindung")));
      leeren(
        inhalt,
        h("p", t("update.version", { version: u.aktuell })),
        u.verfuegbar
          ? [
              h("p.gut", h("strong", t("update.verfuegbar", { version: u.neueste }))),
              u.notizen ? h("pre.notizen", u.notizen) : null,
              u.installierbar
                ? h("button.knopf", { type: "button", onclick: () => installieren(u) }, t("update.installieren"))
                : h("p.hinweis", t("update.manuell"), " ", h("a", { href: u.url, target: "_blank", rel: "noopener" }, u.url)),
            ]
          : h("p.gut", t("update.aktuell"))
      );
    }

    async function installieren(u) {
      if (!(await bestaetigen(t("update.wirklich", { version: u.neueste }), t("update.installieren")))) return;
      leeren(inhalt, h("p", t("update.laeuft")), h("progress"));
      try {
        await api("update", { methode: "POST" });
      } catch (e) {
        fehlerMelden(e);
        return pruefen();
      }
      // Warten, bis der Dienst mit der neuen Version antwortet
      const start = Date.now();
      const warten = async () => {
        try {
          const s = await fetch("/api/status").then((r) => r.json());
          if (s.version === u.neueste) return location.reload();
        } catch {}
        if (Date.now() - start < 5 * 60 * 1000) setTimeout(warten, 3000);
        else leeren(inhalt, h("p.warnung", t("update.zeitueberschreitung")));
      };
      setTimeout(warten, 8000);
    }

    pruefen();
    return box;
  }

  // ---------------------------------------------------------------- Active Directory
  function ldapBox() {
    const inhalt = h("div");
    const box = h("section.karte-box", h("div.box-kopf", h("h2", t("ldap.titel"))), h("p.hinweis", t("ldap.hilfe")), inhalt);

    async function zeigen() {
      let e, rollen;
      try {
        [e, rollen] = await Promise.all([api("einstellungen/ldap"), api("rollen")]);
      } catch (err) {
        return fehlerMelden(err);
      }
      const rollenName = (r) => {
        const x = t(`rollen.${r.schluessel}`);
        return x.startsWith("⟨") ? r.name : x;
      };
      const rollenOptionen = rollen.rollen.map((r) => [r.schluessel, rollenName(r)]);
      const el = {
        aktiv: h("input", { type: "checkbox", checked: e.aktiv }),
        server: h("input", { value: e.server, placeholder: "ldaps://dc01.klinik.local" }),
        domaene: h("input", { value: e.domaene, placeholder: "klinik.local" }),
        basis_dn: h("input", { value: e.basis_dn, placeholder: "DC=klinik,DC=local" }),
        standard: h("select", h("option", { value: "" }, t("ldap.kein_zugang")), rollenOptionen.map(([w, x]) => h("option", { value: w, selected: w === e.standard_rolle }, x))),
      };
      const gruppenBox = h("div");
      const gruppeZeile = (g = { gruppe: "", rolle: "betrachter" }) => {
        const zeile = h(
          "div.zeile",
          h("input", { value: g.gruppe, placeholder: t("ldap.gruppe_beispiel"), style: { flex: 2 } }),
          h("select", rollenOptionen.map(([w, x]) => h("option", { value: w, selected: w === g.rolle }, x))),
          h("button.knopf-flach.gefahr", { type: "button", onclick: () => zeile.remove() }, "×")
        );
        gruppenBox.append(zeile);
      };
      e.gruppen.forEach(gruppeZeile);
      const f = (label, eingabe, hilfe) => h("label.feld", h("span", label), eingabe, hilfe ? h("small", hilfe) : null);
      const testName = h("input", { placeholder: t("anmeldung.benutzername"), autocomplete: "off" });
      const testPw = h("input", { type: "password", placeholder: t("anmeldung.passwort"), autocomplete: "new-password" });
      const testErgebnis = h("p.hinweis");
      leeren(
        inhalt,
        h("label.feld.haken", el.aktiv, h("span", t("ldap.aktiv"))),
        f(t("ldap.server"), el.server, t("ldap.server_hilfe")),
        f(t("ldap.domaene"), el.domaene, t("ldap.domaene_hilfe")),
        f(t("ldap.basis_dn"), el.basis_dn),
        h("div.feld", h("span", t("ldap.gruppen")), gruppenBox, h("button.knopf-flach", { type: "button", onclick: () => gruppeZeile() }, "+ " + t("ldap.gruppe_hinzu")), h("small", t("ldap.gruppen_hilfe"))),
        f(t("ldap.standard_rolle"), el.standard),
        h("button.knopf", { type: "button", onclick: speichern }, t("allgemein.speichern")),
        h("h3", t("ldap.testen")),
        h("div.zeile", testName, testPw, h("button.knopf-flach", { type: "button", onclick: testen }, t("ldap.test_knopf"))),
        testErgebnis
      );

      async function speichern() {
        try {
          await api("einstellungen/ldap", {
            methode: "PUT",
            daten: {
              aktiv: el.aktiv.checked,
              server: el.server.value.trim(),
              domaene: el.domaene.value.trim(),
              basis_dn: el.basis_dn.value.trim(),
              standard_rolle: el.standard.value,
              gruppen: [...gruppenBox.querySelectorAll(".zeile")].map((z) => ({ gruppe: z.querySelector("input").value.trim(), rolle: z.querySelector("select").value })).filter((g) => g.gruppe),
            },
          });
          melden(t("allgemein.gespeichert"));
        } catch (err) {
          fehlerMelden(err);
        }
      }

      async function testen() {
        testErgebnis.textContent = t("allgemein.laedt");
        try {
          const r = await api("einstellungen/ldap/test", { methode: "POST", daten: { benutzername: testName.value, passwort: testPw.value } });
          testErgebnis.textContent = t("ldap.test_ok", { name: r.anzeigename, rolle: r.rolle || t("ldap.kein_zugang"), gruppen: r.gruppen.length });
        } catch (err) {
          testErgebnis.textContent = err.message;
        }
      }
    }

    zeigen();
    return box;
  }

  // ---------------------------------------------------------------- HTTPS
  function httpsBox() {
    const inhalt = h("div");
    const box = h("section.karte-box", h("div.box-kopf", h("h2", t("https.titel"))), h("p.hinweis", t("https.hilfe")), inhalt);

    async function zeigen() {
      let e;
      try {
        e = await api("einstellungen/https");
      } catch (err) {
        return fehlerMelden(err);
      }
      const zert = h("input", { value: e.zertifikat, placeholder: "C:\\Zertifikate\\logistik.pem" });
      const schl = h("input", { value: e.schluessel, placeholder: "C:\\Zertifikate\\logistik-key.pem" });
      leeren(
        inhalt,
        h("p", e.aktiv ? h("span.gut", t("https.an")) : h("span.warnung", t("https.aus"))),
        h("label.feld", h("span", t("https.zertifikat")), zert),
        h("label.feld", h("span", t("https.schluessel")), schl, h("small", t("https.datei_hilfe"))),
        h(
          "div.knopfreihe",
          h("button.knopf", { type: "button", onclick: speichern }, t("allgemein.speichern")),
          h("button.knopf-flach", { type: "button", onclick: neustart }, t("https.neustart"))
        )
      );

      async function speichern() {
        try {
          await api("einstellungen/https", { methode: "PUT", daten: { zertifikat: zert.value.trim(), schluessel: schl.value.trim() } });
          melden(t("https.gespeichert"));
        } catch (err) {
          fehlerMelden(err);
        }
      }

      async function neustart() {
        if (!(await bestaetigen(t("https.neustart_frage"), t("https.neustart")))) return;
        try {
          await api("neustart", { methode: "POST" });
          const k = await api("einstellungen/https").catch(() => null);
          const ziel = `${zert.value.trim() ? "https" : "http"}://${location.hostname}:${k?.port || e.port}/`;
          leeren(inhalt, h("p", t("https.neustart_laeuft")), h("p", h("a", { href: ziel }, ziel)));
          setTimeout(() => (location.href = ziel), 12000);
        } catch (err) {
          fehlerMelden(err);
        }
      }
    }

    zeigen();
    return box;
  }

  laden();
  feiertageLaden();
  void zahl;
}
