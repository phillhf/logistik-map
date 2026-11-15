// Gemeinsame Helfer: Übersetzung, Server-Anfragen, DOM-Aufbau, Dialoge, Meldungen.

// ---------------------------------------------------------------- Übersetzung
let texte = {};
export let sprache = "de";

export async function spracheLaden(code) {
  const r = await fetch(`i18n/${code}.json`, { cache: "no-cache" });
  if (!r.ok && code !== "de") return spracheLaden("de");
  texte = await r.json();
  sprache = code;
  document.documentElement.lang = code;
}

/** t("karte.plan_wird_erstellt", {prozent: 12}) – fehlende Schlüssel werden sichtbar angezeigt. */
export function t(schluessel, werte = {}) {
  let v = schluessel.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), texte);
  if (v === undefined) return `⟨${schluessel}⟩`;
  if (typeof v !== "string") return v;
  return v.replace(/\{(\w+)\}/g, (_, k) => (werte[k] ?? `{${k}}`));
}

/** Setzt Texte für alle Elemente mit data-i18n unterhalb von wurzel. */
export function uebersetzen(wurzel = document) {
  wurzel.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
}

export function zahl(wert, stellen = 1) {
  return new Intl.NumberFormat(sprache, { maximumFractionDigits: stellen }).format(wert);
}

export function datumText(iso) {
  const d = new Date(iso + "T00:00:00");
  return `${t("wochentag")[d.getDay()]}, ${d.toLocaleDateString(sprache)}`;
}

export function groesse(bytes) {
  if (bytes < 1024 * 1024) return `${zahl(bytes / 1024, 0)} KB`;
  return `${zahl(bytes / 1024 / 1024, 1)} MB`;
}

// ---------------------------------------------------------------- Server
export class ApiFehler extends Error {
  constructor(status, detail) {
    const d = detail && typeof detail === "object" && detail.code ? detail : { code: "allgemein" };
    super(fehlerText(d));
    this.status = status;
    this.code = d.code;
    this.detail = d;
  }
}

export function fehlerText(detail) {
  const text = t(`fehler.${detail.code}`, detail);
  return text.startsWith("⟨") ? t("fehler.allgemein") : text;
}

let beiAbmeldung = () => {};
export function wennAbgemeldet(fn) {
  beiAbmeldung = fn;
}

export async function api(pfad, { methode = "GET", daten, roh = false } = {}) {
  const optionen = { method: methode, headers: {}, credentials: "same-origin" };
  if (daten !== undefined) {
    optionen.headers["Content-Type"] = "application/json";
    optionen.body = JSON.stringify(daten);
  }
  let r;
  try {
    r = await fetch(`/api/${pfad}`, optionen);
  } catch {
    throw new ApiFehler(0, { code: "netzwerk" });
  }
  if (!r.ok) {
    let detail = null;
    try {
      detail = (await r.json()).detail;
    } catch {}
    if (r.status === 401 && pfad !== "anmelden") beiAbmeldung();
    if (r.status === 422) detail = { code: "allgemein" };
    throw new ApiFehler(r.status, detail);
  }
  return roh ? r : r.json();
}

/** Datei mit Fortschritt hochladen (fetch kann keinen Upload-Fortschritt). */
export function hochladen(pfad, feld, datei, fortschritt) {
  return new Promise((ok, fehler) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/${pfad}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && fortschritt(e.loaded / e.total);
    xhr.onload = () => {
      let antwort = null;
      try {
        antwort = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) ok(antwort);
      else fehler(new ApiFehler(xhr.status, antwort?.detail));
    };
    xhr.onerror = () => fehler(new ApiFehler(0, { code: "netzwerk" }));
    const form = new FormData();
    form.append(feld, datei);
    xhr.send(form);
  });
}

// ---------------------------------------------------------------- DOM
/**
 * h("button.knopf", {onclick: fn, type: "button"}, "Text", kindElement)
 * Texte werden immer als Text eingefügt, nie als HTML.
 */
export function h(tag, attribute = {}, ...kinder) {
  const [name, ...klassen] = tag.split(".");
  const el = document.createElement(name || "div");
  if (klassen.length) el.className = klassen.join(" ");
  if (attribute === null || typeof attribute !== "object" || attribute instanceof Node || Array.isArray(attribute)) {
    kinder.unshift(attribute);
    attribute = {};
  }
  for (const [k, v] of Object.entries(attribute)) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className += (el.className ? " " : "") + v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kind of kinder.flat(Infinity)) {
    if (kind === null || kind === undefined || kind === false) continue;
    el.append(kind instanceof Node ? kind : String(kind));
  }
  return el;
}

