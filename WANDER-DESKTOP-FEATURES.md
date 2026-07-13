# Wander Desktop — full feature spec (mirror + beat iGo/AnyTo)

Every mode below comes from AnyTo/iGo screenshots. Wander already owns the hard
part (device tunnel + `LocationSimulation.set(lat,lng)`); **every movement mode
is just that `.set()` call fired repeatedly with interpolated coordinates on a
timer.** One movement engine powers them all.

## The 6 modes (top-right toolbar, like iGo)

1. **Teleport** — click/search one spot → instant jump. Options: **Fluctuation**
   (tiny GPS jitter for realism). Shows distance from current. `set()` once.
2. **Jump Teleport** (PoGo signature) — add N spots → jump between them, with a
   **PoGo cooldown timer** and **Auto-jump after cooldown** (waits the safe time
   before advancing so you don't get soft-banned). Point counter N/total.
3. **Two-spot** — A→B path, move at a chosen **speed** (walk/bike/motorbike/car
   preset slider + exact m/s), **Loop / round-trip / once**, **Realistic mode**
   (accel/decel + slight speed variance). Live timer + distance.
4. **Multi-spot** — same as two-spot but many waypoints; toggle line-follow vs
   free. Loop/round-trip.
5. **Joystick** — on-map D-pad + speed slider for free real-time walking; hold a
   direction and the point streams that way.
6. **History** — recent locations + **Favorites** (star a spot to reuse).

## Cross-mode
- Search bar: address **or** raw `lat, lng`.
- **PoGo cooldown table** (distance → safe wait) shown as a countdown, used by
  Jump/Teleport auto-advance. (e.g. ~2 min for 5 km, ~10 min/65 km, up to ~2 h
  for very long jumps — standard PoGo soft-ban curve.)
- **Fluctuation / Realistic** toggles (jitter + human-like speed).
- **Unlock Now** button (top-right) → opens https://wanderspoofer.com to buy
  (per user: desktop paywall just sends them to the site).
- **Trial limits** shown like iGo ("Trial times / Trial Time") — reuse the iOS
  freemium numbers (5 teleports / 30 min joystick / 3 routes) then license.
- Clean light-blue shell; left control panel per mode; right map controls.

## Server routes to add (main.py) — the movement engine
- `POST /wander/teleport {lat,lng,fluctuate}` — one-shot set (+ jitter).
- `POST /wander/route {points[], speed_mps, loop, realistic}` — stream along a
  great-circle-interpolated path; loop/round-trip/once.
- `POST /wander/joystick/start {speed_mps}` + `POST /wander/joystick/dir
  {heading}` + stop — stream in the held heading, updatable live.
- `POST /wander/jump {points[], auto_cooldown}` — set each point, waiting the
  PoGo cooldown between hops when auto_cooldown.
- `POST /wander/stop` — stop any active movement.
- `GET  /wander/cooldown?km=` — return safe wait minutes for a distance.
All reuse ONE held DVT connection (open once, `.set()` in a loop) — opening per
point is too slow.

## UI to add (map.html)
- 6-icon mode toolbar (top-right) switching the left panel.
- Joystick widget (D-pad + center go).
- Click-to-add-waypoint on the map; speed preset slider; loop dropdown; realistic
  + fluctuation checkboxes; live distance/ETA/timer.
- Unlock Now button → site. Favorites (star) + history list.

## Where Wander beats iGo
Cheaper, the app also lives on the phone (no laptop tether after setup), joystick
+ routes are first-class (not paywalled tiers), and it's the same license across
iOS + desktop.

## Build order
P2a **movement engine + routes** (this is the foundation) → P2b **mode UI** in
map.html → P2c cooldown/fluctuation/realistic polish → P3 license/trial + Unlock
→ P4 package. Installer UI redesign is a separate track (see installer repo).
