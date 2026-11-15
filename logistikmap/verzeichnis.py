"""Anmeldung über Active Directory / LDAP.

Einstellung "ldap" (JSON):
  aktiv           true/false
  server          z. B. "ldaps://dc01.klinik.local" (mehrere durch Komma)
  domaene         UPN-Suffix, z. B. "klinik.local" → Anmeldung als benutzer@klinik.local
  basis_dn        z. B. "DC=klinik,DC=local" (für die Suche nach Gruppen und Namen)
  gruppen         [{"gruppe": "CN=Logistik-Admins,OU=…" oder "Logistik-Admins", "rolle": "admin"}, …]
                  Die erste passende Zeile gewinnt.
  standard_rolle  Rolle für angemeldete Benutzer ohne passende Gruppe, "" = kein Zugang

Lokale Benutzer (quelle "lokal") melden sich weiter mit ihrem Passwort an. Benutzer aus dem
Verzeichnis werden bei der ersten Anmeldung angelegt (quelle "ldap"). Ihre Rolle wird bei jeder
Anmeldung aus den Gruppen neu bestimmt.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

STANDARD = {"aktiv": False, "server": "", "domaene": "", "basis_dn": "", "gruppen": [], "standard_rolle": ""}


class VerzeichnisFehler(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def einstellungen(db) -> dict:
    e = dict(STANDARD)
    e.update(db.einstellung("ldap", {}) or {})
    return e


def _escape(wert: str) -> str:
    return re.sub(r"([\\*()\x00])", lambda m: "\\%02x" % ord(m.group(1)), wert)


def _cn(dn: str) -> str:
    m = re.match(r"\s*CN=([^,]+)", dn, re.IGNORECASE)
    return m.group(1) if m else dn


def anmelden(e: dict, benutzer: str, passwort: str, verbindung=None) -> dict:
    """Prüft Benutzer und Passwort am Verzeichnis. Gibt {anzeigename, gruppen} zurück.

    verbindung(server, user, passwort) → ldap3.Connection (für Tests austauschbar).
    """
    if not passwort or not benutzer:
        raise VerzeichnisFehler("anmeldung_falsch")
    if not re.match(r"^[A-Za-z0-9._-]{1,64}$", benutzer):
        raise VerzeichnisFehler("anmeldung_falsch")
    upn = f"{benutzer}@{e['domaene']}" if e.get("domaene") else benutzer
    if verbindung is None:
        verbindung = _ldap3_verbindung
    try:
        con = verbindung(e["server"], upn, passwort)
    except VerzeichnisFehler:
        raise
    except Exception as ex:
        log.warning("LDAP nicht erreichbar: %s", ex)
        raise VerzeichnisFehler("verzeichnis_nicht_erreichbar") from ex
    try:
        anzeigename, gruppen = benutzer, []
        if e.get("basis_dn"):
            con.search(e["basis_dn"], f"(|(sAMAccountName={_escape(benutzer)})(userPrincipalName={_escape(upn)}))",
                       attributes=["displayName", "memberOf"])
            if con.entries:
                eintrag = con.entries[0]
                if "displayName" in eintrag and eintrag.displayName.value:
                    anzeigename = str(eintrag.displayName.value)
                if "memberOf" in eintrag and eintrag.memberOf.values:
                    gruppen = [str(g) for g in eintrag.memberOf.values]
        return {"anzeigename": anzeigename, "gruppen": gruppen}
    finally:
        try:
            con.unbind()
        except Exception:
            pass


def _ldap3_verbindung(server: str, upn: str, passwort: str):
    import ldap3

    pool = ldap3.ServerPool([ldap3.Server(s.strip(), get_info=ldap3.NONE, connect_timeout=5) for s in server.split(",") if s.strip()],
                            ldap3.FIRST, active=1, exhaust=True)
    con = ldap3.Connection(pool, user=upn, password=passwort, authentication=ldap3.SIMPLE, receive_timeout=10)
    if not con.bind():
        raise VerzeichnisFehler("anmeldung_falsch")
    return con


def rolle_fuer(e: dict, gruppen: list[str]) -> str | None:
    namen = {g.lower() for g in gruppen} | {_cn(g).lower() for g in gruppen}
    for zeile in e.get("gruppen", []):
        g = (zeile.get("gruppe") or "").strip().lower()
        if g and (g in namen or _cn(g).lower() in namen):
            return zeile.get("rolle")
    return e.get("standard_rolle") or None
