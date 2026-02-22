#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


def env(name, default=None, required=False):
    val = os.getenv(name, default)
    if required and not val:
        raise SystemExit(f"Missing required env var: {name}")
    return val


def save_token(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def main():
    load_dotenv()
    client_id = env("TWITCH_CLIENT_ID", required=True)
    scopes = env("TWITCH_SCOPES", default="")
    token_path = Path(env("TOKEN_PATH", default="twitch_token.json"))

    device_resp = requests.post(
        "https://id.twitch.tv/oauth2/device",
        data={"client_id": client_id, "scopes": scopes},
        timeout=30,
    )
    device_resp.raise_for_status()
    device_data = device_resp.json()

    print("Go to:", device_data["verification_uri"])
    print("Enter code:", device_data["user_code"])
    print("Waiting for authorization...")

    interval = max(1, int(device_data.get("interval", 5)))
    device_code = device_data["device_code"]
    token_url = "https://id.twitch.tv/oauth2/token"

    while True:
        time.sleep(interval)
        token_resp = requests.post(
            token_url,
            data={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=30,
        )
        if token_resp.status_code == 200:
            token_data = token_resp.json()
            save_token(token_path, token_data)
            print(f"Token saved to {token_path}")
            print("Set TWITCH_USER_OAUTH_TOKEN to access_token from that file.")
            return
        if token_resp.status_code in (400, 428, 429):
            # 400 authorization_pending or slow_down in body
            continue
        token_resp.raise_for_status()


if __name__ == "__main__":
    main()
