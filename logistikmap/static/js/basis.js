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
  constructor(status, detail, roh = "") {
    let d = detail && typeof detail === "object" && detail.code ? detail : { code: "allgemein" };
    // Unbekannte Antwort (z. B. Prüfung der Anfrage, Proxy, Absturz): Code und Text zeigen, damit man es nachverfolgen kann
    if (d.code === "allgemein" && status) {
      const text = (typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((x) => x.msg || "").join("; ") : roh || "")
        .replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 160);
      d = { code: "unbekannt", status, text: text || "–" };
    }
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

// Rückgängig-Gruppe: alle Änderungen innerhalb von gruppe(fn) bilden einen einzigen Rückgängig-Schritt
let aktiveGruppe = null;
export async function gruppe(fn) {
  const vorher = aktiveGruppe;
  aktiveGruppe = vorher || `g${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  try {
    return await fn();
  } finally {
    aktiveGruppe = vorher;
  }
}

export async function api(pfad, { methode = "GET", daten, roh = false } = {}) {
  const optionen = { method: methode, headers: {}, credentials: "same-origin" };
  if (aktiveGruppe && methode !== "GET") optionen.headers["X-Rueckgaengig-Gruppe"] = aktiveGruppe;
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
      else fehler(new ApiFehler(xhr.status, antwort?.detail, xhr.responseText));
    };
    xhr.onerror = () => fehler(new ApiFehler(0, { code: "netzwerk" }));
    const form = new FormData();
    form.append(feld, datei);
    xhr.send(form);
  });
}

/**
 * PDF in Stücken hochladen (je 8 MB). Proxys und Webfilter im Klinik-Netz begrenzen oft die
 * Größe einer einzelnen Anfrage; so bleibt jede Anfrage klein, auch bei Plänen mit Hunderten MB.
 */
export async function pdfHochladen(datei, fortschritt) {
  const { id, stueck } = await api("uploads", { methode: "POST" });
  const anzahl = Math.max(1, Math.ceil(datei.size / stueck));
  for (let nr = 0; nr < anzahl; nr++) {
    const teil = datei.slice(nr * stueck, Math.min(datei.size, (nr + 1) * stueck));
    for (let versuch = 1; ; versuch++) {
      try {
        await stueckSenden(`/api/uploads/${id}?nr=${nr}`, teil, (anteil) => fortschritt((nr * stueck + anteil * teil.size) / datei.size));
        break;
      } catch (e) {
        if (versuch >= 3 || e.status === 409 || e.status === 404) throw e;
        await new Promise((r) => setTimeout(r, 1000 * versuch));
      }
    }
  }
  fortschritt(1);
  return api(`uploads/${id}/fertig`, { methode: "POST", daten: { dateiname: datei.name } });
}

function stueckSenden(url, teil, fortschritt) {
  return new Promise((ok, fehler) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && fortschritt(e.loaded / e.total);
    xhr.onload = () => {
      let antwort = null;
      try {
        antwort = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) ok(antwort);
      else fehler(new ApiFehler(xhr.status, antwort?.detail, xhr.responseText));
    };
    xhr.onerror = () => fehler(new ApiFehler(0, { code: "netzwerk" }));
    xhr.send(teil);
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
    else if (k === "style" && typeof v === "object") {
      for (const [eig, wert] of Object.entries(v)) {
        if (eig.startsWith("--")) el.style.setProperty(eig, wert);
        else el.style[eig] = wert;
      }
    }
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
 * typ: text | number | password | time | date | color | auswahl | haken | mehrfach (Häkchenliste, Wert = Array) | textfeld | ueberschrift
 * speichern(werte) darf einen Fehler werfen – dann bleibt der Dialog offen und zeigt ihn an.
 */
export function formularDialog({ titel, felder, speichernText, speichern, gross = false }) {
  return new Promise((fertig) => {
    const fehlerZeile = h("p.dialog-fehler", { hidden: true });
    const eingaben = {};
    const zeilen = felder.map((f) => {
      let feld;
      if (f.typ === "ueberschrift") return h("h3.dialog-abschnitt", f.label);
      if (f.typ === "element") {
        // eigenes Bedienelement: f.element (DOM) und f.lesen() → Wert
        const el = f.element;
        el.wertLesen = f.lesen;
        eingaben[f.name] = el;
        return h("div.feld", f.label ? h("span", f.label) : null, el, f.hilfe && h("small", f.hilfe));
      }
      if (f.typ === "auswahl") {
        feld = h("select", { name: f.name }, f.optionen.map(([wert, text]) => h("option", { value: wert, selected: String(wert) === String(f.wert) }, text)));
      } else if (f.typ === "mehrfach") {
        const gewaehlt = new Set((f.wert || []).map(String));
        feld = h("div.mehrfach", f.optionen.map(([wert, text]) => h("label.haken", h("input", { type: "checkbox", value: wert, checked: gewaehlt.has(String(wert)) }), h("span", text))));
        feld.wertLesen = () => [...feld.querySelectorAll("input:checked")].map((i) => (isNaN(Number(i.value)) ? i.value : Number(i.value)));
        eingaben[f.name] = feld;
        return h("div.feld", h("span", f.label), feld, f.hilfe && h("small", f.hilfe));
      } else if (f.typ === "textfeld") {
        feld = h("textarea", { name: f.name, rows: 3, ...(f.attr || {}) }, f.wert ?? "");
      } else if (f.typ === "haken") {
        feld = h("input", { type: "checkbox", name: f.name, checked: !!f.wert });
      } else {
        feld = h("input", { type: f.typ || "text", name: f.name, value: f.wert ?? "", required: !!f.pflicht, ...(f.attr || {}) });
      }
      eingaben[f.name] = feld;
      return h(`label.feld${f.typ === "haken" ? ".haken" : ""}`, f.typ === "haken" ? [feld, h("span", f.label)] : [h("span", f.label), feld], f.hilfe && h("small", f.hilfe));
    });
    const dialog = h(gross ? "dialog.dialog.gross" : "dialog.dialog");
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
        werte[name] = el.wertLesen ? el.wertLesen() : el.type === "checkbox" ? el.checked : el.type === "number" ? (el.value === "" ? null : Number(el.value)) : el.value;
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

export function bestaetigen(text, knopf = null) {
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
          h("button.knopf.gefahr", { value: "ja" }, knopf || t("allgemein.loeschen"))
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

/** Auswahl zwischen mehreren Wegen. optionen: [[wert, titel, erklaerung], …] → gewählter Wert oder null. */
export function auswahlDialog(titel, text, optionen) {
  return new Promise((fertig) => {
    const dialog = h("dialog.dialog");
    dialog.append(
      h(
        "form",
        { method: "dialog" },
        h("h2", titel),
        text ? h("p", text) : null,
        h("div.auswahl-optionen", optionen.map(([wert, ueberschrift, erklaerung]) =>
          h("button.auswahl-option", { value: wert }, h("strong", ueberschrift), erklaerung ? h("small", erklaerung) : null))),
        h("div.dialog-knoepfe", h("button.knopf-flach", { value: "" }, t("allgemein.abbrechen")))
      )
    );
    dialog.addEventListener("close", () => {
      dialog.remove();
      fertig(dialog.returnValue || null);
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

// ---------------------------------------------------------------- Zeit
/** Sekunden seit Mitternacht → "08:05" (über Mitternacht hinaus: "+1 00:10") */
export function uhr(sekunden, mitSekunden = false) {
  if (sekunden === null || sekunden === undefined) return "–";
  const tag = Math.floor(sekunden / 86400);
  const s = Math.round(sekunden - tag * 86400);
  const hh = String(Math.floor(s / 3600)).padStart(2, "0");
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  const praefix = tag < 0 ? `${t("zeit.vortag")} ` : tag > 0 ? `+${tag} ` : "";
  return `${praefix}${hh}:${mm}${mitSekunden ? `:${ss}` : ""}`;
}

export function sekunden(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 3600 + m * 60;
}

/** Dauer lesbar: "45 s", "4 min", "1 h 05 min" */
export function dauer(s) {
  s = Math.round(s || 0);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min${s % 60 && s < 600 ? ` ${s % 60} s` : ""}`;
  return `${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")} min`;
}

