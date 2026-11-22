// Einstieg: Anmeldung, Navigation und Seitenwechsel (Hash-Routing: #/karte/3, #/gebaeude …)

import { standortKopf } from "./standorte.js";
import { api, darf, formularDialog, h, leeren, melden, spracheLaden, t, uebersetzen, wennAbgemeldet, zustand } from "./basis.js";
import { zeigeBenutzer } from "./benutzer.js";
import { zeigeEinstellungen } from "./einstellungen.js";
import { zeigeGebaeude } from "./gebaeude.js";
import { KAPITEL_JE_SEITE, zeigeHilfe } from "./hilfe.js";
import { zeigeAuswertung } from "./auswertung.js";
import { zeigeKarte } from "./karte.js";
import { zeigeLieferungen } from "./lieferungen.js";
import { zeigeProtokoll } from "./protokoll.js";
import { zeigeStammdaten } from "./stammdaten.js";
import { zeigeSzenarien } from "./szenarien.js";
import { offeneSchritte, zeigeStart } from "./start.js";

const inhalt = document.getElementById("inhalt");
// Reihenfolge = Arbeitsreihenfolge beim Einrichten
const SEITEN = [
  { pfad: "start", recht: "bearbeiten", zeigen: (w, r) => zeigeStart(w, r, markeSetzen) },
  { pfad: "gebaeude", recht: "bearbeiten", zeigen: zeigeGebaeude },
  { pfad: "karte", recht: "ansehen", zeigen: zeigeKarte },
  { pfad: "stammdaten", recht: "ansehen", zeigen: zeigeStammdaten },
  { pfad: "lieferungen", recht: "ansehen", zeigen: zeigeLieferungen },
  { pfad: "auswertung", recht: "ansehen", zeigen: zeigeAuswertung },
  { pfad: "szenarien", recht: "ansehen", zeigen: zeigeSzenarien },
  { pfad: "benutzer", recht: "verwalten", zeigen: zeigeBenutzer },
  { pfad: "einstellungen", recht: "ansehen", zeigen: zeigeEinstellungen },
  { pfad: "hilfe", recht: "ansehen", zeigen: zeigeHilfe },
  { pfad: "protokoll", recht: "verwalten", zeigen: zeigeProtokoll, versteckt: true },
];

let aufraeumen = null; // Rückgabe der aktuellen Seite, wird beim Wechsel aufgerufen
let letzteSeite = null;
let startSeite = "karte"; // solange die Einrichtung nicht fertig ist: „Erste Schritte“

async function start() {
  let status;
  try {
    status = await api("status");
  } catch (e) {
    await spracheLaden("de");
    leeren(inhalt, h("div.mitte", h("p.fehlertext", e.message)));
    return;
  }
  await spracheLaden(status.sprache || "de");
  uebersetzen();
  zustand.version = status.version;
  zustand.benutzer = status.benutzer;
  if (status.ersteinrichtung) return zeigeErsteinrichtung();
  if (!status.benutzer) return zeigeAnmeldung();
  kopfAufbauen();
  if (darf("bearbeiten")) {
    try {
      const e = await offeneSchritte();
      markeSetzen(e);
      if (!e.fertig) startSeite = "start";
    } catch {}
  }
  updateHinweis();
  // Nach einem Update die neue Oberfläche laden, statt mit dem alten Stand weiterzuarbeiten
  setInterval(versionPruefen, 60000);
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && versionPruefen());
  window.addEventListener("hashchange", () => {
    versionPruefen();
    seiteWechseln();
    // Marke im Menü aktuell halten (die Seite „Erste Schritte“ setzt sie selbst)
    if (darf("bearbeiten") && !location.hash.startsWith("#/start")) offeneSchritte().then(markeSetzen).catch(() => {});
  });
  seiteWechseln();
}

let letztePruefung = 0;
async function versionPruefen() {
  if (Date.now() - letztePruefung < 5000) return;
  letztePruefung = Date.now();
  try {
    const r = await fetch("api/status", { cache: "no-store" });
    const { version } = await r.json();
    if (version && zustand.version && version !== zustand.version) location.reload();
  } catch {
    /* Server startet gerade neu – beim nächsten Mal */
  }
}

