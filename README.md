# Wander Desktop 🌍

Put your iPhone anywhere on Earth — from your Mac or PC. Wander Desktop is the
computer companion to the [Wander](https://wanderspoofer.com) iOS app: plug in
your iPhone (or connect over Wi-Fi) and teleport, joystick-walk, or drive a full
route from a clean map interface. Same idea as iAnyGo / iGo, but cleaner and far
cheaper.

- **No jailbreak.** Works on a normal iPhone.
- **Teleport** anywhere with a click.
- **Joystick walk mode** and **route/drive mode** with realistic speed *(coming in the desktop build)*.
- **Cross-platform** — macOS and Windows.

> Wander Desktop is a fork of [GeoPort](https://github.com/davesc63/GeoPort)
> (AGPL-3.0). Huge credit to the GeoPort project for the underlying
> `pymobiledevice3` device tunnel + location engine. This fork is likewise
> AGPL-3.0 — see [LICENSE](LICENSE).

## Requirements
- **macOS** or **Windows**
- **Python 3.11–3.12** recommended (3.14 may work; pin to 3.12 if you hit issues)
- Your iPhone with **Developer Mode** enabled (Settings → Privacy & Security → Developer Mode)
- Admin rights (the device tunnel needs `sudo` on macOS / UAC on Windows)

## Run it (from source)
```bash
cd wander-desktop
./run.sh          # first run creates a venv, installs deps, and launches
```
`run.sh` re-launches itself with `sudo` on macOS because the developer-service
tunnel requires root (same as Xcode). A browser tab opens with the map UI.

Manual alternative:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo ./.venv/bin/python src/main.py
```

## How it works
A local **Flask** server hosts a **Leaflet** map (`src/templates/map.html`) and
talks to the iPhone through **pymobiledevice3**: it starts a QUIC/TCP tunnel,
mounts the Developer Disk Image, and sets location via the DVT
`LocationSimulation` instrument. Teleporting is a `POST /set_location {lat,lng}`;
walk and route modes drive that same call on a timer.

## Status
Early fork. Rebranded, de-cluttered (removed GeoPort's Australia "fuel prices"
mode), teleport working. Joystick + route modes, license unlock, and a packaged
one-click `.app` / `.exe` are on the roadmap — see
[WANDER-DESKTOP-PLAN.md](WANDER-DESKTOP-PLAN.md).

## Links
- Website: https://wanderspoofer.com
- iOS app + full setup guide: https://wanderspoofer.com
