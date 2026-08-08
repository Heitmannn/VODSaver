#!/usr/bin/env python3
import datetime as dt
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from xml.sax.saxutils import escape as xml_escape


API_BASE = "https://api.twitch.tv/helix"
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


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
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    temporary_path.replace(path)


def acquire_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    return lock_file


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
        raise RuntimeError("Twitch API unauthorized. Check token and Client ID.")
    resp.raise_for_status()
    return resp.json()


def get_user_id(login, token, client_id):
    data = twitch_get(f"{API_BASE}/users", token, client_id, params={"login": login})
    if not data.get("data"):
        raise RuntimeError(f"No Twitch user found for login: {login}")
    return data["data"][0]["id"]


def get_latest_vod(user_id, token, client_id):
    params = {"user_id": user_id, "first": 1, "type": "archive", "sort": "time"}
    data = twitch_get(f"{API_BASE}/videos", token, client_id, params=params)
    if not data.get("data"):
        return None
    return data["data"][0]


def is_stream_live(user_id, token, client_id):
    params = {"user_id": user_id}
    data = twitch_get(f"{API_BASE}/streams", token, client_id, params=params)
    return bool(data.get("data"))


def sanitize_filename(value):
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] if value else "untitled"


def month_name_from_date(d: dt.datetime):
    return MONTH_NAMES[d.month - 1]


def resolve_show_dir(output_dir: Path, channel: str, show_name: str):
    streamer_name = sanitize_filename(channel)
    show_name_clean = sanitize_filename(show_name)
    streamer_dir = output_dir / streamer_name
    if show_name_clean.lower() == streamer_name.lower():
        return streamer_dir
    return streamer_dir / show_name_clean


def choose_base_name(target_dir: Path, vod_dt: dt.datetime):
    day_name = vod_dt.strftime("%Y-%m-%d")
    if not (target_dir / f"{day_name}.mp4").exists() and not (target_dir / f"{day_name}.nfo").exists():
        return day_name

    dt_name = vod_dt.strftime("%Y-%m-%d-%H-%M")
    if not (target_dir / f"{dt_name}.mp4").exists() and not (target_dir / f"{dt_name}.nfo").exists():
        return dt_name

    for suffix in range(2, 1000):
        candidate = f"{dt_name}-{suffix}"
        if not (target_dir / f"{candidate}.mp4").exists() and not (target_dir / f"{candidate}.nfo").exists():
            return candidate
    raise RuntimeError(f"Could not find free filename in {target_dir}")


def build_paths(output_dir: Path, channel: str, show_name: str, vod_dt: dt.datetime):
    month_name = month_name_from_date(vod_dt)
    show_dir = resolve_show_dir(output_dir, channel, show_name)
    month_dir = show_dir / month_name
    month_dir.mkdir(parents=True, exist_ok=True)
    base_name = choose_base_name(month_dir, vod_dt)
    return month_dir, base_name, vod_dt.month, vod_dt.day


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
        "--no-write-cookies",
        "-o",
        str(out_path),
        "--merge-output-format",
        "mp4",
        vod_url,
    ]
    if extra_args:
        cmd[1:1] = extra_args
    subprocess.run(cmd, check=True)


def normalize_channels(channels_value: str):
    return [c.strip().lower() for c in channels_value.split(",") if c.strip()]


def normalize_show_names(names_value: str):
    return [n.strip() for n in names_value.split(",")] if names_value else []


def resolve_state_path(state_path_env: str, output_dir: Path, channel: str, multi: bool):
    if not state_path_env:
        return output_dir / "state" / f"{channel}.json"
    base = Path(state_path_env)
    if not multi:
        return base
    if base.exists() and base.is_dir():
        return base / f"{channel}.json"
    if base.exists() and base.is_file():
        return base.parent / f"{channel}.json"
    if base.suffix.lower() == ".json":
        return base.parent / f"{channel}.json"
    return base / f"{channel}.json"


def resolve_show_name(channel: str, index: int, show_names: list, single_show_name: str = ""):
    if index < len(show_names):
        candidate = show_names[index].strip()
        if candidate:
            return candidate
    if single_show_name.strip():
        return single_show_name.strip()
    return channel


