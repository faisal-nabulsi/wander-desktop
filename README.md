<div align="center">

<a href="https://wanderspoofer.com">
  <img src="https://wanderspoofer.com/wander-logo.png" width="120" alt="Wander logo"/>
</a>

# Wander Desktop 🌍

### Put your iPhone anywhere on Earth — from your Mac or PC. Free, open-source, no jailbreak.

Teleport with a click, walk with a live joystick, or drive a full multi-stop route at realistic speed — all from a clean desktop map. The free alternative to paid tools like **iMyFone AnyTo** and **Tenorshare iAnyGo**.

<br/>

[![Website](https://img.shields.io/badge/🌐_Website-wanderspoofer.com-4C8BF5?style=for-the-badge)](https://wanderspoofer.com)
[![Download](https://img.shields.io/badge/⬇️_Download-Free-22C55E?style=for-the-badge)](https://wanderspoofer.com/#download)
[![Discord](https://img.shields.io/badge/💬_Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/gfHdsRXUVA)

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg?style=flat-square)](LICENSE)
![Platform](https://img.shields.io/badge/platform-macOS_·_Windows-lightgrey?style=flat-square)
[![GitHub stars](https://img.shields.io/github/stars/faisal-nabulsi/wander-desktop?style=flat-square&label=Stars)](https://github.com/faisal-nabulsi/wander-desktop/stargazers)
[![No jailbreak](https://img.shields.io/badge/jailbreak-not_required-success?style=flat-square)](https://wanderspoofer.com)

<br/>

### 👉 [**⬇️ Download at wanderspoofer.com**](https://wanderspoofer.com/#download) &nbsp;·&nbsp; [**⭐ Star this repo**](https://github.com/faisal-nabulsi/wander-desktop)

**The app, all downloads, and the full setup guide live at [wanderspoofer.com](https://wanderspoofer.com).**

<br/>

<a href="https://github.com/faisal-nabulsi/Wander"><img src="https://img.shields.io/badge/⭐_Star_Wander_on_GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="Star Wander on GitHub"/></a>

**⭐ [Star Wander on GitHub](https://github.com/faisal-nabulsi/Wander) — it's free, takes one click, and helps more people find a free alternative to the paid spoofers.**

<br/>

[![Join our Discord](https://img.shields.io/badge/💬_Join_the_Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/gfHdsRXUVA)

**💬 [Join the Wander Discord](https://discord.gg/gfHdsRXUVA) — setup help, release updates, and feature requests. Stuck connecting your iPhone? Ask here and get unstuck fast.**

</div>

---

## ✨ What it does

- 📍 **Teleport** — click anywhere on the map to set your iPhone's location instantly.
- 🕹️ **Joystick walk** — a live stick to move in real time at walk / run / drive speed.
- 🛣️ **Routes** — multi-stop drives that follow the real road with realistic **speed & ETA**.
- 🎮 **PoGo jump-teleport** — long hops with a **cooldown timer** so you stay safe.
- 📂 **GPX import** and 🌫️ **realistic GPS jitter** so a fixed spot never looks robotic.
- 🔌 **iPhone over USB** — plug in and go; connect over Wi-Fi too.
- 🔓 **No jailbreak.** Works on a normal, up-to-date iPhone.
- 💻 **Cross-platform** — macOS and Windows.

Start with a **free trial**. **Wander Pro** unlocks the movement modes (joystick, routes, and more).

> Also on **iPhone, Android, Mac, and Windows** — see the whole family at [wanderspoofer.com](https://wanderspoofer.com).

---

## ⚖️ Wander vs. the paid apps

| | **Wander Desktop** | iMyFone AnyTo | Tenorshare iAnyGo |
|---|:---:|:---:|:---:|
| **Price** | ✅ **Free** | 💰 Paid | 💰 Paid |
| **Open source** | ✅ AGPL-3.0 | ❌ | ❌ |
| **No jailbreak** | ✅ | ✅ | ✅ |
| **Teleport** | ✅ | ✅ | ✅ |
| **Live joystick** | ✅ | ✅ | ✅ |
| **Multi-stop routes** | ✅ | ✅ | ✅ |
| **GPX import** | ✅ | ⚠️ | ⚠️ |
| **macOS + Windows** | ✅ | ⚠️ | ⚠️ |

---

## ⬇️ Get it — in 2 minutes

### 👉 [**Download at wanderspoofer.com**](https://wanderspoofer.com/#download)

The site has the latest desktop build for **Mac & Windows** plus a step-by-step guide. No jailbreak, no paid developer account.

---

## 🧑‍💻 Run from source

For developers who'd rather build it themselves:

```bash
cd wander-desktop
./run.sh          # first run creates a venv, installs deps, and launches
```

`run.sh` re-launches itself with `sudo` on macOS because the developer-service tunnel requires root (same as Xcode). A browser tab opens with the map UI.

**Manual alternative:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo ./.venv/bin/python src/main.py
```

**Requirements**
- **macOS** or **Windows**
- **Python 3.11–3.12** recommended (3.14 may work; pin to 3.12 if you hit issues)
- iPhone with **Developer Mode** enabled (Settings → Privacy & Security → Developer Mode)
- Admin rights (the device tunnel needs `sudo` on macOS / UAC on Windows)

---

## ⚙️ How it works

A local **Flask** server hosts a **Leaflet** map (`src/templates/map.html`) and talks to the iPhone through **pymobiledevice3**: it starts a QUIC/TCP tunnel, mounts the Developer Disk Image, and sets location via the DVT `LocationSimulation` instrument. Teleporting is a `POST /set_location {lat,lng}`; walk and route modes drive that same call on a timer.

---

## 💬 Community & support

[![Join our Discord](https://img.shields.io/badge/💬_Join_the_Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/gfHdsRXUVA)

**[Join the Wander Discord →](https://discord.gg/gfHdsRXUVA)** for setup help, release updates, and feature requests. It's the fastest way to sort out a device-connection hiccup and to hear about new builds first.

- 🌐 **Website & downloads:** [wanderspoofer.com](https://wanderspoofer.com)
- 💬 **Discord:** [join the server](https://discord.gg/gfHdsRXUVA)
- ⭐ **Star the repo:** [give Wander a star](https://github.com/faisal-nabulsi/Wander) — it's the easiest way to support the project.
- 🐛 **Bugs / feature requests:** open an [issue](https://github.com/faisal-nabulsi/wander-desktop/issues).

---

## 🤔 Why Wander?

iAnyGo, AnyTo, and the rest work, but they charge a subscription and ship closed-source binaries. Wander Desktop is **free and open under AGPL-3.0** — teleport, joystick, and routes from your Mac or PC, no jailbreak and no monthly bill. Read every line, build it yourself, see exactly what runs.

---

## 📜 Credits & License

Wander Desktop is a fork of [GeoPort](https://github.com/davesc63/GeoPort) (AGPL-3.0). Huge credit to the GeoPort project for the underlying `pymobiledevice3` device tunnel + location engine. This fork is likewise **AGPL-3.0** — see [LICENSE](LICENSE). If you distribute a modified version, you must make your source available under the same license.

*Use responsibly and legally. Spoofing your location may violate the Terms of Service of some apps and games.*

---

<div align="center">

### ⭐ Star this repo if it saved you from paying for AnyTo or iAnyGo.

**[🌐 wanderspoofer.com](https://wanderspoofer.com)** &nbsp;·&nbsp; **[⬇️ Download](https://wanderspoofer.com/#download)** &nbsp;·&nbsp; **[💬 Discord](https://discord.gg/gfHdsRXUVA)**

</div>