export function heute() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ---------------------------------------------------------------- Stammdaten-Cache
let stammCache = null;
export async function stammdaten(neu = false) {
  if (!stammCache || neu) stammCache = await api("stammdaten");
  return stammCache;
}
export function stammdatenVergessen() {
  stammCache = null;
}

/** Anzeigename eines Punkts: "Rampe · UG (A)" */
export function punktName(p) {
  if (!p) return "–";
  const ort = [p.stockwerk, p.kuerzel || p.gebaeudeteil].filter(Boolean).join(" · ");
  return `${p.name || t(`knoten.art.${p.art}`)}${p.flaeche && p.flaeche !== p.name ? ` (${p.flaeche})` : ""} – ${ort}`;
}

/** <select> mit Punkten gruppiert nach Gebäudeteil und Stockwerk */
export function punktAuswahl(punkte, wert, { leer = null, filter = () => true } = {}) {
  const gruppen = new Map();
  for (const p of punkte.filter(filter)) {
    const g = `${p.kuerzel ? p.kuerzel + " · " : ""}${p.gebaeudeteil} – ${p.stockwerk}`;
    if (!gruppen.has(g)) gruppen.set(g, []);
    gruppen.get(g).push(p);
  }
  return h(
    "select",
    leer !== null ? h("option", { value: "" }, leer) : null,
    [...gruppen].map(([g, liste]) =>
      h("optgroup", { label: g }, liste.map((p) => h("option", { value: p.id, selected: p.id === wert }, `${p.name || t(`knoten.art.${p.art}`)}${p.flaeche && p.flaeche !== p.name ? ` (${p.flaeche})` : ""}`)))
    )
  );
}

/** Datei herunterladen, die der Server erzeugt (Fehler werden als Meldung angezeigt). */
export async function herunterladen(pfad, dateiname) {
  const r = await api(pfad, { roh: true });
  const blob = await r.blob();
  const name = dateiname || /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") || "")?.[1] || "download";
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    a.remove();
  }, 1000);
}

/** Datei auswählen lassen (Promise mit File oder null) */
export function dateiWaehlen(accept) {
  return new Promise((fertig) => {
    const eingabe = h("input", { type: "file", accept, hidden: true });
    eingabe.addEventListener("change", () => {
      fertig(eingabe.files[0] || null);
      eingabe.remove();
    });
    document.body.append(eingabe);
    eingabe.click();
  });
}

/** Szenarien-Auswahl (Ist-Zustand + Szenarien) */
export async function szenarioAuswahl(wert, onchange, leerText) {
  let liste = [];
  try {
    liste = await api("szenarien");
  } catch {}
  const sel = h(
    "select",
    { onchange: (e) => onchange(e.target.value ? Number(e.target.value) : null), title: t("szenario.auswahl") },
    h("option", { value: "" }, leerText || t("szenario.ist")),
    liste.map((s) => h("option", { value: s.id, selected: s.id === wert }, `${t("szenario.kurz")}: ${s.name}`))
  );
  sel.hidden = !liste.length;
  return sel;
}
