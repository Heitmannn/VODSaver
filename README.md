# VODsaver

Downloads the latest Twitch VOD for a channel if it's new and saves it into a Jellyfin-friendly folder structure with basic metadata.

## How it works
- Every run checks the latest VOD for `TWITCH_CHANNEL`.
- If the VOD id differs from `state.json`, it downloads the VOD via `yt-dlp` (cookies required).
- Writes an `.nfo` file and updates `state.json`.

## Environment variables
Required:
- `TWITCH_CHANNEL` (login name)
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `COOKIES_PATH`
- `OUTPUT_DIR`

Optional:
- `TWITCH_USER_OAUTH_TOKEN` (only if app token can't see subscriber-only VODs)
- `STATE_PATH` (defaults to `${OUTPUT_DIR}/state.json`)
- `SHOW_NAME` (folder name; defaults to `TWITCH_CHANNEL`)
- `YTDLP_EXTRA_ARGS` (extra arguments for `yt-dlp`)

## Local run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install yt-dlp==2024.08.06

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
  -e TWITCH_CHANNEL=streamer_login \
  -e TWITCH_CLIENT_ID=... \
  -e TWITCH_CLIENT_SECRET=... \
  -e COOKIES_PATH=/data/cookies.txt \
  -e OUTPUT_DIR=/data/vods \
  -v /path/to/cookies.txt:/data/cookies.txt:ro \
  -v /path/to/jellyfin/library:/data/vods \
  vodsaver
```

## Cron (every 30 minutes)
Example host cron entry:
```
*/30 * * * * /usr/bin/docker run --rm \
  -e TWITCH_CHANNEL=streamer_login \
  -e TWITCH_CLIENT_ID=... \
  -e TWITCH_CLIENT_SECRET=... \
  -e COOKIES_PATH=/data/cookies.txt \
  -e OUTPUT_DIR=/data/vods \
  -v /path/to/cookies.txt:/data/cookies.txt:ro \
  -v /path/to/jellyfin/library:/data/vods \
  vodsaver
```

## Notes
- `yt-dlp` uses cookies to access subscriber-only VODs. The cookies file must be in Netscape format (exported from your browser), not just a raw token.
- Cookies are mounted read-only; the script passes `--no-write-cookies` to avoid write errors.
- Episode numbering uses the day-of-month; seasons are month numbers (`Season 02`).