export function leeren(el, ...kinder) {
  el.replaceChildren(...kinder.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
  return el;
}

// ---------------------------------------------------------------- Meldungen
export function melden(text, art = "ok") {
  const el = h(`div.meldung.${art}`, { role: art === "fehler" ? "alert" : "status" }, text);
  document.getElementById("meldungen").append(el);
  setTimeout(() => el.classList.add("weg"), art === "fehler" ? 6000 : 3000);
  setTimeout(() => el.remove(), art === "fehler" ? 6500 : 3500);
}

export function fehlerMelden(e) {
  console.error(e);
  melden(e instanceof ApiFehler ? e.message : t("fehler.allgemein"), "fehler");
}

// ---------------------------------------------------------------- Dialoge
/**
 * Formular-Dialog. felder: [{name, label, typ, wert, optionen, pflicht, hilfe, attr}]
 * speichern(werte) darf einen Fehler werfen – dann bleibt der Dialog offen und zeigt ihn an.
 */
export function formularDialog({ titel, felder, speichernText, speichern }) {
  return new Promise((fertig) => {
    const fehlerZeile = h("p.dialog-fehler", { hidden: true });
    const eingaben = {};
    const zeilen = felder.map((f) => {
      let feld;
      if (f.typ === "auswahl") {
        feld = h("select", { name: f.name }, f.optionen.map(([wert, text]) => h("option", { value: wert, selected: String(wert) === String(f.wert) }, text)));
      } else if (f.typ === "haken") {
        feld = h("input", { type: "checkbox", name: f.name, checked: !!f.wert });
      } else {
        feld = h("input", { type: f.typ || "text", name: f.name, value: f.wert ?? "", required: !!f.pflicht, ...(f.attr || {}) });
      }
      eingaben[f.name] = feld;
      return h(`label.feld${f.typ === "haken" ? ".haken" : ""}`, f.typ === "haken" ? [feld, h("span", f.label)] : [h("span", f.label), feld], f.hilfe && h("small", f.hilfe));
    });
    const dialog = h("dialog.dialog");
    const form = h(
      "form",
      { method: "dialog" },
      h("h2", titel),
      zeilen,
      fehlerZeile,
      h(
        "div.dialog-knoepfe",
        h("button.knopf-flach", { type: "button", onclick: () => dialog.close() }, t("allgemein.abbrechen")),
        h("button.knopf", { type: "submit" }, speichernText || t("allgemein.speichern"))
      )
    );
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const werte = {};
      for (const [name, el] of Object.entries(eingaben)) {
        werte[name] = el.type === "checkbox" ? el.checked : el.type === "number" ? (el.value === "" ? null : Number(el.value)) : el.value;
      }
      try {
        const ergebnis = await speichern(werte);
        dialog.close();
        fertig(ergebnis ?? werte);
      } catch (err) {
        fehlerZeile.textContent = err instanceof ApiFehler ? err.message : err.message || t("fehler.allgemein");
        fehlerZeile.hidden = false;
      }
    });
    dialog.append(form);
    dialog.addEventListener("close", () => {
      dialog.remove();
      fertig(null);
    });
    document.body.append(dialog);
    dialog.showModal();
    form.querySelector("input, select")?.focus();
  });
}

export function bestaetigen(text) {
  return new Promise((fertig) => {
    const dialog = h("dialog.dialog");
    dialog.append(
      h(
        "form",
        { method: "dialog" },
        h("p", text),
        h(
          "div.dialog-knoepfe",
          h("button.knopf-flach", { value: "nein" }, t("allgemein.abbrechen")),
          h("button.knopf.gefahr", { value: "ja" }, t("allgemein.loeschen"))
        )
      )
    );
    dialog.addEventListener("close", () => {
      dialog.remove();
      fertig(dialog.returnValue === "ja");
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

// ---------------------------------------------------------------- Angemeldeter Benutzer
export const zustand = { benutzer: null, version: "" };

export function darf(recht) {
  return !!zustand.benutzer?.rechte.includes(recht);
}
