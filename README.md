# Logistik Map

*[Deutsche Fassung](README.de.md)*

Logistik Map shows the flow of goods through large buildings such as hospitals. You upload the
floor plans as PDF, draw corridors, lifts and delivery points, enter the deliveries of the day –
and see where goods go, who is waiting where, and which lift becomes the bottleneck at 8 a.m.

![Timeline on the floor plan](docs/screenshots/ablauf.png)
![Analysis with bottlenecks](docs/screenshots/auswertung.png)

The user interface is available in **German and English** (each user chooses their language).
Holidays are calculated for all German federal states.

## Features

- **Built-in manual** (menu “Help”, or “?” at the top for the page you are on): every page and
  every parameter explained, how the simulation calculates, step-by-step guides and
  troubleshooting, with search.
- **Variation and minimum needed**: calculate a day many times with random arrival and unloading
  times and passenger load in lifts; find the smallest number of gates, vehicles or staff that keeps
  waiting below a limit.
- **Several hospitals** in one installation: switch at the top, each with its own buildings,
  plans, paths, master data, deliveries and analyses; users are shared.
- **Getting started** page that guides you through the setup in the right order, checks by
  itself what is missing (a floor without scale, a point not attached to a path, a delivery
  without a route – and where the network breaks) and jumps straight to the place to fix it.
- **Floor plans from PDF**, also very large CAD exports (A0 and beyond), converted once into a
  zoomable map. Enter the scale (e.g. 1:200; suggested when it is text in the PDF) or click two
  points with a known distance.
- **Deliveries in one line**: “At 08:00, 5 pallets from the gate to B25” – the system finds
  route, lift and transport type. Truck gates at the dock with their number of gates; internal
  transports such as a bed exchange.
- **Map editor**: corridors as a path network, start and destination points (ramps, stores,
  wards), lifts and stairs across floors, connections between building sections, areas and rooms.
  Undo, snapping, re-aligning everything to a new version of the plan.
- **Master data**: transport types (e.g. automated guided vehicles that reserve a lift, or staff
  pushing trolleys) with speed, loading times, fleet size and **shifts**; trolley types with the
  space they need in a lift; lifts with capacity and travel, door and waiting times.
- **Deliveries** with time, load, “arrive by”, recurrence rules (weekdays, public holidays,
  periods, exceptions) and return trips (empty, loaded, later, none). Import and export via Excel.
- **Simulation** of a day: vehicles, lift cars and bottlenecks with limited capacity, waiting
  times and late arrivals – including trips that run past midnight.
- **Timeline** on the map, **analysis** per day or as a weekly heat map, export to Excel and PDF.
- **Scenarios** (“what if the linen arrives at 7:30?”, “what if the west lift is out of
  service?”) compared with the current state.
- **Operations**: Windows installer with service, daily backups, one-click updates from GitHub
  releases, HTTPS, sign-in via Active Directory, roles and permissions, audit log.

How the simulation works is described in [KONZEPT.md](KONZEPT.md) (German).

## Installation (Windows server)

1. Download `LogistikMap-Setup-x.y.z.exe` from the [releases](https://github.com/phillhf/logistik-map/releases) and run it as administrator.
2. Choose the port (default 8470) and optionally open it in the Windows firewall.
3. The browser opens afterwards – create the administrator account there.

Logistik Map then runs as the Windows service **LogistikMap** and is available on the network at
`http://<server>:<port>`. Data lives in `C:\ProgramData\Logistik Map` and is kept on updates and
uninstall.

Useful command-line tools (`C:\Program Files\Logistik Map\LogistikMap.exe …`):

| Command | Purpose |
|---|---|
| `plan-test plan.pdf` | Check a PDF plan: size, zoom levels, estimated preparation time |
| `sicherung [target.zip]` | Create a backup |
| `wiederherstellen backup.zip` | Restore a backup (stop the service first) |
| `passwort admin` | Reset a password |
| `config --port 8470 --zertifikat cert.pem --schluessel key.pem` | Port and HTTPS |

## Development

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m logistikmap --data data serve --port 8470
```

Browser tests (Playwright): `pip install -r requirements-e2e.txt`, then run `pytest tests/e2e`
with the environment variable `E2E=1`.

The code is written in German (identifiers, comments). Texts of the user interface are in
`logistikmap/static/i18n/<language>.json` – to add a language, copy `en.json`, translate it and
register it in `SPRACHEN` in `logistikmap/server.py`.

Releases are built by GitHub Actions when a tag `vX.Y.Z` is pushed (`installer/build.ps1`,
Inno Setup, WinSW).

## License

[GNU Affero General Public License v3.0](LICENSE). Licenses of all bundled components (among them
PyMuPDF under AGPL-3.0, ldap3 under LGPL-3.0, Leaflet, WinSW) are installed as
`THIRD_PARTY_LICENSES.txt` in the program folder.