function seiteWechseln() {
  const [pfad, ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  const seite = SEITEN.find((s) => s.pfad === pfad && darf(s.recht));
  if (!seite) {
    location.replace(`#/${startSeite}`);
    return;
  }
  if (aufraeumen) aufraeumen();
  aufraeumen = null;
  document.querySelectorAll("#navigation a").forEach((a) => a.classList.toggle("aktiv", a.dataset.pfad === seite.pfad));
  leeren(inhalt);
  if (seite.pfad !== letzteSeite) window.scrollTo(0, 0);
  letzteSeite = seite.pfad;
  inhalt.className = `seite-${seite.pfad}`;
  Promise.resolve(seite.zeigen(inhalt, rest)).then((r) => (aufraeumen = typeof r === "function" ? r : null));
}

/** Zahl offener Einrichtungsschritte neben „Erste Schritte“ im Menü */
function markeSetzen(e) {
  const a = document.querySelector('#navigation a[data-pfad="start"]');
  if (!a || !e) return;
  const offen = e.gesamt !== undefined ? e.gesamt - e.erledigt : e.offen;
  let marke = a.querySelector(".nav-marke");
  if (!marke) a.append((marke = h("span.nav-marke")));
  marke.textContent = offen || "";
  marke.hidden = !offen;
}

function kopfAufbauen() {
  const kopf = document.getElementById("kopf");
  kopf.hidden = false;
  leeren(
    document.getElementById("navigation"),
    SEITEN.filter((s) => darf(s.recht) && !s.versteckt).map((s) => h("a", { href: `#/${s.pfad}`, "data-pfad": s.pfad }, t(`nav.${s.pfad}`)))
  );
  standortKopf(kopf);
  // Handy: Menü hinter „☰“, klappt unter dem Kopf auf
  if (!document.getElementById("menue-knopf")) {
    const menue = h("button.knopf-flach", { id: "menue-knopf", type: "button", "aria-label": t("menue.navigation"), "aria-expanded": "false" }, h("span", "☰"), h("span.nav-marke", { hidden: true }));
    menue.addEventListener("click", (e) => {
      e.stopPropagation();
      menueOeffnen(!kopf.classList.contains("menue-offen"));
    });
    kopf.prepend(menue);
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#navigation")) menueOeffnen(false);
    });
    window.addEventListener("hashchange", () => menueOeffnen(false));
  }
  // „?“: Hilfe genau zu der Seite, auf der man gerade ist
  if (!document.getElementById("hilfe-knopf")) {
    const hilfe = h("a", { id: "hilfe-knopf", href: "#/hilfe", title: t("hilfe.zu_dieser_seite"), "aria-label": t("hilfe.zu_dieser_seite") }, "?");
    hilfe.addEventListener("click", (e) => {
      const [pfad, unter] = location.hash.replace(/^#\/?/, "").split("/");
      if (pfad === "hilfe") return;
      e.preventDefault();
      location.hash = `#/hilfe/${KAPITEL_JE_SEITE[`${pfad}/${unter}`] || KAPITEL_JE_SEITE[pfad] || ""}`;
    });
    kopf.querySelector(".benutzermenue").before(hilfe);
  }
  const knopf = document.getElementById("benutzer-knopf");
  const liste = document.getElementById("benutzer-liste");
  knopf.textContent = zustand.benutzer.anzeigename;
  const rolle = t(`rollen.${zustand.benutzer.rolle}`);
  knopf.title = `${zustand.benutzer.benutzername} · ${rolle.startsWith("⟨") ? zustand.benutzer.rollenname : rolle} · v${zustand.version}`;
  // Sprachauswahl im Menü
  if (!liste.querySelector("[data-aktion='sprache']")) {
    liste.prepend(h("button", { type: "button", "data-aktion": "sprache" }, `🌐 ${t("menue.sprache")}`));
  }
  knopf.onclick = (e) => {
    e.stopPropagation();
    liste.hidden = !liste.hidden;
  };
  document.addEventListener("click", () => (liste.hidden = true));
  liste.onclick = async (e) => {
    const aktion = e.target.dataset.aktion;
    if (aktion === "abmelden") {
      await api("abmelden", { methode: "POST" });
      location.hash = "";
      location.reload();
    } else if (aktion === "passwort") {
      passwortAendern();
    } else if (aktion === "sprache") {
      spracheWaehlen();
    }
  };
}

