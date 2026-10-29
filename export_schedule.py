import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

AZURACAST_URL = "https://radio.913aycltfm.com"
OUTPUT_FILE = "azuracast_schedule.ics"
API_KEY = os.environ.get("AZURACAST_API_KEY", "")
ALLOWED_SHORTCODES = ["91.3_ayclt_fm", "91.3_ayclt_fm_hd2", "91.3_ayclt_fm_hd3"]
WINDOW_HOURS = 24 * 7
HTTP_TIMEOUT = 30
HTTP_RETRIES = 3

def clean_text(value, fallback="Scheduled Programming"):
    text = str(value or "").strip() or fallback
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    text = text.replace("\r", " ").replace("\n", " ")
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").strip()

def fold_line(line):
    if len(line.encode("utf-8")) <= 75:
        return line
    parts, remaining, first = [], line, True
    while remaining:
        limit = 75 if first else 74
        encoded = remaining.encode("utf-8")
        if len(encoded) <= limit:
            parts.append(remaining if first else " " + remaining)
            break
        cut = limit
        while cut > 0:
            try:
                piece = encoded[:cut].decode("utf-8")
                break
            except UnicodeDecodeError:
                cut -= 1
        if cut == 0:
            raise ValueError("Unable to safely fold UTF-8 iCalendar line.")
        parts.append(piece if first else " " + piece)
        remaining = remaining[len(piece):]
        first = False
    return "\r\n".join(parts)

def build_request(url):
    headers = {"User-Agent": "913AycltFM-AzuraCast-iCal/3.1", "Accept": "application/json",
               "Cache-Control": "no-cache", "Pragma": "no-cache"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return urllib.request.Request(url, headers=headers)

def get_json(url, label="AzuraCast API"):
    last_error = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            print(f"API request: {label} (attempt {attempt}/{HTTP_RETRIES})")
            with urllib.request.urlopen(build_request(url), timeout=HTTP_TIMEOUT) as response:
                raw = response.read().decode("utf-8")
                print(f"API success: {label} HTTP {response.status}, {len(raw)} bytes")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            last_error = exc
            print(f"API HTTP error: {label} HTTP {exc.code}")
            if exc.code not in (429, 500, 502, 503, 504) or attempt == HTTP_RETRIES:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = max(1, min(int(retry_after), 15)) if retry_after else 2 ** (attempt - 1)
            except (TypeError, ValueError):
                delay = 2 ** (attempt - 1)
            print(f"Retrying in {delay}s...")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"Temporary API error: {label}: {exc}")
            if attempt == HTTP_RETRIES:
                raise
            delay = 2 ** (attempt - 1)
            print(f"Retrying in {delay}s...")
            time.sleep(delay)
    raise RuntimeError(f"Unable to fetch JSON from {url}: {last_error}")

def get_filtered_stations():
    data = get_json(f"{AZURACAST_URL}/api/stations", "station list")
    if not isinstance(data, list):
        raise RuntimeError("AzuraCast /api/stations did not return a list.")
    stations = {}
    for station in data:
        if not isinstance(station, dict):
            continue
        shortcode = str(station.get("shortcode", "")).strip()
        if shortcode not in ALLOWED_SHORTCODES:
            continue
        station_id = str(station.get("id", "")).strip()
        if not station_id:
            raise RuntimeError(f"Approved station '{shortcode}' has no ID.")
        if station_id in stations:
            raise RuntimeError(f"Duplicate AzuraCast station ID '{station_id}' detected.")
        stations[station_id] = {"name": str(station.get("name") or shortcode).strip(),
                                "shortcode": shortcode,
                                "public_url": f"{AZURACAST_URL}/public/{shortcode}"}
    found = {s["shortcode"] for s in stations.values()}
    missing = [s for s in ALLOWED_SHORTCODES if s not in found]
    if missing:
        raise RuntimeError("Approved station(s) not found in AzuraCast: " + ", ".join(missing))
    print(f"Validated {len(stations)} approved stations.")
    return stations

