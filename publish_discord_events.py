import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

AZURACAST_URL = "https://radio.913aycltfm.com"
DISCORD_API = "https://discord.com/api/v10"
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
API_KEY = os.environ.get("AZURACAST_API_KEY", "").strip()
SHORTCODES = ["91.3_ayclt_fm", "91.3_ayclt_fm_hd2", "91.3_ayclt_fm_hd3"]
WINDOW_DAYS = 7
TIMEOUT = 25


def request_json(url, headers=None, data=None, method=None):
    req_headers = {"User-Agent": "913AycltFM-AzuraCast-Discord-Events/1.0"}
    if headers:
        req_headers.update(headers)
    body = None if data is None else json.dumps(data).encode("utf-8")
    if body is not None:
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else None


def azura_json(url):
    headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return request_json(url, headers=headers)


def as_datetime(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    text = str(value).strip()
    try:
        dt = datetime.fromtimestamp(float(text), timezone.utc) if text.replace(".", "", 1).isdigit() else datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def event_times(event):
    start = as_datetime(event.get("start_timestamp", event.get("start")))
    end = as_datetime(event.get("end_timestamp", event.get("end")))
    return (start, end) if start and end and end > start else (None, None)


def streamer_id(event):
    for key in ("streamer_id", "dj_id", "streamer"):
        value = event.get(key)
        if isinstance(value, dict):
            value = value.get("id")
        if value is not None and str(value).isdigit():
            return str(value)
    return None


def normalize_streamer_name(value):
    value = str(value or "").lower().strip()
    value = re.sub(r"^\\s*dj\\s+", "", value)
    return re.sub(r"[^a-z0-9]", "", value)


def get_streamer_profiles(station_id):
    try:
        data = azura_json(f"{AZURACAST_URL}/api/station/{station_id}/streamers")
        if isinstance(data, dict):
            for key in ("streamers", "data", "items", "results"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        profiles = {}
        if isinstance(data, list):
            for profile in data:
                if not isinstance(profile, dict) or not profile.get("id"):
                    continue
                name = profile.get("name") or profile.get("display_name") or profile.get("streamer_name")
                normalized = normalize_streamer_name(name)
                if normalized:
                    profiles[normalized] = str(profile["id"])
        print(f"  Loaded {len(profiles)} DJ artwork profile(s) for station {station_id}")
        return profiles
    except Exception as exc:
        print(f"  Could not load DJ profiles for station {station_id}: {exc}")
        return {}


def artwork_data(station_id, event, profiles):
    sid = streamer_id(event)
    if not sid:
        dj_name = event.get("streamer_name") or event.get("dj_name")
        sid = profiles.get(normalize_streamer_name(dj_name))
    if not sid:
        print(f"  No matching DJ artwork profile for {event.get('streamer_name') or event.get('dj_name') or 'this event'}.")
        return None
    url = f"{AZURACAST_URL}/api/station/{urllib.parse.quote(str(station_id))}/streamer/{urllib.parse.quote(sid)}/art"
    headers = {"User-Agent": "913AycltFM-AzuraCast-Discord-Events/1.0"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            image_bytes = response.read()
            mime = response.headers.get_content_type()
        if not image_bytes or not mime.startswith("image/"):
            print(f"  Artwork unavailable for streamer {sid}; event will use no cover image.")
            return None
        return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    except Exception as exc:
        print(f"  Artwork fetch failed for streamer {sid}: {exc}")
        return None


def get_schedule(station_id, station_name, start, end):
    query = urllib.parse.urlencode({"start": start.isoformat(), "end": end.isoformat(), "_": int(time.time())})
    data = azura_json(f"{AZURACAST_URL}/api/station/{station_id}/schedule?{query}")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("schedule", "data", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    raise RuntimeError(f"Unexpected schedule response for {station_name}.")


def event_key(station_id, event, start, end):
    schedule_id = event.get("id") or event.get("schedule_id") or event.get("station_schedule_id") or "event"
    return f"azuracast:{station_id}:{schedule_id}:{int(start.timestamp())}:{int(end.timestamp())}"


def discord_request(method, path, payload=None):
    return request_json(
        f"{DISCORD_API}{path}",
        headers={"Authorization": f"Bot {TOKEN}", "User-Agent": "DiscordBot (https://github.com/913AycltFM/913-Ayclt-FM-Azuracast-Calender, 1.0)"},
        data=payload,
        method=method,
    )


def main():
    if not TOKEN or not GUILD_ID:
        raise RuntimeError("Set GitHub Actions secrets DISCORD_BOT_TOKEN and DISCORD_GUILD_ID before enabling Discord event publishing.")

    now = datetime.now(timezone.utc)
    end_window = now + timedelta(days=WINDOW_DAYS)
    station_data = azura_json(f"{AZURACAST_URL}/api/stations")
    if not isinstance(station_data, list):
        raise RuntimeError("AzuraCast /api/stations did not return a list.")
    stations = [s for s in station_data if isinstance(s, dict) and s.get("shortcode") in SHORTCODES]
    found = {s.get("shortcode") for s in stations}
    missing = [s for s in SHORTCODES if s not in found]
    if missing:
        raise RuntimeError("Missing configured station(s): " + ", ".join(missing))

    guild_path = f"/guilds/{GUILD_ID}/scheduled-events"
    existing = discord_request("GET", guild_path)
    existing = existing if isinstance(existing, list) else []
    by_key = {}
    by_identity = {}
    for item in existing:
        # Keep compatibility with events created by the older script.
        description = item.get("description") or ""
        for line in description.splitlines():
            if line.startswith("AzuraCast event key: "):
                by_key[line.split(": ", 1)[1].strip()] = item
        identity = (
            str(item.get("name") or ""),
            str(item.get("scheduled_start_time") or ""),
        )
        by_identity[identity] = item
    created = updated = skipped = 0

    for station in stations:
        station_id = str(station["id"])
        station_name = str(station.get("name") or station["shortcode"])
        listen_url = f"{AZURACAST_URL}/public/{station['shortcode']}"
        schedule = get_schedule(station_id, station_name, now, end_window)
        streamer_profiles = get_streamer_profiles(station_id)
        print(f"{station_name}: received {len(schedule)} schedule item(s)")
        for event in schedule:
            if not isinstance(event, dict):
                skipped += 1
                continue
            start, finish = event_times(event)
            if not start or not finish or start < now or finish <= now or start >= end_window:
                skipped += 1
                continue
            title = str(event.get("name") or event.get("title") or event.get("playlist_name") or event.get("streamer_name") or "Scheduled Programming").strip()
            dj = str(event.get("streamer_name") or event.get("dj_name") or "").strip()
            key = event_key(station_id, event, start, finish)
            payload = {
                "name": f"{station_name} — {title}"[:100],
                "privacy_level": 2,
                "entity_type": 3,
                "scheduled_start_time": start.isoformat().replace("+00:00", "Z"),
                "scheduled_end_time": finish.isoformat().replace("+00:00", "Z"),
                "entity_metadata": {"location": listen_url[:100]},
            }
            art = artwork_data(station_id, event, streamer_profiles)
            if art:
                payload["image"] = art
            old = by_key.get(key) or by_identity.get((
                payload["name"],
                payload["scheduled_start_time"],
            ))
            try:
                if old:
                    # Do not replace an existing cover image when AzuraCast has no new artwork.
                    if not art:
                        payload.pop("image", None)
                    discord_request("PATCH", f"{guild_path}/{old['id']}", payload)
                    updated += 1
                    print(f"  Updated: {payload['name']}")
                else:
                    discord_request("POST", guild_path, payload)
                    created += 1
                    print(f"  Created: {payload['name']}")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:1200]
                raise RuntimeError(f"Discord API returned HTTP {exc.code}: {detail}") from exc

    print(f"Discord events complete. Created={created}, updated={updated}, skipped={skipped}.")
    print("Existing events are not automatically deleted when removed from the AzuraCast schedule.")


if __name__ == "__main__":
    main()