def process_channel(
    channel: str,
    token: str,
    client_id: str,
    cookies_path: str,
    output_dir: Path,
    state_path: Path,
    show_name: str,
    extra_args: list,
):
    user_id = get_user_id(channel, token, client_id)
    if is_stream_live(user_id, token, client_id):
        print(f"{channel} is live. Skipping VOD download until stream ends.")
        return

    latest = get_latest_vod(user_id, token, client_id)
    if not latest:
        print(f"No VODs found for {channel}.")
        return

    state = load_state(state_path)
    vod_id = latest["id"]
    if state.get("last_vod_id") == vod_id:
        print(f"No new VOD for {channel}. Latest is still {vod_id}.")
        return

    vod_title = latest["title"]
    vod_url = latest["url"]
    published_at = latest["published_at"].replace("Z", "+00:00")
    vod_dt = dt.datetime.fromisoformat(published_at).astimezone()

    month_dir, base_name, season_num, episode_num = build_paths(output_dir, channel, show_name, vod_dt)
    video_path = month_dir / f"{base_name}.mp4"
    nfo_path = month_dir / f"{base_name}.nfo"

    print(f"Downloading VOD {vod_id} for {channel} to {video_path}...")
    run_yt_dlp(vod_url, cookies_path, video_path, extra_args)

    episode_title = vod_dt.strftime("%Y-%m-%d")
    description = latest.get("description", "")
    if vod_title and vod_title != episode_title:
        description = f"{vod_title}\n\n{description}" if description else vod_title
    write_nfo(nfo_path, episode_title, description, vod_dt.date(), season_num, episode_num)

    state["last_vod_id"] = vod_id
    state["last_vod_published_at"] = latest["published_at"]
    save_state(state_path, state)
    print(f"Done for {channel}. Updated state in {state_path}.")


def main():
    load_dotenv()
    channels_env = env("TWITCH_CHANNELS", default="")
    single_channel = env("TWITCH_CHANNEL", default="")
    channels_value = channels_env or single_channel
    if not channels_value:
        raise SystemExit("Missing required env var: TWITCH_CHANNELS or TWITCH_CHANNEL")
    channels = normalize_channels(channels_value)
    if not channels:
        raise SystemExit("No valid channels provided.")

    show_names_value = env("SHOW_NAMES", default="")
    show_names = normalize_show_names(show_names_value)
    single_show_name = env("SHOW_NAME", default="")

    client_id = env("TWITCH_CLIENT_ID", required=True)
    user_token = env("TWITCH_USER_OAUTH_TOKEN", default="")
    client_secret = env("TWITCH_CLIENT_SECRET", required=not bool(user_token))
    cookies_path = env("COOKIES_PATH", required=True)
    output_dir = Path(env("OUTPUT_DIR", required=True))
    state_path_env = env("STATE_PATH", default="")
    extra_args = shlex.split(env("YTDLP_EXTRA_ARGS", default=""))

    if not Path(cookies_path).exists():
        raise SystemExit(f"Cookies file not found: {cookies_path}")

    lock_path = Path(env("LOCK_PATH", default=str(output_dir / ".vodsaver.lock")))
    lock_file = acquire_lock(lock_path)
    if lock_file is None:
        print(f"Another VODsaver run holds {lock_path}; skipping this run.")
        return 0

    failures = []
    try:
        token = user_token or get_app_access_token(client_id, client_secret)
        multi = len(channels) > 1
        for index, channel in enumerate(channels):
            show_name = resolve_show_name(channel, index, show_names, single_show_name)
            state_path = resolve_state_path(state_path_env, output_dir, channel, multi)
            try:
                process_channel(
                    channel=channel,
                    token=token,
                    client_id=client_id,
                    cookies_path=cookies_path,
                    output_dir=output_dir,
                    state_path=state_path,
                    show_name=show_name,
                    extra_args=extra_args,
                )
            except Exception as exc:
                failures.append(channel)
                print(f"Error processing {channel}: {exc}", file=sys.stderr)
    finally:
        lock_file.close()

    if failures:
        print(f"Failed channels: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
