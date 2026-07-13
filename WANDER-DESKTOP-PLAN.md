# Wander Desktop — build plan

A Mac/Windows companion to the iOS Wander app: plug in your iPhone (or connect
over Wi-Fi), and teleport / walk / drive its location from your computer — the
same category as iAnyGo/iGo, but cleaner and cheaper.

## What we forked
GeoPort (davesc63, AGPL) — a Python + Flask app that renders a Leaflet map in
the browser and drives the iPhone via **pymobiledevice3** (tunnel → DDI mount →
DVT `LocationSimulation`). Solid, current device plumbing. **But it is
teleport-only** plus an Australia "fuel prices" gimmick. It has **no joystick and
no route/drive mode** — exactly the two features that make Wander better.

## Architecture (inherited, keep)
- `src/main.py` — Flask server + all pymobiledevice3 device logic (connect,
  enable Developer Mode, mount DDI, set/stop location, tunnel mgmt).
- `src/templates/map.html` (+ `map2.html`) — the Leaflet map UI, served locally
  and opened in the default browser.
- Location is set by POST `/set_location {lat, lng}` → `LocationSimulation.set(...)`.
  Joystick and route modes are just **this same call, fired repeatedly** with
  interpolated coordinates on a timer. That's the key insight — the hard part
  (device tunnel) is already done; we're adding movement on top.

## Phases

### Phase 0 — Fork & scaffold  ✅ DONE
- Copied GeoPort → `~/Developer/wander-desktop`.
- Mechanical rebrand: GeoPort→Wander everywhere (0 refs left), update-check repo
  → `faisal-nabulsi/wander-desktop`, logger → "Wander". Compiles clean.
- Added `requirements.txt` + `run.sh` (venv bootstrap + sudo for the tunnel).

### Phase 1 — De-GeoPort the product (branding + strip cruft)  ✅ DONE
- ✅ **Stripped Fuel mode** entirely: main.py (2 routes + `fetch_api_data` +
  preload + `api_url`/`api_data` globals + version type) → fuel=0, compiles OK;
  map.html (toggle + region/type panel + 3 JS fns + the `appVersionType`
  hide-block that would've null-crashed) → fuel=0, 114 lines removed, forms/
  scripts balanced, core UI (map/connect/set_location/coordinates) intact.
- ✅ Rewrote README (Wander-branded, keeps AGPL attribution to GeoPort);
  cleaned FAQ (dropped buymeacoffee/survey/discord/davesc63 personal links).
- TODO later: Wander brand blue #185FA5, logo/icon, window title (cosmetic;
  fold into Phase 2 UI rework).

### Phase 2 — Feature parity with iOS Wander (the differentiators)
- **Joystick / walk mode:** an on-map joystick that continuously nudges the
  simulated point at a walking speed + heading. Server side: a background
  loop calling `/set_location` every ~1s with the new interpolated coord.
- **Route / drive mode:** click waypoints (or search) → build a path → move the
  point along it at a chosen speed (walk/run/cycle/drive) with realistic
  accel/decel + ETA, matching the iOS route feature. Reuse the same movement
  loop; add pause/resume/stop.
- Optional: import GPX, saved favorites, speed presets — mirror the iOS
  "power-user control pack".

### Phase 3 — Monetization (same system as iOS)
- Reuse the **Cloudflare license Worker** already live for iOS: desktop pastes
  the same license key, `/redeem` binds it, offline signature verify locally.
- Freemium gate on desktop (e.g. teleport free, joystick/route behind license)
  or a straight "unlock with your Wander key" — decide with the iOS funnel.
- Trial counters stored in a local app-support file.

### Phase 4 — Package & ship
- **PyInstaller** → standalone `Wander Desktop.app` (macOS) and `.exe`
  (Windows) — no Python install needed by the user, exactly how iGo ships.
- Code-sign/notarize the Mac app if possible (ad-hoc otherwise, with a
  Gatekeeper-bypass note); NSIS/zip for Windows.
- Download from wanderspoofer.com + a GitHub release, like the iOS installer.

## UI reference — AnyTo / iGo patterns to match or beat
(From competitor screenshots. These are the desktop UX targets.)
- **Onboarding flow:** Connect screen → **Choose Your Device** (lists device;
  **USB + Wi-Fi** connect, "connect via USB first time, same Wi-Fi" note) →
  **Select Mode** (two big cards: *Game Mode* for PoGo/MHN vs *Universal Mode*
  for social/dating apps; disclaimer checkbox) → map. Wander already owns the
  hard device/tunnel layer; add the mode-select + a polished device picker.
- **Live Update dialog:** "New version X detected → What's New → Update/Close".
  Wander can point this at the same OTA/update source.
- **Message Center:** in-app news/blog feed (SEO + engagement driver). Pull from
  an RSS/JSON feed hosted on wanderspoofer.com.
- **"Unlock Now"** button top-right → paywall, wired to the license system
  (same Cloudflare Worker as iOS).
- Clean light-blue modern shell; big friendly cards; account + AI + inbox icons
  in the top bar.
- Wander's edge to lean on: it's **cheaper**, the app lives on the phone too,
  and joystick/route are first-class (not upsold).

## Known constraints
- The device tunnel needs **admin/root** (sudo on Mac, UAC on Windows) — same as
  Xcode. `run.sh` handles the sudo re-launch.
- Testing requires your iPhone physically connected to this Mac + Developer Mode
  on; the device code can't be unit-tested without hardware, so Phase 2/3 land
  in verifiable increments you test on-device.
- Python 3.14 is very new; if pymobiledevice3 misbehaves, pin the venv to 3.12.
