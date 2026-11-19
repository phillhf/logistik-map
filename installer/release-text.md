
<!-- ende-der-neuerungen -->

---

## Über Logistik Map

Logistik Map macht Warenflüsse und Transportwege im Krankenhaus sichtbar: Gebäudepläne als PDF,
Strecken, Aufzüge und Lieferungen einzeichnen, den Tag durchrechnen und sehen, wo es eng wird.
Mehr dazu und Screenshots im [README](https://github.com/phillhf/logistik-map#readme).

## Installation

1. **`LogistikMap-Setup-{VERSION}.exe`** unten unter *Assets* herunterladen.
2. Als Administrator ausführen, Port wählen (Standard 8470).
3. Im Browser das Administrator-Konto anlegen – die Seite *Erste Schritte* führt durch die Einrichtung.

Ein Update einer bestehenden Installation geht unter *Einstellungen → Updates* auf Knopfdruck
oder durch Ausführen dieses Setups. Daten und Einstellungen bleiben erhalten.

**Prüfsumme kontrollieren** (PowerShell, beide Werte müssen gleich sein):

```powershell
(Get-FileHash .\LogistikMap-Setup-{VERSION}.exe -Algorithm SHA256).Hash
Get-Content .\LogistikMap-Setup-{VERSION}.exe.sha256
```

## Technische Eckdaten

| | |
|---|---|
| System | Windows Server 2016+ bzw. Windows 10/11, 64 Bit – keine weiteren Laufzeitumgebungen |
| Betrieb | Windows-Dienst `LogistikMap`, Zugriff per Browser über einen TCP-Port (HTTP oder HTTPS) |
| Daten | lokal in `C:\ProgramData\Logistik Map`, keine Patientendaten, keine Telemetrie |
| Internet | nicht nötig – nur die optionale Update-Prüfung fragt bei github.com nach |
| Unbeaufsichtigt | `LogistikMap-Setup-{VERSION}.exe /VERYSILENT /PORT=8470 /TASKS="firewall"` |
| Herkunft | von GitHub Actions aus dem Tag `v{VERSION}` gebaut, alle Tests vor dem Bau |

Netzwerk, Anmeldung, Datenschutz, Dienstkonto, Sicherung, Protokolle:
**[Weiterführende Informationen](https://github.com/phillhf/logistik-map/blob/main/docs/TECHNIK.md)**

<sub>English: Download `LogistikMap-Setup-{VERSION}.exe`, run it as administrator and open the
browser. See the [English README](https://github.com/phillhf/logistik-map/blob/main/README.en.md).</sub>
