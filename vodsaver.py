#!/usr/bin/env python3
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from xml.sax.saxutils import escape as xml_escape


API_BASE = "https://api.twitch.tv/helix"


def env(name, default=None, required=False):
    val = os.getenv(name, default)
    if required and not val:
        raise SystemExit(f"Missing required env var: {name}")
    return val


def load_state(path: Path):
    if not path.exists():
        return {"last_vod_id": None, "last_vod_published_at": None}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def get_app_access_token(client_id, client_secret):
    resp = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def twitch_get(url, token, client_id, params=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-ID": client_id,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    if resp.status_code == 401:
        raise SystemExit("Twitch API unauthorized. Check token and Client ID.")
    resp.raise_for_status()
    return resp.json()


def get_user_id(login, token, client_id):
    data = twitch_get(f"{API_BASE}/users", token, client_id, params={"login": login})
    if not data.get("data"):
        raise SystemExit(f"No Twitch user found for login: {login}")
    return data["data"][0]["id"]


def get_latest_vod(user_id, token, client_id):
    params = {"user_id": user_id, "first": 1, "type": "archive", "sort": "time"}
    data = twitch_get(f"{API_BASE}/videos", token, client_id, params=params)
    if not data.get("data"):
        return None
    return data["data"][0]


def sanitize_filename(value):
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] if value else "untitled"


def season_from_date(d: dt.datetime):
    return f"Season {d.month:02d}"


def build_paths(output_dir: Path, show_name: str, vod_dt: dt.datetime, title: str):
    season = season_from_date(vod_dt)
    base_name = f"{vod_dt:%Y-%m-%d %H-%M} - {sanitize_filename(title)}"
    show_dir = output_dir / sanitize_filename(show_name)
    season_dir = show_dir / season
    season_dir.mkdir(parents=True, exist_ok=True)
    return season_dir, base_name, season, vod_dt


def write_nfo(nfo_path: Path, title: str, description: str, aired: dt.date, season: int, episode: int):
    plot = description or ""
    title = xml_escape(title)
    plot = xml_escape(plot)
    nfo = f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<episodedetails>
  <title>{title}</title>
  <plot>{plot}</plot>
  <aired>{aired.isoformat()}</aired>
  <season>{season}</season>
  <episode>{episode}</episode>
</episodedetails>
"""
    nfo_path.write_text(nfo, encoding="utf-8")


def run_yt_dlp(vod_url, cookies_path, out_path: Path, extra_args):
    cmd = [
        "yt-dlp",
        "--cookies",
        cookies_path,
        "-o",
        str(out_path),
        "--merge-output-format",
        "mp4",
        vod_url,
    ]
    if extra_args:
        cmd[1:1] = extra_args
    subprocess.run(cmd, check=True)


def main():
    load_dotenv()
    channel = env("TWITCH_CHANNEL", required=True)
    client_id = env("TWITCH_CLIENT_ID", required=True)
    client_secret = env("TWITCH_CLIENT_SECRET", required=True)
    user_token = env("TWITCH_USER_OAUTH_TOKEN", default="")
    cookies_path = env("COOKIES_PATH", required=True)
    output_dir = Path(env("OUTPUT_DIR", required=True))
    state_path = Path(env("STATE_PATH", default=str(output_dir / "state.json")))
    show_name = env("SHOW_NAME", default=channel)
    extra_args = env("YTDLP_EXTRA_ARGS", default="").split()

    if not Path(cookies_path).exists():
        raise SystemExit(f"Cookies file not found: {cookies_path}")

    if user_token:
        token = user_token
    else:
        token = get_app_access_token(client_id, client_secret)

    user_id = get_user_id(channel, token, client_id)
    latest = get_latest_vod(user_id, token, client_id)
    if not latest:
        print("No VODs found.")
        return

    state = load_state(state_path)
    vod_id = latest["id"]
    if state.get("last_vod_id") == vod_id:
        print(f"No new VOD. Latest is still {vod_id}.")
        return

    vod_title = latest["title"]
    vod_url = latest["url"]
    published_at = latest["published_at"].replace("Z", "+00:00")
    vod_dt = dt.datetime.fromisoformat(published_at).astimezone()

    season_dir, base_name, season_label, _ = build_paths(output_dir, show_name, vod_dt, vod_title)
    video_path = season_dir / f"{base_name}.mp4"
    nfo_path = season_dir / f"{base_name}.nfo"

    print(f"Downloading VOD {vod_id} to {video_path}...")
    run_yt_dlp(vod_url, cookies_path, video_path, extra_args)

    season_num = int(season_label.split()[-1])
    episode_num = vod_dt.day
    write_nfo(nfo_path, vod_title, latest.get("description", ""), vod_dt.date(), season_num, episode_num)

    state["last_vod_id"] = vod_id
    state["last_vod_published_at"] = latest["published_at"]
    save_state(state_path, state)
    print(f"Done. Updated state in {state_path}.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
