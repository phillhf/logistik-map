// Hilfe: Anleitung aus static/hilfe/<sprache>.html mit Inhaltsverzeichnis, Suche und Sprungmarken (#/hilfe/<kapitel>)

import { h, leeren, sprache, t } from "./basis.js";

/** Welches Kapitel der „?“-Knopf auf welcher Seite öffnet */
export const KAPITEL_JE_SEITE = {
  start: "erste-schritte",
  gebaeude: "gebaeude",
  karte: "karte",
  stammdaten: "stammdaten",
  lieferungen: "lieferungen",
  "lieferungen/produktion": "produktion",
  auswertung: "auswertung",
  szenarien: "szenarien",
  benutzer: "benutzer",
  einstellungen: "einstellungen",
  protokoll: "einstellungen-protokoll",
};

const cache = new Map(); // sprache → HTML-Text

async function inhaltLaden() {
  for (const code of [sprache, "de"]) {
    if (cache.has(code)) return cache.get(code);
    const r = await fetch(`hilfe/${code}.html`, { cache: "no-cache" });
    if (r.ok) {
      const text = await r.text();
      cache.set(code, text);
      return text;
    }
  }
  throw new Error(t("hilfe.nicht_gefunden"));
}

let letzteSuche = "";

export async function zeigeHilfe(wurzel, rest = []) {
  const ziel = rest[0] || "";
  let html;
  try {
    html = await inhaltLaden();
  } catch (e) {
    leeren(wurzel, h("p.fehlertext", e.message));
    return;
  }
  // Inhalt stammt aus der eigenen Installation (statische Datei), nicht von Benutzern
  const text = h("article.hilfe-text");
  text.innerHTML = html;
  const kapitel = [...text.querySelectorAll("section[id]")];

  const suche = h("input", { type: "search", placeholder: t("hilfe.suchen"), value: letzteSuche, "aria-label": t("hilfe.suchen") });
  const treffer = h("p.hinweis.hilfe-treffer", { hidden: true });
  const verzeichnis = h(
    "nav.hilfe-verzeichnis",
    { "aria-label": t("hilfe.inhalt") },
    h("ol", kapitel.map((k) => {
      const unter = [...k.querySelectorAll("h3[id]")];
      return h(
        "li",
        { "data-kapitel": k.id },
        h("a", { href: `#/hilfe/${k.id}` }, k.querySelector("h2")?.textContent || k.id),
        unter.length ? h("ol", unter.map((u) => h("li", h("a", { href: `#/hilfe/${u.id}` }, u.textContent)))) : null
      );
    }))
  );

  leeren(
    wurzel,
    h(
      "div.hilfe",
      h("aside.hilfe-seite", h("h2", t("hilfe.titel")), suche, treffer, verzeichnis),
      h("div.hilfe-haupt", text)
    )
  );

  // Suche: blendet Kapitel ohne Treffer aus und markiert die Fundstellen
  function filtern() {
    letzteSuche = suche.value;
    const q = suche.value.trim().toLowerCase();
    text.querySelectorAll("mark.hilfe-fund").forEach((m) => m.replaceWith(document.createTextNode(m.textContent)));
    text.normalize();
    let anzahl = 0;
    for (const k of kapitel) {
      const passt = !q || k.textContent.toLowerCase().includes(q);
      k.hidden = !passt;
      verzeichnis.querySelector(`[data-kapitel="${k.id}"]`).hidden = !passt;
      if (passt && q) anzahl += markieren(k, q);
    }
    treffer.hidden = !q;
    treffer.textContent = anzahl ? t("hilfe.treffer", { anzahl }) : t("hilfe.keine_treffer");
  }

  function markieren(el, q) {
    const knoten = [];
    const lauf = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (lauf.nextNode()) if (lauf.currentNode.nodeValue.toLowerCase().includes(q)) knoten.push(lauf.currentNode);
    let n = 0;
    for (const tk of knoten) {
      const wert = tk.nodeValue;
      const klein = wert.toLowerCase();
      const teile = document.createDocumentFragment();
      let pos = 0;
      let i;
      while ((i = klein.indexOf(q, pos)) !== -1) {
        teile.append(wert.slice(pos, i), h("mark.hilfe-fund", wert.slice(i, i + q.length)));
        pos = i + q.length;
        n++;
      }
      teile.append(wert.slice(pos));
      tk.replaceWith(teile);
    }
    return n;
  }

  suche.addEventListener("input", filtern);
  suche.addEventListener("keydown", (e) => {
    if (e.key === "Enter") text.querySelector("mark.hilfe-fund")?.scrollIntoView({ block: "center" });
    if (e.key === "Escape") {
      suche.value = "";
      filtern();
    }
  });
  if (letzteSuche) filtern();

  // Sprungmarke: Ziel anzeigen (auch wenn die Suche es gerade ausblendet)
  const el = ziel && text.querySelector(`[id="${CSS.escape(ziel)}"]`);
  if (el) {
    if (el.closest("section")?.hidden) {
      suche.value = "";
      filtern();
    }
    requestAnimationFrame(() => {
      el.scrollIntoView({ block: "start" });
      el.classList.add("hilfe-ziel");
      setTimeout(() => el.classList.remove("hilfe-ziel"), 2000);
    });
    verzeichnis.querySelectorAll("a").forEach((a) => a.classList.toggle("aktiv", a.getAttribute("href") === `#/hilfe/${ziel}`));
  } else {
    window.scrollTo(0, 0);
  }
}