def fetch_schedule(station_id, start_dt, end_dt, station_name):
    params = urllib.parse.urlencode({"start": start_dt.isoformat(), "end": end_dt.isoformat(),
                                     "_": int(datetime.now(timezone.utc).timestamp())})
    url = f"{AZURACAST_URL}/api/station/{station_id}/schedule?{params}"
    data = get_json(url, f"schedule for {station_name}")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("schedule", "data", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    raise RuntimeError(f"Unexpected schedule response for station {station_id}: {type(data).__name__}")

def timestamp_to_datetime(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def event_times(event):
    if not isinstance(event, dict):
        return None, None
    start = event.get("start_timestamp") if event.get("start_timestamp") is not None else event.get("start")
    end = event.get("end_timestamp") if event.get("end_timestamp") is not None else event.get("end")
    start_dt, end_dt = timestamp_to_datetime(start), timestamp_to_datetime(end)
    return (start_dt, end_dt) if start_dt and end_dt and end_dt > start_dt else (None, None)

def format_ical_date(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def stable_uid(station_id, event, start_dt, end_dt):
    event_id = str(event.get("id") or event.get("schedule_id") or event.get("station_schedule_id") or "event")
    return f"ayclt-{station_id}-{event_id}-{int(start_dt.timestamp())}-{int(end_dt.timestamp())}@913aycltfm"

def ical_text(value, fallback=""):
    """Escape user/API text for an iCalendar TEXT property."""
    text = str(value or fallback).strip()
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    return text.replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")
def first_value(*values):
    for value in values:
        if value is not None and str(value).strip():
            return value
    return ""

def normalize_name(value):
    value = str(value or "").casefold()
    value = re.sub(r"\\b(dj|the|show|with)\\b", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value)

def fetch_streamers(station_id, station_name):
    """Fetch station DJ profiles so scheduled blocks can be linked to their artwork."""
    url = f"{AZURACAST_URL}/api/station/{urllib.parse.quote(str(station_id), safe='')}/streamers"
    try:
        data = get_json(url, f"streamer profiles for {station_name}")
    except Exception as exc:
        print(f"  WARNING: could not fetch streamer profiles: {exc}")
        return []
    if isinstance(data, dict):
        for key in ("streamers", "data", "items", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        print("  WARNING: streamer endpoint did not return a list.")
        return []
    profiles = [item for item in data if isinstance(item, dict) and first_value(item.get("id"))]
    print(f"  Streamer profiles loaded: {len(profiles)}")
    return profiles

def get_streamer_details(event, profiles):
    """Resolve the DJ from schedule metadata or the station's streamer profile list."""
    nested = event.get("streamer") if isinstance(event.get("streamer"), dict) else {}
    dj_name = first_value(
        nested.get("display_name"), nested.get("displayName"), nested.get("name"),
        event.get("streamer_name"), event.get("dj_name"), event.get("dj"),
        event.get("streamer") if not isinstance(event.get("streamer"), dict) else "",
        event.get("host_name")
    )
    streamer_id = first_value(
        nested.get("id"), event.get("streamer_id"), event.get("station_streamer_id"),
        event.get("dj_id"), event.get("host_id")
    )
    event_name = first_value(event.get("name"), event.get("title"), event.get("playlist_name"), event.get("streamer_name"))
    event_norm = normalize_name(event_name)
    matched = None
    for profile in profiles:
        profile_name = first_value(profile.get("display_name"), profile.get("displayName"), profile.get("name"), profile.get("username"))
        profile_norm = normalize_name(profile_name)
        if streamer_id and str(profile.get("id")) == str(streamer_id):
            matched = profile
            break
        if profile_norm and event_norm and (profile_norm == event_norm or profile_norm in event_norm or event_norm in profile_norm):
            matched = profile
            break
    if matched:
        streamer_id = first_value(streamer_id, matched.get("id"))
        dj_name = first_value(dj_name, matched.get("display_name"), matched.get("displayName"), matched.get("name"), matched.get("username"))
    art_url = ""
    if streamer_id:
        art_url = f"{AZURACAST_URL}/api/station/{{station_id}}/streamer/{urllib.parse.quote(str(streamer_id), safe='')}/art"
    elif isinstance(nested.get("art"), str) and nested.get("art").startswith("http"):
        art_url = nested.get("art")
    return str(dj_name or "").strip(), art_url

def make_event(station_id, station, event, start_dt, end_dt, streamer_profiles):
    name = first_value(event.get("name"), event.get("title"), event.get("playlist_name"), event.get("streamer_name"), "Scheduled Programming")
    dj_name, art_url_template = get_streamer_details(event, streamer_profiles)
    art_url = art_url_template.format(station_id=urllib.parse.quote(str(station_id), safe="")) if art_url_template else ""
    summary = clean_text(f"[{station['name']}] {name}")
    description_parts = [f"Station: {station['name']}", f"Show: {name}"]
    if dj_name:
        description_parts.append(f"DJ/Host: {dj_name}")
    description_parts.append(f"Listen live: {station['public_url']}")
    if art_url:
        description_parts.append(f"DJ artwork: {art_url}")
    description = ical_text("\\n".join(description_parts))
    lines = ["BEGIN:VEVENT", f"UID:{stable_uid(station_id, event, start_dt, end_dt)}",
             f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
             f"DTSTART:{format_ical_date(start_dt)}", f"DTEND:{format_ical_date(end_dt)}",
             f"SUMMARY:{summary}", f"DESCRIPTION:{description}",
             f"URL:{station['public_url']}", f"LOCATION:{station['public_url']}"]
    # ATTACH is a standard iCalendar image attachment; many calendar apps show it
    # as an event attachment even if they do not render DESCRIPTION image links.
    if art_url:
        lines.append(f"ATTACH;FMTTYPE=image/jpeg:{art_url}")
    lines.append("END:VEVENT")
    return [fold_line(line) for line in lines]

def main():
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=WINDOW_HOURS)
    print(f"Update started: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Calendar window: {format_ical_date(now)} through {format_ical_date(window_end)}")
    stations = get_filtered_stations()
    events, seen = [], set()
    streamers_by_station = {}
    totals = {"invalid": 0, "expired": 0, "out_of_window": 0, "duplicate": 0}

    for station_id, station in stations.items():
        print(f"\nStation: {station['name']} ({station['shortcode']})")
        schedule_data = fetch_schedule(station_id, now, window_end, station["name"])
        streamer_profiles = fetch_streamers(station_id, station["name"])
        streamers_by_station[station_id] = streamer_profiles
        print(f"  Records returned: {len(schedule_data)}")
        counts = {"added": 0, "invalid": 0, "expired": 0, "out_of_window": 0, "duplicate": 0}
        for event in schedule_data:
            start_dt, end_dt = event_times(event)
            if not start_dt or not end_dt:
                counts["invalid"] += 1
                continue
            if end_dt <= now:
                counts["expired"] += 1
                continue
            if start_dt >= window_end:
                counts["out_of_window"] += 1
                continue
            key = (station_id, str(event.get("id") or event.get("schedule_id") or event.get("station_schedule_id") or ""),
                   int(start_dt.timestamp()), int(end_dt.timestamp()))
            if key in seen:
                counts["duplicate"] += 1
                continue
            seen.add(key)
            events.append((start_dt, end_dt, station_id, station, event))
            counts["added"] += 1
        for key in totals:
            totals[key] += counts[key]
        print(f"  Events added: {counts['added']}")
        print(f"  Skipped: invalid={counts['invalid']}, expired={counts['expired']}, out_of_window={counts['out_of_window']}, duplicate={counts['duplicate']}")

    events.sort(key=lambda item: (item[0], item[2], item[1]))
    uids = set()
    for start_dt, end_dt, station_id, station, event in events:
        uid = stable_uid(station_id, event, start_dt, end_dt)
        if uid in uids:
            raise RuntimeError(f"Duplicate iCalendar UID generated: {uid}")
        uids.add(uid)

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//91.3 Ayclt FM//AzuraCast Rolling Calendar//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:91.3 Ayclt FM"]
    for start_dt, end_dt, station_id, station, event in events:
        lines.extend(make_event(station_id, station, event, start_dt, end_dt, streamers_by_station.get(station_id, [])))
    lines.append("END:VCALENDAR")

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as handle:
        handle.write("\r\n".join(lines) + "\r\n")
    size = os.path.getsize(OUTPUT_FILE)
    print("\n===== UPDATE SUMMARY =====")
    print(f"Stations processed: {len(stations)}")
    print(f"Events exported: {len(events)}")
    print(f"Skipped invalid: {totals['invalid']}")
    print(f"Skipped expired: {totals['expired']}")
    print(f"Skipped out-of-window: {totals['out_of_window']}")
    print(f"Skipped duplicates: {totals['duplicate']}")
    print(f"Calendar size: {size} bytes")
    print("Update completed successfully.")

if __name__ == "__main__":
    main()
