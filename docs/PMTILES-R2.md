# Hosting the PMTiles planet basemap on Cloudflare R2

This is the one part of the PMTiles migration that isn't code — it needs your Cloudflare account. Once the planet `.pmtiles` is on R2, every platform (desktop `protomaps-leaflet`, iOS/Android MapLibre) reads its basemap from that one URL, fully licence-clean (ODbL) and offline-capable.

**You do NOT need to build the basemap** — Protomaps publishes a daily pre-built planet, so this is a download + re-upload, not a `planetiler` run.

**You do NOT need ~107 GB of free disk, either.** Stream the planet straight from Protomaps into R2 so it only passes *through* your machine in small chunks (needs just your bandwidth + a small buffer):

Run these one at a time. (Lines starting with `#` are comments — your interactive shell may try to run them, so skip them.)

```bash
# 1. Install rclone (once):
brew install rclone

# 2. One-time R2 config. Get an R2 API token: Cloudflare dashboard → R2 → "Manage R2 API Tokens"
#    → Create (Object Read & Write) → note Access Key ID, Secret, and your Account ID. Then:
mkdir -p ~/.config/rclone
cat >> ~/.config/rclone/rclone.conf <<'CONF'
[r2]
type = s3
provider = Cloudflare
access_key_id = YOUR_R2_ACCESS_KEY_ID
secret_access_key = YOUR_R2_SECRET
endpoint = https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
acl = private
CONF
rclone mkdir r2:wander-basemap

# 3. Find the latest build date at https://maps.protomaps.com/builds/ , then stream it in
#    (this is ONE line — ~107 GB, so it runs for a while, bandwidth-bound):
curl -L "https://build.protomaps.com/20260714.pmtiles" | rclone rcat r2:wander-basemap/planet.pmtiles --s3-chunk-size 128M
```

That's the recommended path. If you'd rather land the file first (needs the disk space, or use an **external drive** — the file only transits through), the step-by-step download + upload is below.

## 1. Get the planet `.pmtiles` (~107 GB)

Install the `pmtiles` CLI (`brew install pmtiles` or from github.com/protomaps/go-pmtiles releases), then grab the latest Protomaps build:

```bash
# List available daily builds and pick the newest date:
#   https://maps.protomaps.com/builds/   (files look like 20260714.pmtiles)
curl -L -o planet.pmtiles "https://build.protomaps.com/20260714.pmtiles"   # ~107 GB, needs the disk space
```

(Optional sanity check: `pmtiles show planet.pmtiles` should print the header + tile counts.)

## 2. Create an R2 bucket + upload

```bash
# Create the bucket (Cloudflare dashboard → R2, or wrangler):
npx wrangler r2 bucket create wander-basemap

# Upload the 107 GB file. wrangler is slow for this size — use rclone or aws-cli against R2's S3 endpoint:
#   Account ID + an R2 API token (Cloudflare dashboard → R2 → Manage API Tokens).
rclone copyto planet.pmtiles r2:wander-basemap/planet.pmtiles \
  --s3-endpoint "https://<ACCOUNT_ID>.r2.cloudflarestorage.com" --progress
```

## 3. Make it publicly range-readable (+ CORS)

PMTiles is served by **HTTP range requests**, so the object must be publicly GET-able with `Range` allowed.

- **Public URL:** R2 → your bucket → Settings → either enable the `r2.dev` public URL or (better) connect a **custom domain** (e.g. `tiles.wanderspoofer.com`).
- **CORS policy** on the bucket (R2 → Settings → CORS):
  ```json
  [{ "AllowedOrigins": ["*"], "AllowedMethods": ["GET","HEAD"], "AllowedHeaders": ["Range"], "ExposeHeaders": ["Content-Range","Content-Length","ETag"], "MaxAgeSeconds": 86400 }]
  ```

Your basemap URL is now e.g. `https://tiles.wanderspoofer.com/planet.pmtiles`.

## 4. Point the clients at it

- **Desktop:** set `window.WANDER_PMTILES_URL` in `src/templates/map.html` (currently defaults to the Protomaps demo bucket for dev — swap it to your R2 URL before shipping; the demo bucket is not for production).
- **iOS / Android (MapLibre phase):** the PMTiles source URL is a single constant per app — point it at the same R2 URL.

## Cost (rough)

R2 storage ≈ **$0.015/GB-mo → ~$1.6/mo** for 107 GB. R2 has **zero egress fees**, so serving tiles is effectively free (Class B operations are cheap). Re-upload a fresh planet every month or two to keep the map current.

## Offline (per platform)

- **Desktop:** `pip install pmtiles`; a "download this region" action runs `pmtiles extract <R2 url> region.pmtiles --bbox=...` server-side into a local file that `protomaps-leaflet` reads with no network.
- **Mobile:** MapLibre Native's built-in offline-pack manager downloads a bbox+zoom range from the R2 source into its local cache.
