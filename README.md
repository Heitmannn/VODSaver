# VODsaver

Downloads the latest Twitch VOD for one or more channels if it is new and saves it into a Jellyfin-friendly folder structure with basic metadata.

## How it works
- Every run checks the latest VOD for `TWITCH_CHANNEL` or each channel in `TWITCH_CHANNELS`.
- If a VOD id differs from its saved state, it downloads the VOD via `yt-dlp` (cookies required).
- Writes an `.nfo` file and atomically updates the channel state.
- Uses a shared lock in `OUTPUT_DIR` so overlapping cron invocations cannot download the same VOD.

## Environment variables
Required:
- `TWITCH_CHANNEL` (one login name) or `TWITCH_CHANNELS` (comma-separated login names)
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET` unless `TWITCH_USER_OAUTH_TOKEN` is set
- `COOKIES_PATH`
- `OUTPUT_DIR`

Optional:
- `TWITCH_USER_OAUTH_TOKEN` (only if app token can't see subscriber-only VODs)
- `STATE_PATH` (defaults to `${OUTPUT_DIR}/state/<channel>.json`; for multiple channels, use a directory)
- `SHOW_NAME` (single fallback show name; defaults to the channel name)
- `SHOW_NAMES` (comma-separated show names aligned with `TWITCH_CHANNELS`)
- `LOCK_PATH` (defaults to `${OUTPUT_DIR}/.vodsaver.lock`)
- `YTDLP_EXTRA_ARGS` (extra arguments for `yt-dlp`)

## Local run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export TWITCH_CHANNEL=streamer_login
export TWITCH_CLIENT_ID=...
export TWITCH_CLIENT_SECRET=...
export COOKIES_PATH=/path/to/cookies.txt
export OUTPUT_DIR=/path/to/jellyfin/library

python vodsaver.py
```

You can also create a `.env` file (copy from `.env.example`). The script will load it automatically.

## Optional device-code login (user token)
If you need a user token (some subscriber-only VODs might not show up with app tokens), run:
```bash
export TWITCH_CLIENT_ID=...
export TWITCH_SCOPES=
export TOKEN_PATH=./twitch_token.json
python get_token.py
```
Then set `TWITCH_USER_OAUTH_TOKEN` to the `access_token` in that file.

## Docker run
```bash
docker build -t vodsaver .
docker run --rm \
  --env-file .env \
  -e COOKIES_PATH=/data/cookies.txt \
  -e OUTPUT_DIR=/data/vods \
  -v /path/to/cookies.txt:/data/cookies.txt:ro \
  -v /path/to/jellyfin/library:/data/vods \
  vodsaver
```

## Production cron (every 30 minutes)

Create `/home/pi/Documents/VODSaver/run.sh`:

```bash
#!/bin/bash
set -euo pipefail

cd /home/pi/Documents/VODSaver
/usr/bin/docker run --rm \
  --env-file /home/pi/Documents/VODSaver/.env \
  -e COOKIES_PATH=/data/cookies.txt \
  -e OUTPUT_DIR=/data/vods \
  -v /home/pi/Documents/VODSaver/cookies.txt:/data/cookies.txt:ro \
  -v /path/to/jellyfin/library:/data/vods \
  vodsaver:latest
```

Replace `/path/to/jellyfin/library`, make the script executable, then use this host cron entry:

```bash
chmod +x /home/pi/Documents/VODSaver/run.sh
```

```
*/30 * * * * /bin/bash /home/pi/Documents/VODSaver/run.sh >> /home/pi/Documents/VODSaver/cron.log 2>&1
```

The application lock already prevents overlapping runs. Adding `flock` to cron is optional defense in depth.

## Notes
- `yt-dlp` uses cookies to access subscriber-only VODs. The cookies file must be in Netscape format (exported from your browser), not just a raw token.
- Cookies are mounted read-only; the script passes `--no-write-cookies` to avoid write errors.
- The lock and default state files must live on the persistent `/data/vods` mount.
- Default output layout is `OUTPUT_DIR/<channel>/<MonthName>/<YYYY-MM-DD>.mp4` (plus matching `.nfo`).
- Episode title is the date (`YYYY-MM-DD`), season is month number, and episode number is day-of-month.
- If `SHOW_NAME` differs from the channel name, output becomes `OUTPUT_DIR/<channel>/<SHOW_NAME>/<MonthName>/...`.