function menueOeffnen(offen) {
  const kopf = document.getElementById("kopf");
  kopf.classList.toggle("menue-offen", offen);
  document.getElementById("menue-knopf")?.setAttribute("aria-expanded", String(offen));
}

/** Administratoren: Hinweis im Menü, wenn eine neue Version bereitsteht (Server fragt höchstens alle 10 Min. bei GitHub) */
async function updateHinweis() {
  if (!darf("verwalten")) return;
  let u;
  try {
    u = await api("update");
  } catch {
    return;
  }
  const nav = document.getElementById("navigation");
  nav.querySelector(".nav-update")?.remove();
  if (!u.verfuegbar) return;
  nav.append(h("a.nav-update", { href: "#/einstellungen/update", "data-pfad": "update" }, "⬆ " + t("update.nav", { version: u.neueste })));
  const marke = document.querySelector("#menue-knopf .nav-marke");
  if (marke) {
    marke.textContent = "1";
    marke.hidden = false;
  }
}

async function spracheWaehlen() {
  const status = await api("status");
  const ok = await formularDialog({
    titel: t("menue.sprache"),
    felder: [{ name: "sprache", label: t("menue.sprache"), typ: "auswahl", wert: status.sprache, optionen: Object.entries(status.sprachen) }],
    speichern: (w) => api("ich", { methode: "PUT", daten: { sprache: w.sprache } }),
  });
  if (ok) location.reload();
}

async function passwortAendern() {
  const ok = await formularDialog({
    titel: t("passwort.titel"),
    felder: [
      { name: "altes_passwort", label: t("passwort.alt"), typ: "password", pflicht: true, attr: { autocomplete: "current-password" } },
      { name: "neues_passwort", label: t("passwort.neu"), typ: "password", pflicht: true, attr: { autocomplete: "new-password", minlength: 8 } },
    ],
    speichern: (w) => api("ich/passwort", { methode: "POST", daten: w }),
  });
  if (ok) melden(t("passwort.geaendert"));
}

// ---------------------------------------------------------------- Anmeldung & Ersteinrichtung
function anmeldeKarte(titel, text, felder, knopfText, absenden) {
  const fehler = h("p.dialog-fehler", { hidden: true });
  const form = h(
    "form.anmeldekarte",
    h("img", { src: "favicon.svg", alt: "", width: 48, height: 48 }),
    h("h1", titel),
    text && h("p", text),
    felder.map(([name, label, typ, auto]) => h("label.feld", h("span", label), h("input", { name, type: typ, required: true, autocomplete: auto }))),
    fehler,
    h("button.knopf.breit", { type: "submit" }, knopfText)
  );
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const werte = Object.fromEntries(new FormData(form));
    try {
      await absenden(werte);
      location.reload();
    } catch (err) {
      fehler.textContent = err.message;
      fehler.hidden = false;
    }
  });
  leeren(inhalt, h("div.mitte", form));
  form.querySelector("input").focus();
}

function zeigeAnmeldung() {
  wennAbgemeldet(() => {});
  anmeldeKarte(
    t("anmeldung.titel"),
    null,
    [
      ["benutzername", t("anmeldung.benutzername"), "text", "username"],
      ["passwort", t("anmeldung.passwort"), "password", "current-password"],
    ],
    t("anmeldung.anmelden"),
    (w) => api("anmelden", { methode: "POST", daten: w })
  );
}

function zeigeErsteinrichtung() {
  anmeldeKarte(
    t("ersteinrichtung.titel"),
    t("ersteinrichtung.text"),
    [
      ["benutzername", t("anmeldung.benutzername"), "text", "username"],
      ["anzeigename", t("ersteinrichtung.anzeigename"), "text", "name"],
      ["passwort", t("anmeldung.passwort"), "password", "new-password"],
      ["passwort2", t("ersteinrichtung.passwort_wiederholen"), "password", "new-password"],
    ],
    t("ersteinrichtung.anlegen"),
    (w) => {
      if (w.passwort !== w.passwort2) throw new Error(t("ersteinrichtung.ungleich"));
      return api("ersteinrichtung", { methode: "POST", daten: { benutzername: w.benutzername, anzeigename: w.anzeigename, passwort: w.passwort } });
    }
  );
}

// Sitzung abgelaufen → neu laden zeigt die Anmeldung
wennAbgemeldet(() => location.reload());
start();
